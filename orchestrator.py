import os
import time
import json
import argparse
import urllib.parse
import urllib.request
import re
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from deep_translator import GoogleTranslator
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import ollama

try:
    from generated_scraper import extract_page_data
except ImportError:
    print("[!] Fatal Error: 'generated_scraper.py' is missing.")
    print("[!] Please run scout.py and agent.py to generate the extraction logic first.")
    exit(1)

def load_config():
    default_config = {
        "keywords": ["split keyboard"],
        "target_quota": 100,
        "base_currency": "THB"
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

def fetch_amazon_jp_html(keyword, page_number=1):
    safe_keyword = urllib.parse.quote(keyword)
    url = f"https://www.amazon.co.jp/s?k={safe_keyword}&page={page_number}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        # Spoofing a Tokyo machine to bypass the "Ships to Thailand" price block
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", 
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            geolocation={"longitude": 139.6917, "latitude": 35.6895},
            permissions=["geolocation"],
            extra_http_headers={
                "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
                "X-Forwarded-For": "202.214.194.147" # A generic Tokyo IP
            }
        )
        Stealth().apply_stealth_sync(context)
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000) 
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
            page.wait_for_timeout(1000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            page.wait_for_timeout(1000)
            html = page.content()
        except Exception:
            html = ""
        finally:
            browser.close()
        return html

def clean_and_convert_price(raw_price, live_rates, base_currency, debug_mode=False):
    if not isinstance(raw_price, str) or not raw_price.strip() or raw_price.upper() == "N/A": 
        if debug_mode: print(f"    [!] Debug: Missing/Hidden Price Detected -> Raw Input: '{raw_price}'")
        return "UNKNOWN", None, None
        
    currency = "UNKNOWN"
    if re.search(r'(THB)', raw_price, re.IGNORECASE): currency = 'THB'
    elif re.search(r'(￥|JPY|円)', raw_price, re.IGNORECASE): currency = 'JPY'
    elif re.search(r'(\$|USD)', raw_price, re.IGNORECASE): currency = 'USD'
    elif re.search(r'(EUR|€)', raw_price, re.IGNORECASE): currency = 'EUR'

    cleaned_string = re.sub(r'[^\d.,]', ' ', raw_price)
    numbers = [n for n in cleaned_string.split() if re.match(r'^[0-9,.]+$', n)]
    
    original_val = None
    converted_val = None
    
    if numbers:
        val_str = numbers[-1].rstrip('.') 
        try: 
            original_val = float(val_str.replace(',', ''))
        except ValueError: 
            pass
            
    if original_val is not None:
        if currency == "UNKNOWN":
            currency = "JPY" 
            
        if currency == base_currency: 
            converted_val = original_val
        elif live_rates and currency in live_rates: 
            converted_val = round(original_val / live_rates[currency], 2)
            
    return currency, original_val, converted_val

if __name__ == "__main__":
    os.makedirs("exports", exist_ok=True)

    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--keywords', type=str, help="Overrides config keywords")
    parser.add_argument('-n', '--number', type=int, help="Overrides config target quota")
    parser.add_argument('-c', '--currency', type=str, help="Overrides config base target currency")
    parser.add_argument('--debug', action='store_true', help="Enable verbose extraction telemetry")
    args = parser.parse_args()
    
    base_items = [item.strip() for item in args.keywords.split(',')] if args.keywords else config["keywords"]
    target_quota = args.number if args.number else config["target_quota"]
    base_currency = args.currency.upper() if args.currency else config["base_currency"].upper()
    debug_mode = args.debug
    
    live_exchange_rates = fetch_live_exchange_rates(base_currency)
    
    for base_item in base_items:
        global_unique_data = []
        seen_urls = set()
        
        print(f"\n{'='*60}")
        print(f"[*] Engine Active: {base_item.upper()} | TARGET: {target_quota} | BASE: {base_currency}")
        print(f"{'='*60}")
        
        wide_keywords_en = generate_dynamic_modifiers(base_item)
        target_keywords_jp = [translate_to_jp(kw) for kw in wide_keywords_en]
        
        print(f"[*] Generated Target Modifiers (EN): {wide_keywords_en}")
        print(f"[*] Translated Targeting Map (JP): {target_keywords_jp}")
        print(f"{'-'*60}")
        
        page_num = 1
        max_pages = 15 
        global_compute_start = time.time()
        
        try:
            while len(global_unique_data) < target_quota and page_num <= max_pages:
                tasks = [(jp_keyword, page_num) for jp_keyword in target_keywords_jp]
                html_payloads = []
                
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_task = {executor.submit(fetch_amazon_jp_html, task[0], task[1]): task for task in tasks}
                    for future in future_to_task:
                        jp_kw, p_num = future_to_task[future]
                        try: 
                            html_payloads.append((future.result(), jp_kw, p_num))
                        except Exception: pass
                
                for raw_html, jp_kw, p_num in html_payloads:
                    if not raw_html: continue
                    
                    extracted_items = extract_page_data(raw_html)
                    
                    for item in extracted_items:
                        url = item.get("URL", "N/A")
                        if url not in seen_urls and url != "N/A":
                            seen_urls.add(url)
                            
                            formatted_item = {
                                "Platform": "Amazon JP",
                                "Search_Term": jp_kw,
                                "Title": item.get("Title", "N/A"),
                                "URL": url
                            }
                            
                            raw_price = str(item.get("Price", ""))
                            curr, orig_val, conv_val = clean_and_convert_price(raw_price, live_exchange_rates, base_currency, debug_mode)
                            
                            formatted_item["Original_Currency"] = curr
                            formatted_item["Original_Price"] = orig_val
                            formatted_item[f"Price_{base_currency}"] = conv_val
                            
                            global_unique_data.append(formatted_item)
                            
                    current_count = len(global_unique_data)
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
                
                if debug_mode: print() 
                page_num += 1

            print(f"\n[*] {'TARGET QUOTA' if len(global_unique_data) >= target_quota else 'MAX PAGINATION'} REACHED.")

        except KeyboardInterrupt:
            print(f"\n\n[!] Interruption caught (^C). Gracefully halting {base_item} pipeline...")
            break
            
        finally:
            total_time = time.time() - global_compute_start
            mins, secs = divmod(int(total_time), 60)
            print(f"[*] Extraction Time: {mins}m {secs}s")

            if global_unique_data:
                final_data = global_unique_data[:target_quota]
                df = pd.DataFrame(final_data)
                
                columns_order = ["Platform", "Search_Term", "Title", "Original_Currency", "Original_Price", f"Price_{base_currency}", "URL"]
                columns_order = [c for c in columns_order if c in df.columns]
                df = df[columns_order]
                df.columns = [str(col).upper() for col in df.columns]
                
                safe_filename = base_item.replace(" ", "_").lower()
                export_path = f"exports/{safe_filename}_results.csv"
                
                df.to_csv(export_path, index=False, encoding='utf-8-sig')
                print(f"[*] SUCCESS: {len(df)} perfectly unique records saved to {export_path}.\n")
