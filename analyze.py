import os
import sys
import argparse
import pandas as pd
import json
import urllib.request
import re
import glob
import itertools

def fetch_live_exchange_rates(base_currency):
    print(f"[*] Fetching real-time global exchange rates for {base_currency}...")
    url = f"https://open.er-api.com/v6/latest/{base_currency}"
    try:
        req = urllib.request.urlopen(url)
        data = json.loads(req.read().decode('utf-8'))
        return data.get("rates", {})
    except Exception:
        print("[!] Warning: Could not fetch live exchange rates. Using 1:1 fallback.")
        return {}

def get_latest_group_files(group_name):
    """Scans the group directory and isolates the absolute newest CSV file for each unique platform."""
    group_dir = os.path.join("exports", group_name)
    if not os.path.exists(group_dir):
        print(f"[!] Critical Error: Sector directory '{group_dir}' does not exist.")
        return []
        
    all_csvs = glob.glob(f"{group_dir}/*.csv")
    platform_files = {}
    
    for filepath in all_csvs:
        filename = os.path.basename(filepath)
        parts = filename.replace(".csv", "").split("_")
        if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
            platform_name = "_".join(parts[:-2])
        else:
            platform_name = parts[0]
            
        if platform_name not in platform_files:
            platform_files[platform_name] = []
        platform_files[platform_name].append(filepath)
        
    latest_fleet = []
    for platform, files in platform_files.items():
        latest_file = sorted(files, reverse=True)[0]
        latest_fleet.append(latest_file)
        
    return latest_fleet

def load_and_merge(files, target_currency, live_rates):
    """Loads and unifies the latest CSV targets, standardizing any currency column mutations."""
    dataframes = []
    
    for filepath in files:
        file_name = os.path.basename(filepath)
        df = pd.read_csv(filepath)
        df.columns = [str(col).upper() for col in df.columns]
        
        legacy_price_col = next((col for col in df.columns if col.startswith("PRICE_")), None)
        target_price_col = f"PRICE_{target_currency}"
        
        if legacy_price_col and legacy_price_col != target_price_col:
            print(f"[*] Normalizing currency vector in {file_name} ({legacy_price_col} -> {target_price_col})")
            
            def reconvert(row):
                orig_curr = str(row.get('ORIGINAL_CURRENCY', 'UNKNOWN')).upper()
                orig_price = row.get('ORIGINAL_PRICE', pd.NA)
                
                if pd.isna(orig_price) or orig_curr == 'UNKNOWN':
                    return pd.NA
                if orig_curr == target_currency:
                    return orig_price
                if live_rates and orig_curr in live_rates:
                    return round(float(orig_price) / live_rates[orig_curr], 2)
                return pd.NA
                
            df[target_price_col] = df.apply(reconvert, axis=1)
            df = df.drop(columns=[legacy_price_col])
            
        dataframes.append(df)
    
    if not dataframes:
        return None

    return pd.concat(dataframes, ignore_index=True)

def clean_title_tokens(title):
    """Normalizes title strings and strips hyper-generic marketplace fluff for fast set operations."""
    if pd.isna(title): return set()
    
    # Strip brackets, regional signifiers, and common fluff text mutations
    text = re.sub(r'【.*?】|\[.*?\]|国内正規品|並行輸入|新品|新古品', '', str(title), flags=re.IGNORECASE)
    # Strip basic special characters and convert to lowercase
    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text).lower()
    
    # Generic descriptors that cause false positive arbitrage matches
    stop_words = {
        'keyboard', 'kit', 'pad', 'pack', 'hardware', 'edition', 'switch', 'keycaps', 'deskmat', 
        'accessories', 'version', 'case', 'plate', 'pcb', 'ink', 'pen', 'fountain', 'bottle', 'sample'
    }
    
    tokens = set(text.split()) - stop_words
    return tokens

def jaccard_similarity(set1, set2):
    """Calculates Intersection over Union for lightning-fast comparisons."""
    if not set1 or not set2: return 0.0
    intersect = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersect / union if union > 0 else 0.0

