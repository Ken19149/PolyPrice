import argparse
import urllib.parse
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def generate_wide_keywords(base_keyword):
    """Generates specific variations of a keyword to bypass pagination limits."""
    modifiers = ["wireless", "gaming", "budget", "high end", "ergonomic", "compact", "low profile"]
    return [f"{mod} {base_keyword}" for mod in modifiers] + [base_keyword]

def translate_to_jp(keyword):
    """Translates a single English string to Japanese."""
    return GoogleTranslator(source='en', target='ja').translate(keyword)

def fetch_amazon_jp_html(keyword, page_number=1):
    """Launches a headless browser to extract the rendered HTML."""
    safe_keyword = urllib.parse.quote(keyword)
    url = f"https://www.amazon.co.jp/s?k={safe_keyword}&page={page_number}"
    
    print(f"[Fetch] Requesting: {keyword} (Page {page_number})")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled", 
                "--disable-popup-blocking",
                "--no-sandbox"
            ],
            ignore_default_args=["--enable-automation"] 
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1366, "height": 768} 
        )
        
        Stealth().apply_stealth_sync(context)
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page.goto(url)
        page.wait_for_timeout(5000) 
        
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(2000)
        
        html = page.content()
        browser.close()
        
        return html

def parse_amazon_data(html, keyword, page_number):
    """Extracts Title, Price, and URL from the raw HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    items = soup.find_all('div', attrs={'data-component-type': 's-search-result'})
    
    for item in items:
        title_tag = item.find('h2')
        if not title_tag:
            continue
        title = title_tag.text.strip()
        
        link_tag = item.find('a', class_='a-link-normal', href=True)
        link = "https://www.amazon.co.jp" + link_tag['href'] if link_tag else "N/A"
        
        price_tag = item.find('span', class_='a-offscreen')
        if not price_tag:
            price_tag = item.find('span', class_='a-price-whole')
            
        price = price_tag.text.strip() if price_tag else "No Price Listed"
        
        results.append({
            'Platform': 'Amazon JP',
            'Search_Term': keyword,
            'Title': title,
            'Price': price,
            'URL': link
        })
        
    print(f"[Parse] Successfully extracted {len(results)} items for '{keyword}' (Page {page_number}).")
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PolyPrice: Multi-threaded E-commerce Scraper")
    parser.add_argument(
        '-k', '--keywords', 
        type=str, 
        required=True, 
        help='Comma-separated list of items to scrape (e.g., "mechanical keyboard, gaming mouse")'
    )
    
    args = parser.parse_args()
    base_items = [item.strip() for item in args.keywords.split(',')]
    
    all_parsed_data = []
    
    # Process each base category one by one
    for base_item in base_items:
        print(f"\n{'='*40}")
        print(f"[*] Processing Main Category: {base_item.upper()}")
        print(f"{'='*40}")
        
        # 1. Generate wide keywords and translate them
        wide_keywords_en = generate_wide_keywords(base_item)
        target_keywords_jp = [translate_to_jp(kw) for kw in wide_keywords_en]
        
        print(f"[*] Generated {len(target_keywords_jp)} translated sub-queries.")
        
        # 2. Scrape the first 3 pages of EVERY generated sub-query concurrently
        pages_to_scrape = [1, 2, 3]
        tasks = []
        
        for jp_keyword in target_keywords_jp:
            for page in pages_to_scrape:
                tasks.append((jp_keyword, page))
                
        print(f"[*] Firing up thread pool for {len(tasks)} total page requests...\n")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_task = {
                executor.submit(fetch_amazon_jp_html, task[0], task[1]): task 
                for task in tasks
            }
            
            for future in future_to_task:
                jp_kw, page_num = future_to_task[future]
                try:
                    raw_html = future.result()
                    page_data = parse_amazon_data(raw_html, jp_kw, page_num)
                    all_parsed_data.extend(page_data)
                except Exception as exc:
                    print(f"[!] Thread error for '{jp_kw}' Page {page_num}: {exc}")

    # 3. Export and Deduplicate
    if all_parsed_data:
        df = pd.DataFrame(all_parsed_data)
        original_count = len(df)
        
        # Drop duplicates based on URL to ensure clean data
        df = df.drop_duplicates(subset=['URL'])
        final_count = len(df)
        
        print(f"\n[*] Data cleaned. Removed {original_count - final_count} duplicate overlaps.")
        print(f"[*] Exporting {final_count} unique products to PolyPrice_Results.csv...")
        
        df.to_csv('PolyPrice_Results.csv', index=False, encoding='utf-8-sig')
        print("[*] Success! Check your project folder.")
    else:
        print("\n[!] No data parsed to export.")
