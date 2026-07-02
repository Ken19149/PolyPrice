from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import urllib.parse
import pandas as pd

def translate_to_jp(keyword):
    print(f"[*] Translating '{keyword}' to Japanese...")
    # GoogleTranslator is free and doesn't require an API key
    translated = GoogleTranslator(source='en', target='ja').translate(keyword)
    print(f"[*] Translation result: {translated}")
    return translated

def fetch_amazon_jp_html(keyword):
    safe_keyword = urllib.parse.quote(keyword)
    url = f"https://www.amazon.co.jp/s?k={safe_keyword}"
    
    print(f"[*] Launching Playwright to scrape: {url}")
    
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
        
        # Switched locale and timezone to match Tokyo
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1366, "height": 768} 
        )
        
        Stealth().apply_stealth_sync(context)
        page = context.new_page()
        
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        print("[*] Navigating to Amazon Japan...")
        page.goto(url)
        
        # Amazon sometimes throws a visual CAPTCHA (type the letters). 
        # Since headless=False, if you see it, just type it in manually within this 10-second window!
        page.wait_for_timeout(10000) 
        
        # Scroll to load all product images and prices
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
    raw_html = fetch_amazon_jp_html(jp_keyword)
    parsed_data = parse_amazon_data(raw_html)
    
    # Exporting to CSV using Pandas
    if parsed_data:
        print("[*] Exporting data to PolyPrice_Results.csv...")
        df = pd.DataFrame(parsed_data)
        df.to_csv('PolyPrice_Results.csv', index=False, encoding='utf-8-sig')
        print("[*] Success! Check your project folder.")
    else:
        print("[!] No data parsed to export.")
