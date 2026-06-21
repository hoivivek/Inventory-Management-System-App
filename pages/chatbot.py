import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.db import get_inventory, get_sales, get_orders
import requests, json

st.title(":material/chat: AI Assistant")
st.caption("Ask questions about your inventory, sales, and orders in plain English.")

# ── Build context snapshot ────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def build_context():
    inventory = get_inventory()
    sales     = get_sales(30)
    orders    = get_orders()

    inv_summary = "\n".join([
        f"- {i['item_name']} (SKU: {i['sku']}): {i['quantity']} units @ ${i['price']:.2f}, "
        f"category={i['category']}, distributor={i['distributor']}, "
        f"low_stock_threshold={i['low_stock_threshold']}"
        for i in inventory
    ])

    low_stock = [i for i in inventory if i["quantity"] <= i["low_stock_threshold"]]
    low_summary = "\n".join([f"- {i['item_name']}: {i['quantity']} units left" for i in low_stock]) or "None"

    sales_summary = "\n".join([
        f"- {s['item_name']}: sold {s['quantity_sold']} units (${s['total_amount']:.2f}) on {s['sale_date']}"
        for s in sales[:20]
    ])

    pending_orders = [o for o in orders if o["status"] == "pending"]
    order_summary = "\n".join([
        f"- Order #{o['id']}: {o['item_name']}, qty={o['order_quantity']}, "
        f"status={o['status']}, by={o['created_by']}"
        for o in orders[:15]
    ]) or "None"

    return f"""You are an AI assistant for an Inventory Management System. Answer questions about:
- Current inventory stock levels, prices, categories, and distributors
- Recent sales performance (last 30 days)
- Order status and history

CURRENT INVENTORY:
{inv_summary}

LOW/OUT-OF-STOCK ITEMS:
{low_summary}

RECENT SALES (last 30 days, showing latest 20):
{sales_summary}

RECENT ORDERS (showing latest 15):
{order_summary}

Be concise, helpful, and specific. Use actual numbers from the data above.
If asked something outside inventory/sales/orders, politely redirect."""

# ── Chat ──────────────────────────────────────────────────────────────────────
st.session_state.setdefault("chat_messages", [])

# Display history
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Suggested prompts
if not st.session_state.chat_messages:
    st.markdown("**Suggested questions:**")
    suggestions = [
        "Which items are low on stock?",
        "What were our top selling items this month?",
        "Show me all electronics in inventory.",
        "Are there any pending orders?",
        "What's our total inventory value?",
    ]
    cols = st.columns(len(suggestions))
    for col, suggestion in zip(cols, suggestions):
        if col.button(suggestion, use_container_width=True):
            st.session_state.chat_messages.append({"role": "user", "content": suggestion})
            st.rerun()

def generate_response():
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return ("⚠️ No Anthropic API key configured. "
                    "Add `ANTHROPIC_API_KEY` to your `.streamlit/secrets.toml` to enable the AI assistant.")
        system_prompt = build_context()
        messages = [{"role": m["role"], "content": m["content"]}
                    for m in st.session_state.chat_messages]

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": messages
            },
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
    except requests.exceptions.RequestException as e:
        return f"❌ API error: {e}"
    except Exception as e:
        return f"❌ Unexpected error: {e}"

# Handle new chat input
if prompt := st.chat_input("Ask about inventory, sales, or orders..."):
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    st.rerun()

# Respond to any unanswered user message (from input OR a suggestion button)
if (st.session_state.chat_messages
        and st.session_state.chat_messages[-1]["role"] == "user"):
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response_text = generate_response()
        st.markdown(response_text)
    st.session_state.chat_messages.append({"role": "assistant", "content": response_text})

# Clear button
if st.session_state.chat_messages:
    if st.button(":material/delete: Clear conversation", key="clear_chat"):
        st.session_state.chat_messages = []
        st.rerun()