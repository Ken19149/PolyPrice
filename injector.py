import json
import os

REGISTRY_FILE = "registry.json"

def load_registry():
    """Loads the current configuration matrix."""
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"groups": {}, "sites": {}}

def save_registry(data):
    """Safely commits the updated dictionary back to the JSON file."""
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Successfully injected target into {REGISTRY_FILE}!")

def main():
    print("="*60)
    print(" 💉 REGISTRY INJECTION WIZARD")
    print("="*60)
    
    registry = load_registry()
    
    # 1. Get Store Key
    store_key = input("Enter the target key (e.g., 'kbdfans'): ").strip().lower().replace(" ", "_")
    if not store_key:
        print("[!] Target key cannot be empty.")
        return
        
    if store_key in registry["sites"]:
        print(f"[!] Warning: '{store_key}' already exists in the registry. Overwriting configuration...")

    # 2. Get Group
    print(f"\n[*] Active sector clusters: {', '.join(registry['groups'].keys())}")
    group = input("Enter the sector group (e.g., 'keyboards'): ").strip().lower()
    
    # 3. Get URL Template
    print("\n[*] Note: Inject {page} for pagination and {keyword} for search strings.")
    url = input("Enter the URL template (e.g., 'https://domain.com/products.json?limit=250&page={page}'): ").strip()
    
    # 4. Get Parser
    parser = input("Enter the parser type [default: shopify]: ").strip().lower()
    if not parser:
        parser = "shopify"
        
    # 5. Get Domain
    domain = input("Enter the base domain (e.g., 'https://domain.com'): ").strip()
    
    # --- Execute Matrix Update ---
    registry["sites"][store_key] = {
        "url": url,
        "parser": parser,
        "domain": domain
    }
    
    if group not in registry["groups"]:
        registry["groups"][group] = []
    
    if store_key not in registry["groups"][group]:
        registry["groups"][group].append(store_key)
        
    save_registry(registry)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Injection aborted (^C). No changes committed.")
