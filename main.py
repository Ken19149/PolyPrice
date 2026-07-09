import argparse
import urllib.parse
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import json
import ollama
import time
import re
import os
import urllib.request

def load_config():
    """Loads base configuration parameters from config.json."""
    default_config = {
        "keywords": ["keyboard"],
        "target_quota": 100,
        "base_currency": "THB"
    }
    try:
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                user_config = json.load(f)
                default_config.update(user_config)
    except Exception as e:
        print(f"[!] Warning: Could not read config.json properly ({e}). Using defaults.")
    return default_config

def fetch_live_exchange_rates(base_currency):
    """Pings a free, public API to fetch real-time global exchange rates."""
    print(f"[*] Fetching real-time global exchange rates for {base_currency}...")
    url = f"https://open.er-api.com/v6/latest/{base_currency}"
    try:
        req = urllib.request.urlopen(url)
        data = json.loads(req.read().decode('utf-8'))
        rates = data.get("rates", {})
        print(f"[*] Live rates acquired successfully.")
        return rates
    except Exception as e:
        print(f"[!] Critical Warning: Could not fetch live rates ({e}). Data will export without conversion.")
        return {}

def generate_dynamic_modifiers(base_keyword):
    print(f"[*] Asking Qwen 2.5 to generate dynamic search modifiers for '{base_keyword}'...")
    
    prompt = f"""
    You are an e-commerce SEO engine. Generate exactly 5 single-word search modifiers that shoppers use when looking for: "{base_keyword}".
    Provide attributes like style, use-case, or cost tier.
    """
    
    strict_schema = {
        "type": "object",
        "properties": {"modifiers": {"type": "array", "items": {"type": "string"}}},
        "required": ["modifiers"]
    }
    
    try:
        response = ollama.generate(
            model="qwen2.5:7b", prompt=prompt, format=strict_schema, 
            options={"temperature": 0.3, "num_predict": 150}
        )
        
        parsed_json = json.loads(response["response"].strip())
        modifiers = parsed_json.get("modifiers", [])
        
        if not isinstance(modifiers, list) or len(modifiers) == 0:
            raise ValueError("Schema did not yield a valid array.")
            
        clean_modifiers = [re.sub(r'[^a-zA-Z0-9-]', '', str(mod).lower()) for mod in modifiers[:5]]
        print(f"[*] AI Generated Modifiers: {clean_modifiers}")
        return [f"{mod} {base_keyword}" for mod in clean_modifiers] + [base_keyword]
        
    except Exception as e:
        print(f"[!] AI Modifier generation failed: {e}. Falling back to default.")
        return [f"premium {base_keyword}", f"budget {base_keyword}", base_keyword]

def translate_to_jp(keyword):
    return GoogleTranslator(source='en', target='ja').translate(keyword)

def fetch_amazon_jp_html(keyword, page_number=1):
    safe_keyword = urllib.parse.quote(keyword)
    url = f"https://www.amazon.co.jp/s?k={safe_keyword}&page={page_number}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", locale="ja-JP")
        Stealth().apply_stealth_sync(context)
        page = context.new_page()
        page.goto(url)
        page.wait_for_timeout(3000) 
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(1000)
        html = page.content()
        browser.close()
        return html

def clean_and_convert_price(raw_price, live_rates, base_currency):
    """Extracts price strictly bound to a currency symbol and converts it via live API rates."""
    if not isinstance(raw_price, str):
        return "UNKNOWN", None, None
        
    currency_match = re.search(r'(THB|￥|JPY|\$|USD|EUR)', raw_price, re.IGNORECASE)
    if not currency_match:
        return "UNKNOWN", None, None
        
    raw_sym = currency_match.group(1)
    currency = raw_sym.upper()
    if currency == '￥': currency = 'JPY'
    
    pattern = rf'(?:{re.escape(raw_sym)})\s*([0-9,.]+)|([0-9,.]+)\s*(?:{re.escape(raw_sym)})'
    num_match = re.search(pattern, raw_price, re.IGNORECASE)
    
    original_val = None
    converted_val = None
    
    if num_match:
        val_str = num_match.group(1) or num_match.group(2)
        try:
            original_val = float(val_str.replace(',', ''))
        except ValueError:
            return currency, None, None
            
        if currency == base_currency:
            converted_val = original_val
        elif live_rates and currency in live_rates:
            converted_val = round(original_val / live_rates[currency], 2)
                
    return currency, original_val, converted_val

