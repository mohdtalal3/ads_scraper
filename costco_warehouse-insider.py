"""
Costco Weekly Warehouse Insider Scraper
Page: https://www.costco.com/c/-/weekly-warehouse-insider.html
Saves products with per-card valid date ranges.
No flyer image (not available on this page).
"""

import csv
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path
from PIL import Image


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
URL = "https://www.costco.com/c/-/weekly-warehouse-insider.html"
FLYER_NAME = "WeeklyWarehouseInsider"
STORE_NAME = "Costco"


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------
def safe_filename(name):
    """Sanitize file/folder names."""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)


def auto_crop_whitespace(image_path, threshold=250, margin=10):
    try:
        img = Image.open(image_path)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

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
            cropped_img.save(image_path, "JPEG", quality=90, optimize=True)
            img.close()
            cropped_img.close()
            return True

        img.close()
        return False
    except Exception as e:
        print(f"    ⚠️  Auto-crop failed: {e}")
        return False


def download_image(url, path, max_retries=3):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                with open(path, "wb") as f:
                    f.write(resp.content)
                auto_crop_whitespace(path)
                return True
            if attempt < max_retries - 1:
                time.sleep(1)
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(1)
    return False


def parse_date_range(text):
    """
    Extract start/end dates from strings like 'Valid 4/6/26 - 5/3/26'
    Returns (start_str, end_str) in MM-DD-YY format, or today if not found.
    """
    pattern = r"Valid\s+(\d{1,2}/\d{1,2}/\d{2})\s*-\s*(\d{1,2}/\d{1,2}/\d{2})"
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        try:
            start = datetime.strptime(m.group(1), "%m/%d/%y").strftime("%m-%d-%y")
            end = datetime.strptime(m.group(2), "%m/%d/%y").strftime("%m-%d-%y")
            return start, end
        except ValueError:
            pass
    today = datetime.now().strftime("%m-%d-%y")
    return today, today


def parse_card_dates(desc_text, page_from, page_to):
    """
    Extract per-card valid dates from description text.
    Handles:
      'Valid 4/13/26 - 4/19/26'   -> (04-13-26, 04-19-26)
      'Valid through 5/12/26'     -> (page_from, 05-12-26)
    Falls back to page-level dates.
    """
    # Range: Valid MM/DD/YY - MM/DD/YY
    m = re.search(
        r"Valid\s+(\d{1,2}/\d{1,2}/\d{2})\s*-\s*(\d{1,2}/\d{1,2}/\d{2})",
        desc_text, re.IGNORECASE
    )
    if m:
        try:
            start = datetime.strptime(m.group(1), "%m/%d/%y").strftime("%m-%d-%y")
            end = datetime.strptime(m.group(2), "%m/%d/%y").strftime("%m-%d-%y")
            return start, end
        except ValueError:
            pass
    # Single end date: Valid through MM/DD/YY
    m = re.search(
        r"Valid\s+through\s+(\d{1,2}/\d{1,2}/\d{2})",
        desc_text, re.IGNORECASE
    )
    if m:
        try:
            end = datetime.strptime(m.group(1), "%m/%d/%y").strftime("%m-%d-%y")
            return page_from, end
        except ValueError:
            pass
    return page_from, page_to


# --------------------------------------------------
# SCRAPER
# --------------------------------------------------
REQUEST_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "accept-encoding": "gzip, deflate, br",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def fetch_page_html(url, max_retries=3):
    """Fetch raw HTML for the warehouse insider page."""
    session = requests.Session()
    for attempt in range(max_retries):
        try:
            resp = session.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"   ⚠️  Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    return None


