import requests
import json
import time
import csv
import os
from datetime import datetime
from pathlib import Path
from PIL import Image

BASE_URL = "https://wag-dwa-api-prod.przone.net/api/wag/dwa"
STORE_NUMBER = 15196

HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": "https://www.walgreens.com",
    "referer": "https://www.walgreens.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/143.0.0.0 Safari/537.36"
    ),
    "accept-language": "en-US,en;q=0.9",
}

BASE_PAYLOAD = {
    "containerId": "dwa_container",
    "clippedCoupons": None,
    "search": None,
    "seachOfferCodes": [],
    "selectedOffer": "",
    "store": {"storeNumber": STORE_NUMBER},
    "circularId": None,
    "isMobileView": False,
    "customerid": "N",
    "personalizedOffers": "N",
    "selectedCategory": "",
    "viewMode": ""
}


# -------------------------------------------------------
# Helper: Format Date (e.g. 2025-12-27T00:00:00 → 12-27-25)
# -------------------------------------------------------
def format_date(date_str):
    """Convert ISO date to MM-DD-YY format"""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.split("T")[0], "%Y-%m-%d")
        return dt.strftime("%m-%d-%y")
    except Exception:
        return date_str


# -------------------------------------------------------
# Helper: Generate human-readable price text from pricing template
# -------------------------------------------------------
def generate_price_text(pricing_template_id, data_columns, pricing_templates_map):
    """
    Generate human-readable price text by parsing newNativeConfig and replacing datakeys.
    
    Args:
        pricing_template_id: The pricing template ID
        data_columns: Dictionary of data column values
        pricing_templates_map: Map of template IDs to template data (with newNativeConfig)
    
    Returns:
        Human-readable price text string
    """
    if not data_columns:
        return ""
    
    # Get the template config
    template = pricing_templates_map.get(pricing_template_id)
    if not template:
        return ""
    
    # Get the newNativeConfig which has the text structure with [datakey-FieldName] placeholders
    native_config = template.get("newNativeConfig", "")
    if not native_config:
        return ""
    
    # Parse the config and replace datakeys with actual values
    return parse_native_config_to_text(native_config, data_columns)


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
# Helper: Download image with auto-crop
# -------------------------------------------------------
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
                    print(f"  ⚠️ Failed to download image after {max_retries} attempts (status {resp.status_code}): {url}")
                return False
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Error downloading image, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(1)
            else:
                print(f"  ❌ Error downloading image after {max_retries} attempts: {e}")
            return False
    return False


