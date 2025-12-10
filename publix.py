import requests
import csv
import os
import json
import re
import sys
import argparse
import time
from datetime import datetime
from pathlib import Path
import html
from PIL import Image
HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "Origin": "https://platform.liquidus.net",
    "Referer": "https://platform.liquidus.net/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
}
# -------------------------------------------------------
# Helper: Format Date (e.g. 2025-10-08T00:00:00Z → 10-08-25)
# -------------------------------------------------------
def format_date(date_str):
    if not date_str:
        return None
    try:
        # handle both "Oct 08, 2025 12:00:00 AM" and "2025-10-08T00:00:00Z"
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            dt = datetime.strptime(date_str, "%b %d, %Y %I:%M:%S %p")
        return dt.strftime("%m-%d-%y")
    except Exception:
        return None


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
            cropped_img.save(image_path, 'JPEG', quality=95, optimize=True)
            
            img.close()
            cropped_img.close()
            
            return True
        
        img.close()
        return False
        
    except Exception as e:
        print(f"    ⚠️ Auto-crop failed for {os.path.basename(str(image_path))}: {e}")
        return False


# -------------------------------------------------------
# Step 1: Get Store Code by ZIP and Store Name
# -------------------------------------------------------
def get_publix_store(zip_code: str, store_name: str):
    url = "https://services.publix.com/storelocator/api/v1/stores/"
    params = {
        "types": "R,G,H,N,S",
        "count": 30,
        "distance": 50,
        "includeOpenAndCloseDates": "true",
        "zip": zip_code,
        "isWebsite": "true",
        "_": int(time.time() * 1000)  # Cache-busting timestamp
    }
    
    headers_with_cache = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    }

    print(f"📍 Searching for stores near ZIP {zip_code} ...")
    response = requests.get(url, params=params, headers=headers_with_cache)
    response.raise_for_status()
    data = response.json()

    stores = data.get("stores") or data.get("features")
    if not stores:
        print("❌ No stores found for this ZIP code.")
        return None

    store_name_lower = store_name.lower()
    for store in stores:
        props = store.get("properties", store)
        name = props.get("name", "")
        if store_name_lower in name.lower():
            store_code = props.get("storeNumber")
            # Remove '#' if present and pad to 5 digits
            if store_code:
                store_code = str(store_code).lstrip('#')
                # Pad with leading zeros to 5 digits (e.g., 776 → 00776)
                store_code = store_code.zfill(5)
            print(f"✅ Found store: {name} (Code: {store_code})")
            return store_code

    print("⚠️ Store not found for that name. Try again.")
    return None


