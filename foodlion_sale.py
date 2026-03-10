import json
import csv
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from curl_cffi import requests
from PIL import Image

# -----------------------------
# Helper: Extract page key from URL
# -----------------------------
def extract_page_key(main_url: str) -> str:
    """
    Extracts page key from:
    https://foodlion.com/pages/b2g1 -> b2g1
    """
    path = urlparse(main_url).path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "pages":
        return parts[1]
    raise ValueError("Invalid Food Lion page URL format")


# -----------------------------
# Helper: Fetch product group IDs from page
# -----------------------------
def fetch_content_container_data(page_key: str, referer_url: str) -> dict:
    api_url = "https://foodlion.com/api/v4.0/cms/363428687/50001980"

    regions_payload = {
        "content_container_page": {
            "ff": {
                "Content Container URL Key": [page_key]
            },
            "limit": 1
        }
    }

    params = {
        "regions": json.dumps(regions_payload, separators=(",", ":")),
        "appTargeting": "Web",
        "screenSize": "Desktop"
    }

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9,fr;q=0.8,af;q=0.7,ar;q=0.6,be;q=0.5,de;q=0.4",
        "referer": referer_url,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }

    response = session.get(
        api_url,
        params=params,
        headers=headers,
        timeout=30
    )
    response.raise_for_status()
    data = response.json()

    result = {
        "page_key": page_key,
        "content_container_id": None,
        "content_container_key": None,
        "page_title": None,
        "start_date": None,
        "end_date": None,
        "peapod_product_group_ids": []
    }

    regions = data.get("response", {}).get("regionContents", [])
    for region in regions:
        for content in region.get("contents", []):
            container = content.get("map", {})

            result["content_container_id"] = container.get("id")
            result["content_container_key"] = container.get("key")
            result["page_title"] = container.get("Page Title")
            result["start_date"] = container.get("Start Date")
            result["end_date"] = container.get("End Date")

            scheduled = container.get("scheduledContentData", {}).get("map", {})
            parts = scheduled.get("parts", {}).get("myArrayList", [])

            for part in parts:
                part_map = part.get("map", {})
                if "Peapod Product Group Id" in part_map:
                    result["peapod_product_group_ids"].append(
                        part_map["Peapod Product Group Id"]
                    )

    return result


# -----------------------------
# Get page URL and cookies from user
# -----------------------------
print("=" * 70)
print("🍪 FOOD LION SCRAPER SETUP")
print("=" * 70)
print("\nEnter the Food Lion page URL to scrape:")
print("Example: https://foodlion.com/pages/b2g1\n")
main_page_url = input("Page URL: ").strip()

print("\n" + "=" * 70)
print("To get the required cookies:")
print("1. Open the page in Chrome")
print("2. Press F12 to open DevTools")
print("3. Go to 'Application' tab (top menu)")
print("4. In left sidebar: Storage → Cookies → https://foodlion.com")
print("5. Find and copy the cookie values:\n")

# Get DataDome cookie
print("📋 Cookie 1: 'datadome'")
print("   → Look for cookie named 'datadome' in the list")
print("   → Copy the entire 'Value' field (long string)\n")
datadome_value = input("Paste datadome cookie value: ").strip()


print("\n✅ Cookies received! Starting scraper...\n")
print("=" * 70)

# -----------------------------
# Base config
# -----------------------------
BASE_HEADERS = {
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "referer": main_page_url,
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}


