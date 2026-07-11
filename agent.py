import os
import ollama
import argparse

def generate_scraper(site_name="amazon_jp", html_file="sample.html"):
    output_file = f"parsers/{site_name}.py"
    
    if not os.path.exists(html_file):
        print(f"[!] Error: '{html_file}' not found. Run scout.py first.")
        return

    os.makedirs("parsers", exist_ok=True)
    with open("parsers/__init__.py", "w") as f: pass

    with open(html_file, "r", encoding="utf-8") as f:
        html_snippet = f.read()

    print("[*] Waking up Qwen 2.5 Coder 32B...")
    print(f"[*] Deploying strict Template Prompt for site: {site_name}...")

    prompt = (
    f"You are an expert Python data engineer. Analyze the following HTML snippet and write a Python file for {site_name}.\n"
    "Your job is to provide two functions:\n\n"
    "1. 'extract_page_data(html_content)': Safely extract Title, Price, and URL.\n"
    "2. 'normalize_url(url)': Clean the URL. If the target is Amazon, extract the ASIN (the 10-character code) "
    "   and return 'https://www.amazon.co.jp/dp/[ASIN]'. If it is not Amazon, return the original URL.\n\n"
    "RULES:\n"
    "1. Never use `.text` directly. Always use `element.get_text(strip=True) if element else 'N/A'`.\n"
    "2. Prepend the site's base domain to any relative URLs.\n"
    "3. CRITICAL: Your extracted dictionary MUST use exactly these case-sensitive keys: 'Title', 'Price', 'URL'.\n"
    "   EXAMPLE: results.append({'Title': title_val, 'Price': price_val, 'URL': url_val})\n"
    "4. Output ONLY the raw Python code. Do NOT output markdown backticks (```), example usage blocks, or conversational filler.\n\n"
    "HTML SNIPPET:\n"
    f"{html_snippet}\n\n"
    "OUTPUT STRUCTURE:\n"
    "from bs4 import BeautifulSoup\n"
    "import re\n\n"
    "def normalize_url(url):\n"
    "    # Logic to clean URL or extract ASIN\n"
    "    return url\n\n"
    "def extract_page_data(html_content):\n"
    "    # Extraction logic\n"
    "    return results"
    )

    try:
        response = ollama.generate(
            model="qwen2.5-coder:32b",
            prompt=prompt,
            options={"temperature": 0.0, "num_predict": 1000}
        )
        
        generated_code = response["response"]
        
        if "```python" in generated_code:
            generated_code = generated_code.split("```python")[1].split("```")[0]
        elif "```" in generated_code:
            generated_code = generated_code.split("```")[1].split("```")[0]
            
        generated_code = generated_code.strip()
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(generated_code)
            
        print(f"[+] SUCCESS! The AI has successfully engineered the scraper.")
        print(f"[+] Review the code inside '{output_file}'.")
        
    except Exception as e:
        print(f"[!] Agent execution failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--site', type=str, default="amazon_jp", help="Name of the target site (e.g., amazon_jp)")
    parser.add_argument('-f', '--file', type=str, default="sample.html", help="Path to the HTML snippet")
    args = parser.parse_args()
    
    generate_scraper(args.site, args.file)
