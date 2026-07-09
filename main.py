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
import re  # Added for ASIN extraction

def generate_wide_keywords(base_keyword):
    """Generates specific variations of a keyword to bypass pagination limits."""
    modifiers = ["wireless", "gaming", "budget", "high end", "ergonomic", "compact", "low profile"]
    return [f"{mod} {base_keyword}" for mod in modifiers] + [base_keyword]

def translate_to_jp(keyword):
    """Translates a single English string to Japanese."""
    return GoogleTranslator(source='en', target='ja').translate(keyword)

def fetch_amazon_jp_html(keyword, page_number=1):
    """Launches a headless browser concurrently to pull raw target layouts."""
    start_time = time.time()
    safe_keyword = urllib.parse.quote(keyword)
    url = f"https://www.amazon.co.jp/s?k={safe_keyword}&page={page_number}"
    
    print(f"[Network] Requesting: {keyword} (Page {page_number})...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--disable-popup-blocking", "--no-sandbox"],
            ignore_default_args=["--enable-automation"] 
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP", timezone_id="Asia/Tokyo", viewport={"width": 1366, "height": 768} 
        )
        
        Stealth().apply_stealth_sync(context)
        page = context.new_page()
        page.goto(url)
        page.wait_for_timeout(4000) 
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(1000)
        
        html = page.content()
        browser.close()
        
        elapsed = time.time() - start_time
        print(f"[Network] Downloaded '{keyword}' Page {page_number} in {elapsed:.2f}s")
        return html

def parse_amazon_data(html, keyword, page_number):
    """Uses Batch Processing and aggressive type-checking to extract items safely."""
    start_time = time.time()
    soup = BeautifulSoup(html, 'html.parser')
    
    items = soup.find_all('div', attrs={'data-component-type': 's-search-result'})
    if not items:
        return []
        
    all_extracted_items_for_page = []
    chunk_size = 15 
    
    for i in range(0, len(items), chunk_size):
        chunk = items[i:i+chunk_size]
        structured_text_input = ""
        
        for idx, item in enumerate(chunk): 
            text_content = item.get_text(separator=' ', strip=True)
            text_content = " ".join(text_content.split())
            if len(text_content) > 300:
                text_content = text_content[:300] + "..."
                
            link_tag = item.find('a', class_='a-link-normal', href=True)
            raw_link = "https://www.amazon.co.jp" + link_tag['href'] if link_tag else ""
            
            # --- ASIN REGEX STERILIZATION ---
            clean_link = "N/A"
            if raw_link:
                # 1. Unpack hidden sponsored ad URLs
                if "sspa/click" in raw_link:
                    parsed = urllib.parse.urlparse(raw_link)
                    qs = urllib.parse.parse_qs(parsed.query)
                    if 'url' in qs:
                        raw_link = urllib.parse.unquote(qs['url'][0])
                        if not raw_link.startswith("http"):
                            raw_link = "https://www.amazon.co.jp" + raw_link
                
                # 2. Extract the exact 10-character Amazon ASIN
                asin_match = re.search(r'/(?:dp|gp/product|exec/obidos/ASIN|o/ASIN)/([A-Z0-9]{10})', raw_link)
                if asin_match:
                    clean_link = f"https://www.amazon.co.jp/dp/{asin_match.group(1)}"
                else:
                    # Fallback if no ASIN is found
                    clean_link = raw_link.split('?')[0].split('/ref=')[0]
                
            structured_text_input += f"Item {idx+1}:\nText: {text_content}\nLink: {clean_link}\n\n"

        prompt = f"""
        You are an expert data parsing engine. Read the numbered items below.
        Extract the products into a valid JSON array of objects.
        Use EXACTLY these keys for every object: "Platform", "Search_Term", "Title", "Price", "URL".
        
        Keep the "Price" field concise. Extract only the primary retail numeric value and currency marker.
        
        Example Output:
        [
          {{"Platform": "Amazon JP", "Search_Term": "{keyword}", "Title": "Example Keyboard", "Price": "￥1,500", "URL": "https://..."}}
        ]

        Data to process:
        {structured_text_input}
        """

        print(f"[Compute] ↳ Processing Page {page_number} (Items {i+1} to {min(i+chunk_size, len(items))}) across Qwen 2.5 (7B)...")
        
        try:
            response = ollama.generate(
                model="qwen2.5:7b", 
                prompt=prompt, 
                format="json", 
                options={
                    "temperature": 0.0,
                    "num_predict": 4000,
                    "repeat_penalty": 1.3  
                }
            )
            
            response_text = response["response"].strip()
            extracted_data = json.loads(response_text)
            
            # --- AI HALLUCINATION FLATTENING ---
            if isinstance(extracted_data, dict):
                for key, value in extracted_data.items():
                    if isinstance(value, list):
                        extracted_data = value
                        break
                if isinstance(extracted_data, dict):
                    extracted_data = list(extracted_data.values())
                        
            # --- STRICT PANDAS FIREWALL ---
            if isinstance(extracted_data, list):
                valid_items = [item for item in extracted_data if isinstance(item, dict)]
                all_extracted_items_for_page.extend(valid_items)
            
        except json.JSONDecodeError as json_err:
            print(f"[!] JSON Anomaly caught on Page {page_number} (Items {i+1}-{i+chunk_size}). Logging to debug_log.txt...")
            with open("debug_log.txt", "a", encoding="utf-8") as f:
                f.write(f"\n--- TIMEOUT/TRUNCATION ERROR: PAGE {page_number} CHUNK START {i} ({keyword}) ---\n")
                f.write(f"Context Error Details: {json_err}\n")
                f.write(f"Raw Output: {response.get('response', '')}\n")
            continue 
            
        except Exception as e:
            print(f"[!] Processing error on Page {page_number}: {e}")
            continue

    elapsed = time.time() - start_time
    print(f"[Compute] ★ Page {page_number} Complete: Extracted {len(all_extracted_items_for_page)} high-quality items in {elapsed:.2f}s")
    return all_extracted_items_for_page

