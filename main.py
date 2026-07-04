from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import urllib.parse
import pandas as pd
import time

def translate_to_jp(keyword):
    print(f"[*] Translating '{keyword}' to Japanese...")
    # GoogleTranslator is free and doesn't require an API key
    translated = GoogleTranslator(source='en', target='ja').translate(keyword)
    print(f"[*] Translation result: {translated}")
    return translated

def fetch_amazon_jp_html(keyword, page_number=1):
    safe_keyword = urllib.parse.quote(keyword)
    # Added the page parameter to the URL
    url = f"https://www.amazon.co.jp/s?k={safe_keyword}&page={page_number}"
    
    print(f"[*] Launching Playwright to scrape Page {page_number}: {url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
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

def parse_amazon_data(html):
    print("[*] Parsing HTML with BeautifulSoup...")
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    
    # Find all product containers on the page
    items = soup.find_all('div', attrs={'data-component-type': 's-search-result'})
    
    for item in items:
        # 1. Extract the Title
        title_tag = item.find('h2')
        if not title_tag:
            continue
        title = title_tag.text.strip()
        
        # 2. Extract the Link (Search the whole 'item' container, not just 'title_tag')
        link_tag = item.find('a', class_='a-link-normal', href=True)
        link = "https://www.amazon.co.jp" + link_tag['href'] if link_tag else "N/A"
        
        # 3. Extract the Price (With a fallback for alternate layouts)
        price_tag = item.find('span', class_='a-offscreen')
        if not price_tag: # Fallback if the first class isn't found
            price_tag = item.find('span', class_='a-price-whole')
            
        price = price_tag.text.strip() if price_tag else "No Price Listed"
        
        # Save it to our dictionary
        results.append({
            'Platform': 'Amazon JP',
            'Title': title,
            'Price': price,
            'URL': link
        }) 
        
    print(f"[*] Successfully parsed {len(results)} products.")
    return results

if __name__ == "__main__":
    jp_keyword = translate_to_jp("mechanical keyboard")
    
    # Create a master list to hold data from all pages
    all_parsed_data = []
    
    # Loop through pages 1, 2, and 3
    for current_page in range(1, 4):
        raw_html = fetch_amazon_jp_html(jp_keyword, current_page)
        page_data = parse_amazon_data(raw_html)
        
        # Add the new page's data to our master list
        all_parsed_data.extend(page_data)
        
        # Be polite to the server: wait 3 seconds before hitting the next page
        if current_page < 3:
            print("[*] Resting for 3 seconds to avoid rate limits...")
            time.sleep(3)
    
    if all_parsed_data:
        print(f"[*] Exporting {len(all_parsed_data)} total products to PolyPrice_Results.csv...")
        df = pd.DataFrame(all_parsed_data)
        df.to_csv('PolyPrice_Results.csv', index=False, encoding='utf-8-sig')
        print("[*] Success! Check your project folder.")
    else:
        print("[!] No data parsed to export.")
