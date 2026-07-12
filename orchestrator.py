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
from datetime import datetime
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
            "amazon_jp": {
                "url": "https://www.amazon.co.jp/s?k={keyword}&page={page}",
                "parser": "amazon_jp",
                "domain": "https://www.amazon.co.jp"
            },
            "ebay": {
                "url": "https://www.ebay.com/sch/i.html?_nkw={keyword}&_pgn={page}",
                "parser": "ebay",
                "domain": "https://www.ebay.com"
            }
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
        normalizer = getattr(module, 'normalize_url', lambda url, domain="": url)
        return module.extract_page_data, normalizer
    except ImportError:
        print(f"\n[!] Fatal Error: 'parsers/{site_name}.py' is missing.")
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
    
    # --- FAST-PATH FOR JSON APIs (GOD MODE) ---
    if url.endswith(".json") or ".json?" in url:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=15)
            return response.read().decode('utf-8')
        except Exception as e:
            print(f"\n    [!] API Fetch Error on {site_name.upper()}: {e}")
            return ""
    # ----------------------------------------------
    
    time.sleep(page_number * 0.3)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless_mode, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        locale, tz = ("ja-JP", "Asia/Tokyo") if "amazon_jp" in site_name else ("en-US", "America/New_York")

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", 
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

def save_dataframe(data_list, group_folder, filename_prefix, base_currency):
    if not data_list: return
    df = pd.DataFrame(data_list)
    
    left_anchors = ["Platform", "Search_Term"]
    right_anchors = ["URL"] if "URL" in df.columns else []
    financial_matrix = ["Original_Currency", "Original_Price", f"Price_{base_currency}"]
    financial_matrix = [f for f in financial_matrix if f in df.columns]
    
    custom_extracted_fields = [f for f in df.columns if f not in left_anchors + right_anchors + financial_matrix]
    
    ordered_blueprint = left_anchors + custom_extracted_fields + financial_matrix + right_anchors
    df = df[[col for col in ordered_blueprint if col in df.columns]]
    df.columns = [str(col).upper() for col in df.columns]
    
    os.makedirs(f"exports/{group_folder}", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_path = f"exports/{group_folder}/{filename_prefix}_{timestamp}.csv"
    
    df.to_csv(export_path, index=False, encoding='utf-8-sig')
    print(f"[*] SUCCESS: {len(df)} entries successfully committed to archive folder -> {export_path}.\n")

def interactive_wizard(config, registry):
    print("\n" + "="*60)
    print(" ⚡ POLYPRICE V2 - AGNOSTIC UNIVERSAL EXTRACTION ENGINE ⚡")
    print("="*60)
    print("Available CLI Arguments:")
    print("  -k, --keywords   Target terms or platform path category tokens")
    print("  -g, --group      Trigger batch profiles from directory configuration")
    print("  -s, --sites      Explicit targeting override list")
    print("  -n, --number     Target extraction cap size")
    print("  -c, --currency   Target conversion code layer")
    print("  --all            Run omni-sweep across all God Mode catalogs\n")
    print("Configured Profiles Available: " + ", ".join(registry["groups"].keys()))
    print("-" * 60)
    
    choice = input("\nProceed with standard run profile configurations? (y/n): ").strip().lower()
    if choice in ['y', '']: return config

    print("\n[+] Enter Target Blueprint Parameters:")
    g_input = input(f"Target Group Profile (Leave blank to select sites explicitly) []: ").strip().lower()
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
    parser.add_argument('--all', action='store_true', help="Run omni-sweep across all God Mode catalogs")
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--visible', action='store_true')
    
    args, _ = parser.parse_known_args()
    
    if len(sys.argv) == 1:
        config = interactive_wizard(config, registry)
        args = argparse.Namespace(keywords=None, group=None, sites=None, number=None, currency=None, debug=False, visible=False, all=False)
        target_sites = config["sites"]
        chosen_group = "interactive"
    else:
        chosen_group = args.group.lower() if args.group else "misc"

    target_quota = args.number if args.number else config["target_quota"]
    base_currency = args.currency.upper() if args.currency else config["base_currency"].upper()
    debug_mode = args.debug
    headless_mode = not args.visible
    live_exchange_rates = fetch_live_exchange_rates(base_currency)

    # ==========================================
    # PATH A: OMNI-SWEEP (GOD MODE ONLY)
    # ==========================================
    if args.all:
        print("\n" + "="*60)
        print(" 🌐 INITIATING GLOBAL OMNI-SWEEP (GOD MODE) 🌐")
        print("="*60)
        
        for group_name, sites in registry["groups"].items():
            for site_name in sites:
                site_config = registry["sites"].get(site_name, {})
                if "{keyword}" in site_config.get("url", ""):
                    print(f"[-] Skipping {site_name.upper()} (Requires explicit keyword query)")
                    continue
                
                print(f"\n>>> Engaging Target Profile Matrix: {site_name.upper()} [{group_name.upper()}] <<<")
                
                url_template = site_config["url"]
                parser_target = site_config["parser"]
                base_domain = site_config.get("domain", "")
                extract_page_data, normalize_url = load_parser(parser_target)
                
                site_unique_data = []
                seen_keys = set()
                page_num = 1
                max_pages = 200 
                current_count = 0
                global_compute_start = time.time()
                
                site_quota = target_quota 
                
                try:
                    while len(site_unique_data) < site_quota and page_num <= max_pages:
                        current_batch_pages = [page_num + i for i in range(5) if (page_num + i) <= max_pages]
                        html_payloads = []
                        
                        with ThreadPoolExecutor(max_workers=5) as executor:
                            future_to_task = {executor.submit(fetch_site_html, url_template, site_name, "catalog", p, headless_mode): p for p in current_batch_pages}
                            for future in future_to_task:
                                p_num = future_to_task[future]
                                try:
                                    res = future.result()
                                    if res.strip(): html_payloads.append((res, "catalog", p_num))
                                except Exception: pass
                        
                        html_payloads.sort(key=lambda x: x[2])
                        exhausted = False
                        
                        for raw_html, kw, p_num in html_payloads:
                            extracted_items = extract_page_data(raw_html)

                            if len(extracted_items) == 0:
                                print(f"\n    [*] Database exhausted at page {p_num}. Catalog fully mapped.")
                                site_quota = len(site_unique_data) 
                                exhausted = True
                                break

                            previous_count = len(site_unique_data)

                            for item in extracted_items:
                                url_key = next((k for k in item if str(k).upper() == "URL"), None)
                                try: url = normalize_url(item.get(url_key, "N/A"), base_domain) if url_key else "N/A"
                                except TypeError: url = normalize_url(item.get(url_key, "N/A")) if url_key else "N/A"
                                
                                dup_fingerprint = url if url != "N/A" else str(item)
                                if dup_fingerprint not in seen_keys:
                                    seen_keys.add(dup_fingerprint)
                                    formatted_item = {"Platform": site_name.upper(), "Search_Term": "Full Catalog"}
                                    for key, value in item.items():
                                        if str(key).upper() == "PRICE" and value != "N/A":
                                            curr, orig_val, conv_val = clean_and_convert_price(str(value), live_exchange_rates, base_currency, debug_mode)
                                            formatted_item["Original_Currency"], formatted_item["Original_Price"], formatted_item[f"Price_{base_currency}"] = curr, orig_val, conv_val
                                        else: formatted_item[key] = value
                                    if url_key: formatted_item["URL"] = url
                                    site_unique_data.append(formatted_item)

                            if len(site_unique_data) == previous_count:
                                print(f"\n    [*] Pagination trap detected at page {p_num}. Halting extraction.")
                                site_quota = len(site_unique_data)
                                exhausted = True
                                break
                                    
                            current_count = len(site_unique_data)
                            elapsed_time = time.time() - global_compute_start
                            sec_per_item = elapsed_time / current_count if current_count > 0 else 0
                            eta_seconds = (site_quota - current_count) * sec_per_item
                            eta_mins, eta_secs = divmod(int(eta_seconds), 60)
                            bar = '█' * int(20 * min(current_count, site_quota) // site_quota) + '░' * (20 - int(20 * min(current_count, site_quota) // site_quota))
                            print(f"\r[Progress] {bar} {(min(current_count, site_quota) / site_quota) * 100:.1f}% | {current_count} Rows | ETA: {eta_mins:02d}m {eta_secs:02d}s", end="")
                            
                            if current_count >= site_quota: break
                        if exhausted or current_count >= site_quota: break
                        page_num += 5
                        
                    print(f"\n[*] {site_name.upper()} category segment extraction complete.")
                
                except KeyboardInterrupt:
                    print("\n\n[!] EMERGENCY STOP (^C). Halting extraction and packing secured data...")
                
                finally:
                    # Executes no matter what, securing the data to the hard drive
                    save_dataframe(site_unique_data[:site_quota], group_name, site_name, base_currency)

    # ==========================================
    # PATH B: STANDARD KEYWORD/GROUP TARGETING
    # ==========================================
    else:
        if args.group and chosen_group in registry["groups"]: target_sites = registry["groups"][chosen_group]
        else: target_sites = [s.strip() for s in args.sites.split(',')] if args.sites else config["sites"]
            
        base_items = [item.strip() for item in args.keywords.split(',')] if args.keywords else config["keywords"]
        
        for base_item in base_items:
            master_dataset = []
            global_compute_start = time.time()
            
            print(f"\n{'='*60}\n[*] INITIATING EXTRACTION SECTOR: {base_item.upper()}\n[*] Fleet Assignments: {target_sites}\n{'='*60}")
            
            try:
                is_all_god_mode = all("{keyword}" not in registry["sites"].get(site, {}).get("url", "") for site in target_sites)
                
                if is_all_god_mode:
                    wide_keywords_en = [base_item]
                    print(f"[*] Shopify API Target Lock: Bypassing LLM SEO generation for '{base_item}'")
                else:
                    wide_keywords_en = generate_dynamic_modifiers(base_item)
                    print(f"[*] Search Modifiers (EN): {wide_keywords_en}")
                    
                for site_name in target_sites:
                    if site_name not in registry["sites"]: continue
                    site_config = registry["sites"][site_name]
                    url_template = site_config["url"]
                    parser_target = site_config["parser"]
                    base_domain = site_config.get("domain", "")
                    
                    print(f"\n>>> Engaging Target Profile Matrix: {site_name.upper()} [Routing -> {parser_target}.py] <<<")
                    extract_page_data, normalize_url = load_parser(parser_target)
                    
                    target_keywords = [translate_to_jp(kw) for kw in wide_keywords_en] if site_name == "amazon_jp" else wide_keywords_en
                        
                    site_unique_data = []
                    seen_keys = set()
                    page_num = 1
                    max_pages = 200 
                    current_count = 0
                    site_quota = target_quota
                    
                    while len(site_unique_data) < site_quota and page_num <= max_pages:
                        tasks = [(kw, page_num) for kw in target_keywords]
                        html_payloads = []
                        
                        with ThreadPoolExecutor(max_workers=5) as executor:
                            future_to_task = {executor.submit(fetch_site_html, url_template, site_name, task[0], task[1], headless_mode): task for task in tasks}
                            for future in future_to_task:
                                kw, p_num = future_to_task[future]
                                try:
                                    res = future.result()
                                    if res.strip(): html_payloads.append((res, kw, p_num))
                                except Exception: pass
                        
                        if not html_payloads: 
                            print(f"    [!] Sector channel target {site_name.upper()} returned zero tracking data vectors. Breaking loop.")
                            break
                            
                        for raw_html, kw, p_num in html_payloads:
                            extracted_items = extract_page_data(raw_html)

                            if len(extracted_items) == 0:
                                print(f"\n    [*] Database exhausted at page {p_num}. Catalog fully mapped.")
                                site_quota = len(site_unique_data)
                                break
                            
                            previous_count = len(site_unique_data)

                            for item in extracted_items:
                                url_key = next((k for k in item if str(k).upper() == "URL"), None)
                                try: url = normalize_url(item.get(url_key, "N/A"), base_domain) if url_key else "N/A"
                                except TypeError: url = normalize_url(item.get(url_key, "N/A")) if url_key else "N/A"
                                
                                dup_fingerprint = url if url != "N/A" else str(item)
                                if dup_fingerprint not in seen_keys:
                                    seen_keys.add(dup_fingerprint)
                                    formatted_item = {"Platform": site_name.upper(), "Search_Term": kw}
                                    for key, value in item.items():
                                        if str(key).upper() == "PRICE" and value != "N/A":
                                            curr, orig_val, conv_val = clean_and_convert_price(str(value), live_exchange_rates, base_currency, debug_mode)
                                            formatted_item["Original_Currency"], formatted_item["Original_Price"], formatted_item[f"Price_{base_currency}"] = curr, orig_val, conv_val
                                        else: formatted_item[key] = value
                                    if url_key: formatted_item["URL"] = url
                                    site_unique_data.append(formatted_item)

                            if len(site_unique_data) == previous_count:
                                print(f"\n    [*] Pagination trap detected at page {p_num}. Halting extraction.")
                                site_quota = len(site_unique_data)
                                break
                                    
                            current_count = len(site_unique_data)
                            elapsed_time = time.time() - global_compute_start
                            sec_per_item = elapsed_time / current_count if current_count > 0 else 0
                            eta_seconds = (site_quota - current_count) * sec_per_item
                            eta_mins, eta_secs = divmod(int(eta_seconds), 60)
                            bar = '█' * int(20 * min(current_count, site_quota) // site_quota) + '░' * (20 - int(20 * min(current_count, site_quota) // site_quota))
                            print(f"\r[Progress] {bar} {(min(current_count, site_quota) / site_quota) * 100:.1f}% | {current_count} Rows | ETA: {eta_mins:02d}m {eta_secs:02d}s", end="")
                            
                            if current_count >= site_quota: break
                        if current_count >= site_quota: break
                        page_num += 1

                    print(f"\n[*] {site_name.upper()} category segment extraction complete.")
                    master_dataset.extend(site_unique_data[:site_quota])

            except KeyboardInterrupt:
                print("\n\n[!] EMERGENCY STOP (^C). Halting extraction and packing secured data...")
            
            finally:
                # Executes no matter what, securing the data to the hard drive
                safe_filename = base_item.replace(" ", "_").lower()
                save_dataframe(master_dataset, chosen_group, safe_filename, base_currency)
