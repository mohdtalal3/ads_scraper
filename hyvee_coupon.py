import requests
import json
import csv
import time
import os
from pathlib import Path
from PIL import Image
from datetime import datetime


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
                
                # Auto-crop if requested
                if auto_crop:
                    if auto_crop_whitespace(path):
                        return True  # Successfully cropped
                return True  # Downloaded successfully
            else:
                if attempt < max_retries - 1:
                    time.sleep(1)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
    return False


def format_date(date_str):
    """Convert ISO date to MM-DD-YY format without time."""
    try:
        # Parse ISO format: 2026-01-04T21:00:00-08:00
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%m-%d-%y")
    except:
        return date_str


# --------------------------------------------------
# API FETCHING
# --------------------------------------------------


# --------------------------------------------------
# API FETCHING
# --------------------------------------------------
def fetch_coupons(store_id=1759):
    """Fetch coupons from Hy-Vee API."""
    url = "https://www.hy-vee.com/deals/api/graphql/CouponsScreenV4QueryWithoutFuelSaver/two-legged"

    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "apollographql-client-name": "hy-vee-deals",
        "api-version": "1",
        "origin": "https://www.hy-vee.com",
        "referer": "https://www.hy-vee.com/deals/coupons?offerState=Available",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36"
        ),
    }

    payload = {
        "operationName": "CouponsScreenV4QueryWithoutFuelSaver",
        "variables": {
            "storeId": store_id
        },
        "query": """
        fragment ICouponV4 on CouponV4 {
          couponId
          clipStartDate
          category
          imageUrl
          brand
          clipEndDate
          expirationDate
          value
          valueText
          description
          terms
          offerState
          upcs
          redeemedDate
          __typename
        }

        query CouponsScreenV4QueryWithoutFuelSaver($storeId: Int) {
          couponsV4(storeId: $storeId) {
            ...ICouponV4
            __typename
          }
        }
        """
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    
    return response.json()


# --------------------------------------------------
# CSV EXPORT
# --------------------------------------------------
def save_to_csv(coupons_data, csv_file, images_dir):
    """Save coupons to CSV with image downloading."""
    
    coupons = coupons_data.get("data", {}).get("couponsV4", [])
    
    if not coupons:
        print("⚠️ No coupons found")
        return
    
    print(f"📦 Processing {len(coupons)} coupons...")
    
    csv_rows = []
    
    for idx, coupon in enumerate(coupons, 1):
        # Extract coupon details
        coupon_id = coupon.get("couponId", "")
        clip_start_date = format_date(coupon.get("clipStartDate", ""))
        category = coupon.get("category", "")
        image_url = coupon.get("imageUrl", "")
        brand = coupon.get("brand", "")
        clip_end_date = format_date(coupon.get("clipEndDate", ""))
        expiration_date = format_date(coupon.get("expirationDate", ""))
        price = coupon.get("value", 0)
        price_text = coupon.get("valueText", "")
        description = coupon.get("description", "")
        terms = coupon.get("terms", "")
        offer_state = coupon.get("offerState", "")
        
        # Download image
        image_filename = ""
        if image_url:
            image_filename = f"{idx:03d}_{coupon_id[:8]}.png"
            image_path = images_dir / image_filename
            
            print(f"   📥 [{idx}/{len(coupons)}] Downloading: {coupon_id[:8]}", end="")
            success = download_image(image_url, image_path)
            print(" ✓" if success else " ✗")
        
        # Prepare CSV row
        csv_row = {
            "rank": idx,
            "coupon_id": coupon_id,
            "clip_start_date": clip_start_date,
            "clip_end_date": clip_end_date,
            "expiration_date": expiration_date,
            "category": category,
            "brand": brand,
            "price": price,
            "price_text": price_text,
            "description": description,
            "terms": terms,
            "offer_state": offer_state,
            "image_filename": image_filename,
            "image_url": image_url
        }
        
        csv_rows.append(csv_row)
    
    # Write to CSV
    if csv_rows:
        fieldnames = [
            "rank", "coupon_id", "clip_start_date", "clip_end_date", "expiration_date",
            "category", "brand", "price", "price_text", "description", "terms",
            "offer_state", "image_filename", "image_url"
        ]
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
        
        print(f"\n✅ Saved {len(csv_rows)} coupons to CSV")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
if __name__ == "__main__":
    print("=" * 80)
    print("HY-VEE COUPONS SCRAPER")
    print("=" * 80)
    print()
    
    try:
        # Fetch coupons
        print("🔍 Fetching coupons from API...")
        data = fetch_coupons()
        
        # Get date range from first coupon
        coupons = data.get("data", {}).get("couponsV4", [])
        if not coupons:
            print("❌ No coupons found")
            exit(1)
        
        # Find earliest start date and latest expiration date across all coupons
        start_dates = []
        end_dates = []
        
        for coupon in coupons:
            clip_start = coupon.get("clipStartDate", "")
            expiration = coupon.get("expirationDate", "")
            
            if clip_start:
                try:
                    dt = datetime.fromisoformat(clip_start.replace('Z', '+00:00'))
                    start_dates.append(dt)
                except:
                    pass
            
            if expiration:
                try:
                    dt = datetime.fromisoformat(expiration.replace('Z', '+00:00'))
                    end_dates.append(dt)
                except:
                    pass
        
        # Get earliest start and latest end
        earliest_start = min(start_dates) if start_dates else datetime.now()
        latest_end = max(end_dates) if end_dates else datetime.now()
        
        start_date = earliest_start.strftime("%m-%d-%y")
        end_date = latest_end.strftime("%m-%d-%y")
        
        # Create folder structure: HyVee_Coupons/HyVee_Coupons_MM-DD-YY_to_MM-DD-YY
        base_dir = Path("HyVee_Coupons")
        folder_name = f"HyVee_Coupons_{start_date}_to_{end_date}"
        output_dir = base_dir / folder_name
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        csv_file = output_dir / f"{folder_name}.csv"
        
        print(f"✅ Found {len(coupons)} coupons")
        print(f"📁 Folder: {folder_name}")
        print()
        
        # Save to CSV with images
        save_to_csv(data, csv_file, images_dir)
        
        print()
        print("=" * 80)
        print("✅ COMPLETE!")
        print(f"� CSV: {csv_file}")
        print(f"📁 Location: {output_dir}")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

