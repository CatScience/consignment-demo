import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="Consignment Optimizer", layout="wide")

# -------------------------
# Load dataset
# -------------------------
@st.cache_data
def load_demo_dataset():
    return pd.read_csv("diagnostic_kits_consignment_demo.csv")

def calculate_recommendations(df):

    df = df.copy()

    df["Recommended"] = (df["Avg_Weekly_Consumption"] * 6).round().astype(int)
    df["Difference"] = df["Recommended"] - df["Current_Inventory"]

    df["Action"] = df["Difference"].apply(
        lambda x: "Increase" if x > 0 else ("Reduce" if x < 0 else "OK")
    )

    today = datetime.today()
    soon = today + timedelta(days=30)

    def expiry_status(date_str):
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            return "🟩 OK"  # fallback
        if d < today:
            return "🟥 EXPIRED"
        elif today <= d <= soon:
            return "🟧 Expiring Soon"
        else:
            return "🟩 OK"

    df["Expiry_Status"] = df["Expiry_Date"].apply(expiry_status)

    def adjust_action(row):
        if row["Expiry_Status"] == "🟥 EXPIRED":
            return "REMOVE – Expired"
        elif row["Expiry_Status"] == "🟧 Expiring Soon":
            if row["Action"] == "Increase":
                return "Increase (Expiring Soon)"
            elif row["Action"] == "Reduce":
                return "Reduce (Expiring Soon)"
            else:
                return "OK (Expiring Soon)"
        return row["Action"]

    df["Action"] = df.apply(adjust_action, axis=1)

    return df


# -------------------------
# Sidebar
# -------------------------
st.sidebar.title("Data Input")

demo_btn = st.sidebar.button("Use Demo Dataset")

uploaded = st.sidebar.file_uploader("Upload your CSV dataset", type=["csv"])

if demo_btn:
    df = load_demo_dataset()
elif uploaded:
    df = pd.read_csv(uploaded)
else:
    st.sidebar.info("Upload a CSV or click 'Use Demo Dataset'")
    st.stop()

# Make sure required columns exist
required_cols = ["Hospital", "Product", "Current_Inventory",
                 "Avg_Weekly_Consumption", "Expiry_Date"]

if not all(c in df.columns for c in required_cols):
    st.error(f"Dataset missing required columns: {required_cols}")
    st.stop()

# -------------------------
# Filters
# -------------------------
with st.container():
    st.markdown("### Filters")

    col1, col2, col3 = st.columns(3)

    hospitals = col1.multiselect("Hospital", df["Hospital"].unique())
    products = col2.multiselect("Product", df["Product"].unique())
    categories = col3.multiselect("Category", df["Category"].unique() if "Category" in df.columns else [])

    filtered = df.copy()
    if hospitals: filtered = filtered[filtered["Hospital"].isin(hospitals)]
    if products: filtered = filtered[filtered["Product"].isin(products)]
    if categories and "Category" in filtered.columns:
        filtered = filtered[filtered["Category"].isin(categories)]


# -------------------------
# KPI Cards
# -------------------------
st.markdown("### Key Metrics")

rec_df = calculate_recommendations(filtered)

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

kpi1.metric("Avg. weekly consumption", int(filtered["Avg_Weekly_Consumption"].mean()))
kpi2.metric("Current inventory", int(filtered["Current_Inventory"].sum()))
kpi3.metric("Reduction", int(rec_df[rec_df["Difference"] < 0]["Difference"].abs().sum()))
kpi4.metric("Increase", int(rec_df[rec_df["Difference"] > 0]["Difference"].sum()))
kpi5.metric("Optimized inventory", int(rec_df["Recommended"].sum()))

st.divider()


# -------------------------
# Tabs
# -------------------------
tab_matrix, tab_reco = st.tabs(["📊 Inventory Matrix", "✔ Recommendations"])

# -------------------------
# Inventory Matrix (Option B)
# Category × Hospital
# -------------------------
with tab_matrix:

    if "Category" not in rec_df.columns:
        st.warning("Dataset has no 'Category' column — matrix unavailable.")
    else:
        pivot = rec_df.pivot_table(
            index="Category",
            columns="Hospital",
            values="Difference",
            aggfunc="sum",
            fill_value=0
        )

        # Apply color formatting
        def color_cells(val):
            if val < 0:
                return "background-color: #ffcccc;"  # light red
            elif val > 0:
                return "background-color: #ccffcc;"  # light green
            return ""

        st.dataframe(pivot.style.applymap(color_cells), use_container_width=True)

# -------------------------
# Recommendations Tab
# -------------------------
with tab_reco:

    st.markdown("### Recommended Actions")

    show = rec_df[[
        "Hospital", "Product", "Current_Inventory", "Recommended",
        "Difference", "Action", "Expiry_Date", "Expiry_Status"
    ]]

    st.dataframe(show, use_container_width=True)

