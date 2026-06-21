import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.db import get_sales, get_inventory
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.title(":material/bar_chart: Sales Dashboard")

period = st.selectbox("Time period", ["Last 30 days", "Last 60 days", "Last 90 days"], index=0)
days_map = {"Last 30 days": 30, "Last 60 days": 60, "Last 90 days": 90}
days = days_map[period]

sales = get_sales(days)
inventory = get_inventory()

if not sales:
    st.info("No sales data for this period.")
    st.stop()

df    = pd.DataFrame(sales)
inv   = pd.DataFrame(inventory)

df["sale_date"] = pd.to_datetime(df["sale_date"])

# ── KPIs ──────────────────────────────────────────────────────────────────────
total_revenue = df["total_amount"].sum()
total_units   = df["quantity_sold"].sum()
num_txns      = len(df)
avg_order_val = total_revenue / num_txns if num_txns else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Revenue", f"${total_revenue:,.2f}")
c2.metric("Units Sold", f"{total_units:,}")
c3.metric("Transactions", num_txns)
c4.metric("Avg Order Value", f"${avg_order_val:.2f}")

st.divider()

# ── Revenue over time ─────────────────────────────────────────────────────────
daily = df.groupby("sale_date")["total_amount"].sum().reset_index()
fig1 = px.area(daily, x="sale_date", y="total_amount",
               labels={"sale_date": "Date", "total_amount": "Revenue ($)"},
               title="Revenue Over Time")
fig1.update_layout(margin=dict(t=40, l=0, r=0, b=0), showlegend=False)
fig1.update_traces(line_color="#7F77DD", fillcolor="rgba(127,119,221,0.15)")
st.plotly_chart(fig1, use_container_width=True)

col1, col2 = st.columns(2)

# ── Revenue by Category ───────────────────────────────────────────────────────
with col1:
    cat = df.groupby("category")["total_amount"].sum().reset_index().sort_values("total_amount", ascending=False)
    fig2 = px.bar(cat, x="category", y="total_amount",
                  title="Revenue by Category",
                  labels={"category": "Category", "total_amount": "Revenue ($)"},
                  color="total_amount", color_continuous_scale="Purples")
    fig2.update_layout(margin=dict(t=40, l=0, r=0, b=0), showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig2, use_container_width=True)

# ── Top Items by Units Sold ───────────────────────────────────────────────────
with col2:
    top = df.groupby("item_name")["quantity_sold"].sum().reset_index().sort_values("quantity_sold", ascending=True).tail(8)
    fig3 = px.bar(top, x="quantity_sold", y="item_name", orientation="h",
                  title="Top Items by Units Sold",
                  labels={"quantity_sold": "Units", "item_name": "Item"})
    fig3.update_layout(margin=dict(t=40, l=0, r=0, b=0))
    fig3.update_traces(marker_color="#1D9E75")
    st.plotly_chart(fig3, use_container_width=True)

# ── Units sold pie ────────────────────────────────────────────────────────────
col3, col4 = st.columns(2)
with col3:
    cat_units = df.groupby("category")["quantity_sold"].sum().reset_index()
    fig4 = px.pie(cat_units, values="quantity_sold", names="category",
                  title="Units Sold by Category", hole=0.4)
    fig4.update_layout(margin=dict(t=40, l=0, r=0, b=0))
    st.plotly_chart(fig4, use_container_width=True)

# ── Current stock levels ──────────────────────────────────────────────────────
with col4:
    if not inv.empty:
        inv_sorted = inv.sort_values("quantity", ascending=True).tail(10)
        colors = ["#E24B4A" if q <= t else "#1D9E75"
                  for q, t in zip(inv_sorted["quantity"], inv_sorted["low_stock_threshold"])]
        fig5 = go.Figure(go.Bar(
            x=inv_sorted["quantity"], y=inv_sorted["item_name"],
            orientation="h", marker_color=colors
        ))
        fig5.update_layout(title="Stock Levels (red = low stock)",
                           margin=dict(t=40, l=0, r=0, b=0),
                           xaxis_title="Qty", yaxis_title="")
        st.plotly_chart(fig5, use_container_width=True)

# ── Raw sales table ───────────────────────────────────────────────────────────
with st.expander("Raw sales data"):
    st.dataframe(
        df[["sale_date","item_name","category","quantity_sold","price","total_amount"]].rename(columns={
            "sale_date":"Date","item_name":"Item","category":"Category",
            "quantity_sold":"Qty","price":"Unit Price","total_amount":"Total"
        }),
        use_container_width=True, hide_index=True,
        column_config={
            "Unit Price": st.column_config.NumberColumn(format="$%.2f"),
            "Total": st.column_config.NumberColumn(format="$%.2f"),
        }
    )