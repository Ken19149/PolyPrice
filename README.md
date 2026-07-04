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

### Core Features

* **Anti-Bot Evasion:** Implements `playwright-stealth` to strip automation flags, spoof hardware concurrency, and mimic human interaction patterns (scrolling, viewport resizing).
* **Auto-Translation Layer:** Leverages `deep-translator` to dynamically convert English search inputs into target regional languages before execution.
* **Intelligent Pagination:** Programmatically constructs URLs to recursively scrape deep into search results without relying on fragile DOM click events.
* **Robust Parsing:** Utilizes `BeautifulSoup4` with fallback selectors to handle inconsistent HTML structures (e.g., handling missing prices or variable tag wrapping).
* **Normalized Output:** Exports disparate currency and string formats into a standardized Pandas DataFrame for CSV/JSON export.

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
python main.py
