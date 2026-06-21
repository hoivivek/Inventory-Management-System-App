# Inventory Management System App

** A full-featured Streamlit inventory management system with role-based auth, order workflows, sales analytics, and an AI chatbot — backed by Supabase (PostgreSQL), with weekly auto-reorder and error alerting handled by n8n. **

## Features

- **Role-based login** — Admin and User roles with different permissions
- **Inventory management** — View, add, edit, delete items with low-stock alerts
- **Auto-reorder (n8n)** — weekly n8n workflow auto-creates pending orders for any item at/below its low-stock threshold and emails the admin a single combined review/approval alert
- **Error handling (n8n)** — a dedicated error-handler workflow catches failures in any automation (e.g. the auto-reorder job), logs them to the audit log, and emails the admin a diagnostic summary with a link to the failed execution
- **Order workflow** — Users create orders, admins approve/reject, stock auto-updates on approval
- **Sales recording** — Log sales directly from inventory with automatic stock deduction
- **Sales dashboard** — Revenue trends, top items, category breakdown via Plotly charts
- **AI chatbot** — Natural language Q&A on inventory, sales, and orders (via Claude API)
- **Admin panel** — User management, auto-reorder settings, and full audit log
- **Cloud database** — Supabase-hosted PostgreSQL, reachable from both the local Streamlit app and n8n cloud

## Run Locally

```bash
# 1. Clone / download the project
cd inventory_app

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your database on Supabase
#    - Create a project at supabase.com
#    - Grab your pooler connection details from Project Settings → Database
#    - Tables and seed data are created automatically on first app launch (init_db())

# 5. Configure secrets
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit secrets.toml with your Supabase connection details (see below)

# 6. Run the app
streamlit run app.py
```

### Supabase connection details

```toml
[postgres]
host     = "aws-0-us-east-1.pooler.supabase.com"   # your project's pooler host
port     = 6543
dbname   = "postgres"
user     = "postgres.xxxxxxxxxxxx"                  # your pooled user
password = "your-db-password"
```

Use the **Connection pooling** host/port from Supabase (Project Settings → Database), not the direct connection — it's more reliable for external tools and matches what the n8n workflows use.

## Default Credentials

| Role  | Username | Password  |
|-------|----------|-----------|
| Admin | `admin`  | `admin123`|
| User  | `user1`  | `user123` |

Change these immediately in the Admin panel after first login.

## Project Structure

```
inventory_app/
├── app.py                        # Entry point + navigation
├── pages/
│   ├── login.py                  # Auth page
│   ├── inventory.py              # Stock management
│   ├── orders.py                 # Order workflow
│   ├── dashboard.py              # Sales analytics
│   ├── chatbot.py                # AI assistant
│   └── admin.py                  # User mgmt + auto-reorder status + audit log
├── utils/
│   └── db.py                     # All DB functions
├── .streamlit/
│   └── secrets.toml.example      # Credentials template
├── requirements.txt
└── README.md
```

## Inventory Page

<img width="959" height="446" alt="Screenshot 2026-06-18 190959" src="https://github.com/user-attachments/assets/f0e4035f-e851-4b04-bca3-a5045700f106" />

## Orders Page

<img width="955" height="443" alt="Screenshot 2026-06-18 191040" src="https://github.com/user-attachments/assets/1816df9c-716b-46fa-9cdb-4ecbdc0f7c3d" />

## Dashboard

<img width="954" height="442" alt="Screenshot 2026-06-18 191118" src="https://github.com/user-attachments/assets/bf652fd0-1c22-4829-9b05-235cfb56e851" />

## AI Chatbot Setup (Optional)

