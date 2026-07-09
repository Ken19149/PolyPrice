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

def generate_dynamic_modifiers(base_keyword):
    """Uses Qwen 2.5 to autonomously generate category-specific search modifiers."""
    print(f"[*] Asking Qwen 2.5 to generate dynamic search modifiers for '{base_keyword}'...")
    prompt = f"""
    You are an e-commerce SEO engine. Generate a JSON array of exactly 5 single-word or short search modifiers for the product: "{base_keyword}".
    Return ONLY a raw, valid JSON array of strings. Do not include markdown formatting.
    Example for 'keyboard': ["wireless", "gaming", "mechanical", "budget", "ergonomic"]
    Example for 'coffee': ["organic", "dark roast", "decaf", "espresso", "instant"]
    """
    
    try:
        response = ollama.generate(
            model="qwen2.5:7b", 
            prompt=prompt, 
            format="json", 
            options={"temperature": 0.4, "num_predict": 100}
        )
        modifiers = json.loads(response["response"].strip())
        
        if isinstance(modifiers, dict):
            modifiers = list(modifiers.values())[0]
            
        if not isinstance(modifiers, list):
            raise ValueError("LLM did not return a list.")
            
        print(f"[*] AI Generated Modifiers: {modifiers}")
        return [f"{mod} {base_keyword}" for mod in modifiers] + [base_keyword]
        
    except Exception as e:
        print(f"[!] AI Modifier generation failed: {e}. Falling back to default expansion.")
        return [f"premium {base_keyword}", f"budget {base_keyword}", base_keyword]

def translate_to_jp(keyword):
    """Translates a single English string to Japanese."""
    return GoogleTranslator(source='en', target='ja').translate(keyword)

def fetch_amazon_jp_html(keyword, page_number=1):
    """Launches a headless browser concurrently to pull raw target layouts."""
    start_time = time.time()
    safe_keyword = urllib.parse.quote(keyword)
    url = f"https://www.amazon.co.jp/s?k={safe_keyword}&page={page_number}"
    
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
        page.wait_for_timeout(3000) 
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(1000)
        
        html = page.content()
        browser.close()
        
        elapsed = time.time() - start_time
        print(f"[Network] Downloaded '{keyword}' Page {page_number} in {elapsed:.2f}s")
        return html

def parse_amazon_data(html, keyword, page_number):
    """Extracts unstructured text into strictly typed dictionaries."""
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
            
            # ASIN REGEX STERILIZATION
            clean_link = "N/A"
            if raw_link:
                if "sspa/click" in raw_link:
                    parsed = urllib.parse.urlparse(raw_link)
                    qs = urllib.parse.parse_qs(parsed.query)
                    if 'url' in qs:
                        raw_link = urllib.parse.unquote(qs['url'][0])
                        if not raw_link.startswith("http"):
                            raw_link = "https://www.amazon.co.jp" + raw_link
                
                asin_match = re.search(r'/(?:dp|gp/product|exec/obidos/ASIN|o/ASIN)/([A-Z0-9]{10})', raw_link)
                if asin_match:
                    clean_link = f"https://www.amazon.co.jp/dp/{asin_match.group(1)}"
                else:
                    clean_link = raw_link.split('?')[0].split('/ref=')[0]
                
            structured_text_input += f"Item {idx+1}:\nText: {text_content}\nLink: {clean_link}\n\n"

        # Simplified Prompt: No static fields requested to prevent Schema Bleed
        prompt = f"""
        You are an expert data parsing engine. Read the numbered items below.
        Extract the products into a valid JSON array of objects.
        Use EXACTLY these keys for every object: "Title", "Price", "URL".
        
        Keep the "Price" field concise.
        
        Example Output:
        [
          {{"Title": "Logitech Mechanical Keyboard", "Price": "￥1,500", "URL": "https://..."}}
        ]

        Data to process:
        {structured_text_input}
        """
        
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
            
            extracted_data = json.loads(response["response"].strip())
            
            # AI HALLUCINATION FLATTENING
            if isinstance(extracted_data, dict):
                for key, value in extracted_data.items():
                    if isinstance(value, list):
                        extracted_data = value
                        break
                if isinstance(extracted_data, dict):
                    extracted_data = list(extracted_data.values())
                        
            # STATIC DATA INJECTION FIREWALL
            if isinstance(extracted_data, list):
                valid_items = []
                for item in extracted_data:
                    if isinstance(item, dict) and "URL" in item and item["URL"] != "N/A":
                        # Python forces the static keys here, saving tokens and preventing errors
                        item["Platform"] = "Amazon JP"
                        item["Search_Term"] = keyword
                        valid_items.append(item)
                all_extracted_items_for_page.extend(valid_items)
            
        except json.JSONDecodeError:
            continue 
        except Exception:
            continue

    return all_extracted_items_for_page

