import requests
import json
import csv
import time
import os
from datetime import datetime
from pathlib import Path
from PIL import Image

# -------------------------
# CONFIG
# -------------------------
STORE_ID = "770"
API_KEY = "9ba599525edd204c560a2182ae1cbfaa3eeddca5"

HEADERS = {
    "accept": "application/json",
    "user-agent": "Mozilla/5.0"
}


# -------------------------
# HELPER FUNCTIONS
# -------------------------
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

# -------------------------
# STEP 1: FETCH PROMOTIONS
# -------------------------
def fetch_promotions(store_id, max_retries=3):
    """Fetch available promotions for a store."""
    url = "https://api.target.com/weekly_ads/v1/store_promotions"
    params = {
        "key": API_KEY,
        "store_id": store_id
    }
    
    print(f"🔍 Fetching promotions for store {store_id}...")
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            
            promotions = response.json()
            print(f"✅ Found {len(promotions)} promotion(s)\n")
            
            return promotions
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️ Failed to fetch promotions, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                print(f"❌ Failed to fetch promotions after {max_retries} attempts: {e}")
                raise


# -------------------------
# STEP 2: FETCH PRODUCTS FOR PROMOTION
# -------------------------
def fetch_promotion_products(promotion_id, promotion_info, max_retries=3):
    """Fetch pages and products for a specific promotion."""
    url = f"https://api.target.com/weekly_ads/v1/promotions/{promotion_id}"
    params = {"key": API_KEY}
    
    print(f"  📥 Fetching products for promotion: {promotion_id}")
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Failed to fetch products, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                print(f"  ❌ Failed to fetch products after {max_retries} attempts: {e}")
                raise
    
    # Extract pages and products
    output = {
        "store_id": data.get("store_id"),
        "promotion_id": data.get("promotion_id"),
        "pages": {},
        "products": []
    }
    
    # Get promotion dates to use as fallback
    promo_sale_start = promotion_info.get("sale_start_date", "")
    promo_sale_end = promotion_info.get("sale_end_date", "")
    promo_start = promotion_info.get("promotion_start_date", "")
    promo_end = promotion_info.get("promotion_end_date", "")
    
    # Remove time portion from dates (keep only MM/DD/YYYY)
    if promo_sale_start:
        promo_sale_start = promo_sale_start.split(" ")[0]
    if promo_sale_end:
        promo_sale_end = promo_sale_end.split(" ")[0]
    if promo_start:
        promo_start = promo_start.split(" ")[0]
    if promo_end:
        promo_end = promo_end.split(" ")[0]
    
    product_order = 1
    for page_number, page in enumerate(data.get("pages", []), start=1):
        # Save page image URL
        output["pages"][str(page_number)] = page.get("image_url")
        
        # Extract products (hotspots) with all details
        for hotspot in page.get("hotspots", []):
            product = {
                # Most relevant fields first
                "rank": product_order,
                "flyer_id": hotspot.get("listing_id", ""),
                "flyer_name": "",  # Will be filled later
                "page": page_number,
                "title": hotspot.get("title", ""),
                "product_description": hotspot.get("product_description", ""),
                "price": hotspot.get("price", ""),
                "reg_price": hotspot.get("reg_price", ""),
                "price_qualifier": hotspot.get("price_qualifier", ""),
                "promotion_message": hotspot.get("promotion_message", ""),
                
                # Dates - always use promotion dates
                "sale_start_date": promo_sale_start,
                "sale_end_date": promo_sale_end,
                "valid_from": "",  # Will be formatted later
                "valid_to": "",  # Will be formatted later
                "promotion_start_date": promo_start,
                "promotion_end_date": promo_end,
                
                # Product identifiers
                "tcin": hotspot.get("tcin", ""),
                "parent_tcin": hotspot.get("parent_tcin", ""),
                "offer_id": hotspot.get("offer_id", ""),
                "offer_product_count": hotspot.get("offer_product_count", ""),
                "multi_offer": hotspot.get("multi_offer", ""),
                
                # Promotion metadata
                "promotion_code": "",  # Will be filled later
                "promotion_type": "",  # Will be filled later
                
                # URLs and links
                "image_url": hotspot.get("image_url", ""),
                "app_link": hotspot.get("app_link", ""),
                "external_link": hotspot.get("external_link", ""),
                "link_title": hotspot.get("link_title", ""),
                
                # Image placeholder
                "image": "",
                
                # Technical details (least relevant)
                "hotspot_id": hotspot.get("hotspot_id", ""),
                "coordinates": hotspot.get("coordinates", ""),
                "area_shape": hotspot.get("area_shape", ""),
                "listing_type": hotspot.get("listing_type", ""),
                "mobile_coupon_code": hotspot.get("mobile_coupon_code", ""),
                "fine_print": hotspot.get("fine_print", ""),
            }
            output["products"].append(product)
            product_order += 1
    
    print(f"  ✅ Pages: {len(output['pages'])}, Products: {len(output['products'])}")
    return output