# -------------------------------------------------------
# Helper: Auto-crop whitespace from images
# -------------------------------------------------------
def auto_crop_whitespace(image_path, threshold=250, margin=10):
    """
    Crop white borders from an image using Pillow.
    
    Args:
        image_path: Path to the image file (string or Path object)
        threshold: Pixel brightness threshold (0-255). Pixels darker than this are content.
        margin: Extra pixels to keep around detected content
    
    Returns:
        True if cropping was successful, False otherwise
    """
    try:
        img = Image.open(image_path)
        
        # Convert to RGB if necessary
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        
        width, height = img.size
        pixels = img.load()
        
        # Find content boundaries by scanning for non-white pixels
        min_x, min_y = width, height
        max_x, max_y = 0, 0
        
        # Sample every few pixels for speed
        stride = 10
        found_content = False
        
        for y in range(0, height, stride):
            for x in range(0, width, stride):
                pixel = pixels[x, y]
                # Handle both RGB and RGBA
                r, g, b = pixel[0], pixel[1], pixel[2]
                
                # If pixel is darker than threshold, it's content
                if r < threshold or g < threshold or b < threshold:
                    found_content = True
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
        
        if not found_content or min_x >= max_x or min_y >= max_y:
            img.close()
            return False
        
        # Add margin and clamp to image bounds
        min_x = max(0, min_x - margin)
        min_y = max(0, min_y - margin)
        max_x = min(width, max_x + margin)
        max_y = min(height, max_y + margin)
        
        # Calculate crop percentage
        original_area = width * height
        cropped_area = (max_x - min_x) * (max_y - min_y)
        crop_pct = ((original_area - cropped_area) / original_area) * 100
        
        # Only crop if we're removing more than 1% of the image
        if crop_pct > 1:
            # Crop the image
            cropped_img = img.crop((min_x, min_y, max_x, max_y))
            
            # Save the cropped image, replacing the original
            cropped_img.save(image_path, 'PNG', quality=95, optimize=True)
            
            img.close()
            cropped_img.close()
            
            return True
        
        img.close()
        return False
        
    except Exception as e:
        print(f"    ⚠️ Auto-crop failed for {os.path.basename(str(image_path))}: {e}")
        return False


# -------------------------------------------------------
# Helper: Download image with auto-crop and retry logic
# -------------------------------------------------------
def download_image(url, path, auto_crop=True, max_retries=3):
    """Download an image with retry logic and optionally auto-crop whitespace."""
    for attempt in range(max_retries):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 200:
                with open(path, "wb") as f:
                    f.write(resp.content)
                
                # Auto-crop if requested
                if auto_crop:
                    if auto_crop_whitespace(path):
                        return True  # Successfully cropped
                return False  # Downloaded but not cropped
            else:
                if attempt < max_retries - 1:
                    print(f"  ⚠️ Failed to download image (status {resp.status_code}), retrying... (attempt {attempt + 1}/{max_retries})")
                else:
                    print(f"  ⚠️ Failed to download image after {max_retries} attempts (status {resp.status_code}): {url}")
                    return False
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Error downloading image, retrying... (attempt {attempt + 1}/{max_retries}): {e}")
            else:
                print(f"  ❌ Error downloading image after {max_retries} attempts: {e}")
                return False
    
    return False


# -----------------------------
# Create persistent session
# -----------------------------
session = requests.Session(impersonate="chrome107")

# 🔑 Set cookies from user input
session.cookies.set(
    name="datadome",
    value=datadome_value,
    domain=".foodlion.com",
    path="/"
)


# -----------------------------
# STEP 1: Extract page info and product group IDs
# -----------------------------
print("\n[1] Extracting page information...\n")

page_key = extract_page_key(main_page_url)
print(f"  📄 Page key: {page_key}")

page_info = fetch_content_container_data(page_key, main_page_url)
print(f"  📋 Page title: {page_info['page_title']}")
print(f"  🔑 Content container ID: {page_info['content_container_id']}")
print(f"  📅 Start date: {page_info['start_date']}")
print(f"  📅 End date: {page_info['end_date']}")
print(f"  🏷️  Product group IDs: {page_info['peapod_product_group_ids']}")

if not page_info['peapod_product_group_ids']:
    print("\n❌ No product group IDs found on this page.")
    exit(1)

# Use first product group ID for filtering
product_group_id = page_info['peapod_product_group_ids'][0]
page_title = page_info['page_title'] or page_key.upper()

# Use page_key for folder name instead of page_title
folder_prefix = page_key

print(f"\n  ✅ Will scrape products from group: {product_group_id}")
print(f"  📁 Folder prefix: {folder_prefix}\n")


# session.cookies.set(
#     name="ppdtk",
#     value=ppdtk_value,
#     domain=".foodlion.com",
#     path="/"
# )
# -----------------------------
# STEP 2: Call products API with pagination
# -----------------------------
print("[2] Calling products API with pagination...\n")

API_URL = "https://foodlion.com/api/v6.0/products/2/50002071"

PARAMS = {
    "sort": "bestMatch asc",
    "filter": f"productGroups:{product_group_id}",
    "rows": 120,
    "catTreeId": "",
    "start": 0,
    "flags": "true",
    "facet": "nutrition",
    "substitute": "true",
    "facetExcludeFilter": "true",
    "includeOutOfStock": "false",
    "nutrition": "false"
}

all_products = []
start = 0
page_size = 40
total_products = None
page_number = 1

