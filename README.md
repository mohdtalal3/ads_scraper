# 📰 Grocery Store Flyer Scraper

This Python project downloads flyers, product images, and saves product data to CSV files from multiple grocery store chains.

## 🏪 Supported Stores

### 1. **Publix** (`publix.py`)
Complete Publix weekly ads scraper with store-specific data and flyer images.

### 2. **Aldi** (`aldi_scraper.py`)
Downloads Aldi flyer PDFs, page images, and product data.

---

---

## 🚀 Quick Start

### 1) Clone the Repository

```bash
git clone https://github.com/mohdtalal3/ads_scraper.git
cd ads_scraper
```

### 2) Set Up Virtual Environment (Recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3) Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 📖 Usage

### **Publix Scraper** (`publix.py`)

Downloads weekly ads, product images, and flyer pages for a specific Publix store.

#### Run:
```bash
python3 publix.py
```

#### What it does:
1. **Prompts for Store Location**
   - Enter ZIP code (e.g., `31008`)
   - Enter store name (e.g., `Publix at Gunn Battle`)

2. **Fetches Store-Specific Data**
   - Automatically cleans store codes (removes `#`, adds leading zeros)
   - Gets campaign ID and promotion details

3. **Downloads Content**
   - **Product images** (enhanced quality when available)
   - **Flyer page images** (full weekly ad pages)
   - **CSV data** with product details

4. **Retry Mechanism**
   - Automatically retries failed downloads up to 3 times
   - Shows progress for each image downloaded

#### Output Structure:
```
publix/
├── Publix_Weekly Ad_10-08-25_10-14-25/
│   ├── Publix_Weekly Ad_10-08-25_10-14-25.csv
│   ├── PUBLIX_251009_item123_456.jpg (product images)
│   ├── PUBLIX_251009_item789_012.jpg
│   └── Publix_Weekly Ad_10-08-25_10-14-25_flyer_page1.jpg (flyer pages)
└── Publix_Extra Savings_10-09-25_10-15-25/
    ├── Publix_Extra Savings_10-09-25_10-15-25.csv
    └── ...
```

#### CSV Columns:
- `flyer_id` - Weekly ad identifier
- `flyer_name` - Promotion type (e.g., "Weekly Ad", "Extra Savings")
- `id` - Product/deal ID
- `name` - Product name
- `price` - Savings amount
- `description` - Product description
- `additional_deal_info` - Extra deal information
- `valid_from` - Start date (MM-DD-YY)
- `valid_to` - End date (MM-DD-YY)
- `image` - Local product image filename

#### Features:
- ✅ **Smart Store Code Handling**: Removes `#` and formats codes properly
- ✅ **Enhanced Images**: Prioritizes high-quality enhanced images
- ✅ **Clean Filenames**: IDs are sanitized (dashes → underscores)
- ✅ **Retry Logic**: 3 automatic retries for failed downloads
- ✅ **Progress Tracking**: Real-time download status
- ✅ **Multiple Promotions**: Handles Weekly Ad, Extra Savings, and more

---

### **Aldi Scraper** (`aldi_scraper.py`)

Downloads Aldi flyer PDFs, page images, and product data.

#### Run:
```bash
python3 aldi_scraper.py
```

#### What it does:
- Fetches available Aldi flyers
- Downloads flyer PDFs (if available)
- Downloads flyer page images
- Downloads product images
- Saves product metadata to CSV

#### Output Structure:
```
Aldi_<flyer_name>/
├── <flyer_base>_flyer.pdf
├── <flyer_base>_page_1.jpg
├── <flyer_base>_page_2.jpg
├── <flyer_id>_<product_id>.jpg
└── <flyer_base>_products.csv
```

---

## 🔧 Features

### Common Features (All Scrapers)
- 📥 **Automatic Downloads**: Fetches all available images and data
- 🔄 **Retry Mechanism**: 3 automatic retries for failed downloads
- 📊 **Progress Indicators**: Real-time download status
- 📁 **Organized Output**: Clean folder structure per flyer
- 📝 **CSV Export**: All product data saved in structured format
- 🖼️ **Image Management**: Downloads and organizes all images

### Publix-Specific Features
- 🏪 **Store Locator**: Find stores by ZIP code and name
- 🎯 **Store-Specific Ads**: Get deals for your local store
- 🌟 **Enhanced Images**: Prioritizes high-quality product images
- 🗂️ **Multiple Promotions**: Handles all active promotions
- 🔤 **Clean Naming**: Sanitized filenames with underscores

---

## 📂 Project Structure

```
ads_scraper/
├── publix.py              # Publix scraper (recommended)
├── aldi_scraper.py        # Aldi scraper
├── test.py                # Development/testing file
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── publix/               # Output folder (auto-created)
    └── ...
```

---

## ⚙️ Configuration

### Publix Store Codes
- Store codes are automatically cleaned and formatted
- `#1219` → `01219`
- Leading zeros added for 4-digit codes

### Image Quality
- Publix: Automatically uses `enhancedImageUrl` when available
- Falls back to standard `imageUrl` if enhanced not available

---

## 🐛 Troubleshooting

### "No stores found for this ZIP code"
- Verify ZIP code is correct
- Try a nearby ZIP code
- Check internet connection

### "Failed to download image after 3 attempts"
- Some images may be temporarily unavailable
- Script will continue with other images
- CSV will show empty `image` field for failed downloads

### Store code issues
- Script automatically handles `#` prefix
- Ensures proper 5-digit format with leading zeros

---

## 📝 Notes

- **Rate Limiting**: Script includes timeouts to respect server limits
- **Data Accuracy**: Always verify prices and dates in-store
- **Image Rights**: Images are property of respective stores
- **Personal Use**: Intended for personal use only

---

## 🤝 Contributing

Feel free to submit issues or pull requests for:
- Additional store support
- Bug fixes
- Feature improvements
- Documentation updates

---

## 📄 License

This project is for educational and personal use only. All store names, logos, and content are property of their respective owners
