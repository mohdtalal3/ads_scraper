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
print("🍪 FOOD LION COOKIE SETUP")
print("=" * 70)
print("\nTo get the required cookies:")
print("1. Open https://foodlion.com/savings/coupons/browse in Chrome")
print("2. Press F12 to open DevTools")
print("3. Go to 'Application' tab (top menu)")
print("4. In left sidebar: Storage → Cookies → https://foodlion.com")
print("5. Find and copy the cookie values:\n")

# Get DataDome cookie
print("📋 Cookie 1: 'datadome'")
print("   → Look for cookie named 'datadome' in the list")
print("   → Copy the entire 'Value' field (long string)\n")
datadome_value = input("Paste datadome cookie value: ").strip()

# Get ppdtk cookie
print("\n📋 Cookie 2: 'ppdtk'")
print("   → Look for cookie named 'ppdtk' in the list")
print("   → Copy the entire 'Value' field\n")
ppdtk_value = input("Paste ppdtk cookie value: ").strip()

print("\n✅ Cookies received! Starting scraper...\n")
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
# -----------------------------
# -------------------------------------------------------
# Helper: Download image with auto-crop
# -------------------------------------------------------
def download_image(url, path, auto_crop=True):
    """Download an image and optionally auto-crop whitespace."""
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
            print(f"  ⚠️ Failed to download image (status {resp.status_code}): {url}")
            return False
    except Exception as e:
        print(f"  ❌ Error downloading image: {e}")
        return False


# -----------------------------
# Create persistent session
# -----------------------------
session = requests.Session(impersonate="chrome131")

# 🔑 Set cookies from user input
session.cookies.set(
    name="datadome",
    value=datadome_value,
    domain=".foodlion.com",
    path="/"
)
session.cookies.set(
    name="ppdtk",
    value=ppdtk_value,
    domain=".foodlion.com",
    path="/"
)

# -----------------------------
# STEP 1: GET coupons page
# -----------------------------
# print("[1] Loading coupons page with DataDome cookie...")

# r1 = session.get(
#     "https://foodlion.com/savings/coupons/browse",
#     headers={
#         **BASE_HEADERS,
#         # "accept": "text/html,application/xhtml+xml",
#         # "upgrade-insecure-requests": "1",
#         "origin": "https://foodlion.com",
#         "referer": "https://foodlion.com/savings/coupons/browse",
#     },
#     timeout=30
# )
# print(r1.text)


# print("Cookies after r1:")

# for k, v in session.cookies.items():
#     print(f"{k} = {v[:40]}...")


# print("Browse status:", r1.status_code)
# print("Cookies after browse:")
# for c in session.cookies:
#     print(" ", c.name, "=", c.value[:30], "...")

# # Quick bot check
# if "captcha-delivery" in r1.text.lower():
#     raise RuntimeError("❌ DataDome challenge page returned")

# -----------------------------
# STEP 2: Call coupons API with pagination
# -----------------------------
print("[2] Calling coupons API with pagination...")

API_URL = (
    "https://foodlion.com/api/v7.0/coupons/users/363428687/prism/service-locations/1006699/coupons/search?fullDocument=true&unwrap=true"
)

PARAMS = {
    "fullDocument": "true",
    "unwrap": "true"
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

    r2.raise_for_status()
    data = r2.json()
    
    # Get pagination info
    paging = data.get("paging", {})
    total_coupons = paging.get("total", 0)
    current_size = paging.get("size", 0)
    
    # Get coupons from this page
    page_coupons = data.get("coupons", [])
    all_coupons.extend(page_coupons)
    
    print(f"  ✅ Got {len(page_coupons)} coupons (Total so far: {len(all_coupons)}/{total_coupons})")
    
    # Check if we have all coupons
    if len(all_coupons) >= total_coupons or len(page_coupons) == 0:
        break
    
    # Move to next page
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
        cropped = download_image(image_url, img_path)
        local_image_path = image_filename
        
        if cropped:
            print(f"📥 [{i}/{len(coupons)}] Downloaded & cropped: {name}")
        else:
            print(f"📥 [{i}/{len(coupons)}] Downloaded: {name}")
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

