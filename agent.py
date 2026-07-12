import os
import ollama
import argparse

def generate_scraper(site_name, html_file, schema_string):
    output_file = f"parsers/{site_name}.py"
    
    if not os.path.exists(html_file):
        print(f"[!] Error: '{html_file}' not found. Run scout.py first.")
        return

    # Initialize the parsers module directory safely
    os.makedirs("parsers", exist_ok=True)
    with open("parsers/__init__.py", "a") as f: pass

    with open(html_file, "r", encoding="utf-8") as f:
        html_snippet = f.read()

    # Parse schema string into a list of clean, distinct keys
    schema_keys = [key.strip() for key in schema_string.split(',')]
    
    print("\n" + "="*60)
    print(f" 🏭 UNIVERSAL PARSER COMPILER: {site_name.upper()}")
    print(f" [*] Targeting Blueprint: {schema_keys}")
    print("="*60)
    print("[*] Waking up Qwen 2.5 Coder 32B...")

    # Build a sample dictionary structure dynamically to show the LLM exactly what to do
    sample_dict = {key: f"extracted_{key.lower()}_val" for key in schema_keys}

    prompt = f"""You are an expert Python data engineer specializing in Beautiful Soup 4.
Analyze the provided HTML snippet and write a pristine, production-ready Python module named 'parsers/{site_name}.py'.

Your module must expose exactly two functions:
1. 'normalize_url(url)': Cleans tracking tokens or handles relative paths specific to this domain.
2. 'extract_page_data(html_content)': Iterates through the item containers and returns a list of dictionaries.

CRITICAL ARCHITECTURAL BLUEPRINT:
Your 'extract_page_data' function MUST extract exactly the data fields requested by the user's schema.
The output dictionary keys MUST perfectly match the case-sensitivity and naming of the requested schema fields.

REQUESTED SCHEMA FIELDS:
{schema_keys}

EXACT DICTIONARY REPLICA TEMPLATE FOR YOUR CODE:
results.append({sample_dict})

STRICT PIPELINE RULES:
1. Never use `.text` directly on a element selection. Always use `element.get_text(strip=True) if element else 'N/A'` to prevent AttributeErrors.
2. Ensure you find the correct repeating element wrapper that safely captures all items on the page.
3. Output ONLY valid, executable Python code. Do NOT wrap your response in markdown backticks (```), do NOT write an 'Example usage' block at the bottom, and do NOT include conversational filler.

HTML SNIPPET TO ANALYZE:
{html_snippet}

OUTPUT STRUCTURE REFERENCE:
from bs4 import BeautifulSoup
import re

def normalize_url(url):
    if not url or url == "N/A": return "N/A"
    # Domain specific cleaning logic here
    return url

def extract_page_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    # Your extraction loop implementing the requested replica template goes here
    return results
"""

    try:
        response = ollama.generate(
            model="qwen2.5-coder:32b",
            prompt=prompt,
            options={
                "temperature": 0.0, 
                "num_predict": 1200 
            }
        )
        
        generated_code = response["response"]
        
        # Safe extraction of raw code text block
        if "```python" in generated_code:
            generated_code = generated_code.split("```python")[1].split("```")[0]
        elif "```" in generated_code:
            generated_code = generated_code.split("```")[1].split("```")[0]
            
        generated_code = generated_code.strip()
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(generated_code)
            
        print(f"[+] SUCCESS! Universal parser engineered inside '{output_file}'.")
        print("[+] Verify the mapping structure matches your targets.\n")
        
    except Exception as e:
        print(f"[!] Agent compilation failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--site', type=str, required=True, help="Target module nickname (e.g. geekhack, stationery_co)")
    parser.add_argument('-f', '--file', type=str, default="sample.html", help="Path to scanned layout snapshot")
    parser.add_argument('--schema', type=str, default="Title, Price, URL", help="Comma-separated data fields to extract")
    args = parser.parse_args()
    
    generate_scraper(args.site, args.file, args.schema)
