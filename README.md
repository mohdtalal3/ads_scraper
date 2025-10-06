## ADS - Aldi Flyer Scraper

This small Python project downloads Aldi flyer PDFs, page images and product images, and saves product data to CSV files.

### 1) Clone the repo

First, clone the repository to your machine and add the remote (as requested):

```bash
git clone https://github.com/mohdtalal3/ads_scraper.git
cd ads_scraper
```

> Note: If you already cloned a folder named differently (for example `ads`), `cd` into that folder instead.

### 2) Requirements / Virtual environment (recommended)

Create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate   # zsh/bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3) What this script does

- Fetches available Aldi flyers (uses the hard-coded access token in `aldi_scraper.py`).
- Downloads flyer PDF (if available).
- Downloads flyer page images (SFML) when provided.
- Downloads product images and saves product metadata (name, price, dates, image filenames) into a CSV per flyer.

All downloaded files are saved into a folder named after the flyer (e.g. `Aldi_...`). Each folder will contain:

- `<flyer_base>_flyer.pdf` (if available)
- `<flyer_base>_page_1.jpg`, ... (flyer pages)
- `<flyer_id>_<product_id>.jpg` (product images)
- `<flyer_base>_products.csv` (product metadata)

### 4) Running the scraper

From the project root run:

```bash
python3 aldi_scraper.py
```
