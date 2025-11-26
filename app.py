import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# -------------------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------------------
st.set_page_config(page_title="Hospital Consignment Optimizer", layout="wide")

# -------------------------------------------------------------
# LOAD FUNCTIONS
# -------------------------------------------------------------
@st.cache_data
def load_file(uploaded_file):
    """Load CSV or Excel."""
    if uploaded_file.name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file)

@st.cache_data
def load_demo():
    return pd.read_csv("diagnostic_kits_consignment_demo.csv")

# -------------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------------
st.sidebar.header("📁 Data Input")

use_demo = st.sidebar.button("Use Demo Dataset")
uploaded = st.sidebar.file_uploader("Upload your dataset (CSV or Excel)", type=["csv", "xlsx"])

if use_demo:
    df = load_demo()
elif uploaded:
    df = load_file(uploaded)
else:
    st.sidebar.info("Upload a file or click 'Use Demo Dataset'")
    st.stop()

# -------------------------------------------------------------
# VALIDATION
# -------------------------------------------------------------
required_cols = [
    "Record_Type","Hospital_ID","Hospital_Name","Product_ID","Product_Name",
    "Product_Category","Usage_Family","Movement_Date","Movement_Qty",
    "Current_Stock","Expiry_Date","Consignment_Start_Date"
]

if not all(col in df.columns for col in required_cols):
    st.error(f"Your dataset is missing required columns: {required_cols}")
    st.stop()

# Convert date columns
df["Movement_Date"] = pd.to_datetime(df["Movement_Date"], errors="coerce")
df["Expiry_Date"] = pd.to_datetime(df["Expiry_Date"], errors="coerce")
df["Consignment_Start_Date"] = pd.to_datetime(df["Consignment_Start_Date"], errors="coerce")

# Separate movements and inventory snapshot
mov = df[df["Record_Type"] == "movement"].copy()
inv = df[df["Record_Type"] == "inventory"].copy()

# -------------------------------------------------------------
# FILTER PANEL (ABOVE KPIs)
# -------------------------------------------------------------
st.markdown("### 🔍 Filters")

c1, c2, c3 = st.columns(3)

hospital_filter = c1.multiselect("Hospital", df["Hospital_Name"].unique())
category_filter = c2.multiselect("Product Category", df["Product_Category"].unique())
product_filter = c3.multiselect("Product Name", df["Product_Name"].unique())

filtered_mov = mov.copy()
filtered_inv = inv.copy()

if hospital_filter:
    filtered_mov = filtered_mov[filtered_mov["Hospital_Name"].isin(hospital_filter)]
    filtered_inv = filtered_inv[filtered_inv["Hospital_Name"].isin(hospital_filter)]

if category_filter:
    filtered_mov = filtered_mov[filtered_mov["Product_Category"].isin(category_filter)]
    filtered_inv = filtered_inv[filtered_inv["Product_Category"].isin(category_filter)]

if product_filter:
    filtered_mov = filtered_mov[filtered_mov["Product_Name"].isin(product_filter)]
    filtered_inv = filtered_inv[filtered_inv["Product_Name"].isin(product_filter)]

# -------------------------------------------------------------
# STEP 1 — 6-MONTH CONSUMPTION
# -------------------------------------------------------------
today = datetime.today()
six_months_ago = today - timedelta(days=180)

mov_6m = filtered_mov[filtered_mov["Movement_Date"] >= six_months_ago]

consumption_6m = (
    mov_6m.groupby(["Hospital_Name","Product_Name"])["Movement_Qty"]
    .sum()
    .reset_index()
    .rename(columns={"Movement_Qty":"Consumption_6M"})
)

# -------------------------------------------------------------
# STEP 2 — CONSIGNMENT START DATE + DAYS ACTIVE
# -------------------------------------------------------------
eighteen_months_ago = today - timedelta(days=540)

mov_18m = filtered_mov[filtered_mov["Movement_Date"] >= eighteen_months_ago]

start_dates = (
    mov_18m.groupby(["Hospital_Name","Product_Name"])["Movement_Date"]
    .min()
    .reset_index()
    .rename(columns={"Movement_Date":"Start_Date"})
)

start_dates["Days_Active"] = (today - start_dates["Start_Date"]).dt.days

# -------------------------------------------------------------
# STEP 3 — CONSUMPTION STATISTICS (18M)
# -------------------------------------------------------------
stats = (
    mov_18m.groupby(["Hospital_Name","Product_Name"])
    .agg(
        Number_of_Consumptions=("Movement_Qty","count"),
        Max_Consumption=("Movement_Qty","max")
    )
    .reset_index()
)

