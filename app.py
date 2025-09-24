import streamlit as st
import pandas as pd

# ---- Page config ----
st.set_page_config(page_title="Purpose Column + Positive Credit Filter", layout="centered")

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

# ===== File upload + exact column check + filter =====
st.title("📑 Purpose Column + Positive Credit Filter")
st.write("Upload a CSV/XLS/XLSX file. The app looks for the exact header **'Призначення платежу'** and shows only rows where **'Зараховано' > 0**.")

uploaded = st.file_uploader("Choose a statement file", type=["csv", "xls", "xlsx"])

if uploaded:
    try:
        name = uploaded.name.lower()

        # Minimal readers. For .xls you need xlrd; for .xlsx you need openpyxl.
        if name.endswith(".csv"):
            df = pd.read_csv(uploaded, dtype=str)
        elif name.endswith(".xlsx"):
            df = pd.read_excel(uploaded, dtype=str, engine="openpyxl", header=0)
        else:  # .xls
            import xlrd  # ensure xlrd==2.0.1 is in requirements
            df = pd.read_excel(uploaded, dtype=str, engine="xlrd", header=0)

        target_col = "Призначення платежу"
        credit_col = "Зараховано"

        # Check required columns
        missing = [c for c in [target_col, credit_col] if c not in df.columns]
        if missing:
            st.error(f"Missing required column(s): {', '.join(missing)}")
            st.write("Detected headers:", list(df.columns))
            st.stop()

        # Parse 'Зараховано' to numeric and filter > 0 (handles spaces and comma decimals)
        amt = (
            df[credit_col]
            .astype(str)
            .str.replace("\u00a0", " ", regex=False)  # non-breaking spaces
            .str.replace(" ", "", regex=False)       # thousands separators
            .str.replace(",", ".", regex=False)      # decimal comma -> dot
            .str.replace(r"[^\d\.\-]", "", regex=True)  # drop currency symbols etc.
        )
        amt_num = pd.to_numeric(amt, errors="coerce")

        df_pos = df.loc[amt_num > 0].copy()

        if df_pos.empty:
            st.warning("No rows where 'Зараховано' > 0.")
        else:
            st.success(f"Showing {len(df_pos)} row(s) where 'Зараховано' > 0.")
            # Show only the two relevant columns by default
            st.dataframe(df_pos[[credit_col, target_col]].head(200))

    except ModuleNotFoundError as e:
        st.error("Excel engine is missing. For .xlsx add 'openpyxl'; for .xls add 'xlrd==2.0.1' to requirements.txt.")
    except Exception as e:
        st.error(f"Error while processing the file: {e}")
else:
    st.info("Please upload a file with headers on the first row.")