while True:
    PARAMS["start"] = start
    PARAMS["rows"] = page_size
    
    print(f"  📡 Fetching products {start} to {start + page_size} (Page {page_number})...")
    
    try:
        response = session.get(
            API_URL,
            params=PARAMS,
            headers=BASE_HEADERS,
            timeout=30
        )
        
        response.raise_for_status()
        
        # Check if response has content
        if not response.content or len(response.content) == 0:
            print(f"  ⚠️ Empty response received. Stopping pagination.")
            break
        
        data = response.json()
        
    except Exception as e:
        print(f"  ⚠️ Error fetching page {page_number}: {e}")
        print(f"  ℹ️ Stopping pagination. Already fetched {len(all_products)} products.")
        break
    
    # Get pagination info
    pagination = data.get("response", {}).get("pagination", {})
    total_products = pagination.get("total", 0)
   # total_products = 100
    # Get products from this page
    page_products = data.get("response", {}).get("products", [])
    
    # Add page number to each product
    for product in page_products:
        product["_page_number"] = page_number
    
    all_products.extend(page_products)
    
    print(f"  ✅ Got {len(page_products)} products (Total so far: {len(all_products)}/{total_products})")
    
    # Check if we have all products
    if len(all_products) >= total_products or len(page_products) == 0:
        break
    
    # Move to next page
    start += page_size
    page_number += 1

print(f"\n✅ Fetched all {len(all_products)} products\n")

# Save raw JSON for reference
with open("foodlion_b2g1_products.json", "w", encoding="utf-8") as f:
    json.dump({"products": all_products, "total": len(all_products)}, f, indent=2)

products = all_products
print(f"📊 Total products to process: {len(products)}\n")

if not products:
    print("❌ No products found.")
    exit(0)

# Extract date range from coupons
all_start_dates = []
all_end_dates = []

# First, add page-level dates if available
if page_info.get('start_date'):
    all_start_dates.append(page_info['start_date'])
if page_info.get('end_date'):
    all_end_dates.append(page_info['end_date'])

for product in products:
    # Check primary coupon
    primary_coupon = product.get("coupon", {})
    if primary_coupon:
        if primary_coupon.get("startDate"):
            all_start_dates.append(primary_coupon.get("startDate"))
        if primary_coupon.get("endDate"):
            all_end_dates.append(primary_coupon.get("endDate"))
    
    # Check all available coupons
    available_coupons = product.get("availableDisplayCoupons", [])
    for coupon in available_coupons:
        if coupon.get("startDate"):
            all_start_dates.append(coupon.get("startDate"))
        if coupon.get("endDate"):
            all_end_dates.append(coupon.get("endDate"))

# Determine folder name based on date range
base_folder = Path("FoodLion")
base_folder.mkdir(exist_ok=True)

# Use page-level dates if available, otherwise fall back to coupon dates
if page_info.get('start_date') and page_info.get('end_date'):
    earliest_start = page_info['start_date']
    latest_end = page_info['end_date']
    
    # Convert YYYY-MM-DD to YYYY_MM_DD
    start_formatted = earliest_start.replace("-", "_")
    end_formatted = latest_end.replace("-", "_")
    
    folder_name = f"FoodLion_{folder_prefix}_{start_formatted}_{end_formatted}"
    print(f"📅 Using page dates: {earliest_start} to {latest_end}")
elif all_start_dates and all_end_dates:
    # Fallback to coupon dates
    earliest_start = min(all_start_dates)
    latest_end = max(all_end_dates)
    
    # Convert YYYY-MM-DD to YYYY_MM_DD
    start_formatted = earliest_start.replace("-", "_")
    end_formatted = latest_end.replace("-", "_")
    
    folder_name = f"FoodLion_{folder_prefix}_{start_formatted}_{end_formatted}"
    print(f"📅 Using coupon date range: {earliest_start} to {latest_end}")
else:
    # Fallback to timestamp if no dates found
    timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    folder_name = f"FoodLion_{folder_prefix}_{timestamp}"
    print(f"⚠️ No dates found, using timestamp")

folder_path = base_folder / folder_name
folder_path.mkdir(exist_ok=True)

print(f"📁 Saving to: {folder_path}\n")

# Process products and download images
results = []
overall_rank = 1

