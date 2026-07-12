import os
import sys
import argparse
import pandas as pd
import json
import urllib.request
import re

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

def load_and_merge(files, target_currency, live_rates):
    """Loads and merges CSVs, automatically unifying mismatched legacy currency columns."""
    dataframes = []
    
    for file in files:
        filepath = os.path.join("exports", file)
        if not os.path.exists(filepath):
            print(f"[!] Warning: {filepath} not found.")
            continue
            
        df = pd.read_csv(filepath)
        df.columns = [str(col).upper() for col in df.columns]
        
        # Determine if this file has a legacy converted price column
        legacy_price_col = next((col for col in df.columns if col.startswith("PRICE_")), None)
        target_price_col = f"PRICE_{target_currency}"
        
        # If the file's price currency doesn't match our target, we must re-convert
        if legacy_price_col and legacy_price_col != target_price_col:
            print(f"[*] Normalizing legacy currency in {file} ({legacy_price_col} -> {target_price_col})")
            
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
            # Drop the old legacy column so it doesn't pollute the master dataframe
            df = df.drop(columns=[legacy_price_col])
            
        dataframes.append(df)
    
    if not dataframes:
        print("[!] No data loaded. Exiting.")
        return None

    # Perform structural Outer Join
    master_df = pd.concat(dataframes, ignore_index=True)
    return master_df

def market_summary(df, target_currency):
    """Generates a high-level statistical overview across all combined data streams."""
    print("\n" + "="*60)
    print(" 📊 CROSS-FILE SYNTHESIS SUMMARY")
    print("="*60)
    print(f"[*] Combined Dataset Records: {len(df)}")
    
    platforms = df['PLATFORM'].unique() if 'PLATFORM' in df.columns else ['UNKNOWN']
    print(f"[*] Active Data Streams: {', '.join(platforms)}")
    
    price_col = f"PRICE_{target_currency}"
    
    if price_col in df.columns:
        df[price_col] = pd.to_numeric(df[price_col], errors='coerce')
        
        print("\n--- Platform Pricing Footprints ---")
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
    """Cross-references a query string across multiple file sources."""
    print(f"\n[*] Running cross-platform arbitrage analysis for target: '{query}'...")
    
    if 'TITLE' not in df.columns:
        print("[!] Critical Failure: TITLE column missing from unified matrix.")
        return
        
    price_col = f"PRICE_{target_currency}"
    if price_col not in df.columns:
        print(f"[!] Critical Failure: Normalized {price_col} matrix missing.")
        return
        
    df[price_col] = pd.to_numeric(df[price_col], errors='coerce')
    matches = df[df['TITLE'].str.contains(query, case=False, na=False)].copy()
    
    if matches.empty:
        print(f"[!] Zero cross-file matches located for query target '{query}'.")
        return
        
    print(f"[+] Located {len(matches)} historical or multi-platform cross-matches:\n")
    
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
        print(f"\n... and {len(sorted_matches) - 20} more rows hidden.")
    print("="*60 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PolyPrice Advanced Analytics Suite")
    parser.add_argument('-f', '--files', type=str, required=True, help="Comma-separated list of CSV files in exports/ to synthesize")
    parser.add_argument('-c', '--currency', type=str, default="THB", help="Target currency for unification (Default: THB)")
    parser.add_argument('-s', '--search', type=str, help="Filter the combined dataset by a specific keyword")
    parser.add_argument('--compare', type=str, help="Run cross-platform/arbitrage matching for a product token")
    parser.add_argument('--summary', action='store_true', help="Print deep cross-file market summary metrics")
    
    args = parser.parse_args()
    target_currency = args.currency.upper()
    
    live_rates = fetch_live_exchange_rates(target_currency)
    
    target_files = [f.strip() for f in args.files.split(',')]
    master_df = load_and_merge(target_files, target_currency, live_rates)
    
    if master_df is not None:
        if args.summary:
            market_summary(master_df, target_currency)
        if args.compare:
            cross_platform_compare(master_df, args.compare, target_currency)
        if args.search and not args.compare:
            if 'TITLE' in master_df.columns:
                results = master_df[master_df['TITLE'].str.contains(args.search, case=False, na=False)]
                print(f"[*] Found {len(results)} matches for '{args.search}'. Use --compare to view structured tables.")
