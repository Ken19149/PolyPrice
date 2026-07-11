import os
import sys
import time
import json
import argparse
import urllib.parse
import urllib.request
import re
import importlib
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from deep_translator import GoogleTranslator
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import ollama

# --- TEMPORARY SITE REGISTRY ---
SITE_REGISTRY = {
    "amazon_jp": "https://www.amazon.co.jp/s?k={keyword}&page={page}",
    "ebay": "https://www.ebay.com/sch/i.html?_nkw={keyword}&_pgn={page}"
}

def load_parser(site_name):
    """Dynamically loads the target site's parser from the /parsers folder."""
    try:
        module = importlib.import_module(f"parsers.{site_name}")
        normalizer = getattr(module, 'normalize_url', lambda url: url)
        return module.extract_page_data, normalizer
    except ImportError:
        print(f"\n[!] Fatal Error: 'parsers/{site_name}.py' is missing.")
        print(f"[!] Please run: python agent.py -s {site_name} -f <html_file>")
        sys.exit(1)

def load_config():
    default_config = {
        "keywords": ["split keyboard"],
        "target_quota": 100,
        "base_currency": "THB",
        "sites": ["amazon_jp"]
    }
    try:
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                user_config = json.load(f)
                default_config.update(user_config)
    except Exception:
        pass
    return default_config

def fetch_live_exchange_rates(base_currency):
    print(f"[*] Fetching real-time global exchange rates for {base_currency}...")
    url = f"https://open.er-api.com/v6/latest/{base_currency}"
    try:
        req = urllib.request.urlopen(url)
        data = json.loads(req.read().decode('utf-8'))
        return data.get("rates", {})
    except Exception:
        return {}

def generate_dynamic_modifiers(base_keyword):
    print(f"[*] Asking Qwen 32B to generate dynamic SEO search modifiers for '{base_keyword}'...")
    prompt = f"""You are an e-commerce SEO engine. Generate exactly 5 single-word search modifiers that shoppers use when looking for: "{base_keyword}".
Return ONLY a raw JSON object. Do not use markdown backticks."""
    strict_schema = {
        "type": "object",
        "properties": {"modifiers": {"type": "array", "items": {"type": "string"}}},
        "required": ["modifiers"]
    }
    try:
        response = ollama.generate(
            model="qwen2.5-coder:32b", 
            prompt=prompt, 
            format=strict_schema, 
            options={"temperature": 0.3, "num_predict": 150}
        )
        parsed_json = json.loads(response["response"].strip())
        modifiers = parsed_json.get("modifiers", [])
        clean_modifiers = [re.sub(r'[^a-zA-Z0-9-]', '', str(mod).lower()) for mod in modifiers[:5]]
        return [f"{mod} {base_keyword}" for mod in clean_modifiers] + [base_keyword]
    except Exception:
        return [f"premium {base_keyword}", f"budget {base_keyword}", base_keyword]

def translate_to_jp(keyword):
    return GoogleTranslator(source='en', target='ja').translate(keyword)

