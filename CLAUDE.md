# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Install dependencies (Python 3.11 virtual environment already present)
pip install -r requirements.txt

# Run the application
streamlit run app.py
```

Dependencies: `streamlit`, `psycopg2-binary`, `pandas`, `plotly`, `requests`.

Before running, create `.streamlit/secrets.toml` with:
```toml
[postgres]
host = "your host name"
port = 5432
dbname = "your db name"
user = "your user name"
password = "your_password"

ANTHROPIC_API_KEY = "your_api_key_here"
```

The database schema and seed data are auto-initialized on first run via `init_db()` in `utils/db.py`. Default credentials: `admin/admin123` and `user1/user123`.

## Architecture

This is a multi-page Streamlit app (Python) backed by PostgreSQL with an Anthropic AI chatbot integration and an external n8n auto-reorder workflow.

**Entry point:** `app.py` manages authentication state and role-based navigation via `st.navigation`. When not authenticated it renders only the login page; once authenticated it shows Inventory, Orders, Dashboard, and AI Assistant, plus an Admin page for `user_role == "admin"`. A sidebar shows the current user and a logout button.

**Pages (`pages/`):** Each page is an independent Streamlit script that imports from `utils.db` (adding the project root to `sys.path` first). Pages guard access via `st.session_state` and `st.stop()`.

- `login.py` — auth form, triggers `init_db()` on load
- `inventory.py` — item table with search/category/distributor filters, KPI row, low-stock alert; tabs for Add/Edit/Record-Sale (add/edit/delete are admin-only, recording sales is open to all)
- `orders.py` — purchase order workflow with KPI row and three tabs (New Order, All Orders, Pending Approval). Users create pending orders; admins approve/reject from "Pending Approval" (approval increments inventory). Both can edit a still-pending order via a popover. Orders whose `created_by == "system_scheduler"` are badged as auto-reorder.
- `dashboard.py` — Sales dashboard: Plotly charts (revenue over time, revenue by category, top items, units-by-category pie, current stock levels) plus KPIs, with a selectable 30/60/90-day window. **Not** a duplicate of orders.
- `chatbot.py` — AI assistant; builds a system prompt from a live DB snapshot (inventory, last-30-day sales, recent orders) cached 60s, calls the Anthropic Messages API (`claude-sonnet-4-6`) via HTTP POST, stores history in `st.session_state.chat_messages`. Degrades gracefully if no API key is set.
- `admin.py` — admin-only; three tabs: Users (list + create), Audit Log viewer, and Auto-Reorder (settings + run history).

**Database layer (`utils/db.py`):**
- A single connection is cached via `@st.cache_resource` and shared across all reruns
- `autocommit = False` is set **once** in `get_connection()`, before any transaction opens. Never set session params (autocommit, etc.) in `get_cursor()` or elsewhere — doing so inside an open transaction raises `set_session cannot be used inside a transaction`
- `get_cursor()` calls `conn.rollback()` first so every request starts from a clean state (clears any transaction left open or aborted by a prior rerun), and returns a `RealDictCursor`
- Read queries use `@st.cache_data(ttl=30)` (reorder settings use `ttl=15`) — always call `.clear()` on the relevant cached function after any mutation
- Every mutation (INSERT/UPDATE/DELETE/SALE) writes to the `audit_log` table with the performing username via `_log()`

**7 core tables:** `users`, `inventory`, `sales`, `orders`, `audit_log`, `auto_reorder_settings`, `auto_reorder_log`. Schema is defined in `utils/db.py:init_db()`, seeded by `_seed_data()` and `_seed_reorder_settings()`.

## Auto-Reorder / n8n Integration

The actual auto-reorder **execution** lives in an external n8n workflow ("Inventory Auto-Reorder (Weekly)"), not in this app. On a schedule it queries this same Postgres DB for low-stock items, inserts **pending** orders (reorder qty = `low_stock_threshold × reorder_multiplier`), writes to `audit_log` and `auto_reorder_log`, and emails the admin. This app only **displays** the settings and run history (`get_reorder_settings`, `update_reorder_settings`, `get_reorder_run_log`) — it does not run the reorder job itself, to avoid duplicate orders. Auto-created orders still require normal admin approval before inventory updates. (Note: `admin.py`'s help text references a `n8n_auto_reorder` tag, while `orders.py` actually detects auto orders by `created_by == "system_scheduler"`.)

## Key Patterns

**Cache invalidation:** After any write, manually clear the affected cache(s):
```python
get_inventory.clear()         # after inventory mutations
get_orders.clear()            # after order mutations
get_sales.clear()             # after recording a sale
get_reorder_settings.clear()  # after updating reorder settings
```

**RBAC guard:** Pages that are admin-only start with:
```python
if st.session_state.get("user_role") != "admin":
    st.error("Access denied. Admin only.")
    st.stop()
```

**Form returns:** DB utility functions return `(bool, str)` tuples — `(success, message)` — consumed by the calling page to display feedback. The pattern is `ok, msg = fn(...); st.success(msg) if ok else st.error(msg); if ok: st.rerun()`.

**Order workflow:** Orders are created as `pending`, then admins approve or reject. Pending orders are editable (item/quantity) via `update_order()`. Approving an order via `update_order_status()` increments stock on the linked inventory row; rejecting does not touch inventory.
