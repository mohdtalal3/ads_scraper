import requests
import json
import csv
import time
import os
from pathlib import Path
from PIL import Image
from datetime import datetime


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------
def auto_crop_whitespace(image_path, threshold=250, margin=10):
    """
    Crop white borders from an image using Pillow.
    """
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


# --------------------------------------------------
# IMAGE URL EXTRACTION
# --------------------------------------------------
def get_best_image_url(product):
    """Extract the best image URL from product data.

    Prefers primary LEFT/FRONT images at largest size.
    productImages may have multiple isPrimary=true entries (one per size),
    so we rank: isPrimary+LARGE > isPrimary+MEDIUM > isPrimary+any > item.images primary.
    """
    product_images = product.get("productImages", [])

    # Prefer isPrimary=true at the best available size
    preferred_types = ("LEFT", "FRONT")
    for size_pref in ("LARGE", "MEDIUM", "THUMBNAIL"):
        for img_type in preferred_types:
            for img in product_images:
                if (img.get("isPrimary") and
                        img.get("size") == size_pref and
                        img.get("type") == img_type and
                        img.get("uri")):
                    uri = img["uri"]
                    return uri if uri.startswith("http") else f"https://product.hyvee.com{uri}"
        # Any isPrimary at this size regardless of type
        for img in product_images:
            if img.get("isPrimary") and img.get("size") == size_pref and img.get("uri"):
                uri = img["uri"]
                return uri if uri.startswith("http") else f"https://product.hyvee.com{uri}"

    # Fallback: item.images primary
    item = product.get("item") or {}
    item_images = item.get("images", [])
    for img in item_images:
        if img.get("isPrimaryImage") and img.get("url"):
            return img["url"]
    if item_images and item_images[0].get("url"):
        return item_images[0]["url"]

    # Last resort: first productImage
    if product_images and product_images[0].get("uri"):
        uri = product_images[0]["uri"]
        return uri if uri.startswith("http") else f"https://product.hyvee.com{uri}"

    return ""


