import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime, timedelta

# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------
st.set_page_config(
    page_title="Hospital Consignment Demo",
    layout="wide"
)

st.title("📦 Hospital Consignment Intelligence Demo")
st.write("Upload a dataset to analyze consumption, stock levels, expiry risk, and recommended quantities.")


# ---------------------------------------------------
# FILE UPLOADER
# ---------------------------------------------------
uploaded = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded is not None:

    # Load data
    df = pd.read_csv(uploaded)

    # ---------------------------------------------------
    # DATA CLEANING
    # ---------------------------------------------------
    df["Movement_Date"] = pd.to_datetime(df["Movement_Date"], errors="coerce")
    df["Expiry_Date"] = pd.to_datetime(df["Expiry_Date"], errors="coerce")
    df["Consignment_Start_Date"] = pd.to_datetime(df["Consignment_Start_Date"], errors="coerce")

    df["Movement_Qty"] = pd.to_numeric(df["Movement_Qty"], errors="coerce")
    df["Current_Stock"] = pd.to_numeric(df["Current_Stock"], errors="coerce")

    # Separate movement + inventory
    df_mov = df[df["Record_Type"] == "movement"].copy()
    df_inv = df[df["Record_Type"] == "inventory"].copy()

    # ---------------------------------------------------
    # FILTERS
    # ---------------------------------------------------
    st.subheader("🔎 Filters")

    hospitals = ["All"] + sorted(df["Hospital_Name"].dropna().unique())
    categories = ["All"] + sorted(df["Product_Category"].dropna().unique())
    products = ["All"] + sorted(df["Product_Name"].dropna().unique())

    col1, col2, col3 = st.columns(3)

    selected_hospital = col1.selectbox("Hospital", hospitals)
    selected_category = col2.selectbox("Product Category", categories)
    selected_product = col3.selectbox("Product Name", products)

    # Apply filters (safe)
    if selected_hospital != "All":
        df_mov = df_mov[df_mov["Hospital_Name"] == selected_hospital]
        df_inv = df_inv[df_inv["Hospital_Name"] == selected_hospital]

    if selected_category != "All":
        df_mov = df_mov[df_mov["Product_Category"] == selected_category]
        df_inv = df_inv[df_inv["Product_Category"] == selected_category]

    if selected_product != "All":
        df_mov = df_mov[df_mov["Product_Name"] == selected_product]
        df_inv = df_inv[df_inv["Product_Name"] == selected_product]


    # ---------------------------------------------------
    # CALCULATIONS
    # ---------------------------------------------------
    st.subheader("📊 Analytics")

    today = datetime.today()
    six_months_ago = today - timedelta(days=180)

    # Consumption last 6 months
    cons_last6 = (
        df_mov[df_mov["Movement_Date"] >= six_months_ago]
        .groupby("Product_ID")["Movement_Qty"]
        .sum()
        .reset_index()
        .rename(columns={"Movement_Qty": "Consumption_6M"})
    )

    # Merge inventory + consumption
    results = df_inv.merge(cons_last6, on="Product_ID", how="left")
    results["Consumption_6M"] = results["Consumption_6M"].fillna(0)

    # Avg days between movements
    avg_days_list = []
    for pid in df_mov["Product_ID"].unique():
        sub = df_mov[df_mov["Product_ID"] == pid].sort_values("Movement_Date")
        if len(sub) > 1:
            diffs = sub["Movement_Date"].diff().dt.days[1:]
            avg_days_list.append([pid, diffs.mean()])
        else:
            avg_days_list.append([pid, np.nan])

    avg_days = pd.DataFrame(avg_days_list, columns=["Product_ID", "Avg_Days_Between"])
    results = results.merge(avg_days, on="Product_ID", how="left")


    # Activity classification logic
    def classify(row):
        fam = row["Usage_Family"]
        days = row["Avg_Days_Between"]

        if pd.isna(days):
            return "D"

        if fam == "high":
            if days <= 7: return "A"
            elif days <= 14: return "B"
            elif days <= 30: return "C"
            else: return "D"

        if fam == "medium":
            if days <= 14: return "A"
            elif days <= 28: return "B"
            elif days <= 60: return "C"
            else: return "D"

        if fam == "low":
            if days <= 30: return "A"
            elif days <= 60: return "B"
            elif days <= 120: return "C"
            else: return "D"

    results["Activity_Class"] = results.apply(classify, axis=1)


    # Recommended stock logic
    def recommended(row):
        cons_weekly = row["Consumption_6M"] / 26
        fam = row["Usage_Family"]
        cls = row["Activity_Class"]

        if fam == "high":
            return round(cons_weekly * {"A":3,"B":2,"C":1,"D":0.2}[cls])
        if fam == "medium":
            return round(cons_weekly * {"A":2,"B":1.5,"C":1,"D":0.2}[cls])
        if fam == "low":
            return round(cons_weekly * {"A":1,"B":1,"C":1,"D":0}[cls])

    results["Recommended_Stock"] = results.apply(recommended, axis=1)


    # Expiry risk logic
    def expiry_risk(date):
        if pd.isna(date):
            return "Unknown"
        days_left = (date - today).days
        if days_left < 90: return "High"
        elif days_left < 180: return "Medium"
        else: return "Low"

    results["Expiry_Risk"] = results["Expiry_Date"].apply(expiry_risk)

    # Overstock
    results["Overstock"] = results["Current_Stock"] > results["Recommended_Stock"]


    # ---------------------------------------------------
    # MAIN RESULTS TABLE
    # ---------------------------------------------------
    st.write("### 📋 Results Table")
    st.dataframe(results)


    # ---------------------------------------------------
    # PIVOT 1 — Recommended Stock
    # ---------------------------------------------------
    st.write("### 📊 Recommended Stock by Hospital")

    pivot_rec = results.pivot_table(
        index="Product_Name",
        columns="Hospital_Name",
        values="Recommended_Stock",
        aggfunc="first"
    ).fillna(0)

    st.dataframe(pivot_rec.style.format("{:.0f}"))


    # ---------------------------------------------------
    # PIVOT 2 — Current Stock
    # ---------------------------------------------------
    st.write("### 📦 Current Stock by Hospital")

    pivot_curr = results.pivot_table(
        index="Product_Name",
        columns="Hospital_Name",
        values="Current_Stock",
        aggfunc="first"
    ).fillna(0)

    st.dataframe(pivot_curr.style.format("{:.0f}"))


    # ---------------------------------------------------
    # PIVOT 5 — Expiry Risk (with color)
    # ---------------------------------------------------
    st.write("### ⏳ Expiry Risk by Hospital")

    pivot_exp = results.pivot_table(
        index="Product_Name",
        columns="Hospital_Name",
        values="Expiry_Risk",
        aggfunc="first"
    ).fillna("Unknown")

    def color_risk(val):
        if val == "High":
            return "background-color: #ffcccc"
        elif val == "Medium":
            return "background-color: #ffe4b5"
        elif val == "Low":
            return "background-color: #ccffcc"
        return ""

    st.dataframe(pivot_exp.style.applymap(color_risk))
