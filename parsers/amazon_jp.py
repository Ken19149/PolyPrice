from bs4 import BeautifulSoup
import re

def normalize_url(url):
    if not url or url == "N/A": 
        return "N/A"
    match = re.search(r'/dp/([A-Z0-9]{10})', url, re.IGNORECASE)
    if match:
        return f"https://www.amazon.co.jp/dp/{match.group(1)}"
    return f"https://www.amazon.co.jp{url}" if url.startswith('/') else url

def extract_page_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    
    products = soup.find_all('div', {'data-component-type': 's-search-result'})
    
    for product in products:
        h2_tag = product.find('h2')
        if not h2_tag:
            continue
            
        title = h2_tag.get_text(strip=True)
        
        parent_a = h2_tag.find_parent('a')
        if parent_a and 'href' in parent_a.attrs:
            raw_url = parent_a['href']
        else:
            url_tag = product.find('a', class_='a-link-normal', href=True)
            raw_url = url_tag['href'] if url_tag else 'N/A'
            
        # 1. Look for standard offscreen price
        price_tag = product.find('span', class_='a-offscreen')
        
        # 2. Fallback for cosmetics variations (e.g., "X options from ¥Y")
        if not price_tag:
            price_tag = product.find('span', class_='a-color-price')
            
        # 3. Fallback for Subscribe & Save / raw whole numbers
        if not price_tag:
            price_tag = product.find('span', class_='a-price-whole')
            
        price = price_tag.get_text(strip=True) if price_tag else 'N/A'
        
        results.append({
            'Title': title,
            'Price': price,
            'URL': raw_url
        })
    
    return results