# --------------------------------------------------
# API FETCHING
# --------------------------------------------------
FEATURED_COLLECTION_QUERY = """
fragment IProductFragment on product {
  productId
  name
  size
  averageWeight
  upc
  brandName
  isNotEligibleForDelivery
  isSponsored
  adTrackingId
  productImages(where: {viewType: ["default", "full_bleed"]}) {
    ...ProductImageFragment
    __typename
  }
  couponProductV4(targeted: $targeted) {
    upc
    couponsV4 {
      couponId
      brand
      offerState
      valueText
      __typename
    }
    __typename
  }
  productLockers @include(if: $pickupLocationHasLocker) {
    productLockerId
    pickupLocationId
    isLockerEligible
    __typename
  }
  storeProduct(storeId: $storeId, isActive: true) {
    ...IStoreProductFragment
    __typename
  }
  item {
    nutrition @include(if: $foodHealthScoreEnabled) {
      score
      __typename
    }
    ...IItemFragment
    retailItems(locationIds: $locationIds) @include(if: $retailItemEnabled) {
      ...IRetailItemFragment
      __typename
    }
    alternativeItems {
      product {
        productId
        name
        upc
        __typename
      }
      itemId
      __typename
    }
    __typename
  }
  __typename
}

fragment IWicItemFragment on WicItem {
  isCvb
  isBroadbandAllowed
  wicExchangeRate
  wicItemId
  wicSubcategory {
    categoryCode
    categoryDescription
    subcategoryCode
    subcategoryDescription
    unitOfMeasure
    isBroadbandSubcategory
    __typename
  }
  upcHyVee
  __typename
}

fragment IMadeToOrderItemFragment on MtoItem {
  mtoItemId
  prepTime
  fulfillmentBeginDate
  fulfillmentEndDate
  messages {
    name
    __typename
  }
  mtoModifiers {
    options {
      amount
      __typename
    }
    __typename
  }
  __typename
}

fragment IItemFragment on Item {
  itemId
  description
  ecommerceStatus
  source
  images {
    imageId
    url
    isPrimaryImage
    __typename
  }
  source
  unitAverageWeight
  WicItems(locationIds: $locationIds) @include(if: $wicEnabled) {
    ...IWicItemFragment
    __typename
  }
  madeToOrder {
    mtoItems {
      ...IMadeToOrderItemFragment
      __typename
    }
    __typename
  }
  __typename
}

fragment IRetailItemFragment on RetailItem {
  retailItemId
  basePrice
  basePriceQuantity
  ecommerceStatus
  item {
    itemId
    ean13
    __typename
  }
  soldByUnitOfMeasure {
    code
    name
    __typename
  }
  tagPrice
  tagPriceQuantity
  ecommerceTagPrice
  ecommerceTagPriceQuantity
  memberTagPrice
  memberTagPriceQuantity
  sellingRules
  __typename
}

fragment IStoreProductFragment on storeProduct {
  storeProductId
  productId
  onFuelSaver
  onSale
  fuelSaver
  price
  basePrice
  priceMultiple
  isWeighted
  isActive
  isAlcohol
  insertDate
  departmentId
  taxRate
  storeProductDescriptions {
    type
    description
    __typename
  }
  __typename
}

fragment ProductImageFragment on productImage {
  productId
  uri
  size
  type
  viewType
  isPrimary
  __typename
}

query FeaturedCollectionQuery($productGroupId: Int!, $storeId: Int!, $pageSize: Int, $page: Int = 1, $pickupLocationHasLocker: Boolean = false, $sort: String = "priority", $order: String = "asc", $targeted: Boolean = false, $retailItemEnabled: Boolean = false, $locationIds: [ID!]!, $wicEnabled: Boolean = false, $foodHealthScoreEnabled: Boolean = false) {
  productGroup(productGroupId: $productGroupId) {
    productGroupId
    name
    __typename
  }
  pageableProductGroupStoreProducts: productGroupProducts(
    productGroupId: $productGroupId
    pageSize: $pageSize
    page: $page
    sort: $sort
    order: $order
  ) {
    page
    nextPage
    productGroupProducts {
      productGroupId
      productId
      product {
        ...IProductFragment
        __typename
      }
      __typename
    }
    __typename
  }
}
"""


