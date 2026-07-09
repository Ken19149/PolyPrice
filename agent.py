import os
import ollama

def generate_scraper(html_file="sample.html", output_file="generated_scraper.py"):
    if not os.path.exists(html_file):
        print(f"[!] Error: '{html_file}' not found. Run scout.py first.")
        return

    with open(html_file, "r", encoding="utf-8") as f:
        html_snippet = f.read()

    print("[*] Waking up Qwen 2.5 Coder 32B...")
    print("[*] Deploying strict Template Prompt...")

    prompt = (
    "You are an expert Python data engineer. Analyze the following HTML snippet and write a Python file named 'generated_scraper.py'.\n"
    "Your job is to provide two functions:\n\n"
    "1. 'extract_page_data(html_content)': Safely extract Title, Price, and URL.\n"
    "2. 'normalize_url(url)': Clean the URL. If the target is Amazon, extract the ASIN (the 10-character code) "
    "   and return 'https://www.amazon.co.jp/dp/[ASIN]'. If it is not Amazon, return the original URL.\n\n"
    "RULES:\n"
    "1. Never use `.text` directly. Always use `element.get_text(strip=True) if element else 'N/A'`.\n"
    "2. Prepend 'https://www.amazon.co.jp' to any relative URLs.\n"
    "3. Output ONLY the raw Python code. Do not output markdown backticks (```) or conversational filler.\n\n"
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
            options={
                "temperature": 0.0, 
                "num_predict": 1000 
            }
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
    generate_scraper()
