import streamlit as st

st.set_page_config(
    page_title="Inventory Manager",
    page_icon=":material/inventory:",
    layout="wide"
)

# Initialize session state
st.session_state.setdefault("user_role", None)
st.session_state.setdefault("username", None)
st.session_state.setdefault("authenticated", False)

# Define pages
page_login      = st.Page("pages/login.py",      title="Login",       icon=":material/lock:")
page_inventory  = st.Page("pages/inventory.py",  title="Inventory",   icon=":material/inventory:")
page_orders     = st.Page("pages/orders.py",      title="Orders",      icon=":material/shopping_cart:")
page_dashboard  = st.Page("pages/dashboard.py",  title="Dashboard",   icon=":material/bar_chart:")
page_chatbot    = st.Page("pages/chatbot.py",     title="AI Assistant",icon=":material/chat:")
page_admin      = st.Page("pages/admin.py",       title="Admin",       icon=":material/admin_panel_settings:")

if not st.session_state.authenticated:
    pg = st.navigation([page_login])
else:
    pages = [page_inventory, page_orders, page_dashboard, page_chatbot]
    if st.session_state.user_role == "admin":
        pages.append(page_admin)

    with st.sidebar:
        st.markdown(f"**{st.session_state.username}** `{st.session_state.user_role}`")
        if st.button(":material/logout: Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user_role = None
            st.session_state.username = None
            st.rerun()

    pg = st.navigation(pages)

pg.run()