def fetch_collection_page(product_group_id, store_id, location_id, page=1, page_size=50):
    """Fetch one page of products from a Hy-Vee featured collection."""
    url = "https://www.hy-vee.com/aisles-online/api/graphql/two-legged/FeaturedCollectionQuery"

    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "apollographql-client-name": "aisles-online-web",
        "x-operation-name": "FeaturedCollectionQuery",
        "origin": "https://www.hy-vee.com",
        "referer": f"https://www.hy-vee.com/aisles-online/collections/{product_group_id}",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
    }

    payload = {
        "operationName": "FeaturedCollectionQuery",
        "variables": {
            "page": page,
            "pickupLocationHasLocker": False,
            "sort": "priority",
            "order": "asc",
            "targeted": False,
            "retailItemEnabled": True,
            "wicEnabled": True,
            "foodHealthScoreEnabled": False,
            "locationIds": [location_id],
            "pageSize": page_size,
            "productGroupId": product_group_id,
            "storeId": store_id,
        },
        "query": FEATURED_COLLECTION_QUERY,
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def fetch_all_products(product_group_id, store_id, location_id, page_size=50):
    """Fetch all products from a featured collection by paginating."""
    all_products = []
    group_name = ""
    page = 1

    while True:
        print(f"   📄 Fetching page {page}...", end="", flush=True)
        data = fetch_collection_page(product_group_id, store_id, location_id, page, page_size)

        result = data.get("data", {})

        if page == 1:
            group_name = result.get("productGroup", {}).get("name", f"Collection_{product_group_id}")

        pageable = result.get("pageableProductGroupStoreProducts", {})
        products = pageable.get("productGroupProducts", [])
        next_page = pageable.get("nextPage")

        all_products.extend(products)
        print(f" {len(products)} products (total: {len(all_products)})")

        if not next_page:
            break

        page = next_page
        time.sleep(0.5)

    return all_products, group_name


# --------------------------------------------------
# CSV EXPORT
# --------------------------------------------------
def save_to_csv(products, group_name, group_id, csv_file, output_dir):
    """Save products to CSV with image downloading."""
    if not products:
        print("⚠️ No products found")
        return

    print(f"\n📦 Processing {len(products)} products...")

    today_str = datetime.now().strftime("%m-%d-%y")
    csv_rows = []

    for idx, entry in enumerate(products, 1):
        product = entry.get("product") or {}

        product_id = product.get("productId", "")
        name = product.get("name", "")
        size = product.get("size", "")
        brand = product.get("brandName", "")
        upc = product.get("upc", "")

        # Price from storeProduct
        store_product = product.get("storeProduct") or {}
        price = store_product.get("price")
        base_price = store_product.get("basePrice")
        price_multiple = store_product.get("priceMultiple", "")
        on_sale = store_product.get("onSale", False)

        # Skip items missing price or base price
        if price is None or base_price is None:
            print(f"   ⏭️  Skipping (no price): {name[:40]}")
            continue

        # Description from item
        item = product.get("item") or {}
        description = item.get("description", "")

        # Image
        image_url = get_best_image_url(product)
        image_filename = ""
        if image_url:
            image_filename = f"{group_id}_{product_id}.png"
            image_path = output_dir / image_filename

            print(f"   📥 [{idx}/{len(products)}] Downloading: {name[:40]}", end="")
            # success = download_image(image_url, image_path)
            # print(" ✓" if success else " ✗")

        csv_row = {
            "flyer_id": group_id,
            "flyer_name": "Pages",
            "id": product_id,
            "name": name,
            "price": price,
            "valid_from": today_str,
            "valid_to": today_str,
            "image": image_filename,
            "brand": brand,
            "size": size,
            "base_price": base_price,
            "price_multiple": price_multiple,
            "on_sale": on_sale,
            "upc": upc,
            "description": description,
            "image_url": image_url,
        }

        csv_rows.append(csv_row)

    if csv_rows:
        fieldnames = [
            "flyer_id", "flyer_name", "id", "name", "price",
            "valid_from", "valid_to", "image",
            "brand", "size", "base_price", "price_multiple",
            "on_sale", "upc", "description", "image_url",
        ]

        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)

        print(f"\n✅ Saved {len(csv_rows)} products to CSV")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
if __name__ == "__main__":
    print("=" * 80)
    print("HY-VEE PAGES (FEATURED COLLECTION) SCRAPER")
    print("=" * 80)
    print()

    # Configuration
    PRODUCT_GROUP_ID = 31537
    STORE_ID = 1759
    LOCATION_ID = "266a52f4-0e7a-4729-bc6f-25c6ebaca111"

    try:
        # Fetch products
        print("🔍 Fetching products from API...")
        products, group_name = fetch_all_products(PRODUCT_GROUP_ID, STORE_ID, LOCATION_ID)

        if not products:
            print("❌ No products found")
            exit(1)

        # Build folder/file names
        today_str = datetime.now().strftime("%m-%d-%y")
        safe_group = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in group_name)

        base_dir = Path("hyvee")
        folder_name = f"HyVee_Pages_{safe_group}_{today_str}"
        output_dir = base_dir / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        csv_file = output_dir / f"{folder_name}.csv"

        print(f"\n✅ Found {len(products)} products")
        print(f"📂 Collection: {group_name}")
        print(f"📁 Folder: {folder_name}")
        print()

        # Save to CSV with images
        save_to_csv(products, group_name, PRODUCT_GROUP_ID, csv_file, output_dir)

        print()
        print("=" * 80)
        print("✅ COMPLETE!")
        print(f"📄 CSV: {csv_file}")
        print(f"📁 Location: {output_dir}")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
