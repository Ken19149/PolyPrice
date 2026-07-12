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

def load_registry():
    """Safely loads target layouts and groups from external JSON matrix."""
    default_registry = {
        "groups": {"ecommerce": ["amazon_jp", "ebay"]},
        "sites": {
            "amazon_jp": "https://www.amazon.co.jp/s?k={keyword}&page={page}",
            "ebay": "https://www.ebay.com/sch/i.html?_nkw={keyword}&_pgn={page}"
        }
    }
    if os.path.exists("registry.json"):
        try:
            with open("registry.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            print("[!] Warning: 'registry.json' corrupted. Deploying internal fallbacks.")
    return default_registry

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

def fetch_site_html(url_template, site_name, keyword, page_number=1, headless_mode=True):
    safe_keyword = urllib.parse.quote(keyword)
    url = url_template.format(keyword=safe_keyword, page=page_number)
    
    time.sleep(page_number * 0.3)
    
    # --- NEW FAST-PATH FOR JSON APIs (GOD MODE) ---
    if url.endswith(".json") or ".json?" in url:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=15)
            return response.read().decode('utf-8')
        except Exception as e:
            print(f"\n    [!] API Fetch Error: {e}")
            return ""
    # ----------------------------------------------
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless_mode, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        
        if "amazon_jp" in site_name:
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

def interactive_wizard(config, registry):
    print("\n" + "="*60)
    print(" ⚡ POLYPRICE V2 - AGNOSTIC UNIVERSAL EXTRACTION ENGINE ⚡")
    print("="*60)
    print("Available CLI Arguments:")
    print("  -k, --keywords   Target terms or platform path category tokens")
    print("  -g, --group      Trigger batch profiles from directory configuration")
    print("  -s, --sites      Explicit targeting override list")
    print("  -n, --number     Target extraction cap size")
    print("  -c, --currency   Target conversion code layer\n")
    print("Configured Profiles Available: " + ", ".join(registry["groups"].keys()))
    print("-" * 60)
    print(f"DEFAULT CRON VALUES: Keys: {config['keywords']} | Sites: {config['sites']}")
    print("-" * 60)

    choice = input("\nProceed with standard run profile configurations? (y/n): ").strip().lower()
    if choice in ['y', '']: return config

    print("\n[+] Enter Target Blueprint Parameters:")
    g_input = input(f"Target Group Profile (Leave blank to select sites explicitly) []: ").strip()
    if g_input in registry["groups"]:
        config['sites'] = registry["groups"][g_input]
    else:
        s_input = input(f"Target Sites Override [{','.join(config['sites'])}]: ").strip()
        if s_input: config['sites'] = [s.strip() for s in s_input.split(',')]

    k_input = input(f"Target Categories/Keywords [{','.join(config['keywords'])}]: ").strip()
    if k_input: config['keywords'] = [k.strip() for k in k_input.split(',')]

    n_input = input(f"Extraction Target Cap Count [{config['target_quota']}]: ").strip()
    if n_input.isdigit(): config['target_quota'] = int(n_input)

    return config

