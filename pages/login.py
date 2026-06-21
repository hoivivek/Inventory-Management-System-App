import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.db import init_db, authenticate
 
init_db()
 
st.title(":material/inventory: Inventory Manager")
st.subheader("Sign in to continue")
 
with st.form("login_form"):
    username = st.text_input("Username", placeholder="e.g. admin or user1")
    password = st.text_input("Password", type="password", placeholder="Password")
    submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")
 
if submitted:
    if not username or not password:
        st.error("Please enter both username and password.")
    else:
        user = authenticate(username, password)
        if user:
            st.session_state.authenticated = True
            st.session_state.username = user["username"]
            st.session_state.user_role = user["role"]
            st.rerun()
        else:
            st.error("Invalid username or password.")
 
with st.expander("Demo credentials"):
    st.markdown("""
| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| User | `user1` | `user123` |
""")