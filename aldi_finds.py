import csv
import json
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Optional


# -----------------------------
# Helpers: grouping & variants
# -----------------------------
def extract_base_name(title: str) -> str:
    if ' - ' in title:
        return title.rsplit(' - ', 1)[0].strip()
    return title.strip()


def extract_item_pure_and_variant(title: str):
    if ' - ' in title:
        parts = title.rsplit(' - ', 1)
        return parts[0].strip(), parts[1].strip()
    return title.strip(), ""


def assign_group_numbers(products):
    base_name_to_group = {}
    current_group = 1

    for p in products:
        base = extract_base_name(p["title"])
        if base not in base_name_to_group:
            base_name_to_group[base] = current_group
            current_group += 1

    result = []
    for p in products:
        base = extract_base_name(p["title"])
        updated = p.copy()
        updated["group"] = base_name_to_group[base]
        result.append(updated)

    group_counts = {}
    for p in result:
        group_counts[p["group"]] = group_counts.get(p["group"], 0) + 1
    multi = sum(1 for c in group_counts.values() if c > 1)
    print(f"  📊 Created {current_group - 1} groups ({multi} with multiple items)")

    return result

# -----------------------------
# Date range extractor
# -----------------------------
def extract_date_range(soup: BeautifulSoup) -> Optional[str]:
    text = soup.get_text()
    date_pattern = r'(\d{1,2}/\d{1,2}/\d{4})\s*-\s*(\d{1,2}/\d{1,2}/\d{4})'
    match = re.search(date_pattern, text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None


# ---- constants ----
GRAPHQL_URL = "https://www.aldi.us/graphql"
SHOP_ID     = "9816"
POSTAL_CODE = "21075"
ZONE_ID     = "267"
PAGE_VIEW_ID = "db3cb3d8-0b6f-5ab1-baa4-ce1c846bd64c"

session = requests.Session()

# -----------------------------
# Step 1: warm-up request – extract collections + date range
# -----------------------------
WARMUP_URL = "https://www.aldi.us/store/aldi/pages/upcoming-aldi-finds"
print("🔄 Warm-up request...")
warmup_resp = session.get(WARMUP_URL, headers={"user-agent": "Mozilla/5.0"})

with open("aldi_warmup.html", "w", encoding="utf-8") as f:
    f.write(warmup_resp.text)
print("💾 Saved warm-up HTML to aldi_warmup.html")

soup = BeautifulSoup(warmup_resp.text, "html.parser")

date_range = extract_date_range(soup)
print(f"📅 Date range: {date_range}")

# Collect unique collection links from entire page, skip "all aldi finds"
seen_slugs: set = set()
collections: list = []  # [(slug, display_name), ...]

for a in soup.find_all("a", href=True):
    href = a.get("href", "")
    if "/store/aldi/collections/rc-af-" not in href:
        continue
    slug = href.rstrip("/").split("/")[-1]
    if "rc-af-all-aldi-finds" in slug:
        continue
    if slug in seen_slugs:
        continue
    name = ''.join(c for c in a.get_text() if c.isprintable()).strip()
    if not name:
        continue
    seen_slugs.add(slug)
    collections.append((slug, name))

print(f"\n📂 Found {len(collections)} collections:")
for s, n in collections:
    print(f"  - {n} ({s})")

if not collections:
    print("⚠️  No collections found in warm-up HTML – check if page is server-side rendered")

# -----------------------------
# Steps 2-4: iterate over each collection
# -----------------------------
all_items_flat: list = []       # for CSV
all_collection_data: list = []  # for JSON

for slug, category_name in collections:
    print(f"\n🔍 [{category_name}]")

    # -- collection query --
    variables = {
        "shopId": SHOP_ID,
        "postalCode": POSTAL_CODE,
        "zoneId": ZONE_ID,
        "slug": slug,
        "filters": [],
        "pageViewId": PAGE_VIEW_ID,
        "itemsDisplayType": "collections_items_grid",
        "first": 100,
        "pageSource": "browse"
    }
    extensions = {
        "persistedQuery": {
            "version": 1,
            "sha256Hash": "5573f6ef85bfad81463b431985396705328c5ac3283c4e183aa36c6aad1afafe"
        }
    }
    params = {
        "operationName": "CollectionProductsWithFeaturedProducts",
        "variables": json.dumps(variables),
        "extensions": json.dumps(extensions)
    }
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "x-page-view-id": PAGE_VIEW_ID,
        "x-client-identifier": "web",
        "referer": f"https://www.aldi.us/store/aldi/collections/{slug}",
        "user-agent": "Mozilla/5.0"
    }
    resp = session.get(GRAPHQL_URL, params=params, headers=headers)
    data = resp.json()

    try:
        collection   = data["data"]["collectionProducts"]["collection"]
        coll_name    = collection["name"]
        coll_slug    = collection["slug"]
        item_ids     = data["data"]["collectionProducts"]["itemIds"]
    except (KeyError, TypeError) as e:
        print(f"  ⚠️  Skipping (parse error: {e})")
        continue

    print(f"  📦 {len(item_ids)} item IDs")
    if not item_ids:
        continue

    # -- items query --
    items_variables = {
        "ids": item_ids,
        "shopId": SHOP_ID,
        "zoneId": ZONE_ID,
        "postalCode": POSTAL_CODE
    }
    items_extensions = {
        "persistedQuery": {
            "version": 1,
            "sha256Hash": "5116339819ff07f207fd38f949a8a7f58e52cc62223b535405b087e3076ebf2f"
        }
    }
    items_params = {
        "operationName": "Items",
        "variables": json.dumps(items_variables),
        "extensions": json.dumps(items_extensions)
    }
    items_headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "x-page-view-id": PAGE_VIEW_ID,
        "x-ic-view-layer": "true",
        "x-client-identifier": "web",
        "referer": f"https://www.aldi.us/store/aldi/collections/{coll_slug}",
        "user-agent": "Mozilla/5.0"
    }
    items_resp = session.get(GRAPHQL_URL, params=items_params, headers=items_headers)
    items_data = items_resp.json()
    items = items_data.get("data", {}).get("items", [])
    print(f"  ✅ Retrieved {len(items)} items")

    # accumulate JSON data
    all_collection_data.append({
        "collection_name": coll_name,
        "collection_slug": coll_slug,
        "category": category_name,
        "item_ids": item_ids,
        "items": items
    })

    # build flat rows for CSV
    for item in items:
        price_view = (item.get("price") or {}).get("viewSection", {})
        view       = item.get("viewSection") or {}
        img        = view.get("itemImage") or {}
        image_url  = img.get("url", "")

        img_filename = image_url.split("?")[0].split("/")[-1] if image_url else ""
        if img_filename and not img_filename.endswith((".jpg", ".jpeg", ".png", ".gif")):
            img_filename += ".jpg"

        title = item.get("name", "")
        item_pure, item_variant = extract_item_pure_and_variant(title)

        all_items_flat.append({
            "category":     category_name,
            "title":        title,
            "item_pure":    item_pure,
            "item_variant": item_variant,
            "price":        price_view.get("priceString", ""),
            "url":          f"https://www.aldi.us/products/{item.get('evergreenUrl', '')}",
            "image_url":    image_url,
            "image_name":   img_filename,
        })

# -----------------------------
# Step 5: Save combined JSON
# -----------------------------
json_output = {
    "date_range": date_range,
    "collections": all_collection_data
}
with open("aldi_items.json", "w") as f:
    json.dump(json_output, f, indent=2)
print(f"\n✅ Saved JSON with {len(all_collection_data)} collections to aldi_items.json")

# -----------------------------
# Step 6: Save to CSV
# -----------------------------
print(f"\n🔗 Grouping similar products...")
products_with_groups = assign_group_numbers(all_items_flat)

csv_path = Path("aldi_items.csv")
fieldnames = ["group", "category", "title", "item_pure", "item_variant", "price", "url", "image_url", "image_name"]
with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(products_with_groups)

print(f"✅ Saved {len(products_with_groups)} rows to {csv_path}")
if date_range:
    print(f"📅 Date range: {date_range}")