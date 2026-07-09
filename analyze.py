import pandas as pd
import argparse
import sys

def analyze_market_data(csv_path, currency_col):
    print(f"[*] Loading dataset: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"[!] Error: Could not find file {csv_path}")
        sys.exit(1)

    # 1. Clean the Data (Drop UNKNOWN or missing prices)
    initial_count = len(df)
    df = df[df[currency_col].notna()]
    df = df[df[currency_col] != 'UNKNOWN']
    
    # Force the column to be numeric so we can do math on it
    df[currency_col] = pd.to_numeric(df[currency_col], errors='coerce')
    df = df.dropna(subset=[currency_col])
    
    valid_count = len(df)
    
    print("\n========================================")
    print("        MARKET OVERVIEW")
    print("========================================")
    print(f"Total Rows Scanned:  {initial_count}")
    print(f"Valid Priced Items:  {valid_count} ({(valid_count/initial_count)*100:.1f}%)")
    
    if valid_count == 0:
        print("[!] No valid price data to analyze.")
        sys.exit(0)

    median_price = df[currency_col].median()
    avg_price = df[currency_col].mean()
    min_price = df[currency_col].min()
    max_price = df[currency_col].max()

    print(f"Market Median:       ${median_price:.2f}")
    print(f"Market Average:      ${avg_price:.2f}")
    print(f"Price Range:         ${min_price:.2f} - ${max_price:.2f}")

    print("\n========================================")
    print("        TOP 5 PREMIUM OUTLIERS")
    print("========================================")
    top_5 = df.nlargest(5, currency_col)
    for index, row in top_5.iterrows():
        title = str(row['TITLE'])[:60] + "..." if len(str(row['TITLE'])) > 60 else str(row['TITLE'])
        print(f"- ${row[currency_col]:.2f} | {title}")

    print("\n========================================")
    print("      BRAND / KEYWORD PRICING TIER")
    print("========================================")
    # Extract the first word of the title as a rough brand/manufacturer estimate
    df['Brand_Estimate'] = df['TITLE'].apply(lambda x: str(x).split()[0] if pd.notna(x) else 'Unknown')
    
    # Group by brand, filter for brands with at least 3 listings to avoid single-item anomalies
    brand_stats = df.groupby('Brand_Estimate').agg(
        Count=(currency_col, 'count'),
        Median_Price=(currency_col, 'median')
    ).reset_index()
    
    brand_stats = brand_stats[brand_stats['Count'] >= 3].sort_values(by='Median_Price', ascending=False).head(10)
    
    for index, row in brand_stats.iterrows():
        brand_name = str(row['Brand_Estimate'])[:15]
        print(f"- {brand_name:<15} | Listings: {row['Count']:<3} | Median: ${row['Median_Price']:.2f}")
    print()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', required=True, help="Path to the CSV file (e.g., exports/microphone_results.csv)")
    parser.add_argument('-c', '--currency', required=True, help="Target currency column name to analyze (e.g., PRICE_USD)")
    args = parser.parse_args()
    
    analyze_market_data(args.file, args.currency)
