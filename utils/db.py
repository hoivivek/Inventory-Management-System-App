import streamlit as st
import psycopg2
import psycopg2.extras
from datetime import datetime, date
import hashlib

# ── Connection ──────────────────────────────────────────────────────────────

@st.cache_resource
def get_connection():
    cfg = st.secrets["postgres"]
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg.get("port", 5432),
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"]
    )
    # Set session params once, before any transaction is opened on the
    # cached connection. Changing autocommit later (inside a transaction)
    # raises "set_session cannot be used inside a transaction".
    conn.autocommit = False
    return conn

def get_cursor():
    conn = get_connection()
    # The connection is cached and shared across reruns. Roll back any
    # transaction left open (or aborted) by a previous request so we always
    # start from a clean state.
    conn.rollback()
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# ── Schema ───────────────────────────────────────────────────────────────────

def init_db():
    conn, cur = get_cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                serial_id TEXT UNIQUE NOT NULL,
                item_name TEXT NOT NULL,
                sku TEXT UNIQUE NOT NULL,
                price NUMERIC(10,2) NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                category TEXT NOT NULL,
                distributor TEXT NOT NULL,
                low_stock_threshold INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                item_id INTEGER REFERENCES inventory(id),
                item_name TEXT NOT NULL,
                price NUMERIC(10,2) NOT NULL,
                quantity_sold INTEGER NOT NULL,
                total_amount NUMERIC(10,2) NOT NULL,
                category TEXT NOT NULL,
                sale_date DATE NOT NULL DEFAULT CURRENT_DATE,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                distributor TEXT NOT NULL,
                item_id INTEGER REFERENCES inventory(id),
                item_name TEXT NOT NULL,
                order_quantity INTEGER NOT NULL,
                total_amount NUMERIC(10,2) NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_by TEXT NOT NULL,
                approved_by TEXT,
                order_date DATE NOT NULL DEFAULT CURRENT_DATE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id SERIAL PRIMARY KEY,
                action TEXT NOT NULL,
                table_name TEXT NOT NULL,
                record_id INTEGER,
                performed_by TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS auto_reorder_settings (
                id SERIAL PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                run_day TEXT NOT NULL DEFAULT 'monday',
                run_time TEXT NOT NULL DEFAULT '06:00',
                reorder_multiplier NUMERIC(4,2) NOT NULL DEFAULT 2.0,
                last_run_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS auto_reorder_log (
                id SERIAL PRIMARY KEY,
                run_at TIMESTAMP DEFAULT NOW(),
                items_checked INTEGER NOT NULL DEFAULT 0,
                orders_created INTEGER NOT NULL DEFAULT 0,
                details TEXT
            );
        """)
        conn.commit()
        _seed_data(conn, cur)
        _seed_reorder_settings(conn, cur)
    except Exception as e:
        conn.rollback()
        st.error(f"DB init error: {e}")
    finally:
        cur.close()

def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()

def _seed_data(conn, cur):
    cur.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()["c"] > 0:
        return
    # Default users
    cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s),(%s,%s,%s) ON CONFLICT DO NOTHING",
        ("admin", _hash("admin123"), "admin", "user1", _hash("user123"), "user"))
    # Sample inventory
    items = [
        ("SN-001","Wireless Mouse","WM-001",29.99,150,"Electronics","TechSupply Co",20),
        ("SN-002","USB-C Hub","UC-001",49.99,80,"Electronics","TechSupply Co",15),
        ("SN-003","Desk Lamp","DL-001",34.99,8,"Furniture","OfficeWorld",10),
        ("SN-004","Notebook A5","NB-001",4.99,200,"Stationery","PaperMart",50),
        ("SN-005","Ballpoint Pens (10pk)","BP-001",6.99,5,"Stationery","PaperMart",20),
        ("SN-006","Monitor Stand","MS-001",39.99,45,"Furniture","OfficeWorld",10),
        ("SN-007","Mechanical Keyboard","MK-001",89.99,30,"Electronics","TechSupply Co",10),
        ("SN-008","Webcam HD","WC-001",59.99,0,"Electronics","TechSupply Co",10),
        ("SN-009","Sticky Notes","SN-X01",2.99,300,"Stationery","PaperMart",50),
        ("SN-010","Cable Organizer","CO-001",12.99,60,"Accessories","GadgetHub",15),
    ]
    for i in items:
        cur.execute("""
            INSERT INTO inventory (serial_id,item_name,sku,price,quantity,category,distributor,low_stock_threshold)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", i)
    # Sample sales
    sales = [
        (1,"Wireless Mouse",29.99,12,359.88,"Electronics","2026-05-01"),
        (2,"USB-C Hub",49.99,5,249.95,"Electronics","2026-05-03"),
        (4,"Notebook A5",4.99,30,149.70,"Stationery","2026-05-05"),
        (7,"Mechanical Keyboard",89.99,8,719.92,"Electronics","2026-05-10"),
        (1,"Wireless Mouse",29.99,20,599.80,"Electronics","2026-05-15"),
        (5,"Ballpoint Pens",6.99,15,104.85,"Stationery","2026-05-18"),
        (6,"Monitor Stand",39.99,10,399.90,"Furniture","2026-05-20"),
        (10,"Cable Organizer",12.99,25,324.75,"Accessories","2026-05-22"),
        (3,"Desk Lamp",34.99,6,209.94,"Furniture","2026-06-01"),
        (7,"Mechanical Keyboard",89.99,4,359.96,"Electronics","2026-06-03"),
    ]
    for s in sales:
        cur.execute("""
            INSERT INTO sales (item_id,item_name,price,quantity_sold,total_amount,category,sale_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""", s)
    conn.commit()

def _seed_reorder_settings(conn, cur):
    cur.execute("SELECT COUNT(*) as c FROM auto_reorder_settings")
    if cur.fetchone()["c"] > 0:
        return
    cur.execute("""
        INSERT INTO auto_reorder_settings (enabled, run_day, run_time, reorder_multiplier)
        VALUES (TRUE, 'monday', '06:00', 2.0)""")
    conn.commit()

# ── Auth ─────────────────────────────────────────────────────────────────────

def authenticate(username, password):
    conn, cur = get_cursor()
    cur.execute("SELECT * FROM users WHERE username=%s AND password_hash=%s",
                (username, _hash(password)))
    row = cur.fetchone()
    cur.close()
    return dict(row) if row else None

# ── Inventory ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_inventory():
    conn, cur = get_cursor()
    cur.execute("SELECT * FROM inventory ORDER BY category, item_name")
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]

