# PolyPrice (V2 - Hybrid Agentic Architecture)

PolyPrice is an enterprise-grade, multi-threaded e-commerce extraction and arbitrage engine designed to dynamically map market pricing and track global inventory.

V2 completely abandons traditional, brittle LLM row-parsing. By deploying an autonomous 32B parameter AI to engineer custom BeautifulSoup scripts on the fly—combined with a direct JSON API bypass for standard e-commerce architectures—V2 achieves 100x speed improvements and mathematically guarantees zero data hallucination.
## 🏗️ The Architecture

PolyPrice V2 is divided into five distinct operational modules:

    scout.py (The DOM Snapshotter): Uses Playwright to navigate complex target websites, executes a V8 JavaScript DOM purge, and extracts a highly compressed HTML skeleton of the product grid to bypass Enterprise WAFs.

    agent.py (The Architect): Feeds the compressed HTML skeleton to a local qwen2.5-coder:32b model. Using strict Template Prompting, the AI writes a resilient, bug-free Python parsing function tailored perfectly to the website's CSS classes.

    orchestrator.py (The Muscle): Imports the AI-generated logic and deploys a multi-threaded web fleet to rapidly scrape, parse, and export hundreds of items in seconds. Features a "God Mode" bypass that automatically intercepts and parses /products.json endpoints on Shopify-hosted storefronts.

    analyze.py (The Brain): A headless data consolidation layer that unifies legacy currencies, merges fleet datasets by sector, and runs lightning-fast Jaccard Similarity tokenization to detect cross-platform pricing arbitrage anomalies.

    dashboard.py (The Visor): A lightweight Streamlit UI for interactive data filtering, historical archive tracking, and brand distribution charting.

## ⚙️ Setup & Requirements

Hardware Recommendation: Minimum 16GB VRAM / 64GB System RAM to support the 32B local model.

**1. Install Python Dependencies:**
```
Bash

pip install playwright playwright-stealth beautifulsoup4 pandas deep-translator ollama streamlit
playwright install chromium
```

**2. Pull the Architect Model (via Ollama):**
```
Bash

ollama pull qwen2.5-coder:32b
```

## 🛠️ Configuration

Define your extraction ecosystems using the registry.json file. This acts as the targeting matrix for your data sweeps.
```
JSON

{
  "groups": {
    "keyboards": ["kbdfans", "novelkeys", "cannonkeys"],
    "stationery": ["goulet_pens", "yoseka"]
  },
  "sites": {
    "yoseka": {
      "url": "https://yosekastationery.com/products.json?limit=250&page={page}",
      "parser": "shopify",
      "domain": "https://yosekastationery.com"
    }
  }
}
```

## 🚀 Usage: The Four-Phase Pipeline
### Phase 1: Agent Training (Run once per custom HTML target)

For sites without open APIs (e.g., Amazon, eBay), point the Scout at your target website and define the CSS selector for the product grid.

    **Capture the DOM:**
```
    Bash

    python scout.py -u "https://www.amazon.co.jp/s?k=test" -s ".s-main-slot"
```
    **Command the AI to engineer the scraper:**
```
    Bash

    python agent.py
```

### Phase 2: Mass Extraction

Unleash the multi-threaded orchestrator. It will automatically route to the correct parser, translate queries, execute the WAF-evasion loop, and save timestamped CSVs into dedicated group folders (e.g., exports/keyboards/).

**Targeted Keyword Sweep:**
```
Bash

python orchestrator.py -g keyboards -k "split keyboard, switches" -n 250 -c USD
```

**Global Omni-Sweep (God Mode):**
Downloads the entire catalog of every site mapped in your registry.json.
```
Bash

python orchestrator.py --all
```

### Phase 3: Market Intelligence & Arbitrage

Analyze your isolated domain sectors to find pricing anomalies and track inventory.

**View Sector Synthesis Summary:**
```
Bash

python analyze.py -g keyboards --summary
```

**Cross-Platform Asset Tracking:**
```
Bash

python analyze.py -g keyboards --compare "GMK"
```

**Automated Arbitrage Scanner:**
Executes Jaccard Similarity tokenization to find identical products priced differently across competitors.
```
Bash

python analyze.py -g stationery --arbitrage
```

### Phase 4: Data Visualization

Launch the interactive web dashboard to view data feeds without terminal clutter.
```
Bash

streamlit run dashboard.py
```
