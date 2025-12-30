import requests
import json
import csv
import time
import os
from pathlib import Path
from PIL import Image
from datetime import datetime
import html

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
STORE_ID = "01100696"
X_API_KEY = "bqwwosbzrzcvffztxzyczieljzsahmkp"

CIRCULARS_URL = "https://api.kroger.com/digitalads/v1/circulars"
CLASSIC_AD_URL = "https://oms-kroger-webapp-da-classic-api-prod.przone.net/api/dacs/{event_id}"
PAGE_DATA_URL = "https://oms-kroger-webapp-da-classic-api-prod.przone.net/api/dacs/{event_id}/pages/{page_id}"
OFFER_DETAILS_URL = "https://oms-kroger-webapp-da-classic-api-prod.przone.net/api/dacs/{event_id}/offers/{offer_id}"

# --------------------------------------------------
# HEADERS — CIRCULARS
# --------------------------------------------------
CIRCULAR_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://www.kroger.com",
    "referer": "https://www.kroger.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/143.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "x-kroger-channel": "WEB",
    "x-facility-id": STORE_ID,
    "x-modality-type": "IN_STORE",
    "x-modality": json.dumps({
        "type": "IN_STORE",
        "locationId": STORE_ID
    }),
    "x-call-origin": '{"component":"weekly ad","page":"weekly ad"}',
    "x-laf-object": json.dumps([
        {
            "modality": {
                "type": "IN_STORE",
                "handoffLocation": {"storeId": STORE_ID}
            },
            "sources": [{"storeId": STORE_ID}],
            "listingKeys": [STORE_ID]
        }
    ])
}

CIRCULAR_PARAMS = {
    "filter.tags": ["SHOPPABLE", "CLASSIC_VIEW"]
}

# --------------------------------------------------
# HEADERS — CLASSIC AD
# --------------------------------------------------
CLASSIC_HEADERS = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": "https://www.kroger.com",
    "referer": "https://www.kroger.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/143.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "xapikey": X_API_KEY
}

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
            resp = requests.get(url, timeout=30)
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
    """Convert ISO date to MM-DD-YY format."""
    try:
        # Parse ISO format: 2025-12-26T06:00:00Z or 2025-12-26
        if 'T' in date_str:
            date_str = date_str.split('T')[0]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%m-%d-%y")
    except:
        return date_str


# --------------------------------------------------
# FETCH CIRCULARS
# --------------------------------------------------
def fetch_circulars(session, max_retries=3):
    """Fetch circulars with retry logic."""
    for attempt in range(max_retries):
        try:
            r = session.get(
                CIRCULARS_URL,
                headers=CIRCULAR_HEADERS,
                params=CIRCULAR_PARAMS,
                timeout=30
            )
            r.raise_for_status()
            return r.json()["data"]
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Fetch circulars failed, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                print(f"  ❌ Fetch circulars failed after {max_retries} attempts: {e}")
                raise
    return None


