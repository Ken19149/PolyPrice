from bs4 import BeautifulSoup
import re

def normalize_url(url):
    if not url or url == "N/A": 
        return "N/A"
    # Strip tracking junk downstream of the query marker
    return url.split('?')[0]

def extract_page_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    
    # Target the grid items from the new layout[cite: 9]
    items = soup.find_all('li', class_='su-grid__item')
    
    # Fallback to older eBay DOM structure if the new one isn't present
    if not items:
        items = soup.find_all('li', class_='s-item')
    
    for item in items:
        # Find the title anchor tag[cite: 9]
        title_tag = item.find('a', class_=re.compile(r'(su-item-card__title|s-item__link)'))
        if not title_tag:
            continue
            
        title = title_tag.get_text(strip=True)
        raw_url = title_tag.get('href', 'N/A')
        
        # Find the price span[cite: 9]
        price_tag = item.find('span', class_=re.compile(r'(su-item-card__price|s-item__price)'))
        price = price_tag.get_text(strip=True) if price_tag else 'N/A'
        
        results.append({
            'Title': title,
            'Price': price,
            'URL': raw_url
        })
    
    return results