def find_arbitrage_opportunities(df, target_currency, threshold=0.75):
    """Scans cross-platform indices using Jaccard Similarity to track identical inventory mappings."""
    price_col = f"PRICE_{target_currency}"
    if price_col not in df.columns or 'TITLE' not in df.columns:
        print("[!] Execution tracking error: Pricing metadata schemas are absent.")
        return

    # Clean prices and isolate valid numeric rows
    df[price_col] = pd.to_numeric(df[price_col], errors='coerce')
    clean_df = df.dropna(subset=[price_col]).copy()
    clean_df = clean_df[clean_df[price_col] > 0] # Filter out placeholder zero layouts
    
    print(f"[*] Compiling token matrices for {len(clean_df)} items...")
    clean_df['TOKEN_SET'] = clean_df['TITLE'].apply(clean_title_tokens)
    
    platforms = clean_df['PLATFORM'].unique()
    if len(platforms) < 2:
        print("[!] Arbitrage scanner requires at least 2 competitive platform datasets to evaluate metrics.")
        return

    print(f"[*] Scanning cross-platform data pools for anomalies (Threshold: {threshold*100}%)...")
    arbitrage_opportunities = []
    
    # Separate dataframes by platform for fast cross-referencing
    platform_dfs = {plat: clean_df[clean_df['PLATFORM'] == plat] for plat in platforms}

    # Compare platforms in chunks, evaluating A vs B exactly once
    for plat_a, plat_b in itertools.combinations(platforms, 2):
        records_a = platform_dfs[plat_a].to_dict('records')
        records_b = platform_dfs[plat_b].to_dict('records')
        total_a = len(records_a)
        
        print(f"\n[*] Cross-referencing {plat_a} ({total_a} items) vs {plat_b} ({len(records_b)} items)...")
        
        for i, item_a in enumerate(records_a):
            # Update terminal progress bar
            if i % 100 == 0 or i == total_a - 1:
                progress = (i + 1) / total_a
                bar = '█' * int(20 * progress) + '░' * (20 - int(20 * progress))
                print(f"\r    [Progress] {bar} {progress*100:.1f}% | Analyzing...", end="", flush=True)
                
            for item_b in records_b:
                # Compute relative token distance metrics
                sim = jaccard_similarity(item_a['TOKEN_SET'], item_b['TOKEN_SET'])
                
                if sim >= threshold:
                    price_a = item_a[price_col]
                    price_b = item_b[price_col]
                    price_diff = abs(price_a - price_b)
                    
                    # Flag opportunities showing clear price variances
                    if price_diff > 10:  
                        arbitrage_opportunities.append({
                            "Title A": item_a['TITLE'],
                            "Platform A": item_a['PLATFORM'],
                            "Price A": price_a,
                            "Title B": item_b['TITLE'],
                            "Platform B": item_b['PLATFORM'],
                            "Price B": price_b,
                            "Spread": price_diff,
                            "Pct_Diff": (price_diff / min(price_a, price_b)) * 100
                        })
        print() # Drop down a line after progress bar finishes

    if not arbitrage_opportunities:
        print("[+] Zero direct pricing anomalies matched the active threshold layers.")
        return

    # Convert results to DataFrame and sort by the widest spread
    arb_df = pd.DataFrame(arbitrage_opportunities).sort_values(by="Spread", ascending=False)
    
    print(f"\n[+] DETECTED {len(arb_df)} CROSS-PLATFORM ARBITRAGE OPPORTUNITIES:")
    print("="*90)
    
    for idx, row in arb_df.head(20).iterrows():
        print(f"Asset Match Cluster Group Profile Indices:")
        print(f"  -> [{row['Platform A']}] {truncate_string(row['Title A'], 65)}: {row['Price A']:,.2f} THB")
        print(f"  -> [{row['Platform B']}] {truncate_string(row['Title B'], 65)}: {row['Price B']:,.2f} THB")
        print(f"  ⚡ Gross Deviation Delta: {row['Spread']:,.2f} THB ({row['Pct_Diff']:.1f}% Variance Spreads)")
        print("-" * 90)

def market_summary(df, target_currency, group_name):
    """Generates a contextual statistical overview confined strictly to the group domain."""
    print("\n" + "="*60)
    print(f" 📊 SECTOR SYNTHESIS ANALYSIS: {group_name.upper()}")
    print("="*60)
    print(f"[*] Combined Group Records : {len(df)}")
    
    platforms = df['PLATFORM'].unique() if 'PLATFORM' in df.columns else ['UNKNOWN']
    print(f"[*] Mapped Competitors     : {', '.join(platforms)}")
    
    price_col = f"PRICE_{target_currency}"
    if price_col in df.columns:
        df[price_col] = pd.to_numeric(df[price_col], errors='coerce')
        
        print("\n--- Domain Pricing Footprints ---")
        for platform in platforms:
            plat_data = df[df['PLATFORM'] == platform].dropna(subset=[price_col])
            if not plat_data.empty:
                print(f"  [{platform.upper()}] Items: {len(plat_data)} | Avg: {plat_data[price_col].mean():.2f} {target_currency} | Min: {plat_data[price_col].min():.2f} {target_currency}")
    print("="*60 + "\n")

