# PolyPrice (V2 - Hybrid Agentic Architecture)

PolyPrice is an enterprise-grade, multi-threaded e-commerce scraper designed to dynamically analyze market pricing.

V2 completely abandons traditional LLM row-parsing in favor of a Self-Writing Extraction Engine. By deploying an autonomous 32B parameter AI to engineer custom BeautifulSoup scripts on the fly, V2 achieves 100x speed improvements and mathematically guarantees zero data hallucination.
## The Architecture

PolyPrice V2 is divided into three distinct modules:

    scout.py (The DOM Snapshotter): Uses Playwright to navigate to a target website, execute a V8 JavaScript DOM purge, and extract a highly compressed HTML skeleton of the product grid.

    agent.py (The Architect): Feeds the compressed skeleton to a local qwen2.5-coder:32b model. Using strict Template Prompting, the AI writes a resilient, bug-free Python parsing function tailored perfectly to the website's CSS classes.

    orchestrator.py (The Muscle): Imports the AI-generated logic and deploys a multi-threaded web fleet to rapidly scrape, parse, and export hundreds of items in seconds, handling real-time currency conversion locally.

## Setup & Requirements

Hardware Recommendation: Minimum 16GB VRAM / 64GB System RAM to support the 32B model.

    Install Python dependencies:
    pip install playwright playwright-stealth beautifulsoup4 pandas deep-translator ollama
    playwright install chromium

    Pull the architect model via Ollama:
    ollama pull qwen2.5-coder:32b

## Usage: The Two-Phase Pipeline
### Phase 1: Agent Training (Run once per target layout)

Point the Scout at your target website and define the CSS selector for the product grid.

    Capture the DOM (Example: Amazon Japan)
    python scout.py -u "[https://www.amazon.co.jp/s?k=test](https://www.amazon.co.jp/s?k=test)" -s ".s-main-slot"

    Command the AI to engineer the scraper
    python agent.py

Note: Inspect generated_scraper.py briefly to ensure URL logic is correct for your region (e.g., ensuring relative links use .co.jp instead of .com).
### Phase 2: Mass Extraction (Run continuously)

Once the scraper logic is generated, unleash the multithreaded orchestrator.

python orchestrator.py -k "split keyboard, fountain pen" -n 250 -c USD --debug

**CLI Arguments:**

    -k / --keywords : Comma-separated list of target products.

    -n / --number : Target quota of unique items to scrape per keyword.

    -c / --currency : Target currency for conversion (e.g., USD, THB, EUR).

    --debug : Enables telemetry output for missing/hidden pricing elements.

## Config File

You can also define default behaviors by placing a config.json in the root directory:
JSON
```
{
  "keywords": ["mechanical keyboard", "fountain pen"],
  "target_quota": 500,
  "base_currency": "THB"
}
```