if __name__ == "__main__":
    with open("debug_log.txt", "w", encoding="utf-8") as f:
        f.write("=== PolyPrice Pipeline Session Runtime Telemetry ===\n")

    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--keywords', type=str, required=True, help="Base product keyword")
    parser.add_argument('-n', '--number', type=int, default=100, help="Target number of unique products to extract")
    args = parser.parse_args()
    
    base_items = [item.strip() for item in args.keywords.split(',')]
    target_quota = args.number
    
    global_unique_data = []
    seen_urls = set()  # Stateful tracking for real-time deduplication
    
    try:
        for base_item in base_items:
            overall_start = time.time()
            print(f"\n{'='*50}")
            print(f"[*] Pipeline Run Active: {base_item.upper()} | TARGET: {target_quota} UNIQUE ITEMS")
            print(f"{'='*50}")
            
            wide_keywords_en = generate_dynamic_modifiers(base_item)
            target_keywords_jp = [translate_to_jp(kw) for kw in wide_keywords_en]
            
            page_num = 1
            max_pages = 10 # Safety ceiling to prevent infinite loops on extremely niche keywords
            
            while len(global_unique_data) < target_quota and page_num <= max_pages:
                print(f"\n[*] --- INITIATING BATCH: PAGE {page_num} ---")
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

                print(f"[*] Activating Local GPU Inference Engine (Qwen 2.5 7B) for Page {page_num} batch...\n")
                
                for raw_html, jp_kw, p_num in html_payloads:
                    page_data = parse_amazon_data(raw_html, jp_kw, p_num)
                    
                    # Real-Time Deduplication Loop
                    for item in page_data:
                        url = item.get("URL", "")
                        if url not in seen_urls and url != "N/A":
                            seen_urls.add(url)
                            global_unique_data.append(item)
                            
                    # Hard break if quota is hit mid-batch
                    if len(global_unique_data) >= target_quota:
                        break
                        
                current_count = len(global_unique_data)
                bar_len = 20
                filled = int(bar_len * min(current_count, target_quota) // target_quota)
                bar = '█' * filled + '░' * (bar_len - filled)
                percent = (min(current_count, target_quota) / target_quota) * 100
                
                print(f"\n[Quota Progress] {bar} {percent:.1f}% | {current_count}/{target_quota} Unique Items Extracted")
                page_num += 1

            if len(global_unique_data) >= target_quota:
                print(f"\n[*] TARGET QUOTA REACHED. Halting extraction threads.")
            else:
                print(f"\n[*] MAX PAGINATION REACHED. Keyword exhausted at {len(global_unique_data)} items.")

    except KeyboardInterrupt:
        print(f"\n\n[!] Interruption caught (^C). Gracefully halting pipeline and extracting progress...")
    except Exception as e:
        print(f"\n[!] Unexpected pipeline loop crash: {e}")
        
    finally:
        if global_unique_data:
            print(f"\n[*] Launching recovery dump blocks...")
            
            # Slice down to exact target if we slightly overshot during the last batch loop
            final_data = global_unique_data[:target_quota]
            
            df = pd.DataFrame(final_data)
            df.columns = [str(col).upper() for col in df.columns]
            
            df.to_csv('PolyPrice_Results.csv', index=False, encoding='utf-8-sig')
            print(f"[*] SUCCESS: {len(df)} perfectly unique records saved to PolyPrice_Results.csv.")
        else:
            print("\n[!] Pipeline terminated. No valid records were extracted to dump.")
