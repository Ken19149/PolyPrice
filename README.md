# PolyPrice: Multilingual E-Commerce Scraper & Normalizer

PolyPrice is an automated Python utility designed to navigate, extract, and normalize product data across complex international e-commerce platforms (Amazon JP, Shopee). 

Built to handle the intricacies of modern web scraping, this tool bypasses enterprise anti-bot defenses, auto-translates search queries, and outputs clean, client-ready data.

## 🎯 The Problem

Clients frequently require pricing parity data across Asian markets, but extracting this data programmatically presents significant challenges:

1. **Enterprise Anti-Bot Firewalls:** Platforms use advanced TLS fingerprinting, canvas rendering checks, and behavioral analysis to block automated scripts.
2. **Language Barriers:** Keyword searches must be accurately localized (e.g., "Mechanical Keyboard" to "メカニカルキーボード").
3. **Dynamic Rendering:** Modern e-commerce sites rely heavily on JavaScript lazy-loading, rendering standard HTTP requests (`requests`/`curl`) ineffective.

## 🛠️ The Solution (PolyPrice Architecture)

PolyPrice utilizes **Playwright** paired with advanced stealth injections to emulate genuine human browsing behavior. 

### Core Features (Updated)
* **High-Throughput Multi-Threading:** Utilizing Python's `ThreadPoolExecutor` to launch up to 5 concurrent headless Chromium engines simultaneously, slashing total data collection time by over 70%.
* **Dynamic "Wide" Query Expansion:** Features an automatic CLI-driven modifier system that expands general terms into highly distinct niche keywords to bypass pagination thresholds entirely.
* **Smart Deduplication:** Employs Pandas-driven URL data cleaning to filter out overlapping search results across multiple queries automatically.

## 🚀 Usage

Run the multi-threaded scraper straight from your terminal by specifying a comma-separated string of categories:

## 💻 Tech Stack

* **Language:** Python 3.x
* **Browser Automation:** Playwright (Chromium)
* **Parsing:** BeautifulSoup4
* **Data Manipulation:** Pandas
* **Translation:** Deep Translator
* **Environment:** Built and tested on Arch Linux

## 🚀 Quick Start

```bash
# Clone the repository
git clone [https://github.com/yourusername/PolyPrice.git](https://github.com/yourusername/PolyPrice.git)
cd PolyPrice

# Set up a virtual environment 
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run the scraper
python main.py -k "mechanical keyboard, gaming mouse, ultra wide monitor"
