import streamlit as st

# ===== Simple authentication =====
CREDENTIALS = {
    "User": "1",
}

def login():
    st.title("🔐 Sign in")
    with st.form("login_form"):
        username = st.text_input("Login")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")
        if submitted:
            if username in CREDENTIALS and CREDENTIALS[username] == password:
                st.session_state["auth"] = True
                st.session_state["user"] = username
            else:
                st.error("Incorrect login or password")

# Stop rendering the page until the user is authenticated
if "auth" not in st.session_state or not st.session_state["auth"]:
    login()
    st.stop()

# (Placeholder) Authenticated area: add your new bank statement UI here.
# st.success(f"Welcome, {st.session_state['user']}!")