if __name__ == "__main__":
    os.makedirs("exports", exist_ok=True)
    config = load_config()
    registry = load_registry()
    
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-k', '--keywords', type=str)
    parser.add_argument('-g', '--group', type=str)
    parser.add_argument('-s', '--sites', type=str)
    parser.add_argument('-n', '--number', type=int)
    parser.add_argument('-c', '--currency', type=str)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--visible', action='store_true')
    
    if len(sys.argv) == 1:
        config = interactive_wizard(config, registry)
        args = argparse.Namespace(keywords=None, group=None, sites=None, number=None, currency=None, debug=False, visible=False)
        target_sites = config["sites"]
    else:
        args, _ = parser.parse_known_args()
        if args.group and args.group in registry["groups"]:
            target_sites = registry["groups"][args.group]
        else:
            target_sites = [s.strip() for s in args.sites.split(',')] if args.sites else config["sites"]
            
    base_items = [item.strip() for item in args.keywords.split(',')] if args.keywords else config["keywords"]
    target_quota = args.number if args.number else config["target_quota"]
    base_currency = args.currency.upper() if args.currency else config["base_currency"].upper()
    debug_mode = args.debug
    headless_mode = not args.visible
    
    live_exchange_rates = fetch_live_exchange_rates(base_currency)
    
    for base_item in base_items:
        master_dataset = []
        global_compute_start = time.time()
        
        print(f"\n{'='*60}\n[*] INITIATING EXTRACTION SECTOR: {base_item.upper()}\n[*] Fleet Assignments: {target_sites}\n{'='*60}")
        
        try:
            # Skip AI SEO modifiers if targeting God Mode APIs directly
            if "goulet_pens" in target_sites and len(target_sites) == 1:
                wide_keywords_en = [base_item]
                print(f"[*] API Target Lock: Proceeding with strict nomenclature '{base_item}'")
            else:
                wide_keywords_en = generate_dynamic_modifiers(base_item)
                print(f"[*] Search Modifiers (EN): {wide_keywords_en}")
            
            for site_name in target_sites:
                if site_name not in registry["sites"]:
                    print(f"[!] Warning: '{site_name}' missing template endpoint string in registry. Skipping.")
                    continue
                    
                url_template = registry["sites"][site_name]
                print(f"\n>>> Engaging Target Profile Matrix: {site_name.upper()} <<<")
                
                extract_page_data, normalize_url = load_parser(site_name)
                
                if site_name == "amazon_jp":
                    target_keywords = [translate_to_jp(kw) for kw in wide_keywords_en]
                    print(f"[*] Translated Targeting Map (JP): {target_keywords}")
                else:
                    target_keywords = wide_keywords_en
                    
                site_unique_data = []
                seen_keys = set()
                page_num = 1
                max_pages = 200 # Increased max pages to safely grab full catalog databases
                
                while len(site_unique_data) < target_quota and page_num <= max_pages:
                    tasks = [(kw, page_num) for kw in target_keywords]
                    html_payloads = []
                    
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        future_to_task = {executor.submit(fetch_site_html, url_template, site_name, task[0], task[1], headless_mode): task for task in tasks}
                        for future in future_to_task:
                            kw, p_num = future_to_task[future]
                            try: html_payloads.append((future.result(), kw, p_num))
                            except Exception: pass
                    
                    for raw_html, kw, p_num in html_payloads:
                        if not raw_html: continue
                        extracted_items = extract_page_data(raw_html)

                        if len(extracted_items) == 0:
                            print(f"\n    [*] Database exhausted at page {p_num}. Catalog fully mapped.")
                            target_quota = len(site_unique_data) # Force the loop to complete gracefully
                            break

                        if debug_mode: 
                            print(f"\n    [!] Debug: Parser extracted {len(extracted_items)} raw objects for '{kw}' on Page {p_num}")
                        
                        for item in extracted_items:
                            # Universal Key Alignment check
                            url_key = next((k for k in item if str(k).upper() == "URL"), None)
                            url = normalize_url(item.get(url_key, "N/A")) if url_key else "N/A"
                            
                            dup_fingerprint = url if url != "N/A" else str(item)
                            
                            if dup_fingerprint not in seen_keys:
                                seen_keys.add(dup_fingerprint)
                                
                                # Dynamic schema mapping loop block
                                formatted_item = {
                                    "Platform": site_name.upper(),
                                    "Search_Term": kw
                                }
                                
                                for key, value in item.items():
                                    if str(key).upper() == "PRICE" and value != "N/A":
                                        curr, orig_val, conv_val = clean_and_convert_price(str(value), live_exchange_rates, base_currency, debug_mode)
                                        formatted_item["Original_Currency"] = curr
                                        formatted_item["Original_Price"] = orig_val
                                        formatted_item[f"Price_{base_currency}"] = conv_val
                                    else:
                                        formatted_item[key] = value
                                
                                if url_key:
                                    formatted_item["URL"] = url
                                    
                                site_unique_data.append(formatted_item)
                                
                        current_count = len(site_unique_data)
                        elapsed_time = time.time() - global_compute_start
                        sec_per_item = elapsed_time / current_count if current_count > 0 else 0
                        eta_seconds = (target_quota - current_count) * sec_per_item
                            
                        eta_mins, eta_secs = divmod(int(eta_seconds), 60)
                        bar = '█' * int(20 * min(current_count, target_quota) // target_quota) + '░' * (20 - int(20 * min(current_count, target_quota) // target_quota))
                        print(f"\r[Progress] {bar} {(min(current_count, target_quota) / target_quota) * 100:.1f}% | {current_count}/{target_quota} Rows | ETA: {eta_mins:02d}m {eta_secs:02d}s", end="")
                        
                        if current_count >= target_quota: break
                    if current_count >= target_quota: break
                    page_num += 1

                print(f"\n[*] {site_name.upper()} category segment extraction complete.")
                master_dataset.extend(site_unique_data[:target_quota])

        except KeyboardInterrupt:
            print(f"\n\n[!] Interruption caught (^C). Gracefully closing pipes and packing dataset tracking streams...")
            master_dataset.extend(site_unique_data)

        finally:
            total_time = time.time() - global_compute_start
            mins, secs = divmod(int(total_time), 60)
            print(f"[*] Total Sector Run Execution Time: {mins}m {secs}s")

            if master_dataset:
                df = pd.DataFrame(master_dataset)
                
                # Dynamically arrange column pillars to support infinite schema mutations safely
                left_anchors = ["Platform", "Search_Term"]
                right_anchors = ["URL"] if "URL" in df.columns else []
                financial_matrix = ["Original_Currency", "Original_Price", f"Price_{base_currency}"]
                financial_matrix = [f for f in financial_matrix if f in df.columns]
                
                custom_extracted_fields = [f for f in df.columns if f not in left_anchors + right_anchors + financial_matrix]
                
                ordered_blueprint = left_anchors + custom_extracted_fields + financial_matrix + right_anchors
                df = df[[col for col in ordered_blueprint if col in df.columns]]
                df.columns = [str(col).upper() for col in df.columns]
                
                safe_filename = base_item.replace(" ", "_").lower()
                export_path = f"exports/{safe_filename}_master.csv"
                
                df.to_csv(export_path, index=False, encoding='utf-8-sig')
                print(f"[*] SUCCESS: {len(df)} entries successfully committed to archive folder -> {export_path}.\n")
