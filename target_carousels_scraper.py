import json
import re
import requests
import csv
import time
import os
from datetime import datetime
from pathlib import Path
from PIL import Image
from typing import Dict, List, Any, Optional
import html
import ftfy



# -------------------------
# CONFIG
# -------------------------
STORE_ID = "1380"
BASE_OUTPUT_DIR = "Target_Carousels"


# -------------------------
# HELPER FUNCTIONS
# -------------------------
def auto_crop_whitespace(image_path, threshold=250, margin=10):
    """Crop white borders from an image using Pillow."""
    try:
        img = Image.open(image_path)
        
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        
        width, height = img.size
        pixels = img.load()
        
        min_x, min_y = width, height
        max_x, max_y = 0, 0
        
        stride = 10
        found_content = False
        
        for y in range(0, height, stride):
            for x in range(0, width, stride):
                pixel = pixels[x, y]
                r, g, b = pixel[0], pixel[1], pixel[2]
                
                if r < threshold or g < threshold or b < threshold:
                    found_content = True
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
        
        if not found_content or min_x >= max_x or min_y >= max_y:
            img.close()
            return False
        
        min_x = max(0, min_x - margin)
        min_y = max(0, min_y - margin)
        max_x = min(width, max_x + margin)
        max_y = min(height, max_y + margin)
        
        original_area = width * height
        cropped_area = (max_x - min_x) * (max_y - min_y)
        crop_pct = ((original_area - cropped_area) / original_area) * 100
        
        if crop_pct > 1:
            cropped_img = img.crop((min_x, min_y, max_x, max_y))
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
                
                if auto_crop:
                    auto_crop_whitespace(path)
                return True
            else:
                if attempt < max_retries - 1:
                    time.sleep(1)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
    return False


def clean_text(text):
    """Clean HTML entities and special characters from text."""
    if not text:
        return ""
    
    # Convert to string first
    text = str(text)
    
    # Decode HTML entities (like &#38; -> &)
    text = html.unescape(text)
    
    # Remove any remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Use ftfy library if available (best option for fixing encoding issues)
    text = ftfy.fix_text(text)
    # else:
    #     # Fallback: manual Unicode fixes
    #     replacements = {
    #         '\u2019': "'",  # Right single quotation mark
    #         '\u2018': "'",  # Left single quotation mark
    #         '\u201c': '"',  # Left double quotation mark
    #         '\u201d': '"',  # Right double quotation mark
    #         '\u2013': '-',  # En dash
    #         '\u2014': '-',  # Em dash
    #         '\u2026': '...',  # Horizontal ellipsis
    #     }
        
    #     for bad, good in replacements.items():
    #         text = text.replace(bad, good)
    
    # Normalize whitespace
    text = ' '.join(text.split())
    
    return text.strip()


def sanitize_folder_name(name):
    """Sanitize folder name by removing invalid characters."""
    if not name:
        return "unnamed"
    # Remove HTML entities
    name = clean_text(name)
    # Replace invalid characters with underscores
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Remove leading/trailing spaces and dots
    name = name.strip('. ')
    # Limit length
    if len(name) > 100:
        name = name[:100]
    return name or "unnamed"


# -------------------------
# HTML FETCHING
# -------------------------
def extract_page_code_from_url(url: str) -> str:
    """Extract the page code (e.g., 'o9rnh') from Target URL."""
    # Match pattern like /N-o9rnh, /a-xyz, /b-123, etc. (any single char followed by hyphen and code)
    match = re.search(r'/[a-zA-Z]-([a-zA-Z0-9]+)', url)
    if match:
        page_code = match.group(1)
        print(f"📝 Extracted page code: {page_code}")
        return page_code
    
    # Fallback to default
    print(f"⚠️ Could not extract page code from URL, using default: o9rnh")
    return "o9rnh"