Add your Anthropic API key to `.streamlit/secrets.toml`:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```
<img width="955" height="445" alt="Screenshot 2026-06-18 191204" src="https://github.com/user-attachments/assets/3153f6be-de8d-48ad-9e25-52f8f2142b00" />

The chatbot automatically receives a snapshot of your current inventory, recent sales, and order status as context.

## Auto-Reorder (n8n Workflow)

Auto-reorder runs as an **n8n workflow** called **"Inventory Auto-Reorder (Weekly)"**, not inside this app. It connects directly to the same Supabase database.

**Steps:**
1. **Schedule Trigger** — runs weekly (default Monday 06:00 UTC)
2. **Find Low Stock Items** — queries Postgres for items at/below `low_stock_threshold` that don't already have a pending order (prevents duplicate reorders)
3. **Calculate Reorder Amounts** — reorder quantity = `low_stock_threshold × 2` (multiplier configurable in the workflow)
4. **Create Pending Order** — inserts a `pending` row into `orders` for each low-stock item, tagged `created_by = 'n8n_auto_reorder'`
5. **Log Audit Entry** — records each auto-created order in `audit_log`
6. **Fetch Orders Created This Run** — re-aggregates everything created in the last 5 minutes into one batch
7. **Were Orders Created?** — guard node: if nothing was low on stock, the workflow ends quietly — no email, no error
8. **Build Alert Email** — composes **one** HTML summary table listing every order created this run (`executeOnce: true` — fixed after testing surfaced a bug where this fired once per item instead of once per run)
9. **Send Admin Alert Email** — emails the admin via Gmail OAuth with the summary and a reminder to review, edit, and approve/reject in this app

<img width="928" height="380" alt="Screenshot 2026-06-21 113827" src="https://github.com/user-attachments/assets/8a58cb20-331b-438b-976d-a07ee930683a" />


No stock changes happen automatically — admin approval is still required in **Orders → Pending Approval**, exactly like manually-submitted orders.

**Verified by test execution:** ran against live Supabase data, correctly found low-stock items (Webcam HD, Desk Lamp, Ballpoint Pens), created 3 pending orders with correct quantities/totals, logged to audit_log, and sent exactly one summary email — confirmed after fixing the duplicate-email bug.

To adjust the schedule, reorder multiplier, or recipient email, edit the workflow directly in n8n. The **Admin → Auto-Reorder** tab in this app shows status and run history for reference (populated by the workflow's writes to `auto_reorder_log`).

## Error Handling (n8n Workflow)

A second workflow, **"Inventory Workflow Error Handler"**, acts as a central safety net for all automation in this project.

**How it's wired:** other workflows (currently: Inventory Auto-Reorder) point to it via their own **Settings → Error Workflow** setting in n8n. n8n automatically triggers this workflow any time the attached workflow fails — no polling, no separate schedule.

**Steps:**
1. **Error Trigger** — fires on failure of any attached workflow, receiving the error context (failed node, message, stack trace, execution URL)
2. **Format Error Details** — extracts a clean, readable summary
3. Two parallel branches:
   - **Log Error to Audit Log** — writes a `WORKFLOW_ERROR` row to the same `audit_log` table the app already displays
   - **Build Error Email → Send Error Alert Email** — emails the admin an HTML summary with the failed node, error message, timestamp, a direct link to the n8n execution log, and a collapsible stack trace

<img width="930" height="406" alt="Screenshot 2026-06-21 113918" src="https://github.com/user-attachments/assets/96cf4f85-1ae3-4552-b1af-51a5afbc988f" />

Reuse this same workflow as the Error Workflow for any future automation added to the project — no need to duplicate the logic.

## Database (Supabase)

The app originally targeted local PostgreSQL but was migrated to **Supabase** (cloud-hosted Postgres) because n8n cloud cannot reach a `localhost`/`127.0.0.1` database — both the app and the n8n workflows now point at the same Supabase instance.

- Tables (`users`, `inventory`, `sales`, `orders`, `audit_log`, `auto_reorder_settings`, `auto_reorder_log`) and seed data (default users + sample inventory) are created automatically by `init_db()` on first app launch — no manual SQL needed
- Use the **Connection pooling** host/port (not the direct connection) in both `.streamlit/secrets.toml` and the n8n Postgres credential
- Set **SSL: Require** on the n8n Postgres credential — Supabase requires SSL on external connections

## Workflow

1. **User** logs in → checks inventory → creates an order for low-stock items
2. **Admin** reviews pending orders → approves or rejects
3. On **approval**, inventory quantity auto-updates
4. **Sales** are recorded from the Inventory page, deducting stock
5. **Dashboard** shows live sales trends and stock levels
6. **Chatbot** answers questions in natural language
7. **n8n** runs weekly in the background, auto-creating reorder requests for low-stock items and emailing the admin to review — same approval flow as step 2
8. If that automation ever fails, **n8n's error handler** catches it and alerts the admin separately, so failures don't go unnoticed

## Changelog

- **Auto-reorder workflow added** — n8n workflow finds low-stock items weekly, creates pending orders, emails admin
- **Migrated database from local PostgreSQL to Supabase** — required because n8n cloud can't reach `localhost`
- **Error-handling workflow added** — catches failures in any attached n8n workflow, logs to audit_log, emails admin with diagnostics
- **Fixed duplicate-email bug** — auto-reorder workflow was sending one alert email per low-stock item instead of one per run; fixed by setting `executeOnce: true` on the email-building node and verified via test execution (3 emails → 1 email, same correct data)


---

Built with [Streamlit](https://streamlit.io) · [Supabase](https://supabase.com) · [n8n](https://n8n.io) · [Claude API](https://anthropic.com)
