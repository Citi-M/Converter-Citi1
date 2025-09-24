import streamlit as st
import pandas as pd
import re

# ---- Page config ----
st.set_page_config(page_title="Purpose + Credit Filter with VD/VP/IPN", layout="centered")

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

# ===== Helpers: parsing and validation =====

# VD: 5 digits right after "ВД", optional spaces and optional "№"
RE_VD = re.compile(r"(?i)\bВД\s*№?\s*(\d{5})\b")

# VP: 8 digits right after "ВП", optional spaces and optional "№"
RE_VP = re.compile(r"(?i)\bВП\s*№?\s*(\d{8})\b")

# Any 10 consecutive digits (candidate IPN)
RE_IPN_10 = re.compile(r"\b(\d{10})\b")

def extract_vd(text: str) -> str:
    """Extract 5-digit VD after 'ВД', 'ВД№', 'ВД №'."""
    m = RE_VD.search(str(text))
    return m.group(1) if m else ""

def extract_vp(text: str) -> str:
    """Extract 8-digit VP after 'ВП', 'ВП№', 'ВП №'."""
    m = RE_VP.search(str(text))
    return m.group(1) if m else ""

def ipn_control_digit_first9(digits9: list[int]) -> int:
    """
    Compute control digit for Ukrainian RNOKPP (IPN) using weights:
    [-1, 5, 7, 9, 4, 6, 10, 5, 7], then ((sum % 11) % 10).
    """
    weights = [-1, 5, 7, 9, 4, 6, 10, 5, 7]
    s = sum(d * w for d, w in zip(digits9, weights))
    return (s % 11) % 10

def is_valid_ipn(s: str) -> bool:
    """Validate 10-digit Ukrainian IPN by control digit."""
    if not (s and s.isdigit() and len(s) == 10):
        return False
    digits = [int(ch) for ch in s]
    ctrl = ipn_control_digit_first9(digits[:9])
    return digits[9] == ctrl

def extract_ipn(text: str) -> str:
    """
    Find the first 10-digit sequence in text that passes IPN control check.
    Returns empty string if none found.
    """
    for m in RE_IPN_10.finditer(str(text)):
        candidate = m.group(1)
        if is_valid_ipn(candidate):
            return candidate
    return ""

def parse_amount_to_numeric(series: pd.Series) -> pd.Series:
    """
    Convert amount text to float-like numeric:
    - remove NBSP and spaces (thousand sep),
    - replace comma with dot,
    - drop non-numeric leftovers,
    - coerce to numeric.
    """
    amt = (
        series.astype(str)
        .str.replace("\u00a0", " ", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
    )
    return pd.to_numeric(amt, errors="coerce")

# ===== UI: upload + checks + filter + extract =====
st.title("📑 Bank Statement – Filter & Extract (VD/VP/IPN)")
st.write(
    "Upload a CSV/XLS/XLSX file. The app looks for exact headers "
    "**'Призначення платежу'** and **'Зараховано'**, shows only rows where **'Зараховано' > 0**, "
    "and extracts **'ВД'** (5 digits), **'ВП'** (8 digits), and **'ІПН'** (10 digits with valid checksum) from the purpose text."
)

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

        purpose_col = "Призначення платежу"
        credit_col = "Зараховано"

        # Check required columns
        missing = [c for c in [purpose_col, credit_col] if c not in df.columns]
        if missing:
            st.error(f"Missing required column(s): {', '.join(missing)}")
            st.write("Detected headers:", list(df.columns))
            st.stop()

        # Filter rows where 'Зараховано' > 0
        amt_num = parse_amount_to_numeric(df[credit_col])
        df_pos = df.loc[amt_num > 0].copy()

        # Extract VD, VP, IPN from purpose text
        df_pos["ВД"] = df_pos[purpose_col].map(extract_vd)
        df_pos["ВП"] = df_pos[purpose_col].map(extract_vp)
        df_pos["ІПН"] = df_pos[purpose_col].map(extract_ipn)

        if df_pos.empty:
            st.warning("No rows where 'Зараховано' > 0.")
        else:
            st.success(f"Showing {len(df_pos)} row(s) where 'Зараховано' > 0.")
            st.dataframe(df_pos[[credit_col, purpose_col, "ВД", "ВП", "ІПН"]].head(1000))

    except ModuleNotFoundError:
        st.error("Excel engine is missing. For .xlsx add 'openpyxl'; for .xls add 'xlrd==2.0.1' to requirements.txt.")
    except Exception as e:
        st.error(f"Error while processing the file: {e}")
else:
    st.info("Please upload a file with headers on the first row.")
