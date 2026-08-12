from curl_cffi import requests
import re
import json
import csv
import time
import os
import html
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
CAT_ID = "1150109"
FLYER_NAME = "Clearance"
PAGE_SIZE = 45
MAX_PAGES = 1

API_URL = (
    "https://www.samsclub.com/orchestra/snb/graphql/Browse/"
    "e35d593b9ffd2306360ace15d970cbf39cfc38c46cc03dfde5c6537de3d826cb/browse"
)

PDP_API_URL = (
    "https://www.samsclub.com/orchestra/pdp/graphql/ItemById/"
    "dd3d6e9c0df88450b413b724a0996b5a7b48210918c0f5f59d130b22912a95ce/ip/{item_id}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "pragma": "no-cache",
    "cache-control": "no-cache",
    "x-o-mart": "B2C",
    "x-o-gql-query": "query Browse",
    "sec-ch-ua-platform": '"macOS"',
    "x-o-segment": "oaoh",
    "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
    "x-enable-server-timing": "1",
    "sec-ch-ua-mobile": "?0",
    "x-latency-trace": "1",
    "wm_mp": "true",
    "content-type": "application/json",
    "x-apollo-operation-name": "Browse",
    "tenant-id": "gj9b60",
    "downlink": "10",
    "x-o-platform": "rweb",
    "accept-language": "en-US",
    "x-o-ccm": "server",
    "x-o-bu": "SAMS-US",
    "dpr": "1",
    "wm_page_url": f"https://www.samsclub.com/browse/clearance/{CAT_ID}?sort=top_selling",
    "x-o-correlation-id": "x5as-8vXCWsFQDal0nJAl3YO4LxQ_aqNxGLF",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": f"https://www.samsclub.com/browse/clearance/{CAT_ID}?sort=top_selling",
    "priority": "u=1, i",
}




def build_variables(page):
    """Build the variables JSON for the GraphQL Browse request."""
    additional_query_params = {
        "hidden_facet": None,
        "translation": None,
        "isMoreOptionsTileEnabled": True,
        "rootDimension": "",
        "altQuery": "",
        "selectedFilter": "",
        "neuralSearchSeeAll": False,
        "enableGenericItemTileOptions": False,
        "isLMPBrowsePage": False,
    }

    search_args = {
        "query": "",
        "cat_id": CAT_ID,
        "prg": "desktop",
        "facet": "",
    }

    base_search = {
        "id": "",
        "dealsId": "",
        "query": "",
        "nudgeContext": "",
        "page": page,
        "prg": "desktop",
        "catId": CAT_ID,
        "facet": "",
        "sort": "top_selling",
        "rawFacet": "",
        "seoPath": "",
        "ps": PAGE_SIZE,
        "limit": PAGE_SIZE,
        "ptss": "",
        "trsp": "",
        "beShelfId": "",
        "recall_set": "",
        "module_search": "",
        "min_price": "",
        "max_price": "",
        "storeSlotBooked": "",
        "additionalQueryParams": additional_query_params,
        "searchArgs": search_args,
        "enableCopyBlock": True,
        "enableVariantCount": False,
        "enableSlaBadgeV2": False,
        "enableUnifiedProductFragment": False,
        "enableESSCarousel": False,
    }

    fitment_search_params = dict(base_search)
    fitment_search_params["cat_id"] = CAT_ID
    fitment_search_params["_be_shelf_id"] = ""

    search_params = dict(base_search)
    search_params["cat_id"] = CAT_ID
    search_params["_be_shelf_id"] = ""

    variables = {
        "id": "",
        "dealsId": "",
        "query": "",
        "nudgeContext": "",
        "page": page,
        "prg": "desktop",
        "catId": CAT_ID,
        "facet": "",
        "sort": "top_selling",
        "rawFacet": "",
        "seoPath": "",
        "ps": PAGE_SIZE,
        "limit": PAGE_SIZE,
        "ptss": "",
        "trsp": "",
        "beShelfId": "",
        "recall_set": "",
        "module_search": "",
        "min_price": "",
        "max_price": "",
        "storeSlotBooked": "",
        "additionalQueryParams": additional_query_params,
        "searchArgs": search_args,
        "enableCopyBlock": True,
        "enableVariantCount": False,
        "enableSlaBadgeV2": False,
        "enableUnifiedProductFragment": False,
        "enableESSCarousel": False,
        "fitmentFieldParams": {
            "powerSportEnabled": True,
            "dynamicFitmentEnabled": True,
            "extendedAttributesEnabled": True,
            "extendedAttributesV2Enabled": False,
            "fuelTypeEnabled": False,
        },
        "fitmentSearchParams": fitment_search_params,
        "searchParams": search_params,
        "enableFashionTopNav": False,
        "fetchMarquee": True,
        "fetchSkyline": True,
        "fetchSbaTop": True,
        "fetchDataV1": False,
        "fetchDataV2": False,
        "fungibilityEnabled": False,
        "fetchGallery": False,
        "fetchDac": True,
        "enablePortableFacets": True,
        "tenant": "SAMS_GLASS",
        "pageType": "BrowsePage",
        "enableFacetCount": True,
        "enableMultiSave": False,
        "enableInStoreShelfMessage": False,
        "fSeo": True,
        "enableSellerType": False,
        "enableItemRank": False,
        "enableOptimisticWeightUpdate": False,
        "enableFulfillmentTagsEnhacements": False,
        "enableRxDrugScheduleModal": False,
        "enablePromoData": False,
        "enableAdsPromoData": False,
        "enableSeoLangUrl": False,
        "enableImageBannerCarousel": True,
        "enableHero4": False,
        "enableSeoBrowseMetaDataShortDesc": False,
        "enableCanAddToList": True,
        "enablePromotionMessages": True,
        "enableDebugAnalyticsTags": True,
        "enableSignInToSeePrice": True,
        "enableSimpleEmailSignUp": False,
        "enableModuleReposition": True,
        "enableUnifiedSchema": False,
        "version": "v1",
        "postProcessingVersion": 1,
        "enableAdsUnifiedProductTile": False,
    }

    return variables


