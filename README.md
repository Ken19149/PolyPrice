# PolyPrice: AI-Driven E-Commerce Extraction Pipeline

PolyPrice is a high-performance, multi-threaded web scraper and data extraction pipeline. Instead of relying on brittle HTML class targeting, it leverages local Large Language Models (LLMs) to intelligently parse, sterilize, and structure e-commerce data directly from raw DOM text.

## 🚀 Key Architectural Features

### 1. LLM-Powered DOM Parsing (Zero-Shot Extraction)
Traditional scrapers break whenever a website updates its CSS classes. PolyPrice bypasses this entirely. By feeding sanitized, chunked text to a local **Qwen 2.5 (7B)** model via Ollama, the pipeline autonomously identifies products, prices, and links, returning perfectly formatted JSON arrays regardless of layout changes.

### 2. Token-Safe Batch Chunking
To prevent LLM hallucinations and memory overflows (context window limits), the pipeline utilizes dynamic batch processing. It slices massive HTML element arrays into token-safe payloads (e.g., 15 items per chunk), feeding them to the GPU sequentially to guarantee output stability.

### 3. RegEx ASIN Sterilization & Deduplication
E-commerce platforms like Amazon heavily obscure product links with volatile tracking parameters and sponsored ad redirects. PolyPrice utilizes aggressive RegEx to extract the core Amazon Standard Identification Number (ASIN). This normalizes the URLs, allowing the Pandas backend to strictly and accurately deduplicate the final dataset.

### 4. Graceful Pipeline Interruptions (Checkpointing)
Data engineering pipelines should never lose data due to a manual halt. PolyPrice wraps its main execution loop in a strict `SIGINT` (Ctrl+C) trap. If the script is interrupted at any point, the `finally` recovery net catches the signal and safely dumps all data processed up to that exact millisecond into `PolyPrice_Results.csv`.

### 5. Multi-Threaded Headless Fetching
Network I/O and GPU Compute I/O are separated. PolyPrice fires up a `ThreadPoolExecutor` using Playwright Stealth to concurrently download targeted web pages in the background, fully saturating the network connection before passing the payload to the local LLM for sequential processing.

---

## 🛠️ Tech Stack

*   **Language:** Python 3
*   **LLM Engine:** Ollama (Qwen 2.5 7B)
*   **Browser Automation:** Playwright (with Stealth plugin)
*   **Data Processing:** Pandas, BeautifulSoup4, RegEx
*   **Concurrency:** `concurrent.futures.ThreadPoolExecutor`

---

## ⚙️ Installation & Setup

**1. Clone the repository and set up your virtual environment:**
```bash
git clone [https://github.com/yourusername/PolyPrice.git](https://github.com/yourusername/PolyPrice.git)
cd PolyPrice
python -m venv .venv
source .venv/bin/activate```

**2. Install Python dependencies:**
```bash
pip install pandas bs4 deep-translator playwright playwright-stealth ollama
playwright install chromium
```

**3. Install and run Ollama with the Qwen 2.5 model:**
Ensure you have the appropriate CUDA drivers installed for your Linux distribution to enable GPU acceleration.
```bash
ollama pull qwen2.5:7b
sudo systemctl start ollama```

## 💻 Usage
Run the script from your terminal, passing in the base keywords you want to extract. The pipeline will automatically generate variations (wireless, gaming, budget, etc.), translate them, and begin extraction.

```bash
python main.py -k "keyboard, mouse, monitor"```

Output:
The terminal will display a real-time progress bar with Rolling Average ETA calculations. Upon completion (or manual interruption), the cleaned, deduplicated dataset will be saved to PolyPrice_Results.csv in your root directory.

## 🔮 Future Roadmap (The Universal Scraper)

The next evolution of PolyPrice is shifting from targeted div isolation to full-page Markdown Conversion. By parsing an entire website's HTML body into Markdown and passing it to the LLM agent dynamically, PolyPrice will become a platform-agnostic data engine capable of extracting structured JSON from any website in the world using a simple CLI prompt format:
python main.py -a "<URL>" -t "title, price, condition"
