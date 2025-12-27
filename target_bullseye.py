import requests
import json
import csv
import time
import os
from pathlib import Path
from PIL import Image
import html

URL = "https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2"

HEADERS = {
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/143.0.0.0 Safari/537.36",
    "origin": "https://www.target.com",
    "referer": "https://www.target.com/",
}

BASE_PARAMS = {
    "category": "tr36l",
    "count": 24,
    "default_purchasability_filter": "true",
    "include_sponsored": "false",
    "include_review_summarization": "true",
    "platform": "desktop",
    "pricing_store_id": 770,
    "spellcheck": "true",
    "store_ids": "770,1506",
    "visitor_id": "019AE396EF14020190F79DB2954B55FD",
    "scheduled_delivery_store_id": 770,
    "zip": "79707",
    "key": "9f36aeafbe60771e321a7cc95a78140772ab3e96",
    "channel": "WEB",
    "include_dmc_dmr": "true",
    "page": "/c/tr36l",
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
def main():
    all_products = []
    metadata = None
    page = 0

    print(f"🚀 Starting Target Bullseye scraper for category: {BASE_PARAMS['category']}\n")

    while True:
        offset = page * BASE_PARAMS["count"]
        params = {**BASE_PARAMS, "offset": offset}

        print(f"[+] Fetching offset={offset}")

        # Retry logic for API request
        max_retries = 3
        data = None
        for attempt in range(max_retries):
            try:
                r = requests.get(URL, headers=HEADERS, params=params, timeout=30)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  ⚠️ Request failed, retrying... ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(2)
                else:
                    print(f"  ❌ Request failed after {max_retries} attempts: {e}")
                    raise
        
        if data is None:
            print("❌ Failed to fetch data, stopping.")
            break

        search = data["data"]["search"]

        # ✅ METADATA LOCATION (once)
        if metadata is None:
            metadata = search["search_response"]["metadata"]
            total_results = metadata["total_results"]
            print(f"✅ Total results: {total_results}\n")
            #total_results = 100  # Uncomment to limit for testing
            
        # ✅ PRODUCTS LOCATION
        products = search.get("products", [])

        if not products:
            print("❌ No products returned, stopping.")
            break

        for p in products:
            item = p.get("item", {})
            enrichment = item.get("enrichment", {})
            images = enrichment.get("images", {})
            product_desc = item.get("product_description", {})
            primary_brand = item.get("primary_brand", {})
            price = p.get("price", {})
            rating = (
                p.get("ratings_and_reviews", {})
                .get("statistics", {})
                .get("rating", {})
            )
            assets_3d = p.get("cgi_asset", {}).get("formats", {})

            all_products.append({
                # Primary identifiers
                "id": p.get("tcin"),
                "title": html.unescape(product_desc.get("title", "")),
                "brand": html.unescape(primary_brand.get("name", "")),
                "price": price.get("current_retail"),
                "price_formatted": price.get("formatted_current_price"),
                "price_handle": price.get("price_handle"),
                "image": "",  # Will be filled with downloaded filename
                
                # Description
                "bullets": " | ".join([html.unescape(b) for b in product_desc.get("bullet_descriptions", [])]),
                "soft_bullets": " | ".join([html.unescape(b) for b in product_desc.get("soft_bullets", {}).get("bullets", [])]),
                
                # Ratings & social proof
                "rating_avg": rating.get("average"),
                "rating_count": rating.get("count"),
                "social_proof": " | ".join([
                    cue.get("display")
                    for cue in p.get("desirability_cues", [])
                ]),
                
                # Images
                "primary_image_url": images.get("primary_image_url"),
                "alternate_images": " | ".join(images.get("alternate_image_urls", [])),
                
                # URLs
                "buy_url": enrichment.get("buy_url"),
                "brand_url": primary_brand.get("canonical_url"),
                
                # Additional identifiers
                "original_tcin": p.get("original_tcin"),
                "dpci": item.get("dpci"),
                
                # Classification
                "item_type": (
                    item.get("product_classification", {})
                        .get("item_type", {})
                        .get("name")
                ),
                "category_id": p.get("category", {}).get("category_id"),
                "parent_category_id": p.get("category", {}).get("parent_category_id"),
                "department_id": item.get("merchandise_classification", {}).get("department_id"),
                "class_id": item.get("merchandise_classification", {}).get("class_id"),
                
                # Pricing details
                "price_handle": price.get("price_handle"),
                
                # 3D assets
                "3d_glb": assets_3d.get("glb"),
                "3d_gltf": assets_3d.get("gltf"),
                "3d_usdz": assets_3d.get("usdz"),
                
                # Promotions
                "promotions": " | ".join([str(promo) for promo in p.get("promotions", [])]),
            })

        if len(all_products) >= total_results:
            break

        page += 1
        time.sleep(1)

    print(f"\n✅ Total products collected: {len(all_products)}")

    # -----------------------------
    # Create folder and save data
    # -----------------------------
    # Create base Target folder
    base_folder = Path("Target_Bullseye")
    base_folder.mkdir(exist_ok=True)

    # Create category-specific folder
    category_name = BASE_PARAMS["category"]
    folder_name = f"Target_Bullseye_{category_name}"
    folder_path = base_folder / folder_name
    folder_path.mkdir(exist_ok=True)

    print(f"\n📁 Saving to folder: {folder_path}")

    # Download images
    print(f"\n🖼️ Downloading {len(all_products)} product images...")
    downloaded_count = 0

    for idx, product in enumerate(all_products, 1):
        image_url = product.get("primary_image_url", "")
        
        if image_url and image_url.strip():
            # Create filename: Target_Bullseye_id_rank.png
            product_id = product.get("id", "")
            image_filename = f"Target_Bullseye_{product_id}_{idx}.png"
            img_path = folder_path / image_filename
            
            # Download and crop image
            download_image(image_url, img_path, auto_crop=True)
            product["image"] = image_filename
            downloaded_count += 1
            
            if idx % 50 == 0:
                print(f"  📥 Downloaded {idx}/{len(all_products)} images...")
        else:
            product["image"] = ""

    print(f"✅ Downloaded {downloaded_count} product images")

    # Save to CSV
    csv_filename = f"{folder_name}.csv"
    csv_path = folder_path / csv_filename

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        if all_products:
            writer = csv.DictWriter(f, fieldnames=all_products[0].keys())
            writer.writeheader()
            writer.writerows(all_products)

    print(f"💾 Saved CSV: {csv_filename}")

    # Save metadata JSON (commented out)
    # final_output = {
    #     "category": BASE_PARAMS["category"],
    #     "metadata": metadata,
    #     "products": all_products,
    # }
    # with open("target_tr36l_all_products_full.json", "w", encoding="utf-8") as f:
    #     json.dump(final_output, f, indent=2)

    print(f"\n🎯 Scraping complete!")


if __name__ == "__main__":
    main()