def truncate_string(text, max_length=45):
    """Safely truncates long strings for clean terminal printing."""
    if pd.isna(text) or str(text).upper() == 'NAN': return "-"
    text = str(text)
    return text if len(text) <= max_length else text[:max_length-3] + "..."

def cross_platform_compare(df, query, target_currency):
    """Cross-references an asset keyword strictly across the current group fleet."""
    print(f"\n[*] Running domain arbitrage analysis for target token: '{query}'...")
    
    if 'TITLE' not in df.columns:
        print("[!] Error: TITLE column missing from unified matrix.")
        return
        
    price_col = f"PRICE_{target_currency}"
    if price_col not in df.columns:
        print(f"[!] Error: Normalized {price_col} column missing.")
        return
        
    df[price_col] = pd.to_numeric(df[price_col], errors='coerce')
    matches = df[df['TITLE'].str.contains(query, case=False, na=False)].copy()
    
    if matches.empty:
        print(f"[!] Zero cross-platform matches located for query target '{query}' inside this group.")
        return
        
    print(f"[+] Located {len(matches)} matches sorted by lowest price value:\n")
    
    # 1. SORT THE DATA FIRST
    sorted_matches = matches.sort_values(by=price_col)
    
    # 2. FORMAT AND CLEAN STRINGS
    sorted_matches['TITLE'] = sorted_matches['TITLE'].apply(truncate_string)
    if 'VARIANTS' in sorted_matches.columns:
        sorted_matches['VARIANTS'] = sorted_matches['VARIANTS'].apply(lambda x: truncate_string(x, 30))
    if 'BRAND' in sorted_matches.columns:
        sorted_matches['BRAND'] = sorted_matches['BRAND'].apply(lambda x: truncate_string(x, 15))
        
    # 3. REPLACE NaNs WITH DASHES
    sorted_matches = sorted_matches.fillna("-")
    
    display_cols = ['PLATFORM', 'TITLE']
    if 'BRAND' in sorted_matches.columns: display_cols.append('BRAND')
    if 'VARIANTS' in sorted_matches.columns: display_cols.append('VARIANTS')
    display_cols.append(price_col)
    
    # Rename price column for display
    display_name = f"PRICE ({target_currency})"
    sorted_matches = sorted_matches.rename(columns={price_col: display_name})
    display_cols[-1] = display_name
    
    # Print exactly 20 items to prevent terminal flooding
    print(sorted_matches[display_cols].head(20).to_string(index=False, justify='left'))
    
    if len(sorted_matches) > 20:
        print(f"\n... and {len(sorted_matches) - 20} more matched rows hidden.")
    print("="*60 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PolyPrice Advanced Sector Analytics Suite")
    parser.add_argument('-g', '--group', type=str, required=True, help="Target category folder inside exports/")
    parser.add_argument('-c', '--currency', type=str, default="THB", help="Target currency layer (Default: THB)")
    parser.add_argument('-s', '--search', type=str, help="Simple quick filter search")
    parser.add_argument('--compare', type=str, help="Run cross-platform asset searches")
    parser.add_argument('--summary', action='store_true', help="Print macro domain synthesis statistics")
    parser.add_argument('--arbitrage', action='store_true', help="Execute automated fuzzy title tracking across fleet maps")
    
    args = parser.parse_args()
    group_name = args.group.lower()
    target_currency = args.currency.upper()
    
    latest_fleet_files = get_latest_group_files(group_name)
    
    if latest_fleet_files:
        print(f"[*] Targeted Fleet Base Files Located: {[os.path.basename(f) for f in latest_fleet_files]}")
        live_rates = fetch_live_exchange_rates(target_currency)
        master_df = load_and_merge(latest_fleet_files, target_currency, live_rates)
        
        if master_df is not None:
            if args.summary:
                market_summary(master_df, target_currency, group_name)
            if args.compare:
                cross_platform_compare(master_df, args.compare, target_currency)
            if args.arbitrage:
                find_arbitrage_opportunities(master_df, target_currency)
            if args.search and not args.compare and not args.arbitrage:
                if 'TITLE' in master_df.columns:
                    results = master_df[master_df['TITLE'].str.contains(args.search, case=False, na=False)]
                    print(f"[*] Found {len(results)} matches for '{args.search}' inside this group footprint.")
