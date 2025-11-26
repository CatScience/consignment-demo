import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# ------------------------------------------------------------
# PAGE CONFIG
# ------------------------------------------------------------
st.set_page_config(
    page_title="Diagnostic Kits Consignment Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
        .metric-card {
            padding: 20px;
            border-radius: 10px;
            background-color: white;
            border: 1px solid #e6e6e6;
            text-align: center;
        }
        .metric-number {
            font-size: 32px;
            font-weight: 700;
            margin-bottom: -5px;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ------------------------------------------------------------
# LOAD SAMPLE DATASET
# ------------------------------------------------------------
@st.cache_data
def load_demo_data():
    return pd.read_csv("diagnostic_kits_consignment_demo.csv")

# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------
st.sidebar.header("Data Input")

use_demo = st.sidebar.button("Use Demo Dataset")
uploaded_file = st.sidebar.file_uploader("Upload your CSV dataset", type=["csv"])

if use_demo:
    df = load_demo_data()
    st.sidebar.success("Demo dataset loaded.")
elif uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    st.sidebar.success("Your dataset is loaded.")
else:
    st.sidebar.info("Upload a CSV file or click 'Use Demo Dataset'")
    st.stop()

# ------------------------------------------------------------
# VALIDATION
# ------------------------------------------------------------
required_cols = [
    "Record_Type", "Hospital_ID", "Hospital_Name", "Product_ID", "Product_Name",
    "Product_Category", "Usage_Family", "Movement_Date", "Movement_Qty",
    "Current_Stock", "Expiry_Date", "Consignment_Start_Date"
]

missing = [c for c in required_cols if c not in df.columns]

if missing:
    st.error(f"Dataset missing required columns: {missing}")
    st.stop()

# Convert date columns
date_cols = ["Movement_Date", "Expiry_Date", "Consignment_Start_Date"]
for c in date_cols:
    df[c] = pd.to_datetime(df[c], errors="coerce")

# Filter movements and inventory
mov = df[df["Record_Type"] == "movement"].copy()
inv = df[df["Record_Type"] == "inventory"].copy()

# ------------------------------------------------------------
# KPI CALCULATIONS
# ------------------------------------------------------------
six_months_ago = pd.Timestamp.today() - pd.DateOffset(months=6)
last6 = mov[mov["Movement_Date"] >= six_months_ago]

# Weekly usage
weekly_usage = len(last6) / 26

# Current inventory
current_inventory = inv["Current_Stock"].fillna(0).sum()

# Recommended stock (simple logic)
def recommended_stock(row):
    if row["Usage_Family"] == "high":
        return len(last6[last6["Product_ID"] == row["Product_ID"]]) * 1.5
    elif row["Usage_Family"] == "medium":
        return len(last6[last6["Product_ID"] == row["Product_ID"]])
    else:
        return 1

inv["Recommended"] = inv.apply(recommended_stock, axis=1)
recommended_total = inv["Recommended"].sum()

# Reduction / Increase
reduction = (inv["Current_Stock"] - inv["Recommended"]).clip(lower=0).sum()
increase = (inv["Recommended"] - inv["Current_Stock"]).clip(lower=0).sum()

optimized_inventory = recommended_total

# ------------------------------------------------------------
# PAGE HEADER
# ------------------------------------------------------------
st.title("🔬 Diagnostic Kits Consignment Dashboard")
st.write("Upload your dataset or use the demo data to explore consignment stock intelligence.")

# ------------------------------------------------------------
# KPI ROW
# ------------------------------------------------------------
kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)

with kpi1:
    st.markdown("<div class='metric-card'><div class='metric-number'>"
                f"{weekly_usage:.2f}</div>Avg Weekly<br>Consumption</div>", unsafe_allow_html=True)

with kpi2:
    st.markdown("<div class='metric-card'><div class='metric-number'>"
                f"{current_inventory:.0f}</div>Current<br>Inventory</div>", unsafe_allow_html=True)

with kpi3:
    st.markdown("<div class='metric-card'><div class='metric-number'>"
                f"{recommended_total:.0f}</div>Recommended<br>Inventory</div>", unsafe_allow_html=True)

with kpi4:
    st.markdown("<div class='metric-card'><div class='metric-number' style='color:#A020F0;'>"
                f"{reduction:.0f}</div>Reduction<br>Potential</div>", unsafe_allow_html=True)

with kpi5:
    st.markdown("<div class='metric-card'><div class='metric-number' style='color:#3CB371;'>"
                f"{increase:.0f}</div>Increase<br>Needed</div>", unsafe_allow_html=True)

with kpi6:
    st.markdown("<div class='metric-card'><div class='metric-number'>"
                f"{optimized_inventory:.0f}</div>Optimized<br>Inventory</div>", unsafe_allow_html=True)

# ------------------------------------------------------------
# TABS
# ------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview", 
    "📦 Inventory",
    "🔥 Heatmap",
    "📈 Movements",
    "💡 Recommendations"
])

