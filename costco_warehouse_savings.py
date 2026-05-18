"""
Costco Warehouse Savings Scraper
Page: https://www.costco.com/savings/warehouse-savings.html
Saves products organized by category with valid date range.
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
URL = "https://www.costco.com/o/-/warehouse-savings"
FLYER_NAME = "WarehouseSavings"
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
    """Fetch raw HTML for the warehouse savings page."""
    session = requests.Session()
    for attempt in range(max_retries):
        try:
            resp = session.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.content.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"   ⚠️  Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    return None


def scrape_warehouse_savings():
    products = []
    valid_from = datetime.now().strftime("%m-%d-%y")
    valid_to = datetime.now().strftime("%m-%d-%y")

    print(f"🌐 Fetching {URL} ...")
    html = fetch_page_html(URL)
    if not html:
        print("❌ Failed to fetch page")
        return products, valid_from, valid_to

    soup = BeautifulSoup(html, "html.parser")

    # -- Parse date range from page text --
    page_text = soup.get_text(" ", strip=True)
    valid_from, valid_to = parse_date_range(page_text)
    print(f"📅 Date range: {valid_from} → {valid_to}")

    # -- Extract categories and products --
    category_sections = soup.find_all(attrs={"data-testid": re.compile(r"^coupon-set-")})
    print(f"📂 Found {len(category_sections)} categories")

    for section in category_sections:
        # Category name
        heading = section.find("h2")
        category = heading.get_text(strip=True) if heading else "Unknown"
        print(f"\n  📁 Category: {category}")

        # Product cards — direct children of the outer grid container only
        grid_container = section.find(attrs={"data-testid": "Grid"})
        if grid_container:
            cards = grid_container.find_all(attrs={"data-testid": "Grid"}, recursive=False)
        else:
            cards = []
        print(f"     {len(cards)} items found")

        for card in cards:
            try:
                # Product name — text of the product link (its only child is the name)
                link_el_name = card.find("a", attrs={"data-testid": "Link"})
                name = link_el_name.get_text(strip=True) if link_el_name else ""
                name = name.replace(" 's", "'s").replace(" '", "'")

                if not name:
                    continue

                # Product URL
                link_el = card.find("a", attrs={"data-testid": "Link"})
                product_url = link_el["href"] if link_el and link_el.get("href") else ""
                if product_url and not product_url.startswith("http"):
                    product_url = "https://www.costco.com" + product_url

                # Item number — id attribute of the description div
                desc_div = card.find(attrs={"id": re.compile(r"-item-description$")})
                item_id = ""
                if desc_div:
                    raw_id = desc_div.get("id", "")
                    item_id = raw_id.replace("-item-description", "")

                # Price / Discount extraction:
                # - "Save $300 - $500"  → price="",        discount="Save $300 - $500"
                # - "$13.99 After $3 OFF" → price="$13.99", discount="After $3 OFF"
                # - no price element    → price="",         discount=""
                prepend_el = card.find(
                    attrs={"data-testid": "Text_prices_and_percentages_prepend_text"}
                )
                prepend = prepend_el.get_text(strip=True) if prepend_el else ""

                all_price_els = card.find_all(
                    attrs={"data-testid": "Text_prices_and_percentages_prices"}
                )
                prices = [el.get_text(strip=True) for el in all_price_els]
                hyphen_el = card.find(
                    attrs={"data-testid": "Text_prices_and_percentages_hyphen"}
                )
                price_range = (" - " if hyphen_el else "").join(prices)

                append_el = card.find(
                    attrs={"data-testid": "Text_prices_and_percentages_append_text"}
                )
                append = append_el.get_text(strip=True) if append_el else ""

                if prepend.lower() == "save":
                    # Range is a savings amount, not a sale price
                    price_text = ""
                    discount = f"Save {price_range}".strip()
                else:
                    price_text = price_range
                    discount = append

                # Availability — handles both "Warehouse & Online" (multi-child)
                # and "Online Only" / "Warehouse" (single leaf) structures
                AVAIL_PATTERN = re.compile(
                    r"^(Warehouse\s*&\s*Online|Online\s*&\s*Warehouse"
                    r"|Warehouse\s+Only|Online\s+Only|Warehouse|Online)$",
                    re.IGNORECASE,
                )
                availability = ""
                for el in card.find_all(attrs={"data-testid": "Text"}):
                    child_tags = el.find_all(True, recursive=False)
                    if child_tags:
                        parts = [c.get_text(strip=True) for c in child_tags if c.get_text(strip=True) != "&"]
                        candidate = " & ".join(p for p in parts if p)
                    else:
                        candidate = el.get_text(strip=True)
                    if AVAIL_PATTERN.match(candidate):
                        availability = candidate
                        break

                # Product image URL — find by Costco CDN domain (stable across class changes)
                img_el = card.find("img", src=re.compile(r"costco-static\.com"))
                image_url = ""
                if img_el:
                    srcset = img_el.get("srcSet") or img_el.get("srcset") or ""
                    m = re.search(r'(https?://\S+)\s+768w', srcset)
                    image_url = m.group(1) if m else (img_el.get("src") or "")

                products.append(
                    {
                        "category": category,
                        "item_id": item_id,
                        "name": name,
                        "price": price_text,
                        "discount": discount,
                        "availability": availability,
                        "product_url": product_url,
                        "image_url": image_url,
                    }
                )
                print(f"     ✅ {name[:50]} | {price_text} | {discount}")

            except Exception as e:
                print(f"     ⚠️  Error parsing card: {e}")

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

    # flyer_id = folder_name (stable identifier for this savings event)
    flyer_id = folder_name

    csv_rows = []
    for idx, product in enumerate(products, 1):
        item_id = product["item_id"] or f"item_{idx}"
        name = product["name"]
        price = product["price"]
        discount = product["discount"]
        category = product["category"]
        image_url = product["image_url"]
        product_url = product["product_url"]
        availability = product["availability"]

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
                # ok = download_image(image_url, image_path)
                # print(" ✓" if ok else " ✗")
            else:
                print(f"   ⏭️  [{idx}/{len(products)}] Already exists: {name[:45]}")

        csv_rows.append(
            {
                "flyer_id": flyer_id,
                "flyer_name": FLYER_NAME,
                "id": item_id,
                "name": name,
                "price": price,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "image": image_filename,
                "discount": discount,
                "category": category,
                "availability": availability,
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
        "category",
        "availability",
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
    print("COSTCO WAREHOUSE SAVINGS SCRAPER")
    print("=" * 80)
    print()

    products, valid_from, valid_to = scrape_warehouse_savings()

    if products:
        save_results(products, valid_from, valid_to)
    else:
        print("❌ No products scraped.")
