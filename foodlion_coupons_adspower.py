import json
import csv
import os
import time
import requests as std_requests
from datetime import datetime
from pathlib import Path
from curl_cffi import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from PIL import Image

# -----------------------------
# AdsPower Config
# -----------------------------
ADSPOWER_URL = "http://local.adspower.net:50325"
PROFILE_ID   = "k1bwflca"
API_KEY      = "b1b13bd691e95f0b66bae68c5aaa65ed0086a2d00df9de37"

ADS_HEADERS = {"Authorization": f"Bearer {API_KEY}"}

COUPONS_PAGE = "https://foodlion.com/savings/coupons/browse"

# -----------------------------
# Base config (same as simple coupon script)
# -----------------------------
BASE_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "accept-language": "en-US,en;q=0.9",
}

# -----------------------------
# STEP 0: Start AdsPower browser, extract datadome cookie, close browser
# -----------------------------
print("=" * 70)
print("🌐 FOOD LION COUPONS — AdsPower Mode")
print("=" * 70)
print("\n[0] Starting AdsPower browser profile...")

resp = std_requests.get(
    f"{ADSPOWER_URL}/api/v1/browser/start",
    params={"user_id": PROFILE_ID},
    headers=ADS_HEADERS,
    timeout=30
).json()

if resp["code"] != 0:
    raise Exception(f"AdsPower start failed: {resp['msg']}")

chrome_driver = resp["data"]["webdriver"]
debugger_addr = resp["data"]["ws"]["selenium"]

options = Options()
options.add_experimental_option("debuggerAddress", debugger_addr)
driver = webdriver.Chrome(service=Service(chrome_driver), options=options)
driver.set_script_timeout(60)

print("  ✅ Browser attached")
print(f"\n[1] Navigating to {COUPONS_PAGE} ...")
driver.get(COUPONS_PAGE)

# Wait for datadome cookie to appear (up to 30s)
print("  ⏳ Waiting for DataDome cookie...")
datadome_value = None
for _ in range(30):
    for c in driver.get_cookies():
        if c["name"] == "datadome":
            datadome_value = c["value"]
            break
    if datadome_value:
        break
    time.sleep(1)

if not datadome_value:
    # Fallback: let user confirm the page loaded and try once more
    input("  ⏸  Could not auto-detect datadome — press Enter after the page loads in AdsPower browser...")
    for c in driver.get_cookies():
        if c["name"] == "datadome":
            datadome_value = c["value"]
            break

if not datadome_value:
    raise RuntimeError("❌ Failed to extract datadome cookie from AdsPower browser")

print(f"  ✅ Got datadome cookie: {datadome_value[:40]}...")

# Stop AdsPower browser — no longer needed
std_requests.get(
    f"{ADSPOWER_URL}/api/v1/browser/stop",
    params={"user_id": PROFILE_ID},
    headers=ADS_HEADERS,
    timeout=10
)
driver.quit()
print("  🛑 Browser stopped\n")
print("=" * 70)


# -------------------------------------------------------
# Helper: Format Date (e.g. 2025-12-23 → 12-23-25)
# -------------------------------------------------------
def format_date(date_str):
    """Convert YYYY-MM-DD to MM-DD-YY format"""
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
        r = session.get(url, timeout=30)
        if r.status_code == 200:
            with open(path, "wb") as f:
                f.write(r.content)
            if auto_crop:
                if auto_crop_whitespace(path):
                    return True
            return False
        else:
            print(f"  ⚠️ Failed to download image (status {r.status_code}): {url}")
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
# Build curl_cffi session with extracted datadome cookie
# (same pattern as foodlion_coupons.py)
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
# STEP 2: Call coupons API with pagination (same as simple script)
# -----------------------------
print("[2] Calling coupons API with pagination...")

API_URL = (
    "https://foodlion.com/api/v7.0/coupons/users/2/prism/service-locations/50002071/coupons/search?fullDocument=true&unwrap=true"
)

PARAMS = {
    "fullDocument": "true",
    "unwrap": "true",
}

all_coupons = []
start = 0
page_size = 90
total_coupons = None

while True:
    PAYLOAD = {
        "query": {"start": start, "size": page_size},
        "filter": {
            "loadable": True,
            "loaded": False,
            "sourceSystems": ["QUO", "COP", "INM"]
        },
        "copientQuotientTargetingEnabled": True,
        "cardNumber": "",
        "sorts": [{"targeted": "desc"}]
    }

    print(f"  📡 Fetching coupons {start} to {start + page_size}...")

    r2 = session.post(
        API_URL,
        params=PARAMS,
        headers={
            **BASE_HEADERS,
            "accept": "application/json",
            "content-type": "application/json",
            "origin": "https://foodlion.com",
            "referer": "https://foodlion.com/savings/coupons/browse",
        },
        json=PAYLOAD,
        timeout=30
    )
    print(r2.url)
    r2.raise_for_status()
    data = r2.json()

    paging = data.get("paging", {})
    total_coupons = paging.get("total", 0)

    page_coupons = data.get("coupons", [])
    all_coupons.extend(page_coupons)

    print(f"  ✅ Got {len(page_coupons)} coupons (Total so far: {len(all_coupons)}/{total_coupons})")

    if len(all_coupons) >= total_coupons or len(page_coupons) == 0:
        break

    start += page_size

