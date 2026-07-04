from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import urllib.parse
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

def translate_to_jp(keyword):
    print(f"[*] Translating '{keyword}' to Japanese...")
    translated = GoogleTranslator(source='en', target='ja').translate(keyword)
    print(f"[*] Translation result: {translated}")
    return translated

def fetch_amazon_jp_html(keyword, page_number=1):
    safe_keyword = urllib.parse.quote(keyword)
    url = f"https://www.amazon.co.jp/s?k={safe_keyword}&page={page_number}"
    
    print(f"[Thread-{page_number}] Launching Playwright to scrape: {url}")
    
    with sync_playwright() as p:
        # HEADLESS IS NOW TRUE: No visual windows, pure background speed.
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
        
        print(f"[Thread-{page_number}] HTML extraction complete.")
        return html

def parse_amazon_data(html, page_number):
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
            'Title': title,
            'Price': price,
            'URL': link
        })
        
    print(f"[Thread-{page_number}] Successfully parsed {len(results)} products.")
    return results

if __name__ == "__main__":
    jp_keyword = translate_to_jp("mechanical keyboard")
    all_parsed_data = []
    
    # Define how many pages we want to scrape simultaneously
    pages_to_scrape = list(range(1,18))
    
    print(f"\n[*] Firing up {len(pages_to_scrape)} concurrent browsers...\n")
    
    # ThreadPoolExecutor manages our concurrent threads
    # max_workers=5 means it will run exactly 5 instances of the fetch function at the same time
    with ThreadPoolExecutor(max_workers=5) as executor:
        # We create a dictionary to keep track of which thread is processing which page
        future_to_page = {
            executor.submit(fetch_amazon_jp_html, jp_keyword, page): page 
            for page in pages_to_scrape
        }
        
        # As each thread finishes its job, we collect the raw HTML and parse it
        for future in future_to_page:
            page_num = future_to_page[future]
            try:
                raw_html = future.result()
                page_data = parse_amazon_data(raw_html, page_num)
                all_parsed_data.extend(page_data)
            except Exception as exc:
                print(f"[!] Thread for Page {page_num} generated an exception: {exc}")

    # Exporting the combined data
    if all_parsed_data:
        print(f"\n[*] Boom. Exporting {len(all_parsed_data)} total products to PolyPrice_Results.csv...")
        df = pd.DataFrame(all_parsed_data)
        df.to_csv('PolyPrice_Results.csv', index=False, encoding='utf-8-sig')
        print("[*] Success! Check your project folder.")
    else:
        print("\n[!] No data parsed to export.")