# --------------------------------------------------
# API FETCHING
# --------------------------------------------------
def fetch_page(page, max_retries=3):
    """Fetch one page of Sam's Club clearance items."""
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


def fetch_all_products():
    """Fetch all clearance products by paginating."""
    all_items = []
    total_count = None

    for page in range(1, MAX_PAGES + 1):
        print(f"   📄 Fetching page {page}...", end="", flush=True)
        data = fetch_page(page)

        if not data:
            print(" (no data)")
            break

        search = data.get("data", {}).get("search", {})
        search_result = search.get("searchResult", {})

        if total_count is None:
            total_count = search_result.get("aggregatedCount", 0)
            print(f" (total: {total_count})", end="")

        item_stacks = search_result.get("itemStacks", [])
        if not item_stacks:
            print(" (no item stacks)")
            break

        items = item_stacks[0].get("itemsV2", [])
        if not items:
            print(" (no items)")
            break

        all_items.extend(items)
        print(f" +{len(items)} items (collected: {len(all_items)})")

        if len(all_items) >= total_count:
            break

        time.sleep(1)

    return all_items


def build_pdp_variables(item_id, page_url_path):
    """Build the variables JSON for the PDP ItemById GraphQL request."""
    return {
        "isMobile": False,
        "channel": "WWW",
        "version": "v1",
        "postProcessingVersion": 1,
        "pageType": "ItemPageGlobalDesktop",
        "tenant": "SAMS_GLASS",
        "tempo": {
            "targeting": "%7B%22userState%22%3A%22loggedIn%22%7D",
            "params": [
                {"key": "expoVars", "value": "expoVariationValue"},
                {"key": "expoVars", "value": "expoVariationValue2"},
            ],
        },
        "p13nCls": {
            "pageId": item_id,
            "skipPtcFetch": True,
            "p13NCallType": "ATF",
            "userClientInfo": {"isZipLocated": True, "callType": "CLIENT"},
            "userReqInfo": {
                "refererContext": {
                    "source": "itempage",
                    "query": "",
                    "sourceId": None,
                    "wmlspartner": None,
                    "variantSwitch": True,
                    "itemSwitchContext": {
                        "refererItem": item_id,
                        "sizeReferer": None,
                        "sizeReferers": None,
                    },
                },
                "enableSlaBadgeV2": False,
                "isMoreOptionsTileEnabled": True,
            },
        },
        "iId": item_id,
        "layout": ["itemDesktop2"],
        "p13N": {
            "userClientInfo": {
                "isZipLocated": True,
                "deviceType": "desktop",
                "callType": "CLIENT",
            },
            "userReqInfo": {
                "refererContext": {
                    "source": "itempage",
                    "sourceId": None,
                    "wmlspartner": None,
                },
                "pageUrl": page_url_path,
            },
        },
        "cSId": "",
        "sSId": None,
        "fBBAd": True,
        "eLLBBAds": False,
        "adV1Enabled": False,
        "fMq": True,
        "fGalAd": False,
        "fSCar": True,
        "fDac": False,
        "fBB": True,
        "enableAdsTemplateBadging": False,
        "enableAdsUnifiedProductTile": False,
        "fSL": True,
        "fIdml": True,
        "sIdml": False,
        "fMrkDscrp": False,
        "fRev": True,
        "fFit": True,
        "fSeo": True,
        "fP13": True,
        "fAff": True,
        "spVid": False,
        "spSBA": False,
        "eItIb": True,
        "fIlc": True,
        "bbe": False,
        "fSId": False,
        "eSb": True,
        "eCc": False,
        "eSsm": False,
        "enableRelatedSearch": False,
        "enableTopReasonsToBuy": False,
        "enableDetailedBeacon": False,
        "enableImageClassification": False,
        "enableMultiSave": False,
        "enableBnplMessage": False,
        "enableAOSModuleAttribute": False,
        "enableSizePredictor": False,
        "fRem": False,
        "enablePromoData": False,
        "enablePromotionMessages": True,
        "enableFlowerDelivery": True,
        "enableVariantMigration": False,
        "enableChannelLevelPricing": True,
        "enableSignInToSeePrice": True,
        "eTwc": True,
        "enableSecondaryOffers": False,
        "enableSWC": False,
        "enableReimagineSnapshot": False,
        "isSubscriptionFrequencyListEnabled": False,
        "enableWplusFulfillmentModalOnItemPage": False,
        "enableNutritionFacts": True,
        "enableProSellerHighlight": False,
        "enableProductAttributeEnrichment": False,
        "enableContactLensPurchase": False,
        "isSubscriptionEligible": False,
        "vTOP": {
            "personaId": 0,
            "personaManId": 0,
            "isByomActive": False,
            "isCYOMManActive": True,
            "isCYOMImageReductionEnabled": False,
            "isFollowMeActive": False,
        },
        "sV": False,
        "sVC": False,
        "vFId": None,
        "pAdd": None,
        "sFId": None,
        "sizePredictorInput": None,
        "enableTrueFitSizeChart": False,
        "conditionGroupCode": None,
        "conditionCodes": [],
        "selectedOfferId": None,
        "conditionType": "NEW",
        "enableRxDrugScheduleModal": False,
        "isGEPEnable": False,
        "enableUpstreamErrorCode": True,
        "filterCriteria": {"rating": [], "reviewAttributes": [], "aspectId": None},
        "reviewSummaryAspectsLimit": 6,
        "eA2S": False,
        "attributesCacheKey": "",
        "count": 2,
        "startAt": 1,
        "enableB2BItemConditionPricing": False,
        "enableCarouselStrategy": True,
        "enableOptimisticWeightUpdate": False,
        "enableStreamLinedBadging": False,
        "enableSparky": False,
        "enableItemPageFaq": False,
        "includeVideo": False,
    }