print(f"\n✅ Fetched all {len(all_coupons)} coupons\n")

# Save raw JSON for reference
with open("foodlion_coupons.json", "w", encoding="utf-8") as f:
    json.dump({"coupons": all_coupons, "total": len(all_coupons)}, f, indent=2)

coupons = all_coupons
print(f"📊 Total coupons to process: {len(coupons)}\n")

if not coupons:
    print("❌ No coupons found.")
    exit(0)

# Determine date range from coupons
start_dates = [c.get("startDate") for c in coupons if c.get("startDate")]
end_dates = [c.get("endDate") for c in coupons if c.get("endDate")]

if start_dates and end_dates:
    valid_from = format_date(min(start_dates))
    valid_to = format_date(max(end_dates))
else:
    # Fallback to current date
    today = datetime.now().strftime("%m-%d-%y")
    valid_from = today
    valid_to = today

# Create folder structure: FoodLion/FoodLion_Coupons_MM-DD-YY_MM-DD-YY/
base_folder = Path("FoodLion")
base_folder.mkdir(exist_ok=True)

folder_name = f"FoodLion_Coupons_{valid_from}_{valid_to}"
folder_path = base_folder / folder_name
folder_path.mkdir(exist_ok=True)

print(f"📁 Saving to: {folder_path}\n")

# Process coupons and download images
results = []
for i, coupon in enumerate(coupons, 1):
    coupon_id = coupon.get("id", "")
    external_id = coupon.get("externalId", "")
    name = coupon.get("name", "")
    title = coupon.get("title", "")
    description = coupon.get("description", "")
    
    # Get image URL (prefer externalImage, fallback to imageUrl)
    image_url = coupon.get("externalImage") or coupon.get("imageUrl")
    local_image_path = ""
    
    if image_url:
        # Create filename: FoodLion_couponid_externalid.png
        safe_id = coupon_id.replace("/", "_").replace("\\", "_")
        image_filename = f"FoodLion_{safe_id}_{external_id}.png"
        img_path = folder_path / image_filename
        
        # Download and crop image
        #cropped = download_image(image_url, img_path)
        local_image_path = image_filename
        
        # if cropped:
        #     print(f"📥 [{i}/{len(coupons)}] Downloaded & cropped: {name}")
        # else:
        #     print(f"📥 [{i}/{len(coupons)}] Downloaded: {name}")
    else:
        print(f"⚠️ [{i}/{len(coupons)}] No image for: {name}")
    
    # Build CSV row with ALL available fields
    result = {
        "id": coupon_id,
        "external_id": external_id,
        "name": name,
        "title": title,
        "description": description,
        "price": title,  # Title contains price info like "Save $1.00"
        "start_date": coupon.get("startDate", ""),
        "end_date": coupon.get("endDate", ""),
        "max_per_order": coupon.get("maxPerOrder", ""),
        "coupon_g_code": coupon.get("couponGCode", ""),
        "deal_tracking_id": coupon.get("dealTrackingId", ""),
        "product_ids": ", ".join(coupon.get("productIds", [])),
        "pod_group_ids": ", ".join(coupon.get("podGroupIds", [])),
        "image_url": coupon.get("imageUrl", ""),
        "external_image": coupon.get("externalImage", ""),
        "coupon_reward_target": coupon.get("couponRewardTarget", ""),
        "manufacturer_coupon": coupon.get("manufacturerCoupon", ""),
        "source_system": coupon.get("sourceSystem", ""),
        "targeted": coupon.get("targeted", ""),
        "clipped": coupon.get("clipped", ""),
        "clipping_required": coupon.get("clippingRequired", ""),
        "promotion_type": coupon.get("promotionType", ""),
        "category_tree_id": coupon.get("categoryTreeId", ""),
        "category_tree_name": coupon.get("categoryTreeName", ""),
        "top_category_tree_id": coupon.get("topCategoryTreeId", ""),
        "top_category_tree_name": coupon.get("topCategoryTreeName", ""),
        "legal_text": coupon.get("legalText", ""),
        "coupon_channels": ", ".join(coupon.get("couponChannels", [])),
        "source_system_id": coupon.get("sourceSystemId", ""),
        "circular_id": coupon.get("circularId", ""),
        "multi_qty": coupon.get("multiQty", ""),
        "loaded": coupon.get("loaded", ""),
        "loadable": coupon.get("loadable", ""),
        "coupon_type": coupon.get("couponType", ""),
        "channel": ", ".join(coupon.get("channel", [])),
        "max_discount": coupon.get("maxDiscount", ""),
        "badge_ids": ", ".join(str(b) for b in coupon.get("badgeIds", [])),
        "personalized_offer": coupon.get("personalizedOffer", ""),
        "image": local_image_path,
    }
    
    results.append(result)

# Save to CSV
csv_filename = f"{folder_name}.csv"
csv_path = folder_path / csv_filename

with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    if results:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

print(f"\n✅ Saved {len(results)} coupons to CSV: {csv_path}")
print(f"🎯 All done! Folder: {folder_path}")

