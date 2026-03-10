import requests
import csv
import os
from datetime import datetime
from pathlib import Path
import time
import fitz  # PyMuPDF
from PIL import Image
import json

# Food Lion-specific token
FOODLION_ACCESS_TOKEN = "9f64429683bfc0098acb124204462a56"


# ---------- Helper Functions ----------
def safe_filename(name):
    """Sanitize file/folder names."""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)


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
        stride = 20
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


def download_file(url, path, auto_crop=False):
    """Download a file from a URL and optionally auto-crop whitespace."""
    try:
        resp = requests.get(url, stream=True, timeout=20)
        if resp.status_code == 200:
            with open(path, "wb") as f:
                for chunk in resp.iter_content(1024):
                    f.write(chunk)

            # Auto-crop if requested and it's an image
            if auto_crop and str(path).lower().endswith(('.jpg', '.jpeg', '.png')):
                if auto_crop_whitespace(path):
                    return True  # Successfully cropped
            return False  # Downloaded but not cropped
        else:
            print(f"  ⚠️ Skipped (status {resp.status_code}): {url}")
            return False
    except Exception as e:
        print(f"  ❌ Failed to download {url}: {e}")
        return False


def convert_pdf_to_images(pdf_path, output_folder, base_name):
    """Convert PDF pages to JPG images (cross-platform using PyMuPDF), keeping under 500KB."""
    try:
        doc = fitz.open(pdf_path)
        print(f"  📄 Converting {len(doc)} pages from {pdf_path.name} to images...")
        for i, page in enumerate(doc, 1):
            out_path = output_folder / f"{base_name}_page_{i}.jpg"

            # Start with lower DPI to reduce file size
            dpi = 100
            quality = 80

            while dpi >= 50:  # Don't go below 50 DPI for readability
                pix = page.get_pixmap(dpi=dpi)

                # Save with quality setting
                pix.save(out_path, "JPEG", jpg_quality=quality)

                # Check file size
                file_size = out_path.stat().st_size

                if file_size <= 500 * 1024:  # 500KB
                    # Auto-crop whitespace from flyer page
                    if auto_crop_whitespace(out_path):
                        print(f"    ✅ Saved & cropped: {out_path.name} ({file_size // 1024}KB, DPI: {dpi}, Quality: {quality})")
                    else:
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
                # Still try to auto-crop
                if auto_crop_whitespace(out_path):
                    print(f"    ⚠️ Saved & cropped: {out_path.name} ({file_size // 1024}KB) - couldn't reduce below 500KB")
                else:
                    print(f"    ⚠️ Saved: {out_path.name} ({file_size // 1024}KB) - couldn't reduce below 500KB")

        doc.close()
    except Exception as e:
        print(f"  ⚠️ Error converting PDF to images: {e}")


# ---------- Food Lion Scraper ----------
def scrape_foodlion(store_code="2100", postal_code="28202"):
    """Scrape Food Lion weekly ad flyer and product data."""
    pub_url = "https://api.flipp.com/flyerkit/v4.0/publications/foodlion"
    pub_params = {
        "locale": "en-US",
        "access_token": FOODLION_ACCESS_TOKEN,
        "store_code": store_code,
        "postal_code": postal_code
    }

    print(f"\n🔍 Fetching available flyers for store: {store_code} (postal code: {postal_code}) ...")
    response = requests.get(pub_url, params=pub_params)
    if response.status_code != 200:
        print(response.text)
        print(f"❌ Failed to fetch publication list for store {store_code}")
        return []

    flyers = response.json()
    with open("flyers.json", "w", encoding="utf-8") as f:
        json.dump(flyers, f, ensure_ascii=False, indent=2)

    # Filter to only process weekly ads
    weekly_flyers = [f for f in flyers if f.get("external_display_name") == "Weekly Ad"]
    # Pick only the latest weekly ad by valid_from date
    if weekly_flyers:
        weekly_flyers = [max(weekly_flyers, key=lambda x: x["valid_from"])]
    print(f"✅ Found {len(flyers)} flyer(s), using latest weekly ad: valid_from={weekly_flyers[0]['valid_from'].split('T')[0] if weekly_flyers else 'N/A'}.\n")

    all_results = []
    for idx, f in enumerate(weekly_flyers, 1):
        flyer_id = f["id"]
        flyer_name = "WeeklyAd"
        flyer_type = f.get("flyer_type", "")
        valid_from = f["valid_from"].split("T")[0]
        valid_to = f["valid_to"].split("T")[0]
        pdf_url = f.get("pdf_url")

        print(f"📰 Flyer ID: {flyer_id}, Name: {flyer_name}, Type: {flyer_type}, Valid: {valid_from} to {valid_to}")

        # Format dates
        from_fmt = datetime.strptime(valid_from, "%Y-%m-%d").strftime("%m-%d-%y")
        to_fmt = datetime.strptime(valid_to, "%Y-%m-%d").strftime("%m-%d-%y")

        # Create base foodlion folder
        base_folder = Path("foodlion")
        base_folder.mkdir(exist_ok=True)

        # Create specific flyer folder inside foodlion/
        folder_name = f"FoodLion_{flyer_name}_{from_fmt}-{to_fmt}"
        folder_path = base_folder / folder_name
        folder_path.mkdir(exist_ok=True)

        flyer_base_name = f"FoodLion_{flyer_name}_{from_fmt}-{to_fmt}"

        print(f"📰 [{idx}/{len(weekly_flyers)}] Processing flyer: {flyer_base_name}")

        # Download flyer PDF
        if pdf_url:
            pdf_filename = f"{flyer_base_name}_flyer.pdf"
            pdf_path = folder_path / pdf_filename
            print("  ⬇️ Downloading flyer PDF...")
            #download_file(pdf_url, pdf_path)
            print("  ✅ Flyer PDF saved.")

            # Convert PDF → images
            convert_pdf_to_images(pdf_path, folder_path, flyer_base_name)

        # Get product data
        print("  🛒 Fetching product data...")
        prod_url = f"https://api.flipp.com/flyerkit/v4.0/publication/{flyer_id}/products"
        prod_params = {
            "display_type": "all",
            "locale": "en-US",
            "access_token": FOODLION_ACCESS_TOKEN
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
            price_str = " ".join(filter(None, [
                item.get("pre_price_text"),
                item.get("price_text"),
                item.get("post_price_text")
            ]))

            product_id = item.get("id")
            images = item.get("images", [])
            img_list = []

            for img_url in images:
                img_name = f"{flyer_id}_{product_id}.jpg"
                img_path = folder_path / img_name
                cropped = download_file(img_url, img_path, auto_crop=True)
                img_list.append(img_name)

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
    store_code = "2100"
    postal_code = "28202"
    print(f"🚀 Starting Food Lion scraper for store: {store_code} (postal code: {postal_code})\n")
    start_time = time.time()
    data = scrape_foodlion(store_code, postal_code)
    elapsed = time.time() - start_time
    print(f"\n⏱️ Done in {elapsed:.2f} seconds. {len(data)} total products collected.")