def fetch_html_from_url(url: str) -> tuple[str, str]:
    """Fetch HTML content from a Target URL and return (html_content, page_code)."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    
    print(f"🌐 Fetching HTML from URL...")
    print(f"   {url}\n")
    
    # Extract page code from URL
    page_code = extract_page_code_from_url(url)
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        print(f"✅ Successfully fetched HTML (Status: {response.status_code})\n")
        
        return response.text, page_code
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching URL: {e}")
        raise


# -------------------------
# CAROUSEL EXTRACTION
# -------------------------
def extract_carousels_from_html(html_content: str) -> List[Dict[str, Any]]:
    """Extract carousel data from HTML content."""
    carousels = []
    
    tgt_match = re.search(r'__TGT_DATA__.*?value: deepFreeze\(JSON\.parse\("(.+?)"\)\)', html_content, re.DOTALL)
    if not tgt_match:
        print("Could not find __TGT_DATA__ in HTML")
        return carousels
    
    tgt_json_str = tgt_match.group(1).encode().decode('unicode_escape')
    tgt_data = json.loads(tgt_json_str)
    
    queries = tgt_data.get("__PRELOADED_QUERIES__", {}).get("queries", [])
    
    for query in queries:
        if len(query) >= 2 and isinstance(query[1], dict):
            query_data = query[1].get("data", {})
            slots = query_data.get("slots", {})
            
            for slot_id, slot_data in slots.items():
                content = slot_data.get("content", {})
                metadata = slot_data.get("metadata", {})
                components = metadata.get("components", [])
                
                if "container" in content:
                    carousel = extract_single_carousel(content, slot_id, components)
                    if carousel:
                        carousels.append(carousel)
                
                if "tabbed_containers" in content:
                    carousel = extract_tabbed_carousel(content, slot_id, components)
                    if carousel:
                        carousels.append(carousel)
    
    return carousels


def extract_single_carousel(content: Dict, slot_id: str, components: List) -> Optional[Dict]:
    """Extract carousel from single container."""
    container = content.get("container", {})
    key_value_pairs = container.get("keyValuePairs", {})
    context = key_value_pairs.get("context", "")
    
    placement_match = re.search(r'placementId,([^;,]+)', context)
    category_match = re.search(r'categoryId,([^;,]+)', context)
    
    placement_id = placement_match.group(1) if placement_match else None
    category_id = category_match.group(1) if category_match else None
    
    if not placement_id:
        return None
    
    return {
        "slot_id": slot_id,
        "headline": clean_text(content.get("custom_headline", "")),
        "type": "single_container",
        "slingshot_component_id": content.get("id"),
        "placement_id": placement_id,
        "category_id": category_id
    }


def extract_tabbed_carousel(content: Dict, slot_id: str, components: List) -> Optional[Dict]:
    """Extract carousel from tabbed containers."""
    tabs = []
    
    for tab in content.get("tabbed_containers", []):
        container = tab.get("container", {})
        key_value_pairs = container.get("keyValuePairs", {})
        context = key_value_pairs.get("context", "")
        
        placement_match = re.search(r'placementId,([^;,]+)', context)
        category_match = re.search(r'categoryId,([^;,]+)', context)
        
        placement_id = placement_match.group(1) if placement_match else None
        category_id = category_match.group(1) if category_match else None
        
        if not placement_id:
            continue
        
        tabs.append({
            "title": clean_text(tab.get("tab_title", "")),
            "placement_id": placement_id,
            "category_id": category_id
        })
    
    if not tabs:
        return None
    
    return {
        "slot_id": slot_id,
        "headline": clean_text(content.get("custom_headline", "")),
        "type": "tabbed_container",
        "slingshot_component_id": content.get("id"),
        "tabs": tabs
    }


# -------------------------
# API FETCHING
# -------------------------
def fetch_products(placement_id: str, category_id: Optional[str], slingshot_component_id: Optional[str] = None, page_code: str = "o9rnh", store_id: str = "1380", max_retries: int = 3) -> Dict[str, Any]:
    """Fetch products from Target API with retry logic."""
    url = "https://redsky.target.com/redsky_aggregations/v1/web/general_recommendations_placement_v1"
    
    params = {
        "channel": "WEB",
        "include_sponsored_recommendations": "false",
        "key": "9f36aeafbe60771e321a7cc95a78140772ab3e96",
        "page": f"/c/{page_code}",
        "placement_id": placement_id,
        "pricing_store_id": store_id,
        "purchasable_store_ids": f"{store_id},1461,2174,778,2129",
        "visitor_id": "019AE396EF14020190F79DB2954B55FD",
        "resolve_to_first_variation_child": "false",
        "platform": "desktop",
        "include_dmc_dmr": "false"
    }
    
    if category_id:
        params["category_id"] = category_id
    
    if slingshot_component_id:
        params["slingshot_component_id"] = slingshot_component_id
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.target.com/",
        "Origin": "https://www.target.com"
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                print(f"   ⚠️ API error (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"   ❌ Failed after {max_retries} attempts: {e}")
                return {}
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"   ⚠️ Error (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"   ❌ Failed after {max_retries} attempts: {e}")
                return {}
    
    return {}


# -------------------------
# DATA PROCESSING & CSV EXPORT
# -------------------------
def process_and_save_carousel(carousel: Dict, carousel_index: int, total_carousels: int, page_code: str, store_id: str):
    """Process a single carousel and save to CSV with images."""
    
    headline = clean_text(carousel.get("headline", f"carousel_{carousel_index}"))
    folder_name = sanitize_folder_name(headline)
    
    # Create folder structure
    carousel_dir = Path(BASE_OUTPUT_DIR) / folder_name
    images_dir = carousel_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    csv_file = carousel_dir / f"{folder_name}.csv"
    
    print(f"\n{'='*80}")
    print(f"📦 CAROUSEL {carousel_index}/{total_carousels}")
    print(f"{'='*80}")
    print(f"Headline: {headline}")
    print(f"Type: {carousel['type']}")
    print(f"Folder: {carousel_dir}")
    print(f"{'='*80}")
    
    all_products = []
    
    if carousel["type"] == "single_container":
        # Fetch products for single container
        print(f"\n🔍 Fetching products...")
        print(f"   Placement ID: {carousel['placement_id']}")
        print(f"   Category ID: {carousel.get('category_id', 'None')}")
        
        products_data = fetch_products(
            carousel["placement_id"],
            carousel.get("category_id"),
            carousel.get("slingshot_component_id"),
            page_code,
            store_id
        )
        
        products = products_data.get("data", {}).get("recommended_products", {}).get("products", [])
        print(f"   ✅ Found {len(products)} products")
        
        for product in products:
            all_products.append({
                "carousel_headline": headline,
                "carousel_type": "single_container",
                "tab_title": "",
                "product": product
            })
    
    elif carousel["type"] == "tabbed_container":
        # Fetch products for each tab
        tabs = carousel.get("tabs", [])
        print(f"\n📑 Processing {len(tabs)} tabs...")
        
        for tab_idx, tab in enumerate(tabs, 1):
            tab_title = clean_text(tab.get("title", ""))
            print(f"\n   Tab {tab_idx}/{len(tabs)}: {tab_title}")
            print(f"   Placement ID: {tab['placement_id']}")
            print(f"   Category ID: {tab.get('category_id', 'None')}")
            
            products_data = fetch_products(
                tab["placement_id"],
                tab.get("category_id"),
                carousel.get("slingshot_component_id"),
                page_code,
                store_id
            )
            
            products = products_data.get("data", {}).get("recommended_products", {}).get("products", [])
            print(f"   ✅ Found {len(products)} products")
            
            for product in products:
                all_products.append({
                    "carousel_headline": headline,
                    "carousel_type": "tabbed_container",
                    "tab_title": tab_title,
                    "product": product
                })
    
    # Save to CSV
    if all_products:
        print(f"\n💾 Saving to CSV...")
        save_to_csv(all_products, csv_file, images_dir, headline)
        print(f"\n✅ SUCCESS! Saved {len(all_products)} products")
        print(f"   📄 CSV: {csv_file.name}")
        print(f"   📁 Location: {carousel_dir}")
    else:
        print(f"\n⚠️ WARNING: No products found for this carousel")


def save_to_csv(products_data: List[Dict], csv_file: Path, images_dir: Path, carousel_headline: str):
    """Save products to CSV with image downloading."""
    
    csv_rows = []
    
    for idx, item in enumerate(products_data, 1):
        product = item["product"]
        
        # Extract product details
        tcin = product.get("tcin", "")
        item_data = product.get("item", {})
        title = clean_text(item_data.get("product_description", {}).get("title", ""))
        
        # Price information
        price_info = product.get("price", {})
        current_price = price_info.get("formatted_current_price", "")
        current_price_type = price_info.get("formatted_current_price_type", "")
        current_retail = price_info.get("current_retail", "")
        comparison_price = price_info.get("formatted_comparison_price", "")
        reg_retail = price_info.get("reg_retail", "")
        save_dollar = price_info.get("save_dollar", "")
        save_percent = price_info.get("save_percent", "")
        
        # Promotions
        promotions = product.get("promotions", [])
        promo_message = clean_text(promotions[0].get("plp_message", "")) if promotions else ""
        promotion_id = promotions[0].get("promotion_id", "") if promotions else ""
        promotion_class = promotions[0].get("promotion_class", "") if promotions else ""
        circle_offer = promotions[0].get("circle_offer", "") if promotions else ""
        
        # Ratings
        rating_stats = product.get("ratings_and_reviews", {}).get("statistics", {}).get("rating", {})
        rating = rating_stats.get("average", 0)
        rating_count = rating_stats.get("count", 0)
        
        # Desirability cues (social proofing, highly rated, etc.)
        desirability_cues = product.get("desirability_cues", [])
        desirability_display = clean_text(desirability_cues[0].get("display", "")) if desirability_cues else ""
        
        # Ornaments (New at Target, etc.)
        ornaments = product.get("ornaments", [])
        ornament_displays = ", ".join([clean_text(o.get("display", "")) for o in ornaments if o.get("display")])
        
        # Product classification
        product_class = item_data.get("product_classification", {})
        item_type_name = clean_text(product_class.get("item_type", {}).get("name", ""))
        item_type_code = product_class.get("item_type", {}).get("type", "")
        
        # Merchandise classification
        merch_class = item_data.get("merchandise_classification", {})
        class_id = merch_class.get("class_id", "")
        department_id = merch_class.get("department_id", "")
        
        # Other item details
        relationship_type = item_data.get("relationship_type_code", "")
        cart_add_on_threshold = item_data.get("cart_add_on_threshold", "")
        
        # Buy URL
        enrichment = item_data.get("enrichment", {})
        buy_url = enrichment.get("buy_url", "")
        
        # Images
        images_data = enrichment.get("images", {})
        primary_image_url = images_data.get("primary_image_url", "")
        
        # Download primary image
        image_filename = ""
        if primary_image_url and tcin:
            image_filename = f"{idx:03d}_{tcin}.png"
            image_path = images_dir / image_filename
            
            print(f"   📥 [{idx}/{len(products_data)}] Downloading: {tcin}", end="")
            # success = download_image(primary_image_url, image_path)
            # print(" ✓" if success else " ✗")
        
        # Prepare CSV row
        csv_row = {
            "rank": idx,
            "carousel_headline": carousel_headline,
            "carousel_type": item["carousel_type"],
            "category": item["tab_title"],
            "tcin": tcin,
            "title": title,
            "current_price": current_price,
            "current_retail": current_retail,
            "price_type": current_price_type,
            "regular_price": comparison_price,
            "reg_retail": reg_retail,
            "save_dollar": save_dollar,
            "save_percent": save_percent,
            "promotion_message": promo_message,
            "promotion_id": promotion_id,
            "promotion_class": promotion_class,
            "circle_offer": circle_offer,
            "rating": rating,
            "rating_count": rating_count,
            "desirability_cue": desirability_display,
            "ornaments": ornament_displays,
            "item_type": item_type_name,
            "item_type_code": item_type_code,
            "class_id": class_id,
            "department_id": department_id,
            "relationship_type": relationship_type,
            "cart_add_on_threshold": cart_add_on_threshold,
            "buy_url": buy_url,
            "image_filename": image_filename,
            "primary_image_url": primary_image_url
        }
        
        csv_rows.append(csv_row)
    
    # Write to CSV
    if csv_rows:
        fieldnames = [
            "rank", "carousel_headline", "carousel_type", "category",
            "tcin", "title", 
            "current_price", "current_retail", "price_type", "regular_price", "reg_retail",
            "save_dollar", "save_percent",
            "promotion_message", "promotion_id", "promotion_class", "circle_offer",
            "rating", "rating_count",
            "desirability_cue", "ornaments",
            "item_type", "item_type_code", "class_id", "department_id",
            "relationship_type", "cart_add_on_threshold",
            "buy_url", "image_filename", "primary_image_url"
        ]
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)


# -------------------------
# MAIN SCRAPER
# -------------------------
def scrape_all_carousels(html_content: str, page_code: str, store_id: str = "1380"):
    """Main function to scrape carousels and save to CSV."""
    
    # Extract carousels
    print("🔍 Extracting carousels from HTML...")
    carousels = extract_carousels_from_html(html_content)
    print(f"✅ Found {len(carousels)} valid carousels\n")
    
    if not carousels:
        print("⚠️ No carousels found. Exiting.")
        return
    
    # Create base output directory
    Path(BASE_OUTPUT_DIR).mkdir(exist_ok=True)
    
    # Process each carousel
    for i, carousel in enumerate(carousels, 1):
        try:
            process_and_save_carousel(carousel, i, len(carousels), page_code, store_id)
        except Exception as e:
            print(f"\n❌ ERROR processing carousel {i}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print("\n" + "=" * 80)
    print(f"✅ COMPLETE! Scraped {len(carousels)} carousels")
    print(f"📁 Data saved in: {BASE_OUTPUT_DIR}/")
    print("=" * 80)


if __name__ == "__main__":
    print("=" * 80)
    print("TARGET CAROUSEL SCRAPER")
    print("=" * 80)
    print()
    
    # Ask user for URL
    print("Enter the Target URL to scrape:")
    print("Example: https://www.target.com/c/what-s-new/-/N-o9rnh?lnk=C_TargetNewArrivals_WEB-435646_0")
    print()
    url = input("URL: ").strip()
    
    if not url:
        print("❌ No URL provided. Exiting.")
        exit(1)
    
    print()
    
    try:
        # Fetch HTML from URL and extract page code
        html_content, page_code = fetch_html_from_url(url)
        
        # Scrape carousels
        scrape_all_carousels(html_content, page_code, store_id=STORE_ID)
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