def parse_amazon_data(html, keyword, page_number, live_rates, base_currency):
    soup = BeautifulSoup(html, 'html.parser')
    items = soup.find_all('div', attrs={'data-component-type': 's-search-result'})
    if not items: return []
        
    all_extracted_items_for_page = []
    chunk_size = 15 
    
    for i in range(0, len(items), chunk_size):
        chunk = items[i:i+chunk_size]
        structured_text_input = ""
        
        for idx, item in enumerate(chunk): 
            text_content = item.get_text(separator=' ', strip=True)
            text_content = " ".join(text_content.split())
            if len(text_content) > 300: text_content = text_content[:300] + "..."
                
            link_tag = item.find('a', class_='a-link-normal', href=True)
            raw_link = "https://www.amazon.co.jp" + link_tag['href'] if link_tag else ""
            
            clean_link = "N/A"
            if raw_link:
                if "sspa/click" in raw_link:
                    parsed = urllib.parse.urlparse(raw_link)
                    qs = urllib.parse.parse_qs(parsed.query)
                    if 'url' in qs:
                        raw_link = urllib.parse.unquote(qs['url'][0])
                        if not raw_link.startswith("http"): raw_link = "https://www.amazon.co.jp" + raw_link
                
                asin_match = re.search(r'/(?:dp|gp/product|exec/obidos/ASIN|o/ASIN)/([A-Z0-9]{10})', raw_link)
                clean_link = f"https://www.amazon.co.jp/dp/{asin_match.group(1)}" if asin_match else raw_link.split('?')[0].split('/ref=')[0]
                
            structured_text_input += f"Item {idx+1}:\nText: {text_content}\nLink: {clean_link}\n\n"

        prompt = f"""
        Extract the products into a valid JSON array of objects. Use EXACTLY these keys: "Title", "Price", "URL".
        Data to process:
        {structured_text_input}
        """
        
        try:
            response = ollama.generate(model="qwen2.5:7b", prompt=prompt, format="json", options={"temperature": 0.0, "num_predict": 4000, "repeat_penalty": 1.3})
            extracted_data = json.loads(response["response"].strip())
            
            if isinstance(extracted_data, dict):
                for key, value in extracted_data.items():
                    if isinstance(value, list):
                        extracted_data = value
                        break
                if isinstance(extracted_data, dict): extracted_data = list(extracted_data.values())
                        
            if isinstance(extracted_data, list):
                valid_items = []
                for item in extracted_data:
                    if isinstance(item, dict) and "URL" in item and item["URL"] != "N/A":
                        item["Platform"] = "Amazon JP"
                        item["Search_Term"] = keyword
                        
                        curr, orig_val, conv_val = clean_and_convert_price(item.get("Price", ""), live_rates, base_currency)
                        item["Original_Currency"] = curr
                        item["Original_Price"] = orig_val
                        item[f"Price_{base_currency}"] = conv_val
                        
                        if "Price" in item: del item["Price"]
                        
                        valid_items.append(item)
                all_extracted_items_for_page.extend(valid_items)
            
        except Exception:
            continue

    return all_extracted_items_for_page

