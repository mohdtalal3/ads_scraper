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
# Step 2: Pagination over ALL product pages
# --------------------------------------------------
def fetch_all_products(build_id, max_retries=3):
    """Fetch all products with page-based pagination and retry logic."""
    BASE_URL = f"https://www.heb.com/_next/data/{build_id}/en/discover/all-sale.json"

    params = {
        "externalId": "all-sale",
        "sortBy": "PRICE",
        "sortDirection": "DESC",
    }

    api_headers = {
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/107.0.0.0 Safari/537.36"
        ),
        "accept": "application/json",
        "x-nextjs-data": "1",
        "referer": "https://www.heb.com/discover/all-sale",
    }

    all_products = []
    total_pages = None
    
    # First, fetch page 1 to get cursorList and determine total pages
    print(f"➡️ Fetching page 1 to determine total pages...")
    
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
                print(f"  ⚠️ Failed to fetch page 1, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                print(f"  ❌ Failed to fetch page 1 after {max_retries} attempts: {e}")
                return all_products

    if not page_data:
        return all_products

    # Extract data from first page
    page_props = page_data.get("pageProps", {})
    layout = page_props.get("layout", {})
    visual_components = layout.get("visualComponents", [])
    
    if visual_components:
        product_group = visual_components[0].get("productGroupDetails", {})
        records = product_group.get("records", [])
        cursor_list = product_group.get("cursorList", [])
        total = product_group.get("total", 0)
        
        # Determine total pages from cursorList length
        total_pages = len(cursor_list) if cursor_list else 1
        
        print(f"✅ Total pages to fetch: {total_pages} (Total products: {total})")
        
        # Add page number to each product
        for product in records:
            product["_page_number"] = 1
        
        all_products.extend(records)
    else:
        print("⚠️ No visual components found in response")
        return all_products
    return all_products
    
    # Now fetch remaining pages (2 through total_pages)
    for page_num in range(2, total_pages + 1):
        params["page"] = page_num
        
        print(f"➡️ Fetching page {page_num}/{total_pages}")

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
                    continue

        if not page_data:
            continue

        page_props = page_data.get("pageProps", {})
        layout = page_props.get("layout", {})
        visual_components = layout.get("visualComponents", [])
        
        if visual_components:
            product_group = visual_components[0].get("productGroupDetails", {})
            records = product_group.get("records", [])
            
            # Add page number to each product
            for product in records:
                product["_page_number"] = page_num
            
            all_products.extend(records)
        
        time.sleep(0.5)  # Small delay between pages

    return all_products

# --------------------------------------------------
# Step 3: Main execution
# --------------------------------------------------
def main():
    print("🚀 Starting HEB All Sale scraper\n")
    
    # Get Build ID
    print("🔍 Extracting Build ID...")
    build_id = get_build_id()
    print(f"✅ Build ID: {build_id}\n")
    
    # Fetch all products
    print("🛍️ Fetching all sale products...")
    all_products = fetch_all_products(build_id)
    print(f"\n✅ Total products collected: {len(all_products)}\n")
    
    if not all_products:
        print("❌ No products found")
        return
    
    # Create folder structure: HEB_All_Sale/HEB_All_Sale_Date/
    base_folder = Path("HEB_All_Sale")
    base_folder.mkdir(exist_ok=True)
    
    current_date = datetime.now().strftime("%m-%d-%y")
    folder_name = f"HEB_All_Sale_{current_date}"
    folder_path = base_folder / folder_name
    folder_path.mkdir(exist_ok=True)
    
    print(f"📁 Saving to folder: {folder_path}\n")
    
    # Process products
    processed_products = []
    
    overall_rank = 1
    for idx, product in enumerate(all_products, 1):
        page_number = product.get("_page_number", 0)
        
        # Extract product details
        product_id = product.get("id", "")
        store_id = product.get("storeId", "")
        display_name = product.get("displayName", "")
        decoded_display_name = product.get("decodedDisplayName", "")
        full_display_name = product.get("fullDisplayName", "")
        best_available = str(product.get("bestAvailable", ""))
        priced_by_weight = str(product.get("pricedByWeight", ""))
        in_assortment = str(product.get("inAssortment", ""))
        
        # Extract SKU information
        skus = product.get("SKUs", [])
        sku_id = ""
        upc = ""
        customer_friendly_size = ""
        online_list_price = ""
        online_sale_price = ""
        online_is_price_cut = ""
        curbside_list_price = ""
        curbside_sale_price = ""
        curbside_is_price_cut = ""
        is_on_sale = ""
        product_availability = ""
        
        if skus:
            sku = skus[0]  # Get first SKU
            sku_id = sku.get("id", "")
            upc = sku.get("twelveDigitUPC", "")
            customer_friendly_size = sku.get("customerFriendlySize", "")
            product_availability = ", ".join(sku.get("productAvailability", []))
            
            # Extract pricing from contextPrices
            context_prices = sku.get("contextPrices", [])
            for price_context in context_prices:
                if price_context.get("context") == "ONLINE":
                    is_on_sale = str(price_context.get("isOnSale", ""))
                    online_is_price_cut = str(price_context.get("isPriceCut", ""))
                    list_price = price_context.get("listPrice", {})
                    sale_price = price_context.get("salePrice", {})
                    online_list_price = list_price.get("formattedAmount", "")
                    online_sale_price = sale_price.get("formattedAmount", "")
                elif price_context.get("context") == "CURBSIDE":
                    curbside_is_price_cut = str(price_context.get("isPriceCut", ""))
                    list_price = price_context.get("listPrice", {})
                    sale_price = price_context.get("salePrice", {})
                    curbside_list_price = list_price.get("formattedAmount", "")
                    curbside_sale_price = sale_price.get("formattedAmount", "")
        
        # Extract image URL (first image from productImageUrls)
        product_images = product.get("productImageUrls", [])
        image_url = product_images[0].get("url", "") if product_images else ""
        
        # Extract category hierarchy
        full_category_hierarchy = product.get("fullCategoryHierarchy", "")
        
        # Extract brand
        brand_info = product.get("brand", {})
        brand_name = brand_info.get("name", "")
        is_own_brand = str(brand_info.get("isOwnBrand", ""))
        
        # Extract product category
        product_category = product.get("productCategory", {})
        category_name = product_category.get("name", "")
        
        # Extract product location
        product_location = product.get("productLocation", {})
        location = product_location.get("location", "")
        
        # Extract inventory
        inventory = product.get("inventory", {})
        inventory_state = inventory.get("inventoryState", "")
        
        # Extract other flags
        on_ad = str(product.get("onAd", ""))
        is_new = str(product.get("isNew", ""))
        show_coupon_flag = str(product.get("showCouponFlag", ""))
        
        # Extract product page URL
        product_page_url = product.get("productPageURL", "")
        
        # Extract order quantities
        min_order_qty = product.get("minimumOrderQuantity", "")
        max_order_qty = product.get("maximumOrderQuantity", "")
        
        processed_product = {
            # Primary identifiers
            "rank": overall_rank,
            "page_number": page_number,
            "product_id": product_id,
            "store_id": store_id,
            "sku_id": sku_id,
            "upc": upc,
            
            # Product names
            "display_name": html.unescape(display_name) if display_name else "",
            "decoded_display_name": html.unescape(decoded_display_name) if decoded_display_name else "",
            "full_display_name": html.unescape(full_display_name) if full_display_name else "",
            
            # Pricing - Online
            "online_list_price": online_list_price,
            "online_sale_price": online_sale_price,
            "is_on_sale": is_on_sale,
            "online_is_price_cut": online_is_price_cut,
            
            # Pricing - Curbside
            "curbside_list_price": curbside_list_price,
            "curbside_sale_price": curbside_sale_price,
            "curbside_is_price_cut": curbside_is_price_cut,
            
            # Product details
            "customer_friendly_size": customer_friendly_size,
            "brand_name": brand_name,
            "is_own_brand": is_own_brand,
            "category_name": category_name,
            "full_category_hierarchy": full_category_hierarchy,
            "location": location,
            "best_available": best_available,
            "priced_by_weight": priced_by_weight,
            "in_assortment": in_assortment,
            
            # Availability & Inventory
            "product_availability": product_availability,
            "inventory_state": inventory_state,
            
            # Flags
            "on_ad": on_ad,
            "is_new": is_new,
            "show_coupon_flag": show_coupon_flag,
            
            # Order quantities
            "min_order_qty": min_order_qty,
            "max_order_qty": max_order_qty,
            
            # URLs
            "product_page_url": product_page_url,
            "image_url": image_url,
            
            # Images
            "image": "",  # Will be filled with downloaded filename
            
            # Additional fields
            "is_sponsored": product.get("isSponsored", False),
            "is_available": product.get("isAvailable", False),
        }
        
        processed_products.append(processed_product)
        overall_rank += 1
    
    # Download product images
    print(f"🖼️ Downloading {len(processed_products)} product images...")
    downloaded_count = 0
    
    for idx, product in enumerate(processed_products, 1):
        image_url = product.get("image_url", "")
        
        if image_url and image_url.strip():
            sku_id = product.get("sku_id", idx)
            rank = product.get("rank", idx)
            image_filename = f"HEB_Product_{sku_id}_{rank}.png"
            img_path = folder_path / image_filename
            
            # Download and crop image
            download_image(image_url, img_path, auto_crop=True)
            product["image"] = image_filename
            downloaded_count += 1
            
            if idx % 50 == 0:
                print(f"  📥 Downloaded {idx}/{len(processed_products)} images...")
        else:
            product["image"] = ""
    
    print(f"✅ Downloaded {downloaded_count} product images\n")
    
    # Save to CSV
    csv_filename = f"{folder_name}.csv"
    csv_path = folder_path / csv_filename
    
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=processed_products[0].keys())
        writer.writeheader()
        writer.writerows(processed_products)
    
    print(f"💾 Saved CSV: {csv_filename}\n")
    
    # Save JSON (commented out)
    # json_filename = f"{folder_name}.json"
    # json_path = folder_path / json_filename
    # with open(json_path, "w", encoding="utf-8") as f:
    #     json.dump(all_products, f, indent=2, ensure_ascii=False)
    # print(f"💾 Saved JSON: {json_filename}\n")
    
    print(f"\n🎯 HEB All Sale scraping complete!")


if __name__ == "__main__":
    main()