# ------------------------------------------------------------
# TAB 1 — OVERVIEW
# ------------------------------------------------------------
with tab1:
    st.subheader("Activity Classification (A/B/C/D)")

    # Calculate avg interval
    mov_sorted = mov.sort_values(["Product_ID", "Movement_Date"])
    mov_sorted["Prev"] = mov_sorted.groupby("Product_ID")["Movement_Date"].shift(1)
    mov_sorted["Interval"] = (mov_sorted["Movement_Date"] - mov_sorted["Prev"]).dt.days

    avg_intervals = mov_sorted.groupby("Product_ID")["Interval"].mean().reset_index()
    avg_intervals["Class"] = pd.cut(
        avg_intervals["Interval"],
        bins=[-1, 10, 20, 40, 9999],
        labels=["A", "B", "C", "D"]
    )

    class_counts = avg_intervals["Class"].value_counts()

    fig = px.pie(
        values=class_counts.values,
        names=class_counts.index,
        title="Activity Class Distribution"
    )
    st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------
# TAB 2 — INVENTORY
# ------------------------------------------------------------
with tab2:
    st.subheader("Current Inventory")
    st.dataframe(inv[["Hospital_Name", "Product_Name", "Current_Stock", "Recommended"]])

    st.subheader("Optimized Inventory")
    inv["Difference"] = inv["Current_Stock"] - inv["Recommended"]
    st.dataframe(inv[["Hospital_Name", "Product_Name", "Recommended", "Difference"]])

# ------------------------------------------------------------
# TAB 3 — HEATMAP
# ------------------------------------------------------------
with tab3:
    st.subheader("Reduction / Increase Heatmap")

    heat = inv.pivot_table(
        index="Hospital_Name",
        columns="Usage_Family",
        values="Difference",
        aggfunc="mean"
    )

    fig = px.imshow(
        heat,
        color_continuous_scale="RdBu",
        title="Inventory Adjustment Heatmap"
    )
    st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------
# TAB 4 — MOVEMENTS
# ------------------------------------------------------------
with tab4:
    st.subheader("Movement Frequency")
    mov_daily = mov.groupby("Movement_Date").size()
    fig2 = px.line(mov_daily, title="Daily Movements")
    st.plotly_chart(fig2, use_container_width=True)

# ------------------------------------------------------------
# TAB 5 — RECOMMENDATIONS
# ------------------------------------------------------------
with tab5:
    st.subheader("Product-Level Recommendations")
    st.write("Items requiring increase or reduction:")

    rec = inv.copy()
    rec["Action"] = np.where(
        rec["Difference"] > 0, "Reduce",
        np.where(rec["Difference"] < 0, "Increase", "OK")
    )

    st.dataframe(rec[["Hospital_Name", "Product_Name", "Current_Stock", "Recommended", "Action"]])

    st.download_button(
        "Download Recommendations",
        rec.to_csv(index=False).encode("utf-8"),
        file_name="recommendations.csv",
        mime="text/csv"
    )