def scrape_warehouse_insider():
    products = []
    today = datetime.now().strftime("%m-%d-%y")
    valid_from = today
    valid_to = today

    print(f"🌐 Fetching {URL} ...")
    html = fetch_page_html(URL)
    if not html:
        print("❌ Failed to fetch page")
        return products, valid_from, valid_to

    soup = BeautifulSoup(html, "html.parser")

    # -- Parse page-level date range --
    page_text = soup.get_text(" ", strip=True)
    valid_from, valid_to = parse_date_range(page_text)
    print(f"📅 Page date range: {valid_from} → {valid_to}")

    # -- Find all AdBuilder product cards --
    cards = soup.find_all(attrs={"data-testid": "AdBuilder"})
    print(f"📦 Found {len(cards)} cards")

    for card in cards:
        try:
            # Product URL (optional — some cards have no link)
            link_el = card.find("a", attrs={"data-testid": "Link"})
            product_url = link_el.get("href", "") if link_el else ""
            if product_url and not product_url.startswith("http"):
                product_url = "https://www.costco.com" + product_url

            # Marketing typography blocks — first is name, second is description
            marketing_blocks = card.find_all(
                attrs={"data-testid": "Text_MarketingTypography"}
            )
            name = ""
            desc_text = ""
            if len(marketing_blocks) >= 1:
                name = marketing_blocks[0].get_text(strip=True)
            if len(marketing_blocks) >= 2:
                desc_text = marketing_blocks[1].get_text(" ", strip=True)

            name = name.replace(" 's", "'s").replace(" '", "'")
            if not name:
                continue
            # Skip non-product informational cards
            if name.upper() == "DID YOU KNOW?":
                continue

            # Item number — first number sequence from description "Item 1999335, 1999336"
            item_id = ""
            m_item = re.search(r"Item\s+([\d,\s]+)", desc_text, re.IGNORECASE)
            if m_item:
                # Take first item number only
                first_ids = m_item.group(1).strip().rstrip(",")
                item_id = first_ids.split(",")[0].strip()

            # Gather all price-related elements in document order by matching
            # any data-testid starting with "Text_prices", then join their text.
            price_els = card.find_all(
                attrs={"data-testid": re.compile(r"^Text_prices")}
            )
            price_parts = [el.get_text(strip=True) for el in price_els if el.get_text(strip=True)]
            price = " ".join(price_parts)
            discount = ""

            # Per-card valid dates (fall back to page-level)
            card_from, card_to = parse_card_dates(desc_text, valid_from, valid_to)

            # Product image — by Costco CDN domain, prefer 768w from srcset
            img_el = card.find("img", src=re.compile(r"costco-static\.com"))
            if not img_el:
                img_el = card.find(attrs={"data-testid": "ImageVideo_Image"})
            image_url = ""
            if img_el:
                srcset = img_el.get("srcSet") or img_el.get("srcset") or ""
                m_src = re.search(r'(https?://\S+)\s+768w', srcset)
                image_url = m_src.group(1) if m_src else (img_el.get("src") or "")

            products.append(
                {
                    "item_id": item_id,
                    "name": name,
                    "price": price,
                    "discount": discount,
                    "desc_text": desc_text,
                    "valid_from": card_from,
                    "valid_to": card_to,
                    "product_url": product_url,
                    "image_url": image_url,
                }
            )
            print(f"  ✅ {name[:50]} | {price} | {discount} | {card_from}–{card_to}")

        except Exception as e:
            print(f"  ⚠️  Error parsing card: {e}")

    return products, valid_from, valid_to


# --------------------------------------------------
# SAVE OUTPUT
# --------------------------------------------------
def save_results(products, valid_from, valid_to):
    if not products:
        print("⚠️  No products found")
        return

    folder_name = f"{STORE_NAME}_{FLYER_NAME}_{valid_from}_{valid_to}"
    output_dir = Path("costco") / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_file = output_dir / f"{folder_name}.csv"

    print(f"\n📁 Output folder: {output_dir}")
    print(f"📦 Processing {len(products)} products...")

    flyer_id = folder_name

    csv_rows = []
    for idx, product in enumerate(products, 1):
        item_id = product["item_id"] or f"item_{idx}"
        name = product["name"]
        price = product["price"]
        discount = product["discount"]
        image_url = product["image_url"]
        product_url = product["product_url"]
        card_from = product["valid_from"]
        card_to = product["valid_to"]

        # Download product image
        image_filename = ""
        if image_url:
            safe_item = re.sub(r"[^a-zA-Z0-9]", "_", item_id)
            image_filename = f"costco_{safe_item}.jpg"
            image_path = output_dir / image_filename
            if not image_path.exists():
                print(
                    f"   📥 [{idx}/{len(products)}] Downloading: {name[:45]}",
                    end="",
                    flush=True,
                )
                ok = download_image(image_url, image_path)
                print(" ✓" if ok else " ✗")
            else:
                print(f"   ⏭️  [{idx}/{len(products)}] Already exists: {name[:45]}")

        csv_rows.append(
            {
                "flyer_id": flyer_id,
                "flyer_name": FLYER_NAME,
                "id": item_id,
                "name": name,
                "price": price,
                "valid_from": card_from,
                "valid_to": card_to,
                "image": image_filename,
                "discount": discount,
                "product_url": product_url,
                "image_url": image_url,
            }
        )

    fieldnames = [
        "flyer_id",
        "flyer_name",
        "id",
        "name",
        "price",
        "valid_from",
        "valid_to",
        "image",
        "discount",
        "product_url",
        "image_url",
    ]

    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\n✅ Saved {len(csv_rows)} products → {csv_file}")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
if __name__ == "__main__":
    print("=" * 80)
    print("COSTCO WEEKLY WAREHOUSE INSIDER SCRAPER")
    print("=" * 80)
    print()

    products, valid_from, valid_to = scrape_warehouse_insider()

    if products:
        save_results(products, valid_from, valid_to)
    else:
        print("❌ No products scraped.")
