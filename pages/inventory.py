import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.db import (get_inventory, add_inventory_item, update_inventory_item,
                      delete_inventory_item, record_sale)
import pandas as pd

st.title(":material/inventory: Inventory")

inventory = get_inventory()
df = pd.DataFrame(inventory)

# ── KPI row ──────────────────────────────────────────────────────────────────
total_items   = len(df)
total_stock   = int(df["quantity"].sum()) if not df.empty else 0
low_stock     = df[df["quantity"] <= df["low_stock_threshold"]] if not df.empty else pd.DataFrame()
out_of_stock  = df[df["quantity"] == 0] if not df.empty else pd.DataFrame()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total SKUs", total_items)
c2.metric("Total Units", f"{total_stock:,}")
c3.metric("Low Stock", len(low_stock), delta=f"-{len(low_stock)}", delta_color="inverse")
c4.metric("Out of Stock", len(out_of_stock), delta=f"-{len(out_of_stock)}", delta_color="inverse")

if not low_stock.empty:
    with st.expander(f":material/warning: {len(low_stock)} item(s) at or below reorder threshold", expanded=True):
        st.dataframe(
            low_stock[["serial_id","item_name","quantity","low_stock_threshold","distributor"]],
            use_container_width=True, hide_index=True
        )

st.divider()

# ── Filters ───────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([3, 2, 2])
search   = col1.text_input(":material/search: Search", placeholder="Item name, SKU, serial...")
cats     = ["All"] + sorted(df["category"].unique().tolist()) if not df.empty else ["All"]
category = col2.selectbox("Category", cats)
dists    = ["All"] + sorted(df["distributor"].unique().tolist()) if not df.empty else ["All"]
dist     = col3.selectbox("Distributor", dists)

filtered = df.copy()
if search:
    mask = (filtered["item_name"].str.contains(search, case=False, na=False) |
            filtered["sku"].str.contains(search, case=False, na=False) |
            filtered["serial_id"].str.contains(search, case=False, na=False))
    filtered = filtered[mask]
if category != "All":
    filtered = filtered[filtered["category"] == category]
if dist != "All":
    filtered = filtered[filtered["distributor"] == dist]

# ── Table ─────────────────────────────────────────────────────────────────────
display_cols = ["serial_id","item_name","sku","price","quantity","category","distributor","low_stock_threshold"]
st.dataframe(
    filtered[display_cols].rename(columns={
        "serial_id":"Serial ID","item_name":"Item","sku":"SKU","price":"Price ($)",
        "quantity":"Qty","category":"Category","distributor":"Distributor",
        "low_stock_threshold":"Reorder At"
    }),
    use_container_width=True, hide_index=True,
    column_config={
        "Price ($)": st.column_config.NumberColumn(format="$%.2f"),
        "Qty": st.column_config.NumberColumn(),
    }
)

st.divider()

# ── Actions ───────────────────────────────────────────────────────────────────
role = st.session_state.user_role
tab_labels = [":material/add: Add Item", ":material/edit: Edit Item",
              ":material/point_of_sale: Record Sale"]
if role == "admin":
    tab_labels.append(":material/delete: Delete Item")

tabs = st.tabs(tab_labels)

# Add
with tabs[0]:
    if role != "admin":
        st.info("Only admins can add inventory items.")
    else:
        with st.form("add_item"):
            c1, c2 = st.columns(2)
            serial_id   = c1.text_input("Serial ID*")
            item_name   = c2.text_input("Item Name*")
            sku         = c1.text_input("SKU*")
            price       = c2.number_input("Price ($)*", min_value=0.01, step=0.01)
            quantity    = c1.number_input("Initial Qty*", min_value=0, step=1)
            category    = c2.text_input("Category*")
            distributor = c1.text_input("Distributor*")
            threshold   = c2.number_input("Low Stock Threshold", min_value=0, value=10, step=1)
            if st.form_submit_button("Add Item", type="primary"):
                if not all([serial_id, item_name, sku, category, distributor]):
                    st.error("Please fill all required fields.")
                else:
                    ok, msg = add_inventory_item({
                        "serial_id": serial_id, "item_name": item_name, "sku": sku,
                        "price": price, "quantity": quantity, "category": category,
                        "distributor": distributor, "low_stock_threshold": threshold
                    }, st.session_state.username)
                    st.success(msg) if ok else st.error(msg)
                    if ok: st.rerun()

# Edit
with tabs[1]:
    if role != "admin":
        st.info("Only admins can edit inventory items.")
    elif inventory:
        item_options = {f"{i['serial_id']} — {i['item_name']}": i for i in inventory}
        selected_key = st.selectbox("Select item to edit", list(item_options.keys()))
        item = item_options[selected_key]
        with st.form("edit_item"):
            c1, c2 = st.columns(2)
            item_name   = c1.text_input("Item Name", value=item["item_name"])
            price       = c2.number_input("Price ($)", value=float(item["price"]), min_value=0.01, step=0.01)
            quantity    = c1.number_input("Quantity", value=item["quantity"], min_value=0, step=1)
            category    = c2.text_input("Category", value=item["category"])
            distributor = c1.text_input("Distributor", value=item["distributor"])
            threshold   = c2.number_input("Low Stock Threshold", value=item["low_stock_threshold"], min_value=0)
            if st.form_submit_button("Save Changes", type="primary"):
                ok, msg = update_inventory_item(item["id"], {
                    "item_name": item_name, "price": price, "quantity": quantity,
                    "category": category, "distributor": distributor,
                    "low_stock_threshold": threshold
                }, st.session_state.username)
                st.success(msg) if ok else st.error(msg)
                if ok: st.rerun()

# Record Sale
with tabs[2]:
    if inventory:
        item_options = {f"{i['serial_id']} — {i['item_name']} (Qty: {i['quantity']})": i for i in inventory}
        selected_key = st.selectbox("Select item sold", list(item_options.keys()))
        item = item_options[selected_key]
        with st.form("record_sale"):
            qty = st.number_input("Quantity Sold", min_value=1, max_value=max(item["quantity"], 1), step=1)
            st.caption(f"Unit price: **${item['price']:.2f}** | Total: **${item['price'] * qty:.2f}**")
            if st.form_submit_button("Record Sale", type="primary"):
                if qty > item["quantity"]:
                    st.error("Not enough stock.")
                else:
                    ok, msg = record_sale(item["id"], item["item_name"], float(item["price"]),
                                         qty, item["category"], st.session_state.username)
                    st.success(msg) if ok else st.error(msg)
                    if ok: st.rerun()

# Delete (admin only)
if role == "admin" and len(tabs) > 3:
    with tabs[3]:
        if inventory:
            item_options = {f"{i['serial_id']} — {i['item_name']}": i for i in inventory}
            selected_key = st.selectbox("Select item to delete", list(item_options.keys()), key="del_select")
            item = item_options[selected_key]
            st.warning(f"This will permanently delete **{item['item_name']}**.")
            if st.button("Delete Item", type="primary"):
                ok, msg = delete_inventory_item(item["id"], st.session_state.username)
                st.success(msg) if ok else st.error(msg)
                if ok: st.rerun()