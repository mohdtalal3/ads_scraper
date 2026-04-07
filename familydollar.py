import requests
import csv
import os
from datetime import datetime
from pathlib import Path
import time
import fitz  # PyMuPDF

# Family Dollar-specific token
FAMILY_DOLLAR_ACCESS_TOKEN = "86671e3087ed1ff42de6ccd791b7fe3d"


# ---------- Helper Functions ----------
def safe_filename(name):
    """Sanitize file/folder names."""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)


def download_file(url, path):
    """Download a file from a URL."""
    try:
        resp = requests.get(url, stream=True, timeout=20)
        if resp.status_code == 200:
            with open(path, "wb") as f:
                for chunk in resp.iter_content(1024):
                    f.write(chunk)
        else:
            print(f"  ⚠️ Skipped (status {resp.status_code}): {url}")
    except Exception as e:
        print(f"  ❌ Failed to download {url}: {e}")



def convert_pdf_to_images(pdf_path, output_folder, base_name):
    """Convert PDF pages to JPG images (cross-platform using PyMuPDF), keeping under 500KB."""
    try:
        doc = fitz.open(pdf_path)
        print(f"  📄 Converting {len(doc)} pages from {pdf_path.name} to images...")
        for i, page in enumerate(doc, 1):
            out_path = output_folder / f"{base_name}_page_{i}.jpg"
            
            # Start with lower DPI to reduce file size
            dpi = 150
            quality = 85
            
            while dpi >= 50:  # Don't go below 50 DPI for readability
                pix = page.get_pixmap(dpi=dpi)
                
                # Save with quality setting
                pix.save(out_path, "JPEG", jpg_quality=quality)
                
                # Check file size
                file_size = out_path.stat().st_size
                
                if file_size <= 500 * 1024:  # 500KB
                    print(f"    ✅ Saved: {out_path.name} ({file_size // 1024}KB, DPI: {dpi}, Quality: {quality})")
                    break
                else:
                    # Try reducing quality first
                    if quality > 60:
                        quality -= 10
                    else:
                        # If quality is already low, reduce DPI
                        dpi -= 25
                        quality = 85  # Reset quality for new DPI
            else:
                # If we couldn't get under 500KB, keep the last attempt
                print(f"    ⚠️ Saved: {out_path.name} ({file_size // 1024}KB) - couldn't reduce below 500KB")
                
        doc.close()
    except Exception as e:
        print(f"  ⚠️ Error converting PDF to images: {e}")


