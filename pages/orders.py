import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.db import get_inventory, get_orders, create_order, update_order, update_order_status
import pandas as pd

st.title(":material/shopping_cart: Orders")

role     = st.session_state.user_role
username = st.session_state.username


# ── Edit pending order ──────────────────────────────────────────────────────────
def edit_order_popover(order, inventory):
    """Render an Edit popover with a form to change a pending order's item/quantity."""
    options = {f"{i['serial_id']} — {i['item_name']} (${i['price']:.2f})": i for i in inventory}
    keys = list(options.keys())
    # Default the selectbox to the order's current item, if it still exists.
    default_idx = next((n for n, k in enumerate(keys) if options[k]["id"] == order["item_id"]), 0)

    with st.popover(":material/edit: Edit", use_container_width=True):
        with st.form(f"edit_{order['id']}"):
            selected_key = st.selectbox("Item", keys, index=default_idx, key=f"item_{order['id']}")
            item = options[selected_key]
            qty  = st.number_input("Quantity", min_value=1, step=1,
                                   value=int(order["order_quantity"]), key=f"qty_{order['id']}")
            st.caption(f"Distributor: **{item['distributor']}** | Unit price: **${item['price']:.2f}** | "
                       f"New total: **${item['price'] * qty:.2f}**")
            if st.form_submit_button("Save Changes", type="primary"):
                ok, msg = update_order(order["id"], {
                    "distributor": item["distributor"],
                    "item_id": item["id"],
                    "item_name": item["item_name"],
                    "order_quantity": qty,
                    "total_amount": float(item["price"]) * qty,
                }, username)
                st.success(msg) if ok else st.error(msg)
                if ok: st.rerun()

# ── KPIs ──────────────────────────────────────────────────────────────────────
all_orders = get_orders()
pending    = [o for o in all_orders if o["status"] == "pending"]
approved   = [o for o in all_orders if o["status"] == "approved"]
rejected   = [o for o in all_orders if o["status"] == "rejected"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Orders", len(all_orders))
c2.metric("Pending", len(pending))
c3.metric("Approved", len(approved))
c4.metric("Rejected", len(rejected))

st.divider()

tab1, tab2, tab3 = st.tabs([
    ":material/add: New Order",
    ":material/list: All Orders",
    ":material/pending: Pending Approval" if role == "admin" else ":material/pending: My Pending"
])

# ── New Order ─────────────────────────────────────────────────────────────────
with tab1:
    inventory = get_inventory()
    if not inventory:
        st.warning("No inventory items available.")
    else:
        item_options = {f"{i['serial_id']} — {i['item_name']} (${i['price']:.2f})": i for i in inventory}
        with st.form("new_order"):
            selected_key = st.selectbox("Select item to order", list(item_options.keys()))
            item = item_options[selected_key]
            qty  = st.number_input("Order Quantity", min_value=1, step=1, value=10)
            st.caption(f"Distributor: **{item['distributor']}** | Unit price: **${item['price']:.2f}** | "
                       f"Estimated total: **${item['price'] * qty:.2f}**")
            if st.form_submit_button("Submit Order for Approval", type="primary"):
                ok, msg = create_order({
                    "distributor": item["distributor"],
                    "item_id": item["id"],
                    "item_name": item["item_name"],
                    "order_quantity": qty,
                    "total_amount": float(item["price"]) * qty,
                }, username)
                st.success(msg) if ok else st.error(msg)
                if ok: st.rerun()

# ── All Orders ────────────────────────────────────────────────────────────────
with tab2:
    status_filter = st.selectbox("Filter by status", ["All", "pending", "approved", "rejected"], key="sf")
    orders = get_orders(None if status_filter == "All" else status_filter)
    if not orders:
        st.info("No orders found.")
    else:
        df = pd.DataFrame(orders)
        display = df[["id","item_name","distributor","order_quantity","total_amount",
                       "status","created_by","approved_by","order_date"]]
        st.dataframe(
            display.rename(columns={
                "id":"#","item_name":"Item","distributor":"Distributor",
                "order_quantity":"Qty","total_amount":"Total ($)","status":"Status",
                "created_by":"Created By","approved_by":"Approved By","order_date":"Date"
            }),
            use_container_width=True, hide_index=True,
            column_config={"Total ($)": st.column_config.NumberColumn(format="$%.2f")}
        )

# ── Pending Approval ──────────────────────────────────────────────────────────
with tab3:
    if role == "admin":
        if not pending:
            st.success("No orders pending approval.")
        else:
            inventory = get_inventory()
            for order in pending:
                with st.container(border=True):
                    is_auto = order["created_by"] == "system_scheduler"
                    badge = " :material/autorenew: `auto-reorder`" if is_auto else ""
                    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                    c1.markdown(f"**#{order['id']} — {order['item_name']}**{badge}  \n"
                                f"Qty: `{order['order_quantity']}` | Total: `${order['total_amount']:.2f}` | "
                                f"From: `{order['distributor']}` | By: `{order['created_by']}`")
                    if c2.button("✓ Approve", key=f"app_{order['id']}", type="primary"):
                        ok, msg = update_order_status(order["id"], "approved", username)
                        st.success(msg) if ok else st.error(msg)
                        if ok: st.rerun()
                    if c3.button("✗ Reject", key=f"rej_{order['id']}"):
                        ok, msg = update_order_status(order["id"], "rejected", username)
                        st.success(msg) if ok else st.error(msg)
                        if ok: st.rerun()
                    with c4:
                        edit_order_popover(order, inventory)
    else:
        my_pending = [o for o in pending if o["created_by"] == username]
        if not my_pending:
            st.info("You have no pending orders.")
        else:
            inventory = get_inventory()
            for order in my_pending:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**#{order['id']} — {order['item_name']}**  \n"
                                f"Qty: `{order['order_quantity']}` | Total: `${order['total_amount']:.2f}` | "
                                f"Distributor: `{order['distributor']}`  \n"
                                f":material/pending: Awaiting admin approval")
                    with c2:
                        edit_order_popover(order, inventory)