if __name__ == "__main__":
    with open("debug_log.txt", "w", encoding="utf-8") as f:
        f.write("=== PolyPrice Pipeline Telemetry ===\n")

    config = load_config()

    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--keywords', type=str, help="Overrides config keywords")
    parser.add_argument('-n', '--number', type=int, help="Overrides config target quota")
    parser.add_argument('-c', '--currency', type=str, help="Overrides config base target currency (e.g. USD, THB, EUR)")
    args = parser.parse_args()
    
    base_items = [item.strip() for item in args.keywords.split(',')] if args.keywords else config["keywords"]
    target_quota = args.number if args.number else config["target_quota"]
    
    # Establish base currency with a programmatic override flag check
    base_currency = args.currency.upper() if args.currency else config["base_currency"].upper()
    
    # Boot phase: Fetch live exchange rates relative to evaluated currency target
    live_exchange_rates = fetch_live_exchange_rates(base_currency)
    
    global_unique_data = []
    seen_urls = set()  
    
    try:
        for base_item in base_items:
            overall_start = time.time()
            print(f"\n{'='*50}")
            print(f"[*] Pipeline Active: {base_item.upper()} | TARGET: {target_quota} | BASE: {base_currency}")
            print(f"{'='*50}")
            
            wide_keywords_en = generate_dynamic_modifiers(base_item)
            target_keywords_jp = [translate_to_jp(kw) for kw in wide_keywords_en]
            
            page_num = 1
            max_pages = 12 
            
            global_compute_start = time.time()
            total_payloads = len(target_keywords_jp)
            
            while len(global_unique_data) < target_quota and page_num <= max_pages:
                tasks = [(jp_keyword, page_num) for jp_keyword in target_keywords_jp]
                
                html_payloads = []
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_task = {executor.submit(fetch_amazon_jp_html, task[0], task[1]): task for task in tasks}
                    for future in future_to_task:
                        jp_kw, p_num = future_to_task[future]
                        try:
                            html_payloads.append((future.result(), jp_kw, p_num))
                        except Exception:
                            pass
                
                for idx, (raw_html, jp_kw, p_num) in enumerate(html_payloads, 1):
                    page_data = parse_amazon_data(raw_html, jp_kw, p_num, live_exchange_rates, base_currency)
                    
                    for item in page_data:
                        url = item.get("URL", "")
                        if url not in seen_urls and url != "N/A":
                            seen_urls.add(url)
                            global_unique_data.append(item)
                            
                    current_count = len(global_unique_data)
                    elapsed_time = time.time() - global_compute_start
                    
                    if current_count > 0:
                        sec_per_item = elapsed_time / current_count
                        items_remaining = target_quota - current_count
                        eta_seconds = items_remaining * sec_per_item
                    else:
                        eta_seconds = 0
                        
                    eta_mins, eta_secs = divmod(int(eta_seconds), 60)
                    
                    bar_len = 20
                    filled = int(bar_len * min(current_count, target_quota) // target_quota)
                    bar = '█' * filled + '░' * (bar_len - filled)
                    percent = (min(current_count, target_quota) / target_quota) * 100
                    
                    print(f"\n[Progress] {bar} {percent:.1f}% | {current_count}/{target_quota} Items | ETA: {eta_mins:02d}m {eta_secs:02d}s")
                    
                    if current_count >= target_quota:
                        break
                        
                page_num += 1

            if len(global_unique_data) >= target_quota:
                print(f"\n[*] TARGET QUOTA REACHED. Halting extraction threads.")
            else:
                print(f"\n[*] MAX PAGINATION REACHED. Exhausted at {len(global_unique_data)} items.")

    except KeyboardInterrupt:
        print(f"\n\n[!] Interruption caught (^C). Gracefully halting pipeline...")
    except Exception as e:
        print(f"\n[!] Unexpected loop crash: {e}")
        
    finally:
        if global_unique_data:
            final_data = global_unique_data[:target_quota]
            df = pd.DataFrame(final_data)
            
            columns_order = ["Platform", "Search_Term", "Title", "Original_Currency", "Original_Price", f"Price_{base_currency}", "URL"]
            columns_order = [c for c in columns_order if c in df.columns]
            df = df[columns_order]
            df.columns = [str(col).upper() for col in df.columns]
            
            df.to_csv('PolyPrice_Results.csv', index=False, encoding='utf-8-sig')
            print(f"\n[*] SUCCESS: {len(df)} perfectly unique, sanitized records saved to PolyPrice_Results.csv.")
        else:
            print("\n[!] Pipeline terminated. No valid records were extracted.")
