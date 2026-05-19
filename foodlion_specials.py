import json
import csv
import os
from datetime import datetime
from pathlib import Path
from curl_cffi import requests
from PIL import Image

# -----------------------------
# Get cookies from user
# -----------------------------
print("=" * 70)
print("🍪 FOOD LION SPECIALS COOKIE SETUP")
print("=" * 70)
print("\nTo get the required cookies:")
print("1. Open https://foodlion.com/savings/specials in Chrome")
print("2. Press F12 to open DevTools")
print("3. Go to 'Application' tab → Storage → Cookies → https://foodlion.com")
print("4. Find and copy the 'datadome' cookie value\n")

datadome_value = input("Paste datadome cookie value: ").strip()

print("\n✅ Cookie received! Starting scraper...\n")
print("=" * 70)

# -----------------------------
# Base config
# -----------------------------
BASE_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "accept-language": "en-US,en;q=0.9",
}

API_URL = "https://foodlion.com/api/v6.0/products/2/50002071"

BASE_PARAMS = {
    "catTreeId": "2098",
    "sort": "itemsPurchased desc, name asc",
    "filter": "specials",
    "flags": "true",
    "targeter": "browseSpecialsCategory",
    "substitute": "false",
    "nutrition": "false",
    "extendedInfo": "false",
    "facetExcludeFilter": "true",
    "facet": "categories,brands,nutrition,sustainability,newArrivals,privateLabel",
    "facetExcludeAllFilters": "rootCatTrees",
}

PAGE_SIZE = 40  # page size used by this endpoint


# -------------------------------------------------------
# Helper: Format Date
# -------------------------------------------------------
def format_date(date_str):
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%m-%d-%y")
    except Exception:
        return date_str


# -------------------------------------------------------
# Helper: Auto-crop whitespace from images
# -------------------------------------------------------
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
        print(f"    ⚠️ Auto-crop failed for {os.path.basename(str(image_path))}: {e}")


# -------------------------------------------------------
# Helper: Download image with auto-crop
# -------------------------------------------------------
def download_image(url, path, auto_crop=True):
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200:
            with open(path, "wb") as f:
                f.write(resp.content)
            if auto_crop:
                if auto_crop_whitespace(path):
                    return True
            return False
        else:
            print(f"  ⚠️ Failed to download image (status {resp.status_code}): {url}")
            return False
    except Exception as e:
        print(f"  ❌ Error downloading image: {e}")
        return False


# -----------------------------
# Proxy config
# -----------------------------
STATIC_PROXY = "http://b7e4c783105e0a21fd89__cr.us:bfadc321f9ff54fd@gw.dataimpulse.com:823"
PROXIES = {
    "http": STATIC_PROXY,
    "https": STATIC_PROXY,
}

# -----------------------------
# Create persistent session
# -----------------------------
session = requests.Session(impersonate="chrome107")
session.proxies.update(PROXIES)

session.cookies.set(
    name="datadome",
    value=datadome_value,
    domain=".foodlion.com",
    path="/"
)
# -----------------------------
# Paginate through all specials
# -----------------------------
print("[1] Fetching Food Lion Specials with pagination...\n")

all_products = []
start = 0
total_products = None

while True:
    params = {**BASE_PARAMS, "start": str(start)}

    print(f"  📡 Fetching products {start} to {start + PAGE_SIZE}...")

    resp = session.get(
        API_URL,
        params=params,
        headers={
            **BASE_HEADERS,
            "accept": "application/json",
            "referer": "https://foodlion.com/savings/specials",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    response_block = data.get("response", {})

    # Get total on first call
    if total_products is None:
        pagination = response_block.get("pagination", {})
        total_products = pagination.get("total", 0)
        print(f"  📊 Total specials reported by API: {total_products}")

    page_products = response_block.get("products", [])
    all_products.extend(page_products)

    print(f"  ✅ Got {len(page_products)} products (Total so far: {len(all_products)}/{total_products})")

    if len(page_products) == 0 or len(all_products) >= total_products:
        break

    start += PAGE_SIZE

print(f"\n✅ Fetched all {len(all_products)} specials\n")

# Save raw JSON for reference
with open("foodlion_specials.json", "w", encoding="utf-8") as f:
    json.dump({"products": all_products, "total": len(all_products)}, f, indent=2)

if not all_products:
    print("❌ No products found.")
    exit(0)

# -----------------------------
# Folder setup — use today's date
# -----------------------------
today = datetime.now().strftime("%m-%d-%y")
folder_name = f"FoodLion_Specials_{today}"

base_folder = Path("FoodLion")
base_folder.mkdir(exist_ok=True)

folder_path = base_folder / folder_name
folder_path.mkdir(exist_ok=True)

print(f"📁 Saving to: {folder_path}\n")

# -----------------------------
# Process products → CSV
# -----------------------------
results = []
for i, product in enumerate(all_products, 1):
    prod_id = product.get("prodId", "")
    name = product.get("name", "")
    size = product.get("size", "")
    price = product.get("price", "")
    regular_price = product.get("regularPrice", "")
    brand = product.get("brand", "")
    upc = product.get("upc", "")
    root_cat = product.get("rootCatName", "")
    subcat = product.get("subcatName", "")
    unit_price = product.get("unitPrice", "")
    unit_measure = product.get("unitMeasure", "")

    # Flags
    flags = product.get("flags", {})
    sale = flags.get("sale", "")
    bogo = flags.get("bogo", "")
    out_of_stock = flags.get("outOfStock", "")
    new_arrival = flags.get("newArrival", "")
    private_label = flags.get("privateLabel", "")
    special_code = flags.get("specialCode", "")

    # Image
    images = product.get("image", {})
    image_medium = images.get("medium", "")
    image_large = images.get("large", "")

    local_image_path = ""
    if image_medium:
        image_filename = f"FoodLion_{prod_id}.png"
        img_path = folder_path / image_filename
        # Uncomment to download images:
        # download_image(image_medium, img_path)
        local_image_path = image_filename

    # Sale meta
    sale_meta = product.get("saleMeta", {})
    cents_off = sale_meta.get("centsOff", "")
    percent_off = sale_meta.get("percentOff", "")
    price_point = sale_meta.get("pricePoint", "")

    results.append({
        "prod_id": prod_id,
        "name": name,
        "size": size,
        "price": price,
        "regular_price": regular_price,
        "unit_price": unit_price,
        "unit_measure": unit_measure,
        "brand": brand,
        "upc": upc,
        "root_category": root_cat,
        "subcategory": subcat,
        "sale": sale,
        "bogo": bogo,
        "out_of_stock": out_of_stock,
        "new_arrival": new_arrival,
        "private_label": private_label,
        "special_code": special_code,
        "cents_off": cents_off,
        "percent_off": percent_off,
        "price_point": price_point,
        "sale_expiration": product.get("saleExpiration", ""),
        "ebt_eligible": product.get("ebtEligible", ""),
        "image_medium": image_medium,
        "image_large": image_large,
        "image": local_image_path,
    })

# -----------------------------
# Save CSV
# -----------------------------
csv_filename = f"{folder_name}.csv"
csv_path = folder_path / csv_filename

with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    if results:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

print(f"\n✅ Saved {len(results)} specials to CSV: {csv_path}")
print(f"🎯 All done! Folder: {folder_path}")
