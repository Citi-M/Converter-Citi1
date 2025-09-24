import streamlit as st
import pandas as pd
import re
from io import BytesIO

# ---- Page config ----
st.set_page_config(page_title="Statement Filter & Extract (VD/VP/IPN/Name)", layout="centered")

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

# ===== Helpers: parsing/validation (all messages & comments in English) =====

# VD: 5 digits right after "ВД", optional spaces and optional "№"
RE_VD = re.compile(r"(?i)\bВД\s*№?\s*(\d{5})\b")

# VP: 8 digits right after "ВП", optional spaces and optional "№"
RE_VP = re.compile(r"(?i)\bВП\s*№?\s*(\d{8})\b")

# IPN: any 10 consecutive digits
RE_IPN_10 = re.compile(r"\b(\d{10})\b")

# Name after explicit marker "Боржник:"
NAME_AFTER_BORZHNIK = re.compile(
    r"(?i)боржник\s*:\s*([А-ЯA-ZІЇЄҐ][А-Яа-яA-Za-zІЇЄҐіїєґ'`-]+(?:\s+[А-ЯA-ZІЇЄҐ][А-Яа-яA-Za-zІЇЄҐіїєґ'`-]+){1,2})"
)

def extract_vd(text: str) -> str:
    m = RE_VD.search(str(text))
    return m.group(1) if m else ""

def extract_vp(text: str) -> str:
    m = RE_VP.search(str(text))
    return m.group(1) if m else ""

def ipn_control_digit_first9(digits9: list[int]) -> int:
    """Compute control digit for Ukrainian IPN using weights [-1,5,7,9,4,6,10,5,7] and ((sum % 11) % 10)."""
    weights = [-1, 5, 7, 9, 4, 6, 10, 5, 7]
    s = sum(d * w for d, w in zip(digits9, weights))
    return (s % 11) % 10

def is_valid_ipn(s: str) -> bool:
    """Validate 10-digit IPN by checksum."""
    if not (s and s.isdigit() and len(s) == 10):
        return False
    digits = [int(ch) for ch in s]
    return digits[9] == ipn_control_digit_first9(digits[:9])

def extract_ipn(text: str) -> str:
    """Return the first 10-digit sequence that passes IPN validation; otherwise empty string."""
    for m in RE_IPN_10.finditer(str(text)):
        cand = m.group(1)
        if is_valid_ipn(cand):
            return cand
    return ""

def extract_name(text: str) -> str:
    """Extract name after 'Боржник:' and strip trailing digits."""
    s = str(text)
    m = NAME_AFTER_BORZHNIK.search(s)
    if not m:
        return ""
    name = re.sub(r"\s*\d+\s*$", "", m.group(1)).strip()
    return name

def parse_amount_to_numeric(series: pd.Series) -> pd.Series:
    """Normalize amount text to numeric: remove NBSP/spaces, ',' -> '.', drop non-numeric."""
    amt = (
        series.astype(str)
        .str.replace("\u00a0", " ", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
    )
    return pd.to_numeric(amt, errors="coerce")

def normalize_date(series: pd.Series) -> pd.Series:
    """Parse dates with dayfirst=True and return ISO date strings."""
    dt = pd.to_datetime(series, dayfirst=True, errors="coerce")
    return dt.dt.date.astype(str)

# ===== UI: upload + checks + filter + extract =====
st.title("📑 Bank Statement – Filter & Extract")
st.write(
    "Upload a CSV/XLS/XLSX file. Required headers: **'Дата'**, **'Зараховано'**, **'Призначення платежу'**. "
    "The app keeps only rows where **'Зараховано' > 0**, and extracts **'ВД'** (5 digits), **'ВП'** (8 digits), "
    "**'ІПН'** (valid 10 digits), and **'ПІБ'** (after 'Боржник:')."
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
            import xlrd  # ensure xlrd==2.0.1 in requirements
            df = pd.read_excel(uploaded, dtype=str, engine="xlrd", header=0)

        # Required columns (exact names)
        date_col = "Дата"
        credit_col = "Зараховано"
        purpose_col = "Призначення платежу"

        missing = [c for c in [date_col, credit_col, purpose_col] if c not in df.columns]
        if missing:
            st.error(f"Missing required column(s): {', '.join(missing)}")
            st.write("Detected headers:", list(df.columns))
            st.stop()

        # Filter rows where 'Зараховано' > 0
        amt_num = parse_amount_to_numeric(df[credit_col])
        df_pos = df.loc[amt_num > 0].copy()

        # Extract fields
        df_pos["ВД"] = df_pos[purpose_col].map(extract_vd)
        df_pos["ВП"] = df_pos[purpose_col].map(extract_vp)
        df_pos["ІПН"] = df_pos[purpose_col].map(extract_ipn)
        df_pos["ПІБ"] = df_pos[purpose_col].map(extract_name)
        df_pos["Дата"] = normalize_date(df_pos[date_col])

        # Result view
        result_cols = ["Дата", "ВД", "ВП", "ІПН", "ПІБ", purpose_col, credit_col]
        result = df_pos[result_cols].copy()

        if result.empty:
            st.warning("No rows where 'Зараховано' > 0.")
        else:
            st.success(f"Showing {len(result)} row(s) where 'Зараховано' > 0.")
            st.dataframe(result.head(1000), use_container_width=True)

            # Download buttons
            csv_bytes = result.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Download CSV", data=csv_bytes,
                               file_name="parsed_statement.csv", mime="text/csv")

            xls_buffer = BytesIO()
            result.to_excel(xls_buffer, index=False, engine="openpyxl")
            st.download_button("⬇️ Download Excel", data=xls_buffer.getvalue(),
                               file_name="parsed_statement.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except ModuleNotFoundError:
        st.error("Excel engine is missing. For .xlsx add 'openpyxl'; for .xls add 'xlrd==2.0.1' to requirements.txt.")
    except Exception as e:
        st.error(f"Error while processing the file: {e}")
else:
    st.info("Please upload a file with headers on the first row.")