# -------------------------------------------------------------
# STEP 4 — ACTIVITY QUOTIENT + CLASSIFICATION
# -------------------------------------------------------------
merged = filtered_inv.merge(consumption_6m, on=["Hospital_Name","Product_Name"], how="left")
merged = merged.merge(start_dates, on=["Hospital_Name","Product_Name"], how="left")
merged = merged.merge(stats, on=["Hospital_Name","Product_Name"], how="left")

merged["Number_of_Consumptions"] = merged["Number_of_Consumptions"].fillna(0)
merged["Max_Consumption"] = merged["Max_Consumption"].fillna(0)
merged["Consumption_6M"] = merged["Consumption_6M"].fillna(0)

merged["AvgWeekly"] = merged["Consumption_6M"] / 26

merged["Activity_Quotient"] = merged.apply(
    lambda row: row["Days_Active"]/row["Number_of_Consumptions"]
    if row["Number_of_Consumptions"] > 0 else 999,
    axis=1
)

def classify(q):
    if q <= 10: return "A"
    if q <= 20: return "B"
    if q <= 40: return "C"
    return "D"

merged["Class"] = merged["Activity_Quotient"].apply(classify)

safety_map = {"A":3,"B":2,"C":1,"D":0}
merged["SafetyStock"] = merged["Class"].map(safety_map)

# -------------------------------------------------------------
# STEP 5 — RECOMMENDED TARGET STOCK
# -------------------------------------------------------------
merged["Recommended"] = merged["Max_Consumption"] + merged["SafetyStock"]

# -------------------------------------------------------------
# EXPIRY FLAGS
# -------------------------------------------------------------
def expiry_flag(date):
    if pd.isna(date):
        return "🟩 OK"
    if date < today:
        return "🟥 EXPIRED"
    if date <= today + timedelta(days=30):
        return "🟧 Expiring Soon"
    return "🟩 OK"

merged["Expiry_Status"] = merged["Expiry_Date"].apply(expiry_flag)

# -------------------------------------------------------------
# KPI SECTION
# -------------------------------------------------------------
st.markdown("### 📊 Key Metrics")

k1, k2, k3, k4, k5 = st.columns(5)

k1.metric("Total Consumption (6M)", int(merged["Consumption_6M"].sum()))
k2.metric("Current Inventory", int(merged["Current_Stock"].sum()))
k3.metric("Total Recommended", int(merged["Recommended"].sum()))

# Reduction and increase
differences = merged["Current_Stock"] - merged["Recommended"]
k4.metric("Reduction Needed", int(differences[differences > 0].sum()))
k5.metric("Increase Needed", int(-differences[differences < 0].sum()))

st.divider()

# -------------------------------------------------------------
# TABS
# -------------------------------------------------------------
tab_matrix, tab_reco = st.tabs(["📦 Inventory Matrix", "✔ Recommendations"])

# -------------------------------------------------------------
# MATRIX: Category × Hospital
# -------------------------------------------------------------
with tab_matrix:
    st.subheader("Category × Hospital Inventory Difference")

    merged["Difference"] = merged["Current_Stock"] - merged["Recommended"]

    pivot = merged.pivot_table(
        index="Product_Category",
        columns="Hospital_Name",
        values="Difference",
        aggfunc="sum",
        fill_value=0
    )

    def color_cells(val):
        if val < 0: return "background-color:#ffcccc;"
        if val > 0: return "background-color:#ccffcc;"
        return ""

    st.dataframe(pivot.style.applymap(color_cells), use_container_width=True)

# -------------------------------------------------------------
# RECOMMENDATIONS TAB
# -------------------------------------------------------------
with tab_reco:
    st.subheader("Recommended Actions")

    merged["Action"] = merged.apply(
        lambda row: "Reduce" if row["Difference"] > 0
        else ("Increase" if row["Difference"] < 0 else "OK"),
        axis=1
    )

    merged.loc[merged["Expiry_Status"]=="🟥 EXPIRED","Action"]="REMOVE – Expired"

    table = merged[[
        "Hospital_Name","Product_Name","Product_Category",
        "Current_Stock","Recommended","Difference",
        "Class","SafetyStock","Max_Consumption",
        "Expiry_Date","Expiry_Status","Action"
    ]]

    st.dataframe(table, use_container_width=True)