if __name__ == "__main__":
    with open("debug_log.txt", "w", encoding="utf-8") as f:
        f.write("=== PolyPrice Pipeline Session Runtime Telemetry ===\n")

    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--keywords', type=str, required=True)
    args = parser.parse_args()
    base_items = [item.strip() for item in args.keywords.split(',')]
    
    all_parsed_data = []
    
    try:
        for base_item in base_items:
            overall_start = time.time()
            print(f"\n{'='*50}")
            print(f"[*] Pipeline Run Active: {base_item.upper()}")
            print(f"{'='*50}")
            
            wide_keywords_en = generate_wide_keywords(base_item)
            target_keywords_jp = [translate_to_jp(kw) for kw in wide_keywords_en]
            
            pages_to_scrape = [1, 2, 3]
            tasks = [(jp_keyword, page) for jp_keyword in target_keywords_jp for page in pages_to_scrape]
                    
            print(f"[*] Thread Pool active. Fetching {len(tasks)} target pages concurrently...\n")
            
            html_payloads = []
            network_start = time.time()
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_task = {executor.submit(fetch_amazon_jp_html, task[0], task[1]): task for task in tasks}
                for future in future_to_task:
                    jp_kw, page_num = future_to_task[future]
                    try:
                        raw_html = future.result()
                        html_payloads.append((raw_html, jp_kw, page_num))
                    except Exception as exc:
                        print(f"[!] Failed to pull HTML for {jp_kw} Page {page_num}: {exc}")

            print(f"\n[*] All network I/O finished in {time.time() - network_start:.2f} seconds.")
            print(f"[*] Activating Local GPU Inference Engine (Qwen 2.5 7B)...\n")
            
            compute_start = time.time()
            total_pages = len(html_payloads)
            
            for idx, (raw_html, jp_kw, page_num) in enumerate(html_payloads, 1):
                page_data = parse_amazon_data(raw_html, jp_kw, page_num)
                all_parsed_data.extend(page_data)
                
                elapsed_compute = time.time() - compute_start
                avg_time_per_page = elapsed_compute / idx
                eta_seconds = (total_pages - idx) * avg_time_per_page
                eta_mins, eta_secs = divmod(int(eta_seconds), 60)
                percent = (idx / total_pages) * 100
                
                bar_len = 20
                filled = int(bar_len * idx // total_pages)
                bar = '█' * filled + '░' * (bar_len - filled)
                
                print(f"[Progress] {bar} {percent:.1f}% | Page {idx}/{total_pages} | ETA: {eta_mins:02d}m {eta_secs:02d}s\n")
                
            print(f"[*] Total Engine Compute Time: {time.time() - compute_start:.2f} seconds.")

    except KeyboardInterrupt:
        print(f"\n\n[!] Interruption caught (^C). Gracefully halting pipeline and extracting progress...")
    except Exception as e:
        print(f"\n[!] Unexpected pipeline loop crash: {e}")
        
    finally:
        if all_parsed_data:
            print(f"\n[*] Launching recovery dump blocks...")
            
            clean_data = [item for item in all_parsed_data if isinstance(item, dict)]
            
            if clean_data:
                df = pd.DataFrame(clean_data)
                original_count = len(df)
                
                df.columns = [str(col).upper() for col in df.columns]
                df = df.loc[:, ~df.columns.duplicated()]
                
                if 'URL' in df.columns:
                    df = df.drop_duplicates(subset=['URL'])
                else:
                    print("[!] Warning: LLM failed to map URL columns properly. Duplicates may exist.")
                    
                df.to_csv('PolyPrice_Results.csv', index=False, encoding='utf-8-sig')
                print(f"[*] SUCCESS: {len(df)} unique records saved safely to PolyPrice_Results.csv (Filtered {original_count - len(df)} overlaps).")
            else:
                print("\n[!] Pipeline terminated. No valid dictionary records were found to dump.")
        else:
            print("\n[!] Pipeline terminated. No valid records were extracted to dump.")
