import requests
import csv
import os
import json
import re
from datetime import datetime
from pathlib import Path

HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "Origin": "https://platform.liquidus.net",
    "Referer": "https://platform.liquidus.net/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
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
        "isWebsite": "true"
    }

    print(f"📍 Searching for stores near ZIP {zip_code} ...")
    response = requests.get(url, params=params)
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
            # Remove '#' if present and ensure leading zero
            if store_code:
                store_code = str(store_code).lstrip('#')
                # Add leading zero if not already 5 digits
                if len(store_code) == 4:
                    store_code = '0' + store_code
            print(f"✅ Found store: {name} (Code: {store_code})")
            return store_code

    print("⚠️ Store not found for that name. Try again.")
    return None


# -------------------------------------------------------
# Step 2: Get Campaign ID (needed for flyer images)
# -------------------------------------------------------
def get_campaign_id():
    url = "https://graphql-cdn-slplatform.liquidus.net/"
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
    response = requests.post(url, json=payload)
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
    url = "https://graphql-cdn-slplatform.liquidus.net/"
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
            }
          }
        }
        """
    }

    resp = requests.post(url, json=payload)
    resp.raise_for_status()
    promos = resp.json()["data"]["promotions"]["promos"]

    enriched = []
    print("\n✅ Found Promotions:\n")
    for p in promos:
        flyer_name = p.get("title") or "Unknown"
        start = p.get("saleStartDateString")
        end = p.get("saleEndDateString")
        print(f"📰 {flyer_name} | {p['code']} | {start} → {end}")
        enriched.append({
            "flyer_name": flyer_name,
            "code": p["code"],
            "saleStartDateString": start,
            "saleEndDateString": end
        })
    return enriched


# -------------------------------------------------------
# Step 4: Fetch Flyer Page Images
# -------------------------------------------------------
def fetch_flyer_images(campaign_id, promo_code, store_code, folder_path, flyer_name, valid_from, valid_to):
    url = "https://graphql-cdn-slplatform.liquidus.net/"
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
    pages = resp.json().get("data", {}).get("promotion", {}).get("pages", [])
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
    }

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
    }

    print(f"📡 Fetching weekly ad data for store {store_code} ...")
    resp = requests.get(url, params=params, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    savings_list = data.get("Savings", [])
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
        valid_from = format_date(item.get("wa_startDate"))
        valid_to = format_date(item.get("wa_endDate"))
        key = (flyer_name, valid_from, valid_to)
        grouped.setdefault(key, []).append(item)

    for (flyer_name, valid_from, valid_to), deals in grouped.items():
        flyer_folder = base_folder / f"Publix_{flyer_name}_{valid_from}_{valid_to}"
        flyer_folder.mkdir(exist_ok=True)
        csv_path = flyer_folder / f"{flyer_folder.name}.csv"

        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                "flyer_id", "flyer_name", "id", "name", "price", "description", 
                "additional_deal_info", "valid_from", "valid_to", "image"
            ])
            for d in deals:
                # Use enhanced image URL if available, otherwise use regular image URL
                image_url = d.get("enhancedImageUrl") or d.get("imageUrl") or ""
                
                # Download the image if URL exists
                local_image_path = ""
                if image_url:
                    flyer_id = d.get("waId") or d.get("id")
                    clean_flyer_id = clean_id(flyer_id)
                    item_id = clean_id(d.get("id"))
                    
                    # Create filename: flyerid_itemid.jpg
                    image_filename = f"{clean_flyer_id}_{item_id}.jpg"
                    local_image_path = flyer_folder / image_filename
                    
                    # Retry mechanism for image download
                    max_retries = 3
                    retry_count = 0
                    download_success = False
                    
                    while retry_count < max_retries and not download_success:
                        try:
                            img_data = requests.get(image_url, timeout=30).content
                            with open(local_image_path, "wb") as img_file:
                                img_file.write(img_data)
                            local_image_path = image_filename  # Store just filename in CSV
                            download_success = True
                            print(f"📥 Downloaded: {image_filename}")
                        except Exception as e:
                            retry_count += 1
                            if retry_count < max_retries:
                                print(f"⚠️ Retry {retry_count}/{max_retries} for {d.get('title')}")
                            else:
                                print(f"❌ Failed to download image for {d.get('title')} after {max_retries} attempts: {e}")
                                local_image_path = ""
                
                writer.writerow([
                    d.get("waId") or d.get("id"),
                    d.get("wa_promotionType"),
                    d.get("id"),
                    d.get("title"),
                    d.get("savings"),
                    d.get("description") or "",
                    d.get("additionalDealInfo") or "",
                    valid_from,
                    valid_to,
                    local_image_path,
                ])

        print(f"✅ Saved {len(deals)} deals → {csv_path}")
        print(f"📊 Progress: Downloaded images for {flyer_name}")

        # Match promotion by title name (e.g. "Weekly Ad" or "Extra Savings")
        match = next(
            (p for p in promotions if flyer_name.lower() in p["flyer_name"].lower()), None
        )
        if match:
            fetch_flyer_images(campaign_id, match["code"], store_code, flyer_folder, flyer_name, valid_from, valid_to)
        else:
            print(f"⚠️ No matching promotion found for '{flyer_name}'")


# -------------------------------------------------------
# MAIN PROGRAM
# -------------------------------------------------------
if __name__ == "__main__":
    zip_code = input("Enter ZIP code (e.g., 31008): ").strip()
    store_name = input("Enter store name (e.g., Publix at Gunn Battle): ").strip()

    store_code = get_publix_store(zip_code, store_name)
    if store_code:
        campaign_id = get_campaign_id()
        promotions = get_promotions(campaign_id, store_code)
        get_publix_weekly_ad(store_code, campaign_id, promotions)

    print("\n🎯 All flyers processed successfully!")
