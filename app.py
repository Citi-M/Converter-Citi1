import streamlit as st
import pandas as pd

# ---- Page config ----
st.set_page_config(page_title="Purpose Column Check", layout="centered")

# ===== Simple authentication =====
CREDENTIALS = {"User": "1"}

def login():
    st.title("🔐 Sign in")
    with st.form("login_form"):
        u = st.text_input("Login")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Enter"):
            if u in CREDENTIALS and CREDENTIALS[u] == p:
                st.session_state["auth"] = True
            else:
                st.error("Incorrect login or password")

if "auth" not in st.session_state or not st.session_state["auth"]:
    login()
    st.stop()

# ===== File upload + exact column check =====
st.title("📑 Purpose Column Check")
st.write("Upload a CSV/XLS/XLSX file. The app will look for the exact header: **Призначення платежу**.")

uploaded = st.file_uploader("Choose a statement file", type=["csv", "xls", "xlsx"])

if uploaded:
    try:
        name = uploaded.name.lower()

        # Minimal readers. For .xls you need xlrd; for .xlsx you need openpyxl.
        if name.endswith(".csv"):
            df = pd.read_csv(uploaded, dtype=str)
        elif name.endswith(".xlsx"):
            df = pd.read_excel(uploaded, dtype=str, engine="openpyxl")
        else:  # .xls
            import xlrd  # ensure xlrd==2.0.1 is in requirements
            df = pd.read_excel(uploaded, dtype=str, engine="xlrd")

        target = "Призначення платежу"

        if target in df.columns:
            st.success(f"Found column: {target}")
            st.dataframe(df[[target]].head(20))
        else:
            st.error("Column 'Призначення платежу' not found.")
            st.write("Detected headers:", list(df.columns))

    except Exception as e:
        st.error(f"Error while processing the file: {e}")
else:
    st.info("Please upload a file with headers on the first row.")