def fetch_site_html(site_name, keyword, page_number=1, headless_mode=True):
    url_template = SITE_REGISTRY.get(site_name, SITE_REGISTRY["amazon_jp"])
    safe_keyword = urllib.parse.quote(keyword)
    url = url_template.format(keyword=safe_keyword, page=page_number)
    
    # Introduce a slight time stagger to break up concurrent thread execution bursts
    time.sleep(page_number * 0.3)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless_mode, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        
        if site_name == "amazon_jp":
            locale, tz = "ja-JP", "Asia/Tokyo"
        else:
            locale, tz = "en-US", "America/New_York"

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", 
            locale=locale, timezone_id=tz
        )
        Stealth().apply_stealth_sync(context)
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000) 
            
            # IMPLEMENTING THE REFRESH TRICK: Catch error screens or WAF blocks immediately
            if "Something went wrong on our end" in page.content() or "Error Page" in page.title():
                print(f"\n    [!] WAF/Error detected on {site_name.upper()}. Executing reload bypass...")
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
            
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
            page.wait_for_timeout(1000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            page.wait_for_timeout(1000)
            html = page.content()
        except Exception: html = ""
        finally: browser.close()
        return html

def clean_and_convert_price(raw_price, live_rates, base_currency, debug_mode=False):
    if not isinstance(raw_price, str) or not raw_price.strip() or raw_price.upper() == "N/A": 
        if debug_mode: print(f"\n    [!] Debug: Missing/Hidden Price Detected -> Raw Input: '{raw_price}'")
        return "UNKNOWN", None, None
        
    currency = "UNKNOWN"
    if re.search(r'(THB)', raw_price, re.IGNORECASE): currency = 'THB'
    elif re.search(r'(￥|JPY|円)', raw_price, re.IGNORECASE): currency = 'JPY'
    elif re.search(r'(\$|USD)', raw_price, re.IGNORECASE): currency = 'USD'
    elif re.search(r'(EUR|€)', raw_price, re.IGNORECASE): currency = 'EUR'

    cleaned_string = re.sub(r'[^\d.,]', ' ', raw_price)
    numbers = [n for n in cleaned_string.split() if re.match(r'^[0-9,.]+$', n)]
    
    orig_val, conv_val = None, None
    if numbers:
        try: orig_val = float(numbers[-1].rstrip('.').replace(',', ''))
        except ValueError: pass
            
    if orig_val is not None:
        if currency == "UNKNOWN": currency = "JPY" if "amazon_jp" in sys.argv else "USD"
        if currency == base_currency: conv_val = orig_val
        elif live_rates and currency in live_rates: 
            conv_val = round(orig_val / live_rates[currency], 2)
            
    return currency, orig_val, conv_val

def interactive_wizard(config):
    print("\n" + "="*60)
    print(" ⚡ POLYPRICE V2 - HYBRID AGENTIC EXTRACTOR ⚡")
    print("="*60)
    print("Available CLI Arguments:")
    print("  -k, --keywords   Comma-separated list of items")
    print("  -n, --number     Target quota of items PER site")
    print("  -c, --currency   Target conversion currency (e.g., USD, THB)")
    print("  -s, --sites      Comma-separated list of sites (e.g., amazon_jp, ebay)")
    print("  --debug          Show verbose output for missing prices")
    print("  --visible        Run the extraction fleet with visible browser windows\n")
    print("Example Usage:")
    print("  python orchestrator.py -k \"fountain pen, mechanical keyboard\" -s \"amazon_jp, ebay\" -n 500 --visible\n")
    print("-" * 60)
    print("CURRENT DEFAULT CONFIGURATION:")
    print(f"  Keywords: {config['keywords']}")
    print(f"  Sites:    {config['sites']}")
    print(f"  Quota:    {config['target_quota']} items per site")
    print(f"  Currency: {config['base_currency']}")
    print("-" * 60)

    choice = input("\nProceed with this default configuration? (y/n): ").strip().lower()
    if choice == 'y' or choice == '':
        return config

    print("\n[+] Let's configure your run:")
    k_input = input(f"Keywords (comma separated) [{','.join(config['keywords'])}]: ").strip()
    if k_input: config['keywords'] = [k.strip() for k in k_input.split(',')]

    s_input = input(f"Target Sites (comma separated) [{','.join(config['sites'])}]: ").strip()
    if s_input: config['sites'] = [s.strip() for s in s_input.split(',')]

    n_input = input(f"Target Quota per site [{config['target_quota']}]: ").strip()
    if n_input.isdigit(): config['target_quota'] = int(n_input)

    c_input = input(f"Base Currency [{config['base_currency']}]: ").strip()
    if c_input: config['base_currency'] = c_input.upper()

    return config

if __name__ == "__main__":
    os.makedirs("exports", exist_ok=True)
    config = load_config()
    
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-k', '--keywords', type=str)
    parser.add_argument('-n', '--number', type=int)
    parser.add_argument('-c', '--currency', type=str)
    parser.add_argument('-s', '--sites', type=str)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--visible', action='store_true')
    
    if len(sys.argv) == 1:
        config = interactive_wizard(config)
        args = argparse.Namespace(keywords=None, number=None, currency=None, sites=None, debug=False, visible=False)
    else:
        args, _ = parser.parse_known_args()
    
    base_items = [item.strip() for item in args.keywords.split(',')] if args.keywords else config["keywords"]
    target_sites = [s.strip() for s in args.sites.split(',')] if args.sites else config["sites"]
    target_quota = args.number if args.number else config["target_quota"]
    base_currency = args.currency.upper() if args.currency else config["base_currency"].upper()
    debug_mode = args.debug
    headless_mode = not args.visible
    
    live_exchange_rates = fetch_live_exchange_rates(base_currency)
    
    for base_item in base_items:
        master_dataset = []
        global_compute_start = time.time()
        
        print(f"\n{'='*60}")
        print(f"[*] INITIATING MULTI-SITE EXTRACTION: {base_item.upper()}")
        print(f"[*] Target Sites: {target_sites}")
        print(f"[*] Quota: {target_quota} per site | Base Currency: {base_currency}")
        print(f"{'='*60}")
        
        # GLOBAL INTERRUPTION HANDLER - Moved to the very top of the keyword loop
        try:
            wide_keywords_en = generate_dynamic_modifiers(base_item)
            print(f"[*] Search Modifiers (EN): {wide_keywords_en}")
            
            for site_name in target_sites:
                print(f"\n>>> Engaging Target: {site_name.upper()} <<<")
                
                extract_page_data, normalize_url = load_parser(site_name)
                
                if site_name == "amazon_jp":
                    target_keywords = [translate_to_jp(kw) for kw in wide_keywords_en]
                    print(f"[*] Translated Targeting Map (JP): {target_keywords}")
                else:
                    target_keywords = wide_keywords_en
                    
                site_unique_data = []
                seen_urls = set()
                page_num = 1
                max_pages = 15 
                
                while len(site_unique_data) < target_quota and page_num <= max_pages:
                    tasks = [(kw, page_num) for kw in target_keywords]
                    html_payloads = []
                    
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        future_to_task = {executor.submit(fetch_site_html, site_name, task[0], task[1], headless_mode): task for task in tasks}
                        for future in future_to_task:
                            kw, p_num = future_to_task[future]
                            try: html_payloads.append((future.result(), kw, p_num))
                            except Exception: pass
                    
                    for raw_html, kw, p_num in html_payloads:
                        if not raw_html: continue
                        
                        extracted_items = extract_page_data(raw_html)

                        if debug_mode: 
                            print(f"\n    [!] Debug: Parser extracted {len(extracted_items)} items for '{kw}' on Page {p_num}")
                        
                        for item in extracted_items:
                            url = normalize_url(item.get("URL", "N/A"))
                            
                            if url not in seen_urls and url != "N/A":
                                seen_urls.add(url)
                                
                                formatted_item = {
                                    "Platform": site_name.upper(),
                                    "Search_Term": kw,
                                    "Title": item.get("Title", "N/A").replace('\n', ' ').strip(),
                                    "URL": url
                                }
                                
                                raw_price = str(item.get("Price", ""))
                                curr, orig_val, conv_val = clean_and_convert_price(raw_price, live_exchange_rates, base_currency, debug_mode)
                                
                                formatted_item["Original_Currency"] = curr
                                formatted_item["Original_Price"] = orig_val
                                formatted_item[f"Price_{base_currency}"] = conv_val
                                
                                site_unique_data.append(formatted_item)
                                
                        # ETA CALCULATIONS RESTORED
                        current_count = len(site_unique_data)
                        elapsed_time = time.time() - global_compute_start
                        sec_per_item = elapsed_time / current_count if current_count > 0 else 0
                        eta_seconds = (target_quota - current_count) * sec_per_item
                            
                        eta_mins, eta_secs = divmod(int(eta_seconds), 60)
                        bar_len = 20
                        filled = int(bar_len * min(current_count, target_quota) // target_quota)
                        bar = '█' * filled + '░' * (bar_len - filled)
                        percent = (min(current_count, target_quota) / target_quota) * 100
                        
                        print(f"\r[Progress] {bar} {percent:.1f}% | {current_count}/{target_quota} Items | ETA: {eta_mins:02d}m {eta_secs:02d}s", end="")
                        
                        if current_count >= target_quota: break
                    
                    if current_count >= target_quota: break
                    page_num += 1

                print(f"\n[*] {site_name.upper()} extraction complete.")
                master_dataset.extend(site_unique_data[:target_quota])

        except KeyboardInterrupt:
            print(f"\n\n[!] Interruption caught (^C). Gracefully halting {base_item} pipeline...")
            # If interrupted, make sure we save whatever was collected for the current site
            master_dataset.extend(site_unique_data)
            
        finally:
            total_time = time.time() - global_compute_start
            mins, secs = divmod(int(total_time), 60)
            print(f"[*] Extraction Time: {mins}m {secs}s")

            if master_dataset:
                df = pd.DataFrame(master_dataset)
                
                # COLUMN ORDERING AND CAPITALIZATION RESTORED
                columns_order = ["Platform", "Search_Term", "Title", "Original_Currency", "Original_Price", f"Price_{base_currency}", "URL"]
                columns_order = [c for c in columns_order if c in df.columns]
                df = df[columns_order]
                df.columns = [str(col).upper() for col in df.columns]
                
                safe_filename = base_item.replace(" ", "_").lower()
                export_path = f"exports/{safe_filename}_master.csv"
                
                # UTF-8-SIG RESTORED
                df.to_csv(export_path, index=False, encoding='utf-8-sig')
                print(f"[*] SUCCESS: {len(df)} perfectly unique records saved to {export_path}.\n")
