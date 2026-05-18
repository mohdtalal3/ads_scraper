from curl_cffi import requests
import csv
import os
import json
import time
import random
from datetime import datetime
from pathlib import Path
from PIL import Image
from seleniumbase import SB
# ---------- CONFIG ----------
STORE_ID = "3441"
BANNER = "jewelosco"
ROWS_PER_PAGE = 30
VISITOR_ID = "a7140d75-986a-4aec-8307-fe91abdff3ab"  # must match absVisitorId in cookie
BASE_URL = "https://www.jewelosco.com/abs/pub/xapi/search/products"

# Proxy used for both SeleniumBase browser and curl_cffi API requests
PROXY = "http://b7e4c783105e0a21fd89__cr.us:bfadc321f9ff54fd@gw.dataimpulse.com:10000"
PROXY_SB = "b7e4c783105e0a21fd89__cr.us:bfadc321f9ff54fd@gw.dataimpulse.com:10000"  # SB format (no scheme)

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "accept-encoding": "gzip, deflate, br, zstd",
    "ocp-apim-subscription-key": "e914eec9448c4d5eb672debf5011cf8f",
    "referer": "https://www.jewelosco.com/shop/deals/buy-one-get-one-free.html/?sort=price",
    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "priority": "u=1, i",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",

    # IMPORTANT: raw cookie header, not cookies={}
    "cookie": '''absVisitorId=8708826d-5b1b-4925-a1b6-443e59bad6d4; _uetvid=72a86e70411511f1b82925543cfec236; visid_incap_1990338=vqoiCbQvQx2bGhfJt0oq0KZ07WkAAAAAQUIPAAAAAADZJ/p7UASU+qjblqJFmmqc; _fbp=fb.1.1777169579826.490923835245654857; s_ivc=true; _pin_unauth=dWlkPVkySmpOekZoTVRFdFl6RTJOQzAwTWpka0xUaGtOR1l0WWprNE1UUmtOVFE1WXpabA; AMCVS_A7BF3BC75245ADF20A490D4D%40AdobeOrg=1; AMCV_A7BF3BC75245ADF20A490D4D%40AdobeOrg=179643557%7CMCIDTS%7C20570%7CMCMID%7C72678139724867193052402869791784477905%7CMCAAMLH-1777774377%7C9%7CMCAAMB-1777774377%7C6G1ynYcLPuiQxYZrsz_pkqfLG9yMXBpb2zX5dvJdYQJzPXImdj0y%7CMCOPTOUT-1777176777s%7CNONE%7CvVersion%7C5.5.0; abs_gsession=%7B%22info%22%3A%7B%22COMMON%22%3A%7B%22Selection%22%3A%22default%22%2C%22preference%22%3A%22J4U%22%2C%22userType%22%3A%22G%22%2C%22zipcode%22%3A%2260657%22%2C%22banner%22%3A%22jewelosco%22%2C%22siteType%22%3A%22C%22%2C%22customerType%22%3A%22%22%2C%22resolvedBy%22%3A%22%22%7D%2C%22J4U%22%3A%7B%22zipcode%22%3A%2260657%22%2C%22storeId%22%3A%223441%22%7D%2C%22SHOP%22%3A%7B%22zipcode%22%3A%2260657%22%2C%22storeId%22%3A%223441%22%7D%7D%7D; ACI_S_abs_previouslogin=%7B%22info%22%3A%7B%22COMMON%22%3A%7B%22Selection%22%3A%22default%22%2C%22preference%22%3A%22J4U%22%2C%22userType%22%3A%22G%22%2C%22zipcode%22%3A%2260657%22%2C%22banner%22%3A%22jewelosco%22%2C%22siteType%22%3A%22C%22%2C%22customerType%22%3A%22%22%2C%22resolvedBy%22%3A%22%22%7D%2C%22J4U%22%3A%7B%22zipcode%22%3A%2260657%22%2C%22storeId%22%3A%223441%22%7D%2C%22SHOP%22%3A%7B%22zipcode%22%3A%2260657%22%2C%22storeId%22%3A%223441%22%7D%7D%7D; at_check=true; OptanonConsent=isGpcEnabled=0&datestamp=Sun+Apr+26+2026+04%3A13%3A03+GMT%2B0200+(Central+European+Summer+Time)&version=202409.1.0&browserGpcFlag=0&isIABGlobal=false&hosts=&consentId=70cb2668-aab7-404f-beb1-855f9873cfe2&interactionCount=1&isAnonUser=1&landingPath=https%3A%2F%2Fwww.jewelosco.com%2Fshop%2Fdeals%2Fbuy-one-get-one-free.html%2F%3Fsort%3Dprice&groups=C0001%3A1%2CC0002%3A1%2CC0004%3A1%2CC0003%3A1; SWY_SYND_USER_INFO=%7B%22storeAddress%22%3A%22%22%2C%22storeZip%22%3A%2260657%22%2C%22storeId%22%3A%223441%22%2C%22preference%22%3A%22J4U%22%7D; ACI_S_ECommBanner=jewelosco; nlbi_1990338=oyt6QgpQ6l9fn4XYzoaznQAAAABThQFXMfWPFIAsbsAmuLrZ; __pdst=caa594eb6e0f4acaaae06f01c9c5b50e; incap_ses_2103_1990338=HpgyFlzs0zDD/12Ik1svHaZ07WkAAAAAo8kZpd4VhffL9I1e3bLTdg==; akacd_PR-bg-www-prod-jewelosco=3954622374~rv=87~id=49de7d0499ee01843d9677ddf17f5694; reese84=3:Vn3FGw1XCqQdgW4UzCPkmQ==:WOiTdkRboS6K+88bLrlvYCUBewJJBDIGhniwq+7l1XZzSrPf4K+gyRg3/vX0aZ6AVWSC+qatKk+oAT+N3xz7ZPm16Q3JOSO2y1zet8zhUMSA6f2SHwlPDpZq5l1g9rrQIa3AfGBhY+Fxr4/ylH6KHfAH8KWT/wG/NZtCo3hN+qV6anG0y18Vo6smEz/3nGnHpzyV+zYd2ACfHtFROqt/8C7TIgKmxi0qDSYU+RraxbVfF1yOl5kySLhk9Cin+N4U+V7W9fH4rK3qtt8uE74iBtqwkHB6jJ2tADbffT6Nc6PTGISSzmWfIyu1FPzJ930WuVnQINeGz1q1KY++XgIj8zz3At9MLTC2C2+OifTu2s+UoozEIMqaDcGhf9e+BKh+DNq5xh3vCG3g2XMNZ4NsmPYVOrg0WAQLHoZn5x+/gI5TpDZFRx1v4I8ZIZUvE9eal7RpU9IdQpzGSiEHINiD/AAapj8D3FLZj00JdbXNW7QW8BIGKVDkHb/Nbp/4h0uxGQF2Nxj7rQhGqWJd1T5Pr6CnRSJH2eywK4KudBPvT8vGTrEV0QcpPRZwG5QUeBGerfl+aCJhUZToK0Sm5H8rVQ==:1qRXnGdtxmUizcCiicbWDFCdvvlKtTyEwL99TfgA9U4=; SWY_SHARED_SESSION_INFO=%7B%22info%22%3A%7B%22COMMON%22%3A%7B%22Selection%22%3A%22default%22%2C%22preference%22%3A%22J4U%22%2C%22userType%22%3A%22G%22%2C%22zipcode%22%3A%2260657%22%2C%22banner%22%3A%22jewelosco%22%2C%22siteType%22%3A%22C%22%2C%22customerType%22%3A%22%22%2C%22resolvedBy%22%3A%22%22%2C%22grsSessionId%22%3A%2297eaf5ac-27a5-4e31-aade-c4075e19ba43%22%7D%2C%22J4U%22%3A%7B%22zipcode%22%3A%2260657%22%2C%22storeId%22%3A%223441%22%7D%2C%22SHOP%22%3A%7B%22zipcode%22%3A%2260657%22%2C%22storeId%22%3A%223441%22%7D%7D%7D; _gcl_au=1.1.1466168032.1777169580; nlbi_1990338_2147483392=/ArsURENq0iSOW8lzoaznQAAAACgU02rDjHUREx9W0rcefas; ACI_S_ECommSignInCount=0; _ga_8KFH5XL9VW=GS2.1.s1777169584$o1$g0$t1777169584$j60$l0$h0; mbox=session#53419e68083e4f94bf52d18bc402c932#1777171443|PC#53419e68083e4f94bf52d18bc402c932.35_0#1840414383; gpv_Page=jewelosco%3Adelivery%3Adeals%3Abuy-one-get-one-free'''

}