# --------------------------------------------------
# FETCH CLASSIC AD
# --------------------------------------------------
def fetch_classic_ad(session, event_id, max_retries=1):
    """Fetch classic ad data with retry logic."""
    url = CLASSIC_AD_URL.format(event_id=event_id)
    for attempt in range(max_retries):
        try:
            r = session.get(
                url,
                headers=CLASSIC_HEADERS,
                params={"location": STORE_ID},
                timeout=30
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Fetch classic ad failed, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                # Don't raise, return None to allow skipping invalid events
                print(f"  ❌ Coupon id found instead of weekly ads. Skipping event {event_id}")
                return None
    return None


# --------------------------------------------------
# FETCH PAGE DATA
# --------------------------------------------------
def fetch_page_data(session, event_id, page_id, max_retries=3):
    """Fetch page data with retry logic."""
    url = PAGE_DATA_URL.format(event_id=event_id, page_id=page_id)
    for attempt in range(max_retries):
        try:
            r = session.get(
                url,
                headers=CLASSIC_HEADERS,
                params={"location": STORE_ID},
                timeout=30
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Fetch page data failed, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                print(f"  ❌ Fetch page data failed after {max_retries} attempts: {e}")
                return None
    return None


# --------------------------------------------------
# FETCH OFFER DETAILS
# --------------------------------------------------
def fetch_offer_details(session, event_id, offer_id, max_retries=3):
    """Fetch offer details with retry logic."""
    url = OFFER_DETAILS_URL.format(event_id=event_id, offer_id=offer_id)
    for attempt in range(max_retries):
        try:
            r = session.get(
                url,
                headers=CLASSIC_HEADERS,
                params={"location": STORE_ID},
                timeout=30
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Fetch offer details failed, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                print(f"  ❌ Fetch offer details failed after {max_retries} attempts: {e}")
                return None
    return None


# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main():
    session = requests.Session()
    
    print("🚀 Starting Kroger Weekly Ad scraper\n")
    print("🔍 Fetching circulars...")
    
    circulars = fetch_circulars(session)
    
    for circular in circulars:
        event_id = circular["eventId"]
        event_name = circular["eventName"]
        event_start = format_date(circular["eventStartDate"])
        event_end = format_date(circular["eventEndDate"])
        
        print(f"\n{'='*60}")
        print(f"📰 Processing: {event_name}")
        print(f"📅 Period: {event_start} to {event_end}")
        print(f"🆔 Event ID: {event_id}")
        print(f"{'='*60}\n")
        
        # Fetch classic ad data with error handling
        print(f"➡️ Fetching classic ad data...")
        classic_data = fetch_classic_ad(session, event_id)
        
        if not classic_data:
            print(f"⚠️ Skipping event {event_id} - no valid data available\n")
            continue
        
        pages = classic_data.get("pages", [])
        
        # Create folder structure: Kroger/Kroger_EventName_StartDate_EndDate/
        base_folder = Path("Kroger")
        base_folder.mkdir(exist_ok=True)
        
        # Clean event name for folder
        clean_event_name = event_name.replace(" ", "_").replace("/", "_")
        folder_name = f"Kroger_{clean_event_name}_{event_start}_{event_end}"
        folder_path = base_folder / folder_name
        folder_path.mkdir(exist_ok=True)
        
        print(f"📁 Saving to folder: {folder_path}\n")
        
        # Download flyer page images
        print(f"🖼️ Downloading {len(pages)} flyer page images...")
        for idx, page in enumerate(pages, 1):
            page_url = page.get("fileURL") or page.get("compressedFileURL")
            if page_url:
                page_name = page.get("page", f"page_{idx}")
                flyer_filename = f"Kroger_Flyer_{page_name}.jpg"
                flyer_path = folder_path / flyer_filename
                download_image(page_url, flyer_path, auto_crop=False)
                
                if idx % 5 == 0:
                    print(f"  📥 Downloaded {idx}/{len(pages)} flyer pages...")
        
        print(f"✅ Downloaded {len(pages)} flyer page images\n")
        
        # Extract and enrich product offers
        print(f"🛒 Extracting product offers...")
        all_products = []
        
        for page_number, page in enumerate(pages, start=1):
            page_id = page["eventPageId"]
            page_name = page.get("page", f"page_{page_number}")
            
            print(f"  📄 Processing page {page_number}/{len(pages)}: {page_name}")
            
            page_data = fetch_page_data(session, event_id, page_id)
            
            if not page_data:
                continue
            
            rank = 1
            for item in page_data.get("contents", []):
                if item.get("contentType") != "Offer":
                    continue
                
                try:
                    map_cfg = json.loads(item["mapConfig"])
                except:
                    continue
                
                content = map_cfg.get("content", {})
                offer_id = content.get("offerVersionProductGroupId")
                
                if not offer_id:
                    continue
                
                # Fetch offer details
                offer_details = fetch_offer_details(session, event_id, offer_id)
                
                if not offer_details:
                    continue
                
                # Build product record
                product = {
                    # Primary identifiers
                    "id": offer_details.get("id"),
                    "flyer_id": event_id,
                    "flyer_name": event_name,
                    "page_number": page_number,
                    "page_name": page_name,
                    "rank": rank,
                    
                    # Product details
                    "headline": html.unescape(offer_details.get("headline", "")),
                    "body_copy": html.unescape(offer_details.get("bodyCopy", "") or ""),
                    "pricing_text": html.unescape(offer_details.get("pricingText", "")),
                    "pricing_html": offer_details.get("pricingHTML", ""),
                    
                    # Dates
                    "flyer_start_date": event_start,
                    "flyer_end_date": event_end,
                    "offer_start_date": format_date(offer_details.get("startDate", "")),
                    "offer_end_date": format_date(offer_details.get("endDate", "")),
                    
                    # Images
                    "image": "",  # Will be filled with downloaded filename
                    "image_url": offer_details.get("imageURL", ""),
                    
                    # Additional details
                    "upc": offer_details.get("upc", ""),
                    "category": offer_details.get("category", ""),
                    "disclaimer": html.unescape(offer_details.get("disclaimer", "") or ""),
                    "is_shoppable": offer_details.get("isShoppable", False),
                    "is_coupon": offer_details.get("isCoupon", False),
                    "web_url": offer_details.get("webURL", ""),
                    "app_url": offer_details.get("appURL", ""),
                    
                    # Technical identifiers
                    "event_page_id": page_id,
                    "offer_version_product_group_id": offer_id,
                    "item_type": offer_details.get("itemType", ""),
                }
                
                all_products.append(product)
                rank += 1
                
            time.sleep(0.5)  # Small delay between pages
        print(f"\n✅ Total products collected: {len(all_products)}\n")
        
        # Download product images
        if all_products:
            print(f"🖼️ Downloading {len(all_products)} product images...")
            downloaded_count = 0
            
            for idx, product in enumerate(all_products, 1):
                image_url = product.get("image_url", "")
                
                if image_url and image_url.strip():
                    product_id = product.get("id", idx)
                    rank = product.get("rank", idx)
                    image_filename = f"Kroger_{product_id}_{rank}.png"
                    img_path = folder_path / image_filename
                    
                    # Download and crop image
                    download_image(image_url, img_path, auto_crop=True)
                    product["image"] = image_filename
                    downloaded_count += 1
                    
                    if idx % 50 == 0:
                        print(f"  📥 Downloaded {idx}/{len(all_products)} images...")
                else:
                    product["image"] = ""
            
            print(f"✅ Downloaded {downloaded_count} product images\n")
            
            # Save to CSV
            csv_filename = f"{folder_name}.csv"
            csv_path = folder_path / csv_filename
            
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=all_products[0].keys())
                writer.writeheader()
                writer.writerows(all_products)
            
            print(f"💾 Saved CSV: {csv_filename}\n")
        
        # Save metadata JSON (commented out)
        # json_filename = f"{folder_name}.json"
        # json_path = folder_path / json_filename
        # with open(json_path, "w", encoding="utf-8") as f:
        #     json.dump({
        #         "circular_meta": circular,
        #         "classic_ad_data": classic_data,
        #         "products": all_products
        #     }, f, indent=4)
        # print(f"💾 Saved JSON: {json_filename}\n")
    
    print(f"\n🎯 Kroger scraping complete!")


if __name__ == "__main__":
    main()
