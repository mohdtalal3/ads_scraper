import requests
import csv
import time
from pathlib import Path
from PIL import Image
from datetime import datetime


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------
def auto_crop_whitespace(image_path, threshold=250, margin=10):
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
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                with open(path, "wb") as f:
                    f.write(resp.content)
                if auto_crop:
                    auto_crop_whitespace(path)
                return True
            else:
                if attempt < max_retries - 1:
                    time.sleep(1)
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(1)
    return False


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
BASE_URL = "https://search.costco.com/api/apps/www_costco_com/query/www_costco_com_navigation"

ROWS = 24

# Location/warehouse identifiers — update these for a different warehouse
USER_LOCATION = "NJ"
LOC = (
    "729-bd,1-wh,1260-3pl,1321-wm,1477-3pl,283-wm,561-wm,725-wm,731-wm,"
    "758-wm,759-wm,847_0-cor,847_0-cwt,847_0-edi,847_0-ehs,847_0-membership,"
    "847_0-mpt,847_0-spc,847_0-wm,847_1-cwt,847_1-edi,847_d-fis,"
    "847_ge_bal-edi,847_lg_n1a-edi,847_lux_us81-edi,847_NA-cor,"
    "847_NA-pharmacy,847_NA-wm,847_ss_u360-edi,847_wp_r428-edi,"
    "951-wm,952-wm,9847-wcs"
)
WHLOC = "1-wh"

HEADERS = {
    "accept": "application/json",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://www.costco.com",
    "referer": "https://www.costco.com/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "x-api-key": "273db6be-f015-4de7-b0d6-dd4746ccd5c3",
}


# --------------------------------------------------
# API FETCHING
# --------------------------------------------------
def fetch_page(start=0, rows=ROWS):
    """Fetch one page of Costco grocery sale items."""
    params = {
        "expoption": "lws",
        "q": "OFF",
        "locale": "en-US",
        "start": start,
        "expand": "false",
        "userLocation": USER_LOCATION,
        #"loc": LOC,
        "whloc": WHLOC,
        "rows": rows,
        "url": "/grocery-household.html",
        "fq": [
            '{!tag=item_program_eligibility}item_program_eligibility:("InWarehouse")',
            'item_location_availability:("in stock")',
        ],
        "sort": "item_page_views desc",
        "chdcategory": "true",
        "chdheader": "true",
    }

    response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_all_products():
    """Fetch all sale products from Costco grocery by paginating."""
    all_docs = []
    start = 0
    num_found = None

    while True:
        print(f"   📄 Fetching start={start}...", end="", flush=True)
        data = fetch_page(start=start, rows=ROWS)

        response_block = data.get("response", {})
        docs = response_block.get("docs", [])

        if num_found is None:
            num_found = response_block.get("numFound", 0)
            print(f" (total: {num_found})", end="")

        all_docs.extend(docs)
        print(f" +{len(docs)} items (collected: {len(all_docs)})")

        start += ROWS
        if start >= num_found:
            break

        time.sleep(0.5)

    return all_docs


# --------------------------------------------------
# DATA EXTRACTION
# --------------------------------------------------
def get_image_url(doc):
    """Pick the best image URL from a doc entry."""
    for key in ("item_product_primary_image", "item_collateral_primaryimage", "image"):
        url = doc.get(key)
        if url:
            return url
    return ""


# --------------------------------------------------
# CSV EXPORT
# --------------------------------------------------
def save_to_csv(docs, flyer_name, csv_file, output_dir):
    if not docs:
        print("⚠️ No products found")
        return

    today_str = datetime.now().strftime("%m-%d-%y")
    csv_rows = []

    print(f"\n📦 Processing {len(docs)} products...")

    for idx, doc in enumerate(docs, 1):
        item_number = doc.get("item_number", "")
        name = doc.get("item_product_name") or doc.get("name", "")
        price = doc.get("item_location_pricing_salePrice")
        base_price = doc.get("item_location_pricing_listPrice")
        discount = doc.get("item_product_marketing_statement", "")
        brand_list = doc.get("Brand_attr", [])
        brand = brand_list[0] if brand_list else ""
        upc_list = doc.get("item_manufacturing_skus", [])
        upc = upc_list[0] if upc_list else ""
        short_desc = doc.get("item_short_description", "")
        in_stock = doc.get("inWarehouseStatus", "")
        rating = doc.get("item_ratings", "")
        category_paths = doc.get("categoryPath_ss", [])
        raw_cat = category_paths[1] if len(category_paths) > 1 else (category_paths[0] if category_paths else "")
        category = raw_cat.strip("/").replace(".html", "")

        # Skip items without price info
        if price is None or base_price is None:
            print(f"   ⏭️  Skipping (no price): {name[:40]}")
            continue

        image_url = get_image_url(doc)
        image_filename = ""
        if image_url:
            image_filename = f"costco_{item_number}.png"
            image_path = output_dir / image_filename
            print(f"   📥 [{idx}/{len(docs)}] Downloading: {name[:45]}", end="")
            # success = download_image(image_url, image_path)
            # print(" ✓" if success else " ✗")

        csv_rows.append({
            "flyer_id": "grocery-household",
            "flyer_name": flyer_name,
            "id": item_number,
            "name": name,
            "price": price,
            "valid_from": today_str,
            "valid_to": today_str,
            "image": image_filename,
            "base_price": base_price,
            "discount": discount,
            "brand": brand,
            "upc": upc,
            "category": category,
            "description": short_desc,
            "in_stock": in_stock,
            "rating": rating,
            "image_url": image_url,
        })

    if csv_rows:
        fieldnames = [
            "flyer_id", "flyer_name", "id", "name", "price",
            "valid_from", "valid_to", "image",
            "base_price", "discount", "brand", "upc",
            "category", "description", "in_stock", "rating", "image_url",
        ]
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)

        print(f"\n✅ Saved {len(csv_rows)} products to CSV")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
if __name__ == "__main__":
    print("=" * 80)
    print("COSTCO GROCERY SALE SCRAPER")
    print("=" * 80)
    print()

    FLYER_NAME = "Grocery"

    try:
        print("🔍 Fetching sale products from Costco API...")
        docs = fetch_all_products()

        if not docs:
            print("❌ No products found")
            exit(1)

        today_str = datetime.now().strftime("%m-%d-%y")
        folder_name = f"Costco_{FLYER_NAME}_{today_str}"
        output_dir = Path("costco") / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        csv_file = output_dir / f"{folder_name}.csv"

        print(f"\n✅ Found {len(docs)} products")
        print(f"📁 Folder: {folder_name}")
        print()

        save_to_csv(docs, FLYER_NAME, csv_file, output_dir)

        print(f"\n📁 Output folder: {output_dir}")
        print("Done!")

    except requests.HTTPError as e:
        print(f"❌ HTTP error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