IMAGE_BASE_URL = "https://images.albertsons-media.com/is/image/ABS/{pid}?$ng-ecom-pdp-desktop$&defaultImage=Not_Available"

DEALS_PAGE_URL = "https://www.jewelosco.com/shop/deals/buy-one-get-one-free.html/?sort=price"


# ---------- SeleniumBase Cookie Harvester ----------
def get_fresh_cookies(wait_seconds=15):
    """
    Open the Jewel-Osco deals page in an undetected Chrome browser,
    wait for all anti-bot cookies (reese84, incap_ses_*, etc.) to be set,
    then return (cookie_string, visitor_id, user_agent).
    """
    print(f"\n🌐 Launching browser to harvest fresh cookies ...")
    print(f"   ⏳ Will wait {wait_seconds}s for cookies to settle ...\n")

    cookie_str = ""
    visitor_id = ""
    user_agent = ""

    with SB(uc=True) as sb:
        sb.open(DEALS_PAGE_URL)
        sb.sleep(1)
        input("Press Enter to continue...")
        raw_cookies = sb.get_cookies()
        cookie_parts = []
        for c in raw_cookies:
            name = c.get("name", "")
            value = c.get("value", "")
            if name and value:
                cookie_parts.append(f"{name}={value}")
                if name == "absVisitorId":
                    visitor_id = value

        cookie_str = "; ".join(cookie_parts)
        sb.save_screenshot("jewelosco.png")

    print(f"✅ Harvested {len(cookie_parts)} cookies.")
    if visitor_id:
        print(f"   absVisitorId : {visitor_id}")
    if user_agent:
        print(f"   User-Agent   : {user_agent[:80]}")

    return cookie_str, visitor_id, user_agent