# ---------- Family Dollar Scraper ----------
def scrape_family_dollar(store_code="19052"):
    """Scrape Family Dollar flyer and product data."""
    pub_url = "https://dam.flippenterprise.net/flyerkit/publications/familydollar"
    pub_params = {
        "locale": "en",
        "access_token": FAMILY_DOLLAR_ACCESS_TOKEN,
        "show_storefronts": "true",
        "store_code": store_code
    }

    print(f"\n🔍 Fetching available flyers for store: {store_code} ...")
    response = requests.get(pub_url, params=pub_params)
    if response.status_code != 200:
        print(f"❌ Failed to fetch publication list for store {store_code}")
        return []

    flyers = response.json()
    print(f"✅ Found {len(flyers)} flyer(s).\n")

    all_results = []

    for idx, f in enumerate(flyers, 1):
        flyer_id = f["id"]
        flyer_name = f.get("name", "Unknown").replace(" ", "")
        
        # Change "CurrentAd" to "WeeklyAd"
        if flyer_name == "CurrentAd":
            flyer_name = "WeeklyAd"
        
        valid_from = f["valid_from"].split("T")[0]
        valid_to = f["valid_to"].split("T")[0]
        pdf_url = f.get("pdf_url")
        print(f"📰 Flyer ID: {flyer_id}, Name: {flyer_name}, Valid: {valid_from} to {valid_to}")
        # Format dates
        from_fmt = datetime.strptime(valid_from, "%Y-%m-%d").strftime("%m-%d-%y")
        to_fmt = datetime.strptime(valid_to, "%Y-%m-%d").strftime("%m-%d-%y")

        # Folder and file base name - use actual flyer name instead of hardcoded "WeeklyAd"
        safe_flyer_name = safe_filename(flyer_name)
        
        # Create base family_dollar folder
        base_folder = Path("family_dollar")
        base_folder.mkdir(exist_ok=True)
        
        # Create specific flyer folder inside family_dollar/
        folder_name = f"FamilyDollar_{safe_flyer_name}_{from_fmt}-{to_fmt}"
        folder_path = base_folder / folder_name
        folder_path.mkdir(exist_ok=True)

        flyer_base_name = f"FamilyDollar_{safe_flyer_name}_{from_fmt}-{to_fmt}"

        print(f"📰 [{idx}/{len(flyers)}] Processing flyer: {flyer_base_name}")

        # # Download flyer PDF
        if pdf_url:
            pdf_filename = f"{flyer_base_name}_flyer.pdf"
            pdf_path = folder_path / pdf_filename
            print("  ⬇️ Downloading flyer PDF...")
            download_file(pdf_url, pdf_path)
            print("  ✅ Flyer PDF saved.")

            # Convert PDF → images
            convert_pdf_to_images(pdf_path, folder_path, flyer_base_name)

        # Get product data
        print("  🛒 Fetching product data...")
        prod_url = f"https://dam.flippenterprise.net/flyerkit/publication/{flyer_id}/products"
        prod_params = {
            "display_type": "all",
            "locale": "en",
            "access_token": FAMILY_DOLLAR_ACCESS_TOKEN
        }
        resp = requests.get(prod_url, params=prod_params)
        if resp.status_code != 200:
            print(f"  ⚠️ Failed to fetch products for flyer {flyer_id}")
            continue

        data = resp.json()
        print(f"  📦 {len(data)} products found. Downloading images...")

        # First pass: determine maximum number of categories
        max_categories = 0
        for item in data:
            categories = item.get("categories", [])
            max_categories = max(max_categories, len(categories))

        results = []
        for i, item in enumerate(data, 1):
            if not item.get("price_text"):
                continue

            price_str = " ".join(filter(None, [
                item.get("pre_price_text"),
                item.get("price_text"),
                item.get("post_price_text")
            ]))

            product_id = item.get("id")
            images = item.get("images", [])
            img_list = []

            # for img_url in images:
            #     img_name = f"{flyer_id}_{product_id}.jpg"
            #     img_path = folder_path / img_name
            #     download_file(img_url, img_path)
            #     img_list.append(img_name)

            # Get categories dynamically
            categories = item.get("categories", [])
            
            # Build result dictionary
            result = {
                "flyer_id": flyer_id,
                "flyer_name": flyer_name,
                "id": product_id,
                "name": item.get("name", ""),
                "price": price_str,
                "sale_story": item.get("sale_story", ""),
                "description": item.get("description", ""),
                "brand": item.get("brand", ""),
                "original_price": item.get("original_price", ""),
            }
            
            # Add category columns dynamically
            for cat_idx in range(max_categories):
                cat_key = f"category_{cat_idx + 1}"
                result[cat_key] = categories[cat_idx] if cat_idx < len(categories) else ""
            
            # Add remaining fields
            result["valid_from"] = valid_from
            result["valid_to"] = valid_to
            result["images"] = ", ".join(img_list)
            
            results.append(result)

            if i % 10 == 0:
                print(f"    🕓 Processed {i}/{len(data)} products...")

        # Save CSV
        if results:
            csv_filename = f"{flyer_base_name}_products.csv"
            csv_path = folder_path / csv_filename
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)
            print(f"  ✅ Saved CSV: {csv_filename}")

        print(f"✅ Finished flyer: {flyer_base_name}\n")
        all_results.extend(results)

    print(f"🎯 Scraping complete. Total products saved: {len(all_results)}")
    return all_results


# ---------- Main Entry ----------
if __name__ == "__main__":
    store_code = "4558"
    print(f"🚀 Starting Family Dollar scraper for store: {store_code}\n")
    start_time = time.time()
    data = scrape_family_dollar(store_code)
    elapsed = time.time() - start_time
    print(f"\n⏱️ Done in {elapsed:.2f} seconds. {len(data)} total products collected.")
