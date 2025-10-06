import requests
import csv
import os
from datetime import datetime
from pathlib import Path
import time

# Aldi-specific token
ALDI_ACCESS_TOKEN = "29d9bfdcf546dc601c10c64ed1e932f5"


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


def download_flyer_images(sfml_url, output_folder, flyer_base_name):
    """Download flyer page images."""
    try:
        data = requests.get(sfml_url).json()
        pages = data.get("flyer", {}).get("pages", [])
        print(f"  📄 Downloading {len(pages)} flyer page images...")
        for i, page in enumerate(pages, 1):
            img_url = page.get("image_url")
            if not img_url:
                continue
            img_name = f"{flyer_base_name}_page_{i}.jpg"
            download_file(img_url, os.path.join(output_folder, img_name))
            print(f"    ✅ Page {i} saved")
    except Exception as e:
        print(f"⚠️ Error fetching flyer images: {e}")


# ---------- Aldi Scraper ----------
def scrape_aldi(store_code="440-018"):
    """Scrape Aldi flyer and product data."""
    pub_url = "https://dam.flippenterprise.net/flyerkit/publications/aldi"
    pub_params = {
        "locale": "en",
        "access_token": ALDI_ACCESS_TOKEN,
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
        valid_from = f["valid_from"].split("T")[0]
        valid_to = f["valid_to"].split("T")[0]
        pdf_url = f.get("pdf_url")
        sfml_url = f.get("sfml_url")

        # Format dates
        from_fmt = datetime.strptime(valid_from, "%Y-%m-%d").strftime("%m-%d-%y")
        to_fmt = datetime.strptime(valid_to, "%Y-%m-%d").strftime("%m-%d-%y")

        # Folder and file base name
        flyer_base_name = f"Aldi_{flyer_name}_{from_fmt}_{to_fmt}"
        folder_path = Path(flyer_base_name)
        folder_path.mkdir(exist_ok=True)

        print(f"📰 [{idx}/{len(flyers)}] Processing flyer: {flyer_base_name}")

        # Download flyer PDF
        if pdf_url:
            pdf_filename = f"{flyer_base_name}_flyer.pdf"
            pdf_path = folder_path / pdf_filename
            print("  ⬇️ Downloading flyer PDF...")
            download_file(pdf_url, pdf_path)
            print("  ✅ Flyer PDF saved.")

        # Download full flyer page images
        if sfml_url:
            download_flyer_images(sfml_url, folder_path, flyer_base_name)

        # Get product data
        print("  🛒 Fetching product data...")
        prod_url = f"https://dam.flippenterprise.net/flyerkit/publication/{flyer_id}/products"
        prod_params = {
            "display_type": "all",
            "locale": "en",
            "access_token": ALDI_ACCESS_TOKEN
        }
        resp = requests.get(prod_url, params=prod_params)
        if resp.status_code != 200:
            print(f"  ⚠️ Failed to fetch products for flyer {flyer_id}")
            continue

        data = resp.json()
        print(f"  📦 {len(data)} products found. Downloading images...")

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

            for img_url in images:
                img_name = f"{flyer_id}_{product_id}.jpg"
                img_path = folder_path / img_name
                download_file(img_url, img_path)
                img_list.append(img_name)

            results.append({
                "flyer_id": flyer_id,
                "flyer_name": flyer_name,
                "id": product_id,
                "name": item.get("name"),
                "price": price_str,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "images": ", ".join(img_list)
            })

            if i % 10 == 0:
                print(f"    🕓 Processed {i}/{len(data)} products...")

        # Save CSV
        if results:
            csv_filename = f"{flyer_base_name}_products.csv"
            csv_path = folder_path / csv_filename
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
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
    store_code = "440-018"
    print(f"🚀 Starting Aldi scraper for store: {store_code}\n")
    start_time = time.time()
    data = scrape_aldi(store_code)
    elapsed = time.time() - start_time
    print(f"\n⏱️ Done in {elapsed:.2f} seconds. {len(data)} total products collected.")