# ---------- Helper Functions ----------
def safe_filename(name):
    """Sanitize file/folder names."""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)


def format_date(date_str):
    """Convert ISO date string to MM-DD-YY format."""
    if not date_str:
        return ""
    try:
        if "T" in date_str:
            date_str = date_str.split("T")[0]
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%m-%d-%y")
    except Exception:
        return date_str


def auto_crop_whitespace(image_path, threshold=250, margin=10):
    """Crop white borders from an image using Pillow."""
    try:
        img = Image.open(image_path)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        width, height = img.size
        pixels = img.load()
        min_x, min_y = width, height
        max_x, max_y = 0, 0
        found_content = False
        stride = 10
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
            cropped_img.save(image_path, "JPEG", quality=95, optimize=True)
            img.close()
            cropped_img.close()
            return True
        img.close()
        return False
    except Exception as e:
        print(f"    ⚠️ Auto-crop failed for {os.path.basename(str(image_path))}: {e}")
        return False


def download_image(url, path, auto_crop=True, max_retries=3):
    """Download a product image and optionally auto-crop whitespace."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
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
            else:
                print(f"  ❌ Failed to download image: {e}")
    return False


# ---------- API Fetcher ----------
def build_url(start, next_page_token=None):
    """Build raw URL string exactly as the browser sends it (no params dict)."""
    request_id = str(random.randint(100,999)) + str(int(time.time()*1000)) + str(random.randint(100,999))

    url = (
        f"{BASE_URL}"
        f"?request-id={request_id}"
        f"&url=https://www.jewelosco.com"
        f"&pageurl=https://www.jewelosco.com"
        f"&pagename=deals"
        f"&rows={ROWS_PER_PAGE}"
        f"&start={start}"
        f"&search-type=keyword"
        f"&storeid={STORE_ID}"
        f"&featured=false"
        f"&q="
        f"&sort=price%2Basc"
        f"&userid="
        f"&dvid=web-4.1search"
        f"&visitorId={VISITOR_ID}"
        f"&channel=instore"
        f"&includeOffer=true"
        f"&banner={BANNER}"
        f"&fq=promoType:%22M%22OR%22B%22"
        f"&fq=instoreInventory:%221%22"
    )
    if next_page_token:
        url += f"&nextPageToken={next_page_token}"
    return url


def fetch_deals_page(start, next_page_token=None):
    """Fetch a single page of deals from the Jewel-Osco API."""
    url = build_url(start, next_page_token)
    resp = requests.get(
        url,
        headers=HEADERS,
        impersonate="chrome136",
        http_version=2,
        proxies={"http": PROXY, "https": PROXY},
        timeout=90,
    )
    if resp.status_code != 200:
        print(f"  ❌ API error {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.json()


# ---------- Main Scraper ----------
def scrape_jewelosco_deals(store_id=None):
    """Scrape all Jewel-Osco in-store deals (B1G1 + mix & match) and save to CSV with images."""

    global STORE_ID
    if store_id:
        STORE_ID = store_id

    today_str = datetime.now().strftime("%m-%d-%y")

    print(f"\n🛒 Jewel-Osco Deals Scraper")
    print(f"   Store ID : {STORE_ID}")
    print(f"   Banner   : {BANNER}")
    print(f"   Date     : {today_str}")
    print(f"   Visitor  : {VISITOR_ID}\n")

    # ── Step 1: Fetch first page to get total count ──
    print("📡 Fetching page 1 ...")
    first = fetch_deals_page(start=0)
    if not first:
        print("❌ Failed to fetch first page. Aborting.")
        return []

    total_found = first.get("response", {}).get("numFound", 0)
    print(f"✅ Total deals found: {total_found}")

    all_docs = []
    all_docs.extend(first.get("response", {}).get("docs", []))
    next_page_token = first.get("response", {}).get("miscInfo", {}).get("nextPageToken")

    # ── Step 2: Fetch remaining pages ──
    start = ROWS_PER_PAGE
    page_num = 2
    while start < total_found and next_page_token:
        print(f"📡 Fetching page {page_num} (start={start}) ...")
        time.sleep(0.5)  # polite delay
        data = fetch_deals_page(start=start, next_page_token=next_page_token)
        if not data:
            print(f"  ⚠️ Failed to fetch page {page_num}, stopping pagination.")
            break
        docs = data.get("response", {}).get("docs", [])
        all_docs.extend(docs)
        next_page_token = data.get("response", {}).get("miscInfo", {}).get("nextPageToken")
        start += ROWS_PER_PAGE
        page_num += 1

    print(f"\n✅ Total products collected: {len(all_docs)}")

    if not all_docs:
        print("⚠️ No products found.")
        return []

    # ── Step 3: Determine date range from promo end dates ──
    promo_end_dates = [
        d["promoEndDate"].split("T")[0]
        for d in all_docs
        if d.get("promoEndDate")
    ]
    if promo_end_dates:
        latest_end = max(promo_end_dates)
        end_fmt = format_date(latest_end)
    else:
        latest_end = ""
        end_fmt = today_str

    flyer_name = "Deals"
    folder_base = f"JewelOsco_{flyer_name}_{today_str}_{end_fmt}"
    store_root = Path("jewelosco")
    folder_path = store_root / folder_base
    folder_path.mkdir(parents=True, exist_ok=True)

    csv_filename = f"{folder_base}.csv"
    csv_path = folder_path / csv_filename

    print(f"\n📁 Output folder : {folder_path}")
    print(f"📄 CSV file      : {csv_filename}\n")

    # ── Step 4: Write CSV + Download Images ──
    csv_columns = [
        "flyer_id",
        "flyer_name",
        "id",
        "pid",
        "upc",
        "name",
        "price",
        "base_price",
        "price_per_unit",
        "promo_description",
        "promo_text",
        "promo_type",
        "valid_from",
        "valid_to",
        "department",
        "aisle",
        "shelf",
        "aisle_location",
        "snap_eligible",
        "unit_of_measure",
        "display_size",
        "channel_pickup",
        "channel_delivery",
        "channel_instore",
        "avg_rating",
        "review_count",
        "image",
    ]

    flyer_id = f"jewelosco_{STORE_ID}_{today_str}"
    rows = []
    total = len(all_docs)

    for i, doc in enumerate(all_docs, 1):
        pid = doc.get("pid", "")
        product_id = doc.get("id", pid)
        name = doc.get("name", "")
        price = doc.get("price", "")
        base_price = doc.get("basePrice", "")
        price_per = doc.get("pricePer", doc.get("basePricePer", ""))
        promo_desc = doc.get("promoDescription", "")
        promo_text = doc.get("promoText", "")
        promo_type = doc.get("promoType", "")
        promo_end_raw = doc.get("promoEndDate", "")
        valid_to = format_date(promo_end_raw.split("T")[0]) if promo_end_raw else ""
        department = doc.get("departmentName", "")
        aisle = doc.get("aisleName", "").split("|")[0] if doc.get("aisleName") else ""
        shelf = doc.get("shelfName", "")
        aisle_location = doc.get("aisleLocation", "")
        snap_eligible = "Yes" if doc.get("snapEligible") else "No"
        uom = doc.get("unitOfMeasure", "")
        size_qty = doc.get("dispItemSizeQty", "")
        disp_uom = doc.get("dispUnitOfMeasure", "")
        display_size = f"{size_qty} {disp_uom}".strip() if size_qty else ""
        channel_eligibility = doc.get("channelEligibility", {})
        channel_pickup = "Yes" if channel_eligibility.get("pickUp") else "No"
        channel_delivery = "Yes" if channel_eligibility.get("delivery") else "No"
        channel_instore = "Yes" if channel_eligibility.get("inStore") else "No"
        review = doc.get("productReview", {})
        avg_rating = review.get("avgRating", "")
        review_count = review.get("reviewCount", "")

        # Download product image
        img_filename = f"{pid}.jpg"
        img_path = folder_path / img_filename
        image_url = doc.get("imageUrl", IMAGE_BASE_URL.replace("{pid}", pid))
        if image_url and not img_path.exists():
            print(f"  [{i}/{total}] 🖼️  {name[:50]}")
            download_image(image_url, img_path)
        else:
            print(f"  [{i}/{total}] ✅ {name[:50]}")

        rows.append({
            "flyer_id": flyer_id,
            "flyer_name": flyer_name,
            "id": product_id,
            "pid": pid,
            "upc": doc.get("upc", ""),
            "name": name,
            "price": price,
            "base_price": base_price,
            "price_per_unit": price_per,
            "promo_description": promo_desc,
            "promo_text": promo_text,
            "promo_type": promo_type,
            "valid_from": today_str,
            "valid_to": valid_to,
            "department": department,
            "aisle": aisle,
            "shelf": shelf,
            "aisle_location": aisle_location,
            "snap_eligible": snap_eligible,
            "unit_of_measure": uom,
            "display_size": display_size,
            "channel_pickup": channel_pickup,
            "channel_delivery": channel_delivery,
            "channel_instore": channel_instore,
            "avg_rating": avg_rating,
            "review_count": review_count,
            "image": img_filename if img_path.exists() else "",
        })

    # Write CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns)
        writer.writeheader()
        writer.writerows(rows)

    # Save raw JSON snapshot for debugging
    json_path = folder_path / f"{folder_base}_raw.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_docs, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done!")
    print(f"   📄 CSV saved     : {csv_path}")
    print(f"   🗂️  JSON snapshot : {json_path}")
    print(f"   🛒 Total deals   : {len(rows)}")
    return rows


# ---------- Entry Point ----------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Jewel-Osco In-Store Deals Scraper")
    parser.add_argument(
        "--store",
        default=STORE_ID,
        help=f"Jewel-Osco store ID (default: {STORE_ID})",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Skip browser cookie harvest and use the hardcoded cookie in HEADERS",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=15,
        help="Seconds to wait in browser for cookies to settle (default: 15)",
    )
    args = parser.parse_args()

    if not args.no_browser:
        cookie_str, vis_id, ua = get_fresh_cookies(wait_seconds=args.wait)
        if cookie_str:
            HEADERS["cookie"] = cookie_str
            print("HEADER COOKIE:")
            print(HEADERS["cookie"])
            print("✅ Injected fresh browser cookies into HEADERS.")
        if vis_id:
            VISITOR_ID = vis_id
            print(f"✅ Updated VISITOR_ID to: {VISITOR_ID}")
        if ua:
            HEADERS["user-agent"] = ua
    else:
        print("⚠️  --no-browser set: using hardcoded cookie from HEADERS.")

    results = scrape_jewelosco_deals(store_id=args.store)
    print(f"\n🏁 Scraping complete. {len(results)} deals processed.")
