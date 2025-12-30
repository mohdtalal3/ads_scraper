from curl_cffi import requests
import re
import json
import csv
import time
import os
from pathlib import Path
from PIL import Image
from datetime import datetime
import html
from urllib.parse import urlparse, parse_qs

# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------
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


def download_image(url, path, auto_crop=True, max_retries=3):
    """Download an image and optionally auto-crop whitespace."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=30, impersonate="chrome107")
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
                    print(f"  ⚠️ Download failed (status {resp.status_code}), retrying... ({attempt + 1}/{max_retries})")
                    time.sleep(1)
                else:
                    print(f"  ⚠️ Failed to download image after {max_retries} attempts (status {resp.status_code})")
                return False
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Error downloading image, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(1)
            else:
                print(f"  ❌ Error downloading image after {max_retries} attempts: {e}")
            return False
    return False


def format_date(date_str):
    """Convert date to MM-DD-YY format."""
    try:
        # Parse YYYY-MM-DD format
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%m-%d-%y")
    except:
        return date_str

# --------------------------------------------------
# Step 1: Extract Next.js BUILD ID
# --------------------------------------------------
def get_build_id(max_retries=3):
    """Extract Build ID from HEB app.js with retry logic."""
    APP_JS_URL = "https://cx.static.heb.com/_next/static/chunks/pages/_app-e2f7cb1e0021c7d8.js"

    headers = {
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/107.0.0.0 Safari/537.36"
        ),
        "accept": "*/*",
    }

    for attempt in range(max_retries):
        try:
            resp = requests.get(
                APP_JS_URL,
                headers=headers,
                impersonate="chrome107",
                timeout=30,
            )
            resp.raise_for_status()

            js_text = resp.text

            m = re.search(
                r'SENTRY_RELEASE\s*=\s*\{\s*id:\s*"([a-f0-9]{32,})"\s*\}',
                js_text
            )

            if not m:
                raise RuntimeError("❌ Build ID not found")

            return m.group(1)
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Failed to get Build ID, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                print(f"  ❌ Failed to get Build ID after {max_retries} attempts: {e}")
                raise
    return None

# --------------------------------------------------
# Step 2: Pagination over ALL coupon pages
# --------------------------------------------------
def fetch_all_coupons(build_id, max_retries=3):
    """Fetch all coupons with pagination and retry logic."""
    BASE_URL = f"https://www.heb.com/_next/data/{build_id}/en/digital-coupon/coupon-selection/all-coupons.json"

    params = {
        "pageName": "all-coupons",
        "sort_order": "FEATURED",
    }

    api_headers = {
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/107.0.0.0 Safari/537.36"
        ),
        "accept": "application/json",
        "x-nextjs-data": "1",
        "referer": "https://www.heb.com/digital-coupon/coupon-selection/all-coupons",
    }

    all_coupons = []
    cursor = None
    page_num = 1

    while True:
        if cursor:
            params["cursor"] = cursor
        else:
            params.pop("cursor", None)

        print(f"➡️ Fetching page {page_num}")

        # Retry logic for each page
        page_data = None
        for attempt in range(max_retries):
            try:
                r = requests.get(
                    BASE_URL,
                    headers=api_headers,
                    params=params,
                    impersonate="chrome107",
                    timeout=30,
                )
                r.raise_for_status()
                page_data = r.json()
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  ⚠️ Failed to fetch page {page_num}, retrying... ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(2)
                else:
                    print(f"  ❌ Failed to fetch page {page_num} after {max_retries} attempts: {e}")
                    return all_coupons

        if not page_data:
            break

        page_props = page_data["pageProps"]
        coupons = page_props.get("couponData", [])

        # Add page number to each coupon
        for coupon in coupons:
            coupon["_page_number"] = page_num
        
        all_coupons.extend(coupons)

        # Pagination via _head.next
        next_url = page_props.get("_head", {}).get("next")
        if not next_url:
            break

        parsed = urlparse(next_url)
        qs = parse_qs(parsed.query)
        cursor = qs.get("cursor", [None])[0]

        if not cursor:
            break

        page_num += 1
        time.sleep(0.5)  # Small delay between pages

    return all_coupons

# --------------------------------------------------
# Step 3: Main execution
# --------------------------------------------------
def main():
    print("🚀 Starting HEB Coupons scraper\n")
    
    # Get Build ID
    print("🔍 Extracting Build ID...")
    build_id = get_build_id()
    print(f"✅ Build ID: {build_id}\n")
    
    # Fetch all coupons
    print("🎟️ Fetching all coupons...")
    all_coupons = fetch_all_coupons(build_id)
    print(f"\n✅ Total coupons collected: {len(all_coupons)}\n")
    
    if not all_coupons:
        print("❌ No coupons found")
        return
    
    # Create folder structure: HEB_Coupons/HEB_Coupons_Date/
    base_folder = Path("HEB_Coupons")
    base_folder.mkdir(exist_ok=True)
    
    current_date = datetime.now().strftime("%m-%d-%y")
    folder_name = f"HEB_Coupons_{current_date}"
    folder_path = base_folder / folder_name
    folder_path.mkdir(exist_ok=True)
    
    print(f"📁 Saving to folder: {folder_path}\n")
    
    # Process coupons
    processed_coupons = []
    
    overall_rank = 1
    for idx, coupon in enumerate(all_coupons, 1):
        group_details = coupon.get("groupDetails", {})
        reward = coupon.get("reward", {})
        page_number = coupon.get("_page_number", 0)
        
        processed_coupon = {
            # Primary identifiers
            "id": coupon.get("id"),
            "rank": overall_rank,
            "page_number": page_number,
            "description": html.unescape(coupon.get("description", "")),
            "short_description": html.unescape(coupon.get("shortDescription", "")),
            
            # Redemption details
            "redemption_limit": coupon.get("redemptionLimit"),
            "redemption_availability": coupon.get("redemptionAvailability"),
            "expiration_date": format_date(coupon.get("expirationDate", "")),
            
            # Classification
            "marketing_type": coupon.get("marketingType"),
            "type": coupon.get("type"),
            "reward_type": reward.get("__typename", ""),
            
            # Print status
            "print_statuses": " | ".join(coupon.get("printStatuses", [])),
            
            # Group details
            "group_id": group_details.get("groupId"),
            
            # Images
            "image": "",  # Will be filled with downloaded filename
            "image_url": coupon.get("imageUrl", ""),
            
            # Technical
            "typename": coupon.get("__typename", ""),
        }
        
        processed_coupons.append(processed_coupon)
        overall_rank += 1
    
    # Download coupon images
    print(f"🖼️ Downloading {len(processed_coupons)} coupon images...")
    downloaded_count = 0
    
    for idx, coupon in enumerate(processed_coupons, 1):
        image_url = coupon.get("image_url", "")
        
        if image_url and image_url.strip():
            coupon_id = coupon.get("id", idx)
            rank = coupon.get("rank", idx)
            image_filename = f"HEB_Coupon_{coupon_id}_{rank}.png"
            img_path = folder_path / image_filename
            
            # Download and crop image
            download_image(image_url, img_path, auto_crop=True)
            coupon["image"] = image_filename
            downloaded_count += 1
            
            if idx % 50 == 0:
                print(f"  📥 Downloaded {idx}/{len(processed_coupons)} images...")
        else:
            coupon["image"] = ""
    
    print(f"✅ Downloaded {downloaded_count} coupon images\n")
    
    # Save to CSV
    csv_filename = f"{folder_name}.csv"
    csv_path = folder_path / csv_filename
    
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=processed_coupons[0].keys())
        writer.writeheader()
        writer.writerows(processed_coupons)
    
    print(f"💾 Saved CSV: {csv_filename}\n")
    
    # Save JSON (commented out)
    # json_filename = f"{folder_name}.json"
    # json_path = folder_path / json_filename
    # with open(json_path, "w", encoding="utf-8") as f:
    #     json.dump(all_coupons, f, indent=2, ensure_ascii=False)
    # print(f"💾 Saved JSON: {json_filename}\n")
    
    print(f"\n🎯 HEB Coupons scraping complete!")


if __name__ == "__main__":
    main()
