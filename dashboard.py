import streamlit as st
import pandas as pd
import os
import glob

st.set_page_config(page_title="PolyPrice Intel", page_icon="☁️", layout="wide")

st.markdown("<h1 style='text-align: center; color: #8BB8E8;'>PolyPrice Data Hub</h1>", unsafe_allow_html=True)
st.markdown("---")

# 1. Dynamic Directory Scanning
if not os.path.exists("exports"):
    st.error("No exports folder found. Please run the Orchestrator first.")
    st.stop()

groups = [d for d in os.listdir("exports") if os.path.isdir(os.path.join("exports", d))]
if not groups:
    st.warning("No data groups found in the exports folder.")
    st.stop()

# 2. Sidebar Navigation
st.sidebar.markdown("### 🗂️ Navigation")
selected_group = st.sidebar.selectbox("Select Market Sector", groups)

files = glob.glob(f"exports/{selected_group}/*.csv")
if not files:
    st.sidebar.warning(f"No CSV files found in {selected_group}.")
    st.stop()

selected_file = st.sidebar.selectbox("Select Historical Archive", sorted(files, reverse=True))

# 3. Data Processing
if selected_file:
    df = pd.read_csv(selected_file)
    
    # Optional: Fill empty NA values for a cleaner look
    df.fillna("N/A", inplace=True)
    
    # 4. Top Level Metrics
    st.markdown(f"### Snapshot: `{os.path.basename(selected_file)}`")
    col1, col2, col3 = st.columns(3)
    
    col1.metric("Total Inventory Tracked", f"{len(df):,}")
    
    # Dynamic Currency Metric
    price_col = [col for col in df.columns if col.startswith("PRICE_")]
    if price_col:
        currency_code = price_col[0].split("_")[1]
        avg_price = df[price_col[0]].replace('N/A', 0).astype(float).mean()
        col2.metric("Average Market Price", f"{avg_price:,.2f} {currency_code}")
    else:
        col2.metric("Average Market Price", "Data Unavailable")
        
    unique_brands = df["BRAND"].nunique() if "BRAND" in df.columns else "N/A"
    col3.metric("Unique Brands", unique_brands)

    st.markdown("<br>", unsafe_allow_html=True)

    # 5. Search & Filter
    search_query = st.text_input("🔍 Search Database (Title, Brand, or Tags)", "")
    if search_query:
        # Create a mask to search across all columns as strings
        mask = df.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)
        display_df = df[mask]
    else:
        display_df = df

    # 6. The Data Grid
    st.dataframe(display_df, width="stretch", height=600)
