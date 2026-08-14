from curl_cffi import requests
import math
import re
import json
import csv
import time
import os
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image
from datetime import datetime
from urllib.parse import urlencode, urlparse

from categorize import categorize_products

# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------
def safe_filename(name):
    """Sanitize file/folder names."""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)


def clean_id(item_id):
    """Replace dashes and other special characters with underscores."""
    if not item_id:
        return "unknown"
    return re.sub(r'[^a-zA-Z0-9]', '_', str(item_id))


def auto_crop_whitespace(image_path, threshold=250, margin=10):
    """Crop white borders from an image using Pillow."""
    try:
        img = Image.open(image_path)
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        width, height = img.size
        pixels = img.load()

        min_x, min_y = width, height
        max_x, max_y = 0, 0

        stride = 10
        found_content = False

        for y in range(0, height, stride):
            for x in range(0, width, stride):
                pixel = pixels[x, y]
                r, g, b = pixel[0], pixel[1], pixel[2]
                if r < threshold or g < threshold or b < threshold:
                    found_content = True
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)

        if not found_content or min_x >= max_x or min_y >= max_y:
            img.close()
            return False

        min_x = max(0, min_x - margin)
        min_y = max(0, min_y - margin)
        max_x = min(width, max_x + margin)
        max_y = min(height, max_y + margin)

        original_area = width * height
        cropped_area = (max_x - min_x) * (max_y - min_y)
        crop_pct = ((original_area - cropped_area) / original_area) * 100

        if crop_pct > 1:
            cropped_img = img.crop((min_x, min_y, max_x, max_y))
            cropped_img.save(image_path, 'PNG', quality=95, optimize=True)
            img.close()
            cropped_img.close()
            return True

        img.close()
        return False

    except Exception as e:
        print(f"    ⚠️ Auto-crop failed: {e}")
        return False


