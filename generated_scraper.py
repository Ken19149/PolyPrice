from bs4 import BeautifulSoup
import re

def extract_page_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    
    # Find all product containers
    items = soup.find_all('div', class_='s-result-item')
    
    for item in items:
        # Skip empty layout blocks
        if not item.text.strip(): continue

        # Extract title and URL
        title_tag = item.find('a', class_=re.compile(r'a-text-normal'))
        if title_tag:
            title = title_tag.get_text(strip=True)
            url = 'https://www.amazon.co.jp' + title_tag['href']
        else:
            title = 'N/A'
            url = 'N/A'

        # Extract price
        price_tag = item.find('span', class_=re.compile(r'a-offscreen'))
        if price_tag:
            price = price_tag.get_text(strip=True)
        else:
            price = 'N/A'

        results.append({'Title': title, 'Price': price, 'URL': url})
        
    return results