def fetch_circular(max_retries=3):
    """Step 1: Fetch circular metadata"""
    url = f"{BASE_URL}/circular"
    for attempt in range(max_retries):
        try:
            r = requests.post(url, headers=HEADERS, json=BASE_PAYLOAD, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️ Failed to fetch circular, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                print(f"❌ Failed to fetch circular after {max_retries} attempts: {e}")
                raise


def extract_collections(circular_json):
    """Extract collectionId, name, index"""
    collections = []

    pages = circular_json.get("pages", [])
    for page in pages:
        if page.get("collectionId"):
            collections.append({
                "collectionId": page["collectionId"],
                "name": page.get("name"),
                "index": page.get("index"),
                "circularPageId": page.get("circularPageId"),
            })

    return collections


def fetch_collection_data(collection_id, max_retries=3):
    """Step 2: Fetch collection details"""
    url = f"{BASE_URL}/collection"
    params = {
        "collectionid": collection_id,
        "store": STORE_NUMBER
    }

    for attempt in range(max_retries):
        try:
            r = requests.post(
                url,
                headers=HEADERS,
                params=params,
                json=BASE_PAYLOAD,
                timeout=30
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Failed to fetch collection, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                print(f"  ❌ Failed to fetch collection after {max_retries} attempts: {e}")
                raise


def build_pricing_templates_map(collections_data):
    """Build a map of pricing template ID to template config from collections data"""
    templates_map = {}
    
    for collection_id, collection_info in collections_data.items():
        pricing_templates = collection_info.get("data", {}).get("pricingTemplates", [])
        for template in pricing_templates:
            template_id = template.get("pricingTemplateId")
            if template_id and template_id not in templates_map:
                templates_map[template_id] = template
    
    return templates_map


def parse_native_config_to_text(native_config, data_columns):
    """
    Parse newNativeConfig and replace [datakey-FieldName] with actual values.
    Preserves all text (like 'to', 'or', '$', etc.) and only replaces data placeholders.
    """
    if not native_config or not data_columns:
        return ""
    
    import re
    
    # Extract all text content from the native config
    # Remove all XML/JSX tags but keep the text and datakey placeholders
    text = native_config
    
    # Remove opening and closing tags but keep content
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Now replace [datakey-FieldName] with actual values
    def replace_datakey(match):
        field_name = match.group(1)
        value = data_columns.get(field_name, "")
        return str(value) if value else ""
    
    # Replace all [datakey-FieldName] patterns
    text = re.sub(r'\[datakey-([^\]]+)\]', replace_datakey, text)
    
    # Clean up extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def main():
    print("🚀 Starting Walgreens scraper for store: {}\n".format(STORE_NUMBER))
    
    print("📥 Fetching circular...")
    circular_data = fetch_circular()
    print("📦 Extracting collections...")
    collections = extract_collections(circular_data)
    collections=collections[:3]    
    with open("collections_index.json", "w", encoding="utf-8") as f:
        json.dump(collections, f, indent=2)

    print(f"✅ Found {len(collections)} collections\n")

    # Create base Walgreens folder
    base_folder = Path("Walgreens")
    base_folder.mkdir(exist_ok=True)

    all_collections_data = {}
    all_offers = []

    for i, col in enumerate(collections, start=1):
        cid = col["collectionId"]
        collection_name = col['name']
        collection_index = col.get('index', i)
        
        print(f"➡️  [{i}/{len(collections)}] Fetching collection: {collection_name}")

        try:
            data = fetch_collection_data(cid)
            all_collections_data[cid] = {
                "meta": col,
                "data": data
            }
            
            # Build pricing templates map from current collection data
            pricing_templates_map = build_pricing_templates_map(all_collections_data)
            
            # Process offers from this collection
            offers = data.get("offers", [])
            
            # First pass: determine maximum number of categories and all data column keys
            max_categories = 0
            all_data_column_keys = set()
            
            for offer in offers:
                categories = offer.get("categories", [])
                max_categories = max(max_categories, len(categories))
                
                # Collect all unique data column keys
                data_columns = offer.get("dataColumns", {})
                all_data_column_keys.update(data_columns.keys())
            
            # Convert to sorted list for consistent column ordering
            data_column_keys = sorted(all_data_column_keys)
            
            for offer in offers:
                # Extract dates
                start_date = offer.get("startDate", "")
                end_date = offer.get("endDate", "")
                valid_from = format_date(start_date)
                valid_to = format_date(end_date)
                
                # Build offer record with ALL fields
                offer_record = {
                    # Collection metadata
                    "flyer_id": cid,
                    "flyer_name": collection_name,
                    "flyer_index": collection_index,
                    
                    # Core offer fields
                    "offer_version_id": offer.get("offerVersionId", ""),
                    "offer_version_group_id": offer.get("offerVersionGroupId", ""),
                    "unique_id": offer.get("uniqueId", ""),
                    "offer_id": offer.get("offerId", ""),
                    # Pricing & description
                    "pricing_header": offer.get("pricingHeader", ""),
                    "price_text": "",
                    "pricing_body": offer.get("pricingBody", ""),
                    "pricing_template_id": offer.get("pricingTemplateId", ""),
                    "pricing_template_name": offer.get("pricingTemplateName", ""),
                    "page_number": offer.get("pageNumber", ""),
                    "position": offer.get("position", ""),
                    # Dates
                    "start_date": start_date,
                    "end_date": end_date,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "coupon_expiration_date": offer.get("couponExpirationDate", ""),
                    # Product info
                    "category": offer.get("category", ""),
                    "category_name": offer.get("categoryName", ""),
                    "ops": offer.get("ops", ""),
                    "wic": offer.get("wic", ""),
                    

                    

                    # Lists (convert to comma-separated)
                    "ops_list": ", ".join(str(x) for x in offer.get("opsList", []) if x),
                    "slugs": ", ".join(offer.get("slugs", [])),
                    "logos": ", ".join(offer.get("logos", [])),
                    "tags": ", ".join(offer.get("tags", [])),
                }
                
                # Add dynamic categories (category_1, category_2, etc.)
                categories = offer.get("categories", [])
                for cat_idx in range(max_categories):
                    cat_key = f"category_{cat_idx + 1}"
                    if cat_idx < len(categories):
                        cat = categories[cat_idx]
                        # Only use categoryName, not the category number
                        offer_record[cat_key] = cat.get('categoryName', '')
                    else:
                        offer_record[cat_key] = ""
                
                # Add all data columns dynamically
                data_columns = offer.get("dataColumns", {})
                for col_key in data_column_keys:
                    # Convert key to snake_case for consistency
                    snake_key = ''.join(['_' + c.lower() if c.isupper() else c for c in col_key]).lstrip('_')
                    offer_record[snake_key] = data_columns.get(col_key, "")
                
                # Generate human-readable price text from pricing template and data columns
                pricing_template_id = offer.get("pricingTemplateId", "")
                offer_record["price_text"] = generate_price_text(pricing_template_id, data_columns, pricing_templates_map)
                
                # Add image URL and placeholder at the end
                offer_record["image_url"] = offer.get("imageUrl", "")
                offer_record["image"] = ""
                
                all_offers.append(offer_record)
                
        except Exception as e:
            print(f"❌ Failed collection {cid}: {e}")

        time.sleep(0.3)  # polite delay

    # Save full JSON
    with open("collections_full_data.json", "w", encoding="utf-8") as f:
        json.dump(all_collections_data, f, indent=2)

    print(f"\n✅ Collected {len(all_offers)} total offers")
    
    if not all_offers:
        print("❌ No offers found.")
        return
    
    # Group offers by collection
    collections_map = {}
    for offer in all_offers:
        coll_name = offer["flyer_name"]
        if coll_name not in collections_map:
            collections_map[coll_name] = []
        collections_map[coll_name].append(offer)
    
    print(f"\n📁 Creating folders for {len(collections_map)} collections...\n")
    
    # Process each collection separately
    for collection_name, collection_offers in collections_map.items():
        # Determine date range for this collection
        start_dates = [o["start_date"] for o in collection_offers if o["start_date"]]
        end_dates = [o["end_date"] for o in collection_offers if o["end_date"]]
        
        if start_dates and end_dates:
            valid_from = format_date(min(start_dates))
            valid_to = format_date(max(end_dates))
        else:
            today = datetime.now().strftime("%m-%d-%y")
            valid_from = today
            valid_to = today
        
        # Clean collection name for folder
        safe_collection_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in collection_name)
        
        # Create folder structure: Walgreens/Walgreens_CollectionName_MM-DD-YY_MM-DD-YY/
        folder_name = f"Walgreens_{safe_collection_name}_{valid_from}_{valid_to}"
        folder_path = base_folder / folder_name
        folder_path.mkdir(exist_ok=True)
        
        print(f"📂 Processing collection: {collection_name}")
        print(f"   Folder: {folder_path}")
        print(f"   Offers: {len(collection_offers)}")
        
        # Download images for this collection
        downloaded_count = 0
        for idx, offer in enumerate(collection_offers, 1):
            image_url = offer.get("image_url", "")
            
            if image_url and image_url.strip():
                # Create filename: Walgreens_offerid_uniqueid.png
                offer_id = offer.get("offer_id", "")
                unique_id = offer.get("unique_id", "").replace("/", "_").replace("\\", "_")
                image_filename = f"Walgreens_{offer_id}_{unique_id}.png"
                img_path = folder_path / image_filename
                
                # Download and crop image
                print(f"   📥 Downloading {idx}/{len(collection_offers)}: {image_filename}")
                cropped = download_image(image_url, img_path)
                offer["image"] = image_filename
                downloaded_count += 1
            else:
                offer["image"] = ""
        
        print(f"   ✅ Downloaded {downloaded_count} images")
        
        # Save to CSV for this collection
        csv_filename = f"{folder_name}.csv"
        csv_path = folder_path / csv_filename
        
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            if collection_offers:
                writer = csv.DictWriter(f, fieldnames=collection_offers[0].keys())
                writer.writeheader()
                writer.writerows(collection_offers)
        
        print(f"   ✅ Saved CSV: {csv_filename}\n")
    
    print(f"🎯 All done! Processed {len(collections_map)} collections with {len(all_offers)} total offers")


if __name__ == "__main__":  
    main()