def download_image(url, path, auto_crop=True, max_retries=3):
    """Download an image and optionally auto-crop whitespace."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=30, impersonate="chrome")
            if resp.status_code == 200:
                with open(path, "wb") as f:
                    f.write(resp.content)
                if auto_crop:
                    auto_crop_whitespace(path)
                return True
            else:
                if attempt < max_retries - 1:
                    print(f"  ⚠️ Download failed (status {resp.status_code}), retrying... ({attempt + 1}/{max_retries})")
                    time.sleep(1)
                else:
                    print(f"  ❌ Failed to download image after {max_retries} attempts (status {resp.status_code})")
                return False
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Error downloading image, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(1)
            else:
                print(f"  ❌ Error downloading image after {max_retries} attempts: {e}")
            return False
    return False


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
FLYER_ID = "clearance"
FLYER_NAME = "Clearance"
PAGE_SIZE = 40
MAX_PAGES = 200

DEALS_ID = "deals/clearance"
SEO_PATH = "/shop/deals/clearance"
SORT = "best_seller"
MIN_DISCOUNT_PCT = 60
FACET = "special_offers:Clearance||special_offers:Reduced Price"
PAGE_URL = (
    f"https://www.walmart.com{SEO_PATH}"
    "?facet=special_offers%3AClearance%7C%7Cspecial_offers%3AReduced+Price"
    f"&sort={SORT}"
)

API_URL = (
    "https://www.walmart.com/orchestra/snb/graphql/Deals/"
    "d040963bed06ab4b9ae3816e0c5402e4d1df4067ade6bdb0490be9e2976d97ed/deals"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "x-o-mart": "B2C",
    "x-o-gql-query": "query Deals",
    "sec-ch-ua-platform": '"macOS"',
    "x-o-segment": "oaoh",
    "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
    "x-enable-server-timing": "1",
    "sec-ch-ua-mobile": "?0",
    "x-latency-trace": "1",
    "wm_mp": "true",
    "content-type": "application/json",
    "x-apollo-operation-name": "Deals",
    "tenant-id": "elh9ie",
    "x-o-platform": "rweb",
    "x-o-platform-version": "usweb-1.295.0-65a75e3a0476446cc49bfea95f9b9c4b5ac07929-8101858r",
    "accept-language": "en-US",
    "x-o-ccm": "server",
    "x-o-bu": "WALMART-US",
    "dpr": "1",
    "wm_page_url": PAGE_URL,
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": PAGE_URL,
    "priority": "u=1, i",
}


def discount_pct(item):
    """Compute discount % from priceInfo. For variant (priceRange) items,
    uses the lowest price so the best discount of the family counts."""
    price_info = item.get("priceInfo") or {}

    list_price = None
    for key in ("wasPrice", "listPrice"):
        entry = price_info.get(key) or {}
        if entry.get("price"):
            list_price = entry["price"]
            break

    if not list_price:
        return 0.0

    current = None
    price_range = price_info.get("priceRange") or {}
    if price_range.get("minPrice"):
        current = price_range["minPrice"]
    elif (price_info.get("currentPrice") or {}).get("price"):
        current = price_info["currentPrice"]["price"]

    if not current or current >= list_price:
        return 0.0

    return (list_price - current) / list_price * 100


def strip_image_params(url):
    """Remove odn sizing params so we get the full-resolution image."""
    if url and "?" in url:
        return url.split("?")[0]
    return url




def build_variables(page):
    """Build the variables JSON for the GraphQL Deals request."""
    additional_query_params = {
        "isMoreOptionsTileEnabled": True,
        "rootDimension": "",
        "altQuery": "",
        "selectedFilter": "",
    }

    enable_flags = {
        "enableClickTrackingURL": False,
        "enableSeoMetaData": True,
        "enableVolumePricing": False,
        "enableSlaBadgeV2": True,
        "fetchSkyline": True,
        "enableProductsField": True,
        "enableSwatch": True,
        "enableHeroCarousel": True,
        "showInteractiveImageCarousel": True,
        "enablePromotionMessages": False,
        "enableDebugAnalyticsTags": False,
        "enableMultiSave": False,
        "enableVariantCount": False,
        "enableCanAddToList": False,
        "enableIsFreeWarranty": False,
        "enableSignInToSeePrice": False,
        "enableHero4": False,
        "enableItemLimits": False,
        "fungibilityEnabled": False,
        "fetchDataV1": False,
        "fetchDataV2": False,
        "enableAdsPromoData": False,
        "fetchDac": False,
        "enableSimpleEmailSignUp": False,
        "enableUnifiedProductFragment": False,
        "enableAdsUnifiedProductTile": False,
    }

    base_search = {
        "id": "",
        "dealsId": DEALS_ID,
        "page": page,
        "mosaicPage": page,
        "prg": "desktop",
        "facet": FACET,
        "catId": "",
        "rawFacet": FACET,
        "seoPath": SEO_PATH,
        "ps": 0,
        "limit": PAGE_SIZE,
        "ptss": "",
        "trsp": "",
        "min_price": "",
        "max_price": "",
        "sort": SORT,
        "beShelfId": "",
        "recall_set": "",
        "module_search": "",
        "storeSlotBooked": "",
        "additionalQueryParams": additional_query_params,
        **enable_flags,
    }

    search_params = dict(base_search)
    search_params["cat_id"] = ""
    search_params["_be_shelf_id"] = ""
    search_params["pageType"] = "DealsPage"

    variables = dict(base_search)
    variables.update({
        "searchParams": search_params,
        "query": None,
        "pageType": "DealsPage",
        "fetchSbaTop": False,
        "enablePortableFacets": True,
        "enableEmailCaptureBanner": True,
        "enableFacetCount": True,
        "enableSellerType": False,
        "enableItemRank": False,
        "enableOptimisticWeightUpdate": False,
        "tenant": "WM_GLASS",
        "fSeo": True,
        "enableRxDrugScheduleModal": False,
        "enableSeoLangUrl": False,
        "enableModuleReposition": False,
        "enableUnifiedSchema": False,
        "version": "v1",
        "postProcessingVersion": 1,
        "enableSkinnyBannner": True,
        "enableSkinnyBannerUnified": False,
        "enableHeroCarouselUnified": False,
    })

    return variables


# --------------------------------------------------
# API FETCHING
# --------------------------------------------------
def fetch_page(page, max_retries=3):
    """Fetch one page of Walmart clearance deals."""
    variables = build_variables(page)
    params = {"variables": json.dumps(variables, separators=(',', ':'))}

    headers = dict(HEADERS)

    for attempt in range(max_retries):
        try:
            resp = requests.get(
                API_URL,
                headers=headers,
                params=params,
                impersonate="chrome",
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Failed to fetch page {page}, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                print(f"  ❌ Failed to fetch page {page} after {max_retries} attempts: {e}")
                return None

    return None


def extract_items(data):
    """Pull the itemsV2 list out of a Deals response."""
    search_result = data.get("data", {}).get("search", {}).get("searchResult", {})
    item_stacks = search_result.get("itemStacks") or []
    if not item_stacks:
        return []
    return item_stacks[0].get("itemsV2", []) or []


def fetch_all_products():
    """Fetch all clearance deals with threaded pagination."""
    print("   📄 Fetching page 1...", end="", flush=True)
    first = fetch_page(1)
    if not first:
        print(" (no data)")
        return []

    search_result = first.get("data", {}).get("search", {}).get("searchResult", {})
    total_count = search_result.get("aggregatedCount", 0)
    first_items = extract_items(first)
    print(f" (total: {total_count}) +{len(first_items)} items")

    if not first_items:
        return []

    num_pages = min(MAX_PAGES, max(1, math.ceil(total_count / PAGE_SIZE)))
    page_items = {1: first_items}

    if num_pages > 1:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_page, p): p for p in range(2, num_pages + 1)}
            for future in as_completed(futures):
                page = futures[future]
                data = future.result()
                if not data:
                    continue
                items = extract_items(data)
                if not items:
                    continue
                page_items[page] = items
                print(f"   📄 Page {page}: +{len(items)} items")

    all_items = []
    for page in sorted(page_items):
        all_items.extend(page_items[page])

    # Dedupe by usItemId (Walmart repeats items across pages)
    seen_ids = set()
    unique_items = []
    for item in all_items:
        uid = item.get("usItemId") or item.get("id")
        if uid and uid in seen_ids:
            continue
        seen_ids.add(uid)
        unique_items.append(item)

    print(f"   📦 Fetched {len(all_items)} items, {len(unique_items)} unique after dedupe")
    return unique_items


# --------------------------------------------------
# DATA EXTRACTION
# --------------------------------------------------
def extract_product(item, flyer_id, output_dir, idx, total, image_cache):
    """Extract product data and download images.

    image_cache maps image URL -> filename so identical images (e.g. the
    same product family returned under different usItemIds) are only
    downloaded once and all rows reference the same file.
    """
    product_id = item.get("usItemId", "")
    item_id = item.get("id", "")
    name = item.get("name", "")
    product_type = item.get("type", "")
    brand = item.get("brand", "")
    short_desc = item.get("shortDescription", "")
    if short_desc:
        short_desc = re.sub(r'<[^>]+>', '', short_desc)
        short_desc = html.unescape(short_desc)
        short_desc = short_desc.strip()
    canonical_url = item.get("canonicalUrl", "")

    # Price info: variant items show a priceRange (e.g. "$23.99 – $29.99")
    price_info = item.get("priceInfo", {})
    current_price = ""
    list_price = ""
    savings = ""

    price_range = price_info.get("priceRange") or {}
    if price_range.get("priceString"):
        current_price = price_range["priceString"]
    elif price_info.get("currentPrice"):
        current_price = price_info["currentPrice"].get("priceString", "")
    if price_info.get("wasPrice"):
        list_price = price_info["wasPrice"].get("priceString", "")
    elif price_info.get("listPrice"):
        list_price = price_info["listPrice"].get("priceString", "")
    if price_info.get("savingsAmount"):
        savings = price_info["savingsAmount"].get("priceString", "")

    # Category path (captured in main before AI categorization)
    category_path = item.get("category_path", "")

    # AI-assigned category (set by categorize_products before this runs),
    # falling back to the browse API's product type
    ai_category = item.get("ai_category") or product_type

    # Main image (strip odn sizing params for full resolution)
    image_info = item.get("imageInfo", {})
    image_url = strip_image_params(image_info.get("thumbnailUrl", "")) if image_info else ""
    image_filename = ""

    if image_url:
        if image_url in image_cache:
            image_filename = image_cache[image_url]
            print(f"   📥 [{idx}/{total}] Reusing cached image for: {name[:45]} ✓")
        else:
            image_filename = f"{clean_id(flyer_id)}_{clean_id(product_id)}.jpg"
            image_path = output_dir / image_filename
            print(f"   📥 [{idx}/{total}] Downloading: {name[:45]}", end="")
            #download_image(image_url, image_path, auto_crop=False)
            image_cache[image_url] = image_filename
            print(" ✓")

    # Variants - the deals response already includes per-variant images in
    # variantCriteria[].variantList[].images (fallback: swatchImageUrl)
    variant_criteria = item.get("variantCriteria", [])

    variants = []
    seen_names = set()
    seen_urls = set()

    for vc in variant_criteria or []:
        for vl in vc.get("variantList", []) or []:
            if not isinstance(vl, dict):
                continue

            v_name = vl.get("name") or vl.get("displayName") or ""
            if not v_name:
                continue

            normalized = v_name.strip().lower()
            if normalized in seen_names:
                continue

            v_images = vl.get("images") or []
            v_image_url = strip_image_params(v_images[0]) if v_images else ""
            if not v_image_url:
                v_image_url = strip_image_params(vl.get("swatchImageUrl", ""))

            if not v_image_url or v_image_url in seen_urls:
                continue

            seen_names.add(normalized)
            seen_urls.add(v_image_url)
            v_avail = vl.get("availabilityStatus", "")

            if v_image_url in image_cache:
                v_image_filename = image_cache[v_image_url]
            else:
                v_image_filename = (
                    f"{clean_id(flyer_id)}_{clean_id(product_id)}_"
                    f"variant{len(variants) + 1}.jpg"
                )
                v_image_path = output_dir / v_image_filename
                #download_image(v_image_url, v_image_path, auto_crop=False)
                image_cache[v_image_url] = v_image_filename

            variants.append({
                "name": v_name,
                "image": v_image_filename,
                "availability": v_avail,
                "image_url": v_image_url,
            })

    # Build variant columns (up to 15 variants)
    max_variants = 15
    variant_cols = {}
    for i in range(max_variants):
        if i < len(variants):
            variant_cols[f"variant_{i + 1}_name"] = variants[i]["name"]
            variant_cols[f"variant_{i + 1}_image"] = variants[i]["image"]
            variant_cols[f"variant_{i + 1}_image_url"] = variants[i]["image_url"]
        else:
            variant_cols[f"variant_{i + 1}_name"] = ""
            variant_cols[f"variant_{i + 1}_image"] = ""
            variant_cols[f"variant_{i + 1}_image_url"] = ""

    today_str = datetime.now().strftime("%m-%d-%y")

    row = {
        "flyer_id": flyer_id,
        "flyer_name": FLYER_NAME,
        "id": product_id,
        "name": name,
        "price": current_price,
        "valid_from": today_str,
        "valid_to": today_str,
        "image": image_filename,
        "description": short_desc,
        "category": ai_category,
        "brand": brand,
        "list_price": list_price,
        "savings": savings,
        "category_path": category_path,
        "canonical_url": canonical_url,
        "image_url": image_url,
        "item_id": item_id,
    }
    row.update(variant_cols)

    return row


# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main():
    print("=" * 80)
    print("WALMART CLEARANCE SCRAPER")
    print("=" * 80)
    print()

    try:
        print("🔍 Fetching clearance deals from Walmart API...")
        items = fetch_all_products()

        if not items:
            print("❌ No products found")
            return

        print(f"\n✅ Found {len(items)} products")

        # Keep only items flagged as Clearance, Reduced Price, or Best seller
        before = len(items)
        filtered = []
        for it in items:
            keys = {
                (f or {}).get("key")
                for f in ((it.get("badges") or {}).get("flags") or [])
            }
            if not keys & {"CLEARANCE", "REDUCED_PRICE", "BESTSELLER"}:
                continue
            if discount_pct(it) < MIN_DISCOUNT_PCT:
                continue
            filtered.append(it)
        items = filtered
        print(f"🏷️  Filtered to {len(items)} clearance/reduced-price/best-seller items (of {before}, discount >= {MIN_DISCOUNT_PCT}%)")

        if not items:
            print("❌ No clearance/reduced-price products found")
            return

        # AI categorization (before any image downloading)
        # Preserve the browse API's categoryPathId first — categorize_products
        # overwrites the "category" key with the AI-assigned string
        for item in items:
            cat = item.get("category") or {}
            item["category_path"] = cat.get("categoryPathId", "") if isinstance(cat, dict) else ""
        #categorize_products(items, "Walmart")
        for item in items:
            cat = item.pop("category", "")
            item["ai_category"] = cat if isinstance(cat, str) else ""

        # Create folder structure
        today_str = datetime.now().strftime("%m-%d-%y")
        folder_name = f"Walmart_{FLYER_NAME}_{today_str}"
        output_dir = Path("walmart") / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # Remove stale images from previous runs (browse API can return the
        # same product family under a different usItemId between runs)
        for old_file in output_dir.glob("*.jpg"):
            old_file.unlink()

        csv_file = output_dir / f"{folder_name}.csv"
        json_file = output_dir / f"{folder_name}.json"

        print(f"📁 Folder: {output_dir}")
        print()

        # Process all products
        image_cache = {}
        rows = []
        for idx, item in enumerate(items, 1):
            row = extract_product(item, FLYER_ID, output_dir, idx, len(items), image_cache)
            rows.append(row)

        # Write CSV
        if rows:
            fieldnames = list(rows[0].keys())
            with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            print(f"\n✅ Saved {len(rows)} products to CSV: {csv_file.name}")

        # Write JSON
        if rows:
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(rows, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved {len(rows)} products to JSON: {json_file.name}")

        print(f"\n📁 Output folder: {output_dir}")
        print("Done!")

    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