# -------------------------
# STEP 3: SAVE TO CSV AND DOWNLOAD IMAGES
# -------------------------
def save_to_csv(promotion_info, products_data, output_folder):
    """Save products to CSV file and download images."""
    if not products_data["products"]:
        print("  ⚠️ No products to save")
        return
    
    # Format dates for folder name
    start_date = promotion_info.get("sale_start_date", "")
    end_date = promotion_info.get("sale_end_date", "")
    
    if start_date and end_date:
        # Handle Target's date format: "12/21/2025 12:00:00 AM"
        try:
            start_fmt = datetime.strptime(start_date.split(" ")[0], "%m/%d/%Y").strftime("%m-%d-%y")
            end_fmt = datetime.strptime(end_date.split(" ")[0], "%m/%d/%Y").strftime("%m-%d-%y")
        except:
            # Fallback to current date if parsing fails
            start_fmt = end_fmt = datetime.now().strftime("%m-%d-%y")
    else:
        start_fmt = end_fmt = datetime.now().strftime("%m-%d-%y")
    
    # Create folder structure
    promotion_title = promotion_info.get("title", "WeeklyAd").replace(" ", "_")
    folder_name = f"Target_{promotion_title}_{start_fmt}_{end_fmt}"
    folder_path = output_folder / folder_name
    folder_path.mkdir(exist_ok=True)
    
    # Add promotion metadata to each product
    for product in products_data["products"]:
        product["flyer_name"] = promotion_info.get("title", "")
        product["promotion_code"] = promotion_info.get("code", "")
        product["promotion_type"] = promotion_info.get("promotion_type", "")
        product["valid_from"] = start_fmt
        product["valid_to"] = end_fmt
    
    # Download flyer page images
    print(f"  📄 Downloading {len(products_data['pages'])} flyer page(s)...")
    for page_num, page_url in products_data["pages"].items():
        if page_url:
            page_filename = f"Target_{promotion_title}_page_{page_num}.png"
            page_path = folder_path / page_filename
            download_image(page_url, page_path, auto_crop=True)
    
    # Download product images
    print(f"  🖼️ Downloading product images...")
    downloaded_count = 0
    for idx, product in enumerate(products_data["products"], 1):
        image_url = product.get("image_url", "")
        
        if image_url and image_url.strip():
            # Create filename: Target_flyerid_rank.png
            flyer_id = product.get("flyer_id", "").replace("/", "_").replace("\\", "_")
            rank = product.get("rank", idx)
            image_filename = f"Target_{flyer_id}_{rank}.png"
            img_path = folder_path / image_filename
            
            # Download and crop image
            download_image(image_url, img_path, auto_crop=True)
            product["image"] = image_filename
            downloaded_count += 1
        else:
            product["image"] = ""
    
    print(f"  ✅ Downloaded {downloaded_count} product images")
    
    # Save CSV
    csv_filename = f"{folder_name}.csv"
    csv_path = folder_path / csv_filename
    
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        if products_data["products"]:
            writer = csv.DictWriter(f, fieldnames=products_data["products"][0].keys())
            writer.writeheader()
            writer.writerows(products_data["products"])
    
    print(f"  💾 Saved CSV: {csv_filename}\n")


# -------------------------
# MAIN
# -------------------------
def main():
    print(f"🚀 Starting Target scraper for store: {STORE_ID}\n")
    
    # Create base Target folder
    base_folder = Path("Target")
    base_folder.mkdir(exist_ok=True)
    
    # Step 1: Fetch all promotions
    promotions = fetch_promotions(STORE_ID)
    
    # Save promotions list
    # with open("target_promotions.json", "w") as f:
    #     json.dump(promotions, f, indent=2)
    
    # Step 2: Process each promotion
    all_products = []
    for idx, promo in enumerate(promotions, 1):
        promotion_id = promo.get("promotion_id")
        print(f"📰 [{idx}/{len(promotions)}] Processing: {promo.get('title', 'Unknown')}")
        
        # Fetch products for this promotion
        products_data = fetch_promotion_products(promotion_id, promo)
        
        # Save full JSON
        # json_filename = f"target_{promotion_id}_full.json"
        # with open(json_filename, "w") as f:
        #     json.dump(products_data, f, indent=2)
        
        # Save to CSV
        save_to_csv(promo, products_data, base_folder)
        
        all_products.extend(products_data["products"])
    
    print(f"🎯 Scraping complete. Total products: {len(all_products)}")


if __name__ == "__main__":
    main()