def build_pdp_headers(item_id, product_page_url):
    """Build headers for the PDP ItemById request."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "pragma": "no-cache",
        "cache-control": "no-cache",
        "x-o-gql-query": "query ItemById",
        "ip-session-traffic-type": "",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        "traffic-type": "Internal",
        "sec-ch-ua-mobile": "?0",
        "content-type": "application/json",
        "cyomv2enabled": "true",
        "x-apollo-operation-name": "ItemById",
        "downlink": "1.45",
        "accept-language": "en-US",
        "x-o-item-id": item_id,
        "dpr": "1",
        "is-variant-fetch": "true",
        "x-o-mart": "B2C",
        "sec-ch-ua-platform": '"macOS"',
        "x-o-segment": "oaoh",
        "x-enable-server-timing": "1",
        "x-latency-trace": "1",
        "wm_mp": "true",
        "tenant-id": "gj9b60",
        "x-o-platform": "rweb",
        "x-o-ccm": "server",
        "x-o-bu": "SAMS-US",
        "calltype": "CLIENT",
        "wm_page_url": product_page_url,
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "referer": product_page_url,
        "priority": "u=1, i",
    }


def fetch_pdp_variant_images(us_item_id, canonical_url="", max_retries=3):
    """Fetch PDP data for a product and extract variant image URLs."""
    if not us_item_id:
        return []

    url = PDP_API_URL.format(item_id=us_item_id)

    page_url_path = canonical_url if canonical_url else f"/ip/{us_item_id}"
    if page_url_path.startswith("http"):
        parsed = urlparse(page_url_path)
        page_url_path = parsed.path

    product_page_url = f"https://www.samsclub.com{page_url_path}"

    variables = build_pdp_variables(us_item_id, page_url_path)
    headers = build_pdp_headers(us_item_id, product_page_url)
    #headers["Cookie"] = COOKIE

    params = {"variables": json.dumps(variables, separators=(',', ':'))}

    for attempt in range(max_retries):
        try:
            resp = requests.get(
                url,
                headers=headers,
                params=params,
                impersonate="chrome",
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            product = data.get("data", {}).get("product", {})
            if not product:
                return []

            # Map variant product id -> variant entry (which holds imageInfo)
            product_map = {}
            for v in product.get("variants", []) or []:
                if isinstance(v, dict) and v.get("id"):
                    product_map[v["id"]] = v

            # Walk variantCriteria[].variantList[]: each entry has the real
            # variant name (e.g. "Black", "Blue") plus a "products" list of
            # ids that link into product_map for the full-size image
            variant_images = []
            seen_names = set()
            seen_urls = set()

            for vc in product.get("variantCriteria", []) or []:
                for vl in vc.get("variantList", []) or []:
                    if not isinstance(vl, dict):
                        continue

                    v_name = vl.get("name", "")
                    v_products = vl.get("products") or []
                    if not v_name or not v_products:
                        continue

                    normalized = v_name.strip().lower()
                    if normalized in seen_names:
                        continue

                    v_avail = vl.get("availabilityStatus", "")

                    # Find the first linked product that has an image
                    image_url = ""
                    for pid in v_products:
                        p = product_map.get(pid)
                        if not p:
                            continue
                        image_info = p.get("imageInfo") or {}
                        image_url = image_info.get("thumbnailUrl", "")
                        if not image_url:
                            all_images = image_info.get("allImages") or []
                            if all_images:
                                image_url = all_images[0].get("url", "")
                        if image_url:
                            break

                    # Fallback to the swatch image
                    if not image_url:
                        image_url = vl.get("swatchImageUrl", "")

                    if not image_url or image_url in seen_urls:
                        continue

                    seen_names.add(normalized)
                    seen_urls.add(image_url)
                    variant_images.append({
                        "name": v_name,
                        "image_url": image_url,
                        "availability": v_avail,
                    })

            return variant_images

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ PDP fetch retry for {us_item_id} ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                print(f"  ❌ PDP fetch failed for {us_item_id}: {e}")
                return []

    return []


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

    # Price info
    price_info = item.get("priceInfo", {})
    current_price = ""
    current_price_display = ""
    list_price = ""
    savings = ""
    unit_price = ""

    if price_info.get("currentPrice"):
        current_price = price_info["currentPrice"].get("priceString", "")
        current_price_display = price_info["currentPrice"].get("priceDisplay", "")
    if price_info.get("listPrice"):
        list_price = price_info["listPrice"].get("priceString", "")
    if price_info.get("savingsAmount"):
        savings = price_info["savingsAmount"].get("priceString", "")
    if price_info.get("unitPrice"):
        unit_price = price_info["unitPrice"].get("priceString", "")

    # Rating
    avg_rating = item.get("averageRating", "")
    num_reviews = item.get("numberOfReviews", "")

    # Availability
    availability = ""
    avail_status = item.get("availabilityStatusV2", {})
    if avail_status:
        availability = avail_status.get("display", "")

    # Fulfillment
    fulfillment_summary = item.get("fulfillmentSummary", [])
    fulfillment_types = []
    for fs in fulfillment_summary:
        fulfillment_types.append(fs.get("fulfillment", ""))
    fulfillment_str = ", ".join(fulfillment_types)

    # Badges
    badges = item.get("badges", {})
    badge_tags = []
    if badges and badges.get("tags"):
        for tag in badges["tags"]:
            badge_tags.append(tag.get("text", "").strip())
    badges_str = ", ".join(badge_tags)

    # Promotion messages
    promo_msgs = item.get("promotionMessages", [])
    promo_str = ""
    if promo_msgs:
        promo_str = "; ".join(
            pm.get("message", "") for pm in promo_msgs if pm.get("message")
        )

    # Category path (captured in main before AI categorization)
    category_path = item.get("category_path", "")

    # AI-assigned category (set by categorize_products before this runs),
    # falling back to the browse API's product type
    ai_category = item.get("ai_category") or product_type

    # Main image
    image_info = item.get("imageInfo", {})
    image_url = image_info.get("thumbnailUrl", "") if image_info else ""
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

    # Variants - fetch from PDP API for detailed variant image URLs
    variant_criteria = item.get("variantCriteria", [])
    has_variants = bool(variant_criteria)

    variants = []
    variant_image_filenames = []

    if has_variants and product_id:
        print(f"   🔍 [{idx}/{total}] Fetching PDP variants for: {name[:40]}")
        pdp_variants = fetch_pdp_variant_images(product_id, canonical_url)

        for v_idx, v in enumerate(pdp_variants):
            v_name = v.get("name", "")
            v_image_url = v.get("image_url", "")
            v_avail = v.get("availability", "")

            v_image_filename = ""
            if v_image_url:
                if v_image_url in image_cache:
                    v_image_filename = image_cache[v_image_url]
                else:
                    v_image_filename = (
                        f"{clean_id(flyer_id)}_{clean_id(product_id)}_"
                        f"variant{v_idx + 1}.jpg"
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
            variant_image_filenames.append(v_image_filename)

        time.sleep(0.5)

    # Fallback: use browse API variant data if PDP returned nothing
    if not variants and has_variants:
        for vc in variant_criteria:
            variant_list = vc.get("variantList", [])
            for v_idx, variant in enumerate(variant_list):
                v_name = variant.get("name", "")
                v_swatch_url = variant.get("swatchImageUrl", "")
                v_avail = variant.get("availabilityStatus", "")

                v_image_filename = ""
                if v_swatch_url:
                    if v_swatch_url in image_cache:
                        v_image_filename = image_cache[v_swatch_url]
                    else:
                        v_image_filename = (
                            f"{clean_id(flyer_id)}_{clean_id(product_id)}_"
                            f"variant{v_idx + 1}.jpg"
                        )
                        v_image_path = output_dir / v_image_filename
                        #download_image(v_swatch_url, v_image_path, auto_crop=False)
                        image_cache[v_swatch_url] = v_image_filename

                variants.append({
                    "name": v_name,
                    "image": v_image_filename,
                    "availability": v_avail,
                    "image_url": v_swatch_url,
                })
                variant_image_filenames.append(v_image_filename)

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
        "promotion": promo_str,
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
    print("SAM'S CLUB CLEARANCE SCRAPER")
    print("=" * 80)
    print()

    try:
        print("🔍 Fetching clearance products from Sam's Club API...")
        items = fetch_all_products()

        if not items:
            print("❌ No products found")
            return

        print(f"\n✅ Found {len(items)} products")

        # AI categorization (before any image downloading)
        # Preserve the browse API's categoryPathId first — categorize_products
        # overwrites the "category" key with the AI-assigned string
        for item in items:
            cat = item.get("category") or {}
            item["category_path"] = cat.get("categoryPathId", "") if isinstance(cat, dict) else ""
        categorize_products(items, "Sam's Club")
        for item in items:
            cat = item.pop("category", "")
            item["ai_category"] = cat if isinstance(cat, str) else ""

        # Create folder structure
        today_str = datetime.now().strftime("%m-%d-%y")
        folder_name = f"SamsClub_{FLYER_NAME}_{today_str}"
        output_dir = Path("samsclub") / folder_name
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
            row = extract_product(item, CAT_ID, output_dir, idx, len(items), image_cache)
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
