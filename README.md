# PolyPrice: Multilingual E-Commerce Scraper & Normalizer

PolyPrice is an automated Python utility designed to navigate, extract, and normalize product data across complex Asian e-commerce platforms (Shopee, AliExpress, Amazon JP).

## 🎯 The Problem

Western clients frequently require pricing parity data across Asian markets. However, extracting this data is difficult due to:

1. **Language Barriers:** Keyword searches must be localized (e.g., "Mechanical Keyboard" to "メカニカルキーボード").
2. **Dynamic Rendering:** Modern e-commerce sites rely heavily on JavaScript, rendering standard HTTP requests (like `requests` or `curl`) useless.
3. **Currency Fragmentation:** Output data is scattered across different currencies and formats.

## 🛠️ The Solution (PolyPrice)

This script utilizes **Playwright** as a headless browser to execute JavaScript and bypass basic bot-protection, **BeautifulSoup4** to parse the rendered DOM, and **Pandas** to output normalized, client-ready data.

### Core Features

* **Auto-Translation:** Translates English search inputs into target regional languages (TH, JP, CN).
* **Headless Execution:** Silently navigates complex DOM structures to extract Product Titles, Prices, and URLs.
* **Currency Normalization:** Standardizes disparate currencies into a single comparative format (e.g., USD).
* **Client-Ready Output:** Exports cleanly to CSV/JSON.

## 💻 Tech Stack

* **Language:** Python 3.x
* **Browser Automation:** Playwright
* **Parsing:** BeautifulSoup4
* **Data Manipulation:** Pandas
* **Development Environment:** Neovim on Arch Linux

## 🚀 Quick Start

```bash
# Clone the repository
git clone [https://github.com/yourusername/PolyPrice.git](https://github.com/yourusername/PolyPrice.git)

# Navigate to the directory
cd PolyPrice

# Set up a virtual environment (Recommended)
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install

# Run the scraper
python main.py --query "mechanical keyboard"