def add_inventory_item(data, performed_by):
    conn, cur = get_cursor()
    try:
        cur.execute("""
            INSERT INTO inventory (serial_id,item_name,sku,price,quantity,category,distributor,low_stock_threshold)
            VALUES (%(serial_id)s,%(item_name)s,%(sku)s,%(price)s,%(quantity)s,%(category)s,%(distributor)s,%(low_stock_threshold)s)
            RETURNING id""", data)
        new_id = cur.fetchone()["id"]
        _log(cur, "INSERT", "inventory", new_id, performed_by, f"Added {data['item_name']}")
        conn.commit()
        get_inventory.clear()
        return True, "Item added successfully."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()

def update_inventory_item(item_id, data, performed_by):
    conn, cur = get_cursor()
    try:
        cur.execute("""
            UPDATE inventory SET item_name=%(item_name)s, price=%(price)s, quantity=%(quantity)s,
            category=%(category)s, distributor=%(distributor)s, low_stock_threshold=%(low_stock_threshold)s,
            updated_at=NOW() WHERE id=%(id)s""", {**data, "id": item_id})
        _log(cur, "UPDATE", "inventory", item_id, performed_by, f"Updated {data['item_name']}")
        conn.commit()
        get_inventory.clear()
        return True, "Item updated."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()

def delete_inventory_item(item_id, performed_by):
    conn, cur = get_cursor()
    try:
        cur.execute("DELETE FROM inventory WHERE id=%s", (item_id,))
        _log(cur, "DELETE", "inventory", item_id, performed_by, f"Deleted item {item_id}")
        conn.commit()
        get_inventory.clear()
        return True, "Item deleted."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()

# ── Orders ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_orders(status=None):
    conn, cur = get_cursor()
    if status:
        cur.execute("SELECT * FROM orders WHERE status=%s ORDER BY created_at DESC", (status,))
    else:
        cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]

def create_order(data, performed_by):
    conn, cur = get_cursor()
    try:
        cur.execute("""
            INSERT INTO orders (distributor,item_id,item_name,order_quantity,total_amount,created_by)
            VALUES (%(distributor)s,%(item_id)s,%(item_name)s,%(order_quantity)s,%(total_amount)s,%(created_by)s)
            RETURNING id""", {**data, "created_by": performed_by})
        new_id = cur.fetchone()["id"]
        _log(cur, "INSERT", "orders", new_id, performed_by, f"Order for {data['item_name']}")
        conn.commit()
        get_orders.clear()
        return True, "Order created and pending admin approval."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()

