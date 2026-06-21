import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.db import (get_users, get_audit_log, get_reorder_settings,
                      update_reorder_settings, get_reorder_run_log)
import psycopg2, hashlib
import pandas as pd

# Guard: admin only
if st.session_state.get("user_role") != "admin":
    st.error("Access denied. Admin only.")
    st.stop()

st.title(":material/admin_panel_settings: Admin Panel")

tab1, tab2, tab3 = st.tabs([
    ":material/people: Users",
    ":material/history: Audit Log",
    ":material/autorenew: Auto-Reorder"
])

# ── Users ─────────────────────────────────────────────────────────────────────
with tab1:
    users = get_users()
    df = pd.DataFrame(users)
    if not df.empty:
        st.dataframe(
            df[["id","username","role","created_at"]].rename(columns={
                "id":"#","username":"Username","role":"Role","created_at":"Created"
            }),
            use_container_width=True, hide_index=True
        )

    st.subheader("Add User")
    with st.form("add_user"):
        c1, c2, c3 = st.columns(3)
        new_username = c1.text_input("Username")
        new_password = c2.text_input("Password", type="password")
        new_role     = c3.selectbox("Role", ["user", "admin"])
        if st.form_submit_button("Create User", type="primary"):
            if not new_username or not new_password:
                st.error("Username and password required.")
            else:
                try:
                    from utils.db import get_cursor
                    conn, cur = get_cursor()
                    pw_hash = hashlib.sha256(new_password.encode()).hexdigest()
                    cur.execute(
                        "INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
                        (new_username, pw_hash, new_role)
                    )
                    conn.commit()
                    cur.close()
                    get_users.clear()
                    st.success(f"User `{new_username}` created.")
                    st.rerun()
                except psycopg2.errors.UniqueViolation:
                    st.error("Username already exists.")
                except Exception as e:
                    st.error(str(e))

# ── Audit Log ─────────────────────────────────────────────────────────────────
with tab2:
    logs = get_audit_log(200)
    if not logs:
        st.info("No audit events yet.")
    else:
        df_log = pd.DataFrame(logs)
        st.dataframe(
            df_log[["created_at","action","table_name","record_id","performed_by","details"]].rename(columns={
                "created_at":"Timestamp","action":"Action","table_name":"Table",
                "record_id":"Record","performed_by":"User","details":"Details"
            }),
            use_container_width=True, hide_index=True,
            column_config={"Timestamp": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")}
        )

# ── Auto-Reorder ──────────────────────────────────────────────────────────────
with tab3:
    settings = get_reorder_settings()

    st.subheader("Weekly Auto-Reorder")
    st.caption(
        "Powered by an **n8n workflow** that runs on a schedule, checks every "
        "inventory item against its low-stock threshold, and automatically "
        "creates a **pending** order for any item at or below it. The admin "
        "is emailed a combined alert listing every order created, with links "
        "back to this app to review, edit, and approve or reject each one. "
        "No stock changes happen until you approve."
    )

    if settings:
        c1, c2, c3 = st.columns(3)
        c1.metric("Status", "✅ Enabled" if settings["enabled"] else "⏸️ Disabled")
        c2.metric("Scheduled", f"{settings['run_day'].capitalize()} @ {settings['run_time']}")
        last_run = settings["last_run_at"].strftime("%Y-%m-%d %H:%M") if settings["last_run_at"] else "Never"
        c3.metric("Last Run", last_run)

    st.divider()

    with st.form("reorder_settings"):
        st.markdown("**Reorder Settings**")
        st.caption("These values are stored here for reference. Update the schedule and multiplier "
                   "directly in the n8n workflow editor to change actual behavior.")
        c1, c2, c3, c4 = st.columns(4)
        enabled = c1.toggle("Enabled", value=settings["enabled"] if settings else True)
        run_day = c2.selectbox(
            "Day of week",
            ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
            index=["monday","tuesday","wednesday","thursday","friday","saturday","sunday"].index(
                settings["run_day"]) if settings else 0
        )
        run_time = c3.text_input("Time (24h, HH:MM)", value=settings["run_time"] if settings else "06:00")
        multiplier = c4.number_input(
            "Reorder multiplier", min_value=1.0, max_value=10.0, step=0.5,
            value=float(settings["reorder_multiplier"]) if settings else 2.0,
            help="Reorder quantity = low_stock_threshold × multiplier"
        )
        if st.form_submit_button("Save Settings", type="primary"):
            ok, msg = update_reorder_settings(enabled, run_day, run_time, multiplier,
                                              st.session_state.username)
            st.success(msg) if ok else st.error(msg)
            if ok: st.rerun()

    st.divider()
    st.markdown("**Run History**")
    st.caption("Populated by the n8n workflow each time it runs.")
    run_log = get_reorder_run_log(20)
    if not run_log:
        st.info("No auto-reorder runs yet. The n8n workflow will log here after its first scheduled run.")
    else:
        df_runs = pd.DataFrame(run_log)
        st.dataframe(
            df_runs[["run_at","items_checked","orders_created","details"]].rename(columns={
                "run_at":"Run Time","items_checked":"Items Checked",
                "orders_created":"Orders Created","details":"Details"
            }),
            use_container_width=True, hide_index=True,
            column_config={"Run Time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")}
        )

    with st.expander(":material/account_tree: How the n8n workflow works"):
        st.markdown("""
**Workflow: "Inventory Auto-Reorder (Weekly)"**

1. **Schedule Trigger** — fires weekly (default: Monday 06:00)
2. **Find Low Stock Items** — queries Postgres directly for items where
   `quantity <= low_stock_threshold` that don't already have a pending order
3. **Calculate Reorder Amounts** — quantity = threshold × multiplier (default 2x)
4. **Create Pending Order** — inserts a row into `orders` with `status = 'pending'`
5. **Log Audit Entry** — writes to `audit_log` for traceability
6. **Fetch Orders Created This Run** — aggregates everything created in this run
7. **Build Alert Email** — composes one HTML summary table of all new orders
8. **Send Admin Alert Email** — emails the admin via Gmail with the summary
   and a reminder to review, edit, and approve in this app

If no items are low on stock, the workflow simply does nothing that run —
no email is sent, no orders are created.

Orders created this way appear in **Orders → Pending Approval** tagged as
`n8n_auto_reorder`, exactly like manually-submitted orders, and require the
same admin approval before inventory quantities update.
""")