for i, product in enumerate(products, 1):
    page_num = product.get("_page_number", 1)
    
    # Extract primary product fields
    prod_id = product.get("prodId", "")
    name = product.get("name", "")
    size = product.get("size", "")
    price = product.get("price", "")
    regular_price = product.get("regularPrice", "")
    unit_price = product.get("unitPrice", "")
    unit_measure = product.get("unitMeasure", "")
    
    # Brand and category
    brand = product.get("brand", "")
    brand_id = product.get("brandId", "")
    root_cat_name = product.get("rootCatName", "")
    root_cat_id = product.get("rootCatId", "")
    subcat_name = product.get("subcatName", "")
    subcat_id = product.get("subcatId", "")
    
    # UPC and IDs
    upc = product.get("upc", "")
    review_id = product.get("reviewId", "")
    
    # Ratings and reviews
    rating = product.get("rating", "")
    rating_reviews_suppressed = product.get("ratingReviewsSuppressed", "")
    
    # Store location
    aisle = product.get("aisle", "")
    pick_store_location_id = product.get("pickStoreLocationId", "")
    
    # Extract flags
    flags = product.get("flags", {})
    flag_sale = flags.get("sale", "")
    flag_bogo = flags.get("bogo", "")
    flag_new_arrival = flags.get("newArrival", "")
    flag_organic = flags.get("organic", "")
    flag_private_label = flags.get("privateLabel", "")
    flag_out_of_stock = flags.get("outOfStock", "")
    flag_special_code = flags.get("specialCode", "")
    
    # Extract all dietary/allergen flags
    flag_dairy = flags.get("dairy", "")
    flag_egg = flags.get("egg", "")
    flag_gluten = flags.get("gluten", "")
    flag_kosher = flags.get("kosher", "")
    flag_peanut = flags.get("peanut", "")
    flag_non_gmo = flags.get("nonGMO", "")
    flag_vegan = flags.get("vegan", "")
    flag_vegetarian = flags.get("vegetarian", "")
    flag_lactose_free = flags.get("lactoseFree", "")
    flag_antibiotic_free = flags.get("antibioticFree", "")
    flag_wheat_free = flags.get("wheatFree", "")
    flag_hormone_free = flags.get("hormoneFree", "")
    flag_nitrate_free = flags.get("nitrateFree", "")
    flag_nitrite_free = flags.get("nitriteFree", "")
    
    # Other product attributes
    has_substitute = product.get("hasSubstitute", "")
    ebt_eligible = product.get("ebtEligible", "")
    is_alcohol = product.get("isAlcohol", "")
    variable_weight = product.get("variableWeight", "")
    weight_increment = product.get("weightIncrement", "")
    guiding_stars = product.get("guidingStars", "")
    sustainability_rating = product.get("sustainabilityRating", "")
    
    # Price adjustment and availability
    has_price_adjustment = product.get("hasPriceAdjustment", "")
    has_coupon = product.get("hasCoupon", "")
    show_strikethrough = product.get("showStrikethrough", "")
    advertise_on_sale = product.get("advertiseOnSale", "")
    
    # Extract image URLs
    image_obj = product.get("image", {})
    image_small = image_obj.get("small", "")
    image_medium = image_obj.get("medium", "")
    image_large = image_obj.get("large", "")
    image_xlarge = image_obj.get("xlarge", "")
    
    # Download largest available image
    local_image_path = ""
    image_url = image_xlarge or image_large or image_medium or image_small
    
    if image_url:
        # Create filename: prodid_upc.png
        image_filename = f"{prod_id}_{upc}.png"
        img_path = folder_path / image_filename
        
        # # Download and crop image
        #cropped = download_image(image_url, img_path)
        local_image_path = image_filename
        
    #     if cropped:
    #         print(f"📥 [{i}/{len(products)}] Downloaded & cropped: {name}")
    #     else:
    #         print(f"📥 [{i}/{len(products)}] Downloaded: {name}")
    # else:
    #     print(f"⚠️ [{i}/{len(products)}] No image for: {name}")
    
    # Extract primary coupon (first one)
    primary_coupon = product.get("coupon", {})
    
    # Extract ALL available coupons dynamically
    available_coupons = product.get("availableDisplayCoupons", [])
    
    # Build base result with product info
    result = {
        # Most important columns first
        "rank": overall_rank,
        "page": page_num,
        "prod_id": prod_id,
        "name": name,
        "brand": brand,
        "size": size,
        "price": price,
        "regular_price": regular_price,
        "unit_price": unit_price,
        "unit_measure": unit_measure,
    }
    
    # Dynamically add all coupons
    for idx, coupon in enumerate(available_coupons, 1):
        coupon_prefix = f"coupon{idx}_"
        result[f"{coupon_prefix}id"] = coupon.get("id", "")
        result[f"{coupon_prefix}title"] = coupon.get("title", "")
        result[f"{coupon_prefix}name"] = coupon.get("name", "")
        result[f"{coupon_prefix}description"] = coupon.get("description", "")
        result[f"{coupon_prefix}start_date"] = coupon.get("startDate", "")
        result[f"{coupon_prefix}end_date"] = coupon.get("endDate", "")
        result[f"{coupon_prefix}max_discount"] = coupon.get("maxDiscount", "")
        result[f"{coupon_prefix}display_priority"] = coupon.get("displayPriority", "")
        result[f"{coupon_prefix}clipping_required"] = coupon.get("clippingRequired", "")
        result[f"{coupon_prefix}targeted"] = coupon.get("targeted", "")
        result[f"{coupon_prefix}source_system"] = coupon.get("sourceSystem", "")
        result[f"{coupon_prefix}source_system_id"] = coupon.get("sourceSystemId", "")
        result[f"{coupon_prefix}badge_id"] = coupon.get("badgeId", "")
        result[f"{coupon_prefix}loaded"] = coupon.get("loaded", "")
        result[f"{coupon_prefix}promotion_type"] = coupon.get("promotionType", "")
        result[f"{coupon_prefix}multi_qty"] = coupon.get("multiQty", "")
    
    # Add remaining product fields
    result.update({
        # Category information
        "root_cat_name": root_cat_name,
        "root_cat_id": root_cat_id,
        "subcat_name": subcat_name,
        "subcat_id": subcat_id,
        "brand_id": brand_id,
        
        # Store location
        "aisle": aisle,
        "pick_store_location_id": pick_store_location_id,
        
        # Product identifiers
        "upc": upc,
        "review_id": review_id,
        
        # Ratings
        "rating": rating,
        "rating_reviews_suppressed": rating_reviews_suppressed,
        "guiding_stars": guiding_stars,
        "sustainability_rating": sustainability_rating,
        
        # Sale flags
        "flag_sale": flag_sale,
        "flag_bogo": flag_bogo,
        "flag_new_arrival": flag_new_arrival,
        "flag_special_code": flag_special_code,
        "has_price_adjustment": has_price_adjustment,
        "has_coupon": has_coupon,
        "show_strikethrough": show_strikethrough,
        "advertise_on_sale": advertise_on_sale,
        
        # Product attributes
        "flag_organic": flag_organic,
        "flag_private_label": flag_private_label,
        "flag_out_of_stock": flag_out_of_stock,
        "has_substitute": has_substitute,
        "ebt_eligible": ebt_eligible,
        "is_alcohol": is_alcohol,
        "variable_weight": variable_weight,
        "weight_increment": weight_increment,
        
        # Dietary/allergen flags
        "flag_dairy": flag_dairy,
        "flag_egg": flag_egg,
        "flag_gluten": flag_gluten,
        "flag_kosher": flag_kosher,
        "flag_peanut": flag_peanut,
        "flag_non_gmo": flag_non_gmo,
        "flag_vegan": flag_vegan,
        "flag_vegetarian": flag_vegetarian,
        "flag_lactose_free": flag_lactose_free,
        "flag_antibiotic_free": flag_antibiotic_free,
        "flag_wheat_free": flag_wheat_free,
        "flag_hormone_free": flag_hormone_free,
        "flag_nitrate_free": flag_nitrate_free,
        "flag_nitrite_free": flag_nitrite_free,
        
        # Image URLs
        "image": local_image_path,
        "image_small": image_small,
        "image_medium": image_medium,
        "image_large": image_large,
        "image_xlarge": image_xlarge,
    })
    
    results.append(result)
    overall_rank += 1

# Save to CSV
csv_filename = f"{folder_name}.csv"
csv_path = folder_path / csv_filename

with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    if results:
        # Collect ALL unique field names from all products
        all_fieldnames = []
        seen_fields = set()
        
        for result in results:
            for key in result.keys():
                if key not in seen_fields:
                    all_fieldnames.append(key)
                    seen_fields.add(key)
        
        writer = csv.DictWriter(f, fieldnames=all_fieldnames)
        writer.writeheader()
        writer.writerows(results)

print(f"\n✅ Saved {len(results)} products to CSV: {csv_path}")
print(f"🎯 All done! Folder: {folder_path}")