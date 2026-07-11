import argparse
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def scrape_snapshot(url, selector=None, output_path="sample.html"):
    print(f"[*] Scout deployed. Targeting URL: {url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="ja-JP"
        )
        
        Stealth().apply_stealth_sync(context)
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(6000) 
            
            print("[*] Triggering lazy-loads...")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
            page.wait_for_timeout(1000)
            
            # --- THE V8 JAVASCRIPT PURGE ---
            # This executes instantly inside the Chromium browser engine.
            print("[*] Initiating V8 Engine DOM Purge...")
            page.evaluate("""() => {
                const tagsToKill = ['script', 'style', 'svg', 'noscript', 'iframe', 'path', 'canvas', 'img', 'video', 'nav', 'footer', 'form'];
                tagsToKill.forEach(tag => {
                    document.querySelectorAll(tag).forEach(el => el.remove());
                });
                
                // Keep only class and href attributes
                document.querySelectorAll('*').forEach(el => {
                    let attrs = el.attributes;
                    let toRemove = [];
                    for (let i = 0; i < attrs.length; i++) {
                        if (attrs[i].name !== 'class' && attrs[i].name !== 'href') {
                            toRemove.push(attrs[i].name);
                        }
                    }
                    toRemove.forEach(attr => el.removeAttribute(attr));
                });
            }""")
            
            if selector:
                print(f"[*] Targeting specific container: '{selector}'")
                page.wait_for_selector(selector, timeout=10000)
                raw_html = page.locator(selector).inner_html()
            else:
                raw_html = page.locator("body").inner_html()
            
            # Remove giant blocks of empty space
            import re
            clean_markup = re.sub(r'\n\s*\n', '\n', raw_html)
            
            # Context window protection (roughly top 5-10 items)
            char_limit = 25000
            if len(clean_markup) > char_limit:
                clean_markup = clean_markup[:char_limit] + "\n\n<!-- TRUNCATED TO PROTECT LLM CONTEXT WINDOW -->"
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(clean_markup)
                
            print(f"[+] SUCCESS! Universal layout exported to: '{output_path}' ({len(clean_markup) / 1024:.2f} KB)")
            return True
            
        except Exception as e:
            print(f"[!] Scout execution failed: {e}")
            return False
        finally:
            browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PolyPrice V2 Universal Scout")
    parser.add_argument("-u", "--url", type=str, required=True, help="Target URL")
    parser.add_argument("-s", "--selector", type=str, required=False, help="CSS Selector for the product grid")
    args = parser.parse_args()
    
    scrape_snapshot(args.url, args.selector)