def update_order(order_id, data, performed_by):
    """Edit a pending order's item/quantity/total. Only pending orders are editable."""
    conn, cur = get_cursor()
    try:
        cur.execute("""
            UPDATE orders
            SET distributor=%(distributor)s, item_id=%(item_id)s, item_name=%(item_name)s,
                order_quantity=%(order_quantity)s, total_amount=%(total_amount)s, updated_at=NOW()
            WHERE id=%(order_id)s AND status='pending'
            RETURNING id""", {**data, "order_id": order_id})
        if cur.fetchone() is None:
            conn.rollback()
            return False, "Order not found or no longer pending."
        _log(cur, "UPDATE", "orders", order_id, performed_by, f"Edited order for {data['item_name']}")
        conn.commit()
        get_orders.clear()
        return True, "Order updated."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()

def update_order_status(order_id, status, approved_by):
    conn, cur = get_cursor()
    try:
        cur.execute("""
            UPDATE orders SET status=%s, approved_by=%s, updated_at=NOW() WHERE id=%s
            RETURNING item_id, order_quantity, item_name""",
            (status, approved_by, order_id))
        row = cur.fetchone()
        if status == "approved" and row:
            cur.execute("UPDATE inventory SET quantity=quantity+%s, updated_at=NOW() WHERE id=%s",
                        (row["order_quantity"], row["item_id"]))
            get_inventory.clear()
        _log(cur, "UPDATE", "orders", order_id, approved_by, f"Status → {status}")
        conn.commit()
        get_orders.clear()
        return True, f"Order {status}."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()

def record_sale(item_id, item_name, price, quantity, category, performed_by):
    conn, cur = get_cursor()
    try:
        total = price * quantity
        cur.execute("""
            INSERT INTO sales (item_id,item_name,price,quantity_sold,total_amount,category,sale_date)
            VALUES (%s,%s,%s,%s,%s,%s,CURRENT_DATE)""",
            (item_id, item_name, price, quantity, total, category))
        cur.execute("UPDATE inventory SET quantity=quantity-%s, updated_at=NOW() WHERE id=%s",
                    (quantity, item_id))
        _log(cur, "SALE", "sales", item_id, performed_by, f"Sold {quantity}x {item_name}")
        conn.commit()
        get_inventory.clear()
        get_sales.clear()
        return True, f"Sale recorded. Total: ${total:.2f}"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()

# ── Sales ─────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_sales(days=30):
    conn, cur = get_cursor()
    cur.execute("""
        SELECT * FROM sales
        WHERE sale_date >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY sale_date DESC""", (days,))
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]

# ── Audit ─────────────────────────────────────────────────────────────────────

def _log(cur, action, table, record_id, performed_by, details=""):
    cur.execute("""
        INSERT INTO audit_log (action,table_name,record_id,performed_by,details)
        VALUES (%s,%s,%s,%s,%s)""", (action, table, record_id, performed_by, details))

@st.cache_data(ttl=30)
def get_audit_log(limit=100):
    conn, cur = get_cursor()
    cur.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]

@st.cache_data(ttl=30)
def get_users():
    conn, cur = get_cursor()
    cur.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at")
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]

# ── Auto-Reorder ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=15)
def get_reorder_settings():
    conn, cur = get_cursor()
    cur.execute("SELECT * FROM auto_reorder_settings ORDER BY id LIMIT 1")
    row = cur.fetchone()
    cur.close()
    return dict(row) if row else None

def update_reorder_settings(enabled, run_day, run_time, multiplier, performed_by):
    conn, cur = get_cursor()
    try:
        cur.execute("""
            UPDATE auto_reorder_settings
            SET enabled=%s, run_day=%s, run_time=%s, reorder_multiplier=%s, updated_at=NOW()
            WHERE id = (SELECT id FROM auto_reorder_settings ORDER BY id LIMIT 1)""",
            (enabled, run_day, run_time, multiplier))
        _log(cur, "UPDATE", "auto_reorder_settings", None, performed_by,
             f"enabled={enabled}, day={run_day}, time={run_time}, multiplier={multiplier}")
        conn.commit()
        get_reorder_settings.clear()
        return True, "Auto-reorder settings updated."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()

@st.cache_data(ttl=30)
def get_reorder_run_log(limit=20):
    conn, cur = get_cursor()
    cur.execute("SELECT * FROM auto_reorder_log ORDER BY run_at DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]

# NOTE: The actual auto-reorder execution logic now lives in the n8n workflow
# "Inventory Auto-Reorder (Weekly)", which queries this same database directly,
# inserts pending orders, writes to audit_log and auto_reorder_log, and emails
# the admin. This app only displays settings/history — it does not run the
# reorder job itself, to avoid creating duplicate orders alongside n8n.