# -------------------------------------------------------
# Step 2: Get Campaign ID (needed for flyer images)
# -------------------------------------------------------
def get_campaign_id():
    # Add timestamp to bypass CDN cache
    url = f"https://graphql-cdn-slplatform.liquidus.net/?_={int(time.time() * 1000)}"
    payload = {
        "operationName": "getConfigFile",
        "variables": {
            "id": "publix_full_config",
            "country": "us",
            "language": "en",
            "origin": "www.publix.com"
        },
        "query": """
        query getConfigFile($id: ID!, $country: String, $language: String, $origin: String) {
            config(id: $id, country: $country, language: $language, origin: $origin)
        }
        """
    }
    response = requests.post(url, json=payload, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    config_data = json.loads(data["data"]["config"])
    campaign_id = config_data.get("campaignId")
    print(f"✅ Campaign ID: {campaign_id}")
    return campaign_id


# -------------------------------------------------------
# Step 3: Get Promotions (flyer name, code, date range)
# -------------------------------------------------------
def get_promotions(campaign_id, store_code):
    # Add timestamp to bypass CDN cache
    url = f"https://graphql-cdn-slplatform.liquidus.net/?_={int(time.time() * 1000)}"
    payload = {
        "operationName": "promotionsList",
        "variables": {
            "sort": "",
            "previewHash": None,
            "require": "sneakpeek,posted",
            "campaignid": campaign_id,
            "storeid": "undefined",
            "storeref": store_code,
            "countryid": 1,
            "languageid": 1,
            "env": "undefined"
        },
        "query": """
        query promotionsList(
          $previewHash: String, $sort: String, $require: String,
          $campaignid: String, $storeid: String, $storeref: String,
          $countryid: Int, $languageid: Int, $env: String
        ) {
          promotions(
            imageWidth: 1200,
            previewHash: $previewHash,
            sort: $sort,
            require: $require,
            campaignid: $campaignid,
            storeid: $storeid,
            storeref: $storeref,
            countryid: $countryid,
            languageid: $languageid,
            env: $env
          ) {
            promos {
              id
              title
              code
              saleStartDateString
              saleEndDateString
              imageURL
              pageCount
              typeID
            }
          }
        }
        """
    }

    resp = requests.post(url, json=payload, headers=HEADERS)
    resp.raise_for_status()
    promos = resp.json()["data"]["promotions"]["promos"]

    enriched = []
    print("\n✅ Found Promotions:\n")
    for p in promos:
        flyer_name = p.get("title") or "Unknown"
        start = p.get("saleStartDateString")
        end = p.get("saleEndDateString")
        type_id = p.get("typeID")
        print(f"📰 {flyer_name} | {p['code']} | TypeID: {type_id} | {start} → {end}")
        enriched.append({
            "flyer_name": flyer_name,
            "code": p["code"],
            "type_id": type_id,
            "saleStartDateString": start,
            "saleEndDateString": end
        })
    return enriched


# -------------------------------------------------------
# Step 4: Fetch Flyer Page Images
# -------------------------------------------------------
def fetch_flyer_images(campaign_id, promo_code, store_code, folder_path, flyer_name, valid_from, valid_to):
    # Add timestamp to bypass CDN cache
    url = f"https://graphql-cdn-slplatform.liquidus.net/?_={int(time.time() * 1000)}"
    payload = {
        "operationName": "Promotion",
        "variables": {
            "promotionCode": promo_code,
            "isDynamicV2": False,
            "sort": "",
            "previewHash": None,
            "require": "",
            "disablesneakpeekhero": False,
            "forcesneakpeekhero": False,
            "nuepOpen": False,
            "campaignid": campaign_id,
            "storeid": "undefined",
            "storeref": store_code,
            "countryid": 1,
            "languageid": 1,
            "env": "undefined"
        },
        "query": """
        query Promotion(
          $promotionCode: ID, $previewHash: String, $sort: String,
          $require: String, $disablesneakpeekhero: Boolean,
          $forcesneakpeekhero: Boolean, $nuepOpen: Boolean,
          $campaignid: String, $storeid: String, $storeref: String,
          $countryid: Int, $languageid: Int, $env: String,
          $isDynamicV2: Boolean!
        ) {
          promotion(
            code: $promotionCode,
            imageWidth: 1200, previewHash: $previewHash, sort: $sort,
            require: $require, disablesneakpeekhero: $disablesneakpeekhero,
            forcesneakpeekhero: $forcesneakpeekhero, campaignid: $campaignid,
            storeid: $storeid, storeref: $storeref, countryid: $countryid,
            languageid: $languageid, env: $env
          ) @skip(if: $isDynamicV2) {
            pages(
              imageWidth: 1200, previewHash: $previewHash,
              require: $require, nuepOpen: $nuepOpen
            ) {
              order
              imageURL(previewHash: $previewHash, require: $require)
            }
          }
        }
        """
    }

    resp = requests.post(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    
    # Safely extract pages, handling None values at any level
    response_data = resp.json()
    if not response_data:
        print(f"⚠️ Empty response for {promo_code}")
        return
    
    data = response_data.get("data")
    if not data:
        print(f"⚠️ No data in response for {promo_code}")
        return
    
    promotion = data.get("promotion")
    if not promotion:
        print(f"⚠️ No promotion data for {promo_code}")
        return
    
    pages = promotion.get("pages", [])
    if not pages:
        print(f"⚠️ No images found for {promo_code}")
        return

    print(f"📰 Downloading {len(pages)} flyer pages for {flyer_name}...")
    
    for page in pages:
        img_url = page.get("imageURL")
        page_num = page.get("order")
        if not img_url:
            continue
        # Format: Publix_promotion_name_10-08-25_10-14-25_flyer_page1.jpg
        filename = f"Publix_{flyer_name}_{valid_from}_{valid_to}_flyer_page{page_num}.jpg"
        img_path = os.path.join(folder_path, filename)
        
        # Retry mechanism for flyer page images
        max_retries = 3
        retry_count = 0
        download_success = False
        
        while retry_count < max_retries and not download_success:
            try:
                img_data = requests.get(img_url, timeout=60).content
                with open(img_path, "wb") as f:
                    f.write(img_data)
                download_success = True
                
                # Auto-crop whitespace from flyer page
                if auto_crop_whitespace(img_path):
                    print(f"📥 Downloaded & cropped: Page {page_num}/{len(pages)}")
                else:
                    print(f"📥 Downloaded: Page {page_num}/{len(pages)}")
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    print(f"⚠️ Retry {retry_count}/{max_retries} for page {page_num}")
                else:
                    print(f"❌ Failed to download page {page_num} after {max_retries} attempts: {e}")

    print(f"🖼️ Completed: Saved {len(pages)} flyer pages → {folder_path}")


# -------------------------------------------------------
# Step 5: Fetch Weekly Ads & Save + Match Flyers
# -------------------------------------------------------
def get_publix_weekly_ad(store_code, campaign_id, promotions):
    url = "https://services.publix.com/api/v4/savings"
    
    # Try to get the current date range from promotions if available
    current_promo = next((p for p in promotions if "Weekly Ad" in p.get("flyer_name", "")), None)
    
    params = {
        "smImg": "235",
        "enImg": "368",
        "fallbackImg": "false",
        "isMobile": "false",
        "page": "1",
        "pageSize": "0",
        "includePersonalizedDeals": "false",
        "languageID": "1",
        "getSavingType": "WeeklyAd",
        "isWeb": "true",
        "_": int(time.time() * 1000)  # Cache-busting timestamp
    }
    
    # Debug: Show what promotion dates we expect
    if current_promo:
        print(f"🔍 Expected Weekly Ad dates: {current_promo.get('saleStartDateString')} → {current_promo.get('saleEndDateString')}")
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.publix.com",
        "Referer": "https://www.publix.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/141.0.0.0 Safari/537.36"
        ),
        "PublixStore": store_code,
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    print(f"📡 Fetching weekly ad data for store {store_code} ...")
    print(f"🔍 Debug: Request URL with params: {url}?_={params['_']}")
    resp = requests.get(url, params=params, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    savings_list = data.get("Savings", [])
    
    # Debug: Show what date ranges we're actually getting
    if savings_list:
        first_item = savings_list[0]
        start_date = first_item.get("wa_startDate")
        end_date = first_item.get("wa_endDate")
        promo_type = first_item.get("wa_promotionType")
        print(f"🔍 Debug: First deal received - {promo_type}: {start_date} → {end_date}")
        print(f"🔍 Debug: Total deals received: {len(savings_list)}")
    if not savings_list:
        print("❌ No weekly ad data found.")
        return

    base_folder = Path("publix")
    base_folder.mkdir(exist_ok=True)

    def clean_id(flyer_id):
        """Replace dashes and other special characters with underscores"""
        if not flyer_id:
            return "unknown"
        return re.sub(r'[^a-zA-Z0-9]', '_', str(flyer_id))

    grouped = {}
    for item in savings_list:
        flyer_name = item.get("wa_promotionType") or "Unknown"
        promotion_type_id = item.get("wa_promotionTypeId")
        valid_from = format_date(item.get("wa_startDate"))
        valid_to = format_date(item.get("wa_endDate"))
        key = (flyer_name, promotion_type_id, valid_from, valid_to)
        grouped.setdefault(key, []).append(item)

    for (flyer_name, promotion_type_id, valid_from, valid_to), deals in grouped.items():
        flyer_folder = base_folder / f"Publix_{flyer_name}_{valid_from}_{valid_to}"
        flyer_folder.mkdir(exist_ok=True)
        csv_path = flyer_folder / f"{flyer_folder.name}.csv"
        
        print(f"\n🔍 Processing: {flyer_name} (TypeID: {promotion_type_id})")

        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)

            # Determine maximum number of categories in all deals
            max_cats = max(len(d.get("categories") or []) for d in deals)

            # Base header
            header = [
                "flyer_id", "flyer_name", "id", "name", "price", "description",
                "additional_deal_info", "valid_from", "valid_to", "image",
                "brand", "department", "isPrintable", "isClipped",
                "isSneakPeek", "recommendedRank"
            ]

            # Add dynamic category columns: cat1, cat2, ..., catN
            for i in range(1, max_cats + 1):
                header.append(f"cat{i}")

            writer.writerow(header)

            # Write deal rows
            for d in deals:

                # Get all categories for this item
                categories = d.get("categories") or []

                # Use enhanced image URL, fallback to normal
                image_url = d.get("enhancedImageUrl") or d.get("imageUrl") or ""
                local_image_path = ""

                if image_url:
                    flyer_id = d.get("waId") or d.get("id")
                    clean_flyer_id = clean_id(flyer_id)
                    item_id = clean_id(d.get("id"))
                    image_filename = f"{clean_flyer_id}_{item_id}.jpg"
                    local_image_path = flyer_folder / image_filename

                    max_retries = 3
                    retry_count = 0
                    download_success = False
                    
                    while retry_count < max_retries and not download_success:
                        try:
                            img_data = requests.get(image_url, timeout=30).content
                            with open(local_image_path, "wb") as img_file:
                                img_file.write(img_data)
                            
                            # Auto-crop whitespace from product image
                            cropped = auto_crop_whitespace(local_image_path)
                            local_image_path = image_filename
                            download_success = True
                            
                            if cropped:
                                print(f"📥 Downloaded & cropped: {image_filename}")
                            else:
                                print(f"📥 Downloaded: {image_filename}")
                        except Exception as e:
                            retry_count += 1
                            if retry_count < max_retries:
                                print(f"⚠️ Retry {retry_count}/{max_retries} for {d.get('title')}")
                            else:
                                print(f"❌ Failed to download image for {d.get('title')}: {e}")
                                local_image_path = ""

                # Base row data
                row = [
                    d.get("waId") or d.get("id"),
                    html.unescape(d.get("wa_promotionType") or ""),
                    d.get("id"),
                    html.unescape(d.get("title") or ""),
                    html.unescape(d.get("savings") or ""),
                    html.unescape(d.get("description") or ""),
                    html.unescape(d.get("additionalDealInfo") or ""),
                    valid_from,
                    valid_to,
                    local_image_path,
                    html.unescape(d.get("brand") or ""),
                    html.unescape(d.get("department") or ""),
                    d.get("isPrintable"),
                    d.get("isClipped"),
                    d.get("isSneakPeek"),
                    d.get("recommendedRank"),
                ]
                # Add dynamic categories (cat1 → catN)
                for i in range(max_cats):
                    row.append(categories[i] if i < len(categories) else "")
                categories = [html.unescape(c) for c in (d.get("categories") or [])]

                writer.writerow(row)

        print(f"✅ Saved {len(deals)} deals → {csv_path}")
        print(f"📊 Progress: Downloaded images for {flyer_name}")

        # Match promotion by typeID instead of name
        match = next(
            (p for p in promotions if p.get("type_id") == promotion_type_id), None
        )
        if match:
            print(f"✅ Matched promotion by TypeID {promotion_type_id}: {match['flyer_name']}")
            fetch_flyer_images(campaign_id, match["code"], store_code, flyer_folder, flyer_name, valid_from, valid_to)
        else:
            print(f"⚠️ No matching promotion found for TypeID {promotion_type_id} ('{flyer_name}')")


# -------------------------------------------------------
# MAIN PROGRAM
# -------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape Publix weekly ads and deals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (prompts for zip and store)
  python publix_weekly_ad.py
  
  # Command-line mode (for cron jobs)
  python publix_weekly_ad.py --zip 31008 --store "Publix at Gunn Battle"
        """
    )
    parser.add_argument('--zip', '--zip-code', dest='zip_code', 
                        help='ZIP code (e.g., 31008)')
    parser.add_argument('--store', '--store-name', dest='store_name',
                        help='Store name (e.g., "Publix at Gunn Battle")')
    
    args = parser.parse_args()
    
    # Use command-line args if provided, otherwise prompt interactively
    if args.zip_code and args.store_name:
        zip_code = args.zip_code.strip()
        store_name = args.store_name.strip()
        print(f"🔍 Using ZIP: {zip_code}, Store: {store_name}")
    else:
        zip_code = input("Enter ZIP code (e.g., 31008): ").strip()
        store_name = input("Enter store name (e.g., Publix at Gunn Battle): ").strip()

    store_code = get_publix_store(zip_code, store_name)
    if store_code:
        campaign_id = get_campaign_id()
        promotions = get_promotions(campaign_id, store_code)
        get_publix_weekly_ad(store_code, campaign_id, promotions)

    print("\n🎯 All flyers processed successfully!")