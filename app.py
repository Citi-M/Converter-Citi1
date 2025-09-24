import streamlit as st
import pandas as pd
import re
from io import BytesIO

# ---- Page config ----
st.set_page_config(page_title="Bank Statement Convertor", layout="centered")

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

# ===== Helpers =====

def _clean_header(s: str) -> str:
    """Normalize header: strip spaces/NBSP/BOM and collapse whitespace."""
    if s is None:
        return ""
    s = str(s).replace("\u00a0", " ").replace("\ufeff", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def pick_col(df: pd.DataFrame, candidates):
    """Pick the first existing column from candidates (after header normalization)."""
    if isinstance(candidates, str):
        return candidates if candidates in df.columns else None
    for c in candidates:
        if c in df.columns:
            return c
    return None

# VD: 5 digits right after "ВД", optional spaces and optional "№"
RE_VD = re.compile(r"(?i)\bВД\s*№?\s*(\d{5})\b")

# VP: 8 digits after "ВП", optional spaces and optional "№"
# Extra rule: after ';', '; ', or '; №', take 8 digits starting with '6' and ending before ';'
RE_VP = re.compile(r"(?i)вп\s*№?\s*([0-9]{8})")
RE_VP_SEMI = re.compile(r";\s*(?:№\s*)?(6\d{7})\s*;")

# IPN: any 10 consecutive digits (validated by checksum)
RE_IPN_10 = re.compile(r"\b(\d{10})\b")

# CaseID: 6 digits starting with 1 or 2, right after a word containing "іден"/"иден"/"iden"
RE_CASEID = re.compile(r"(?iu)\b[\w\-]*[іиi]ден[\w\-]*\b[\s:;#№\-]*([12]\d{5})")

# Name after explicit marker "Боржник:"
NAME_AFTER_BORZHNIK = re.compile(
    r"(?i)боржник\s*:\s*([А-ЯA-ZІЇЄҐ][А-Яа-яA-Za-zІЇЄҐіїєґ'`-]+(?:\s+[А-ЯA-ZІЇЄҐ][А-Яа-яA-Za-zІЇЄҐіїєґ'`-]+){1,2})"
)

def extract_vd(text: str) -> str:
    m = RE_VD.search(str(text))
    return m.group(1) if m else ""

def extract_vp(text: str) -> str:
    s = str(text)
    m = RE_VP.search(s)
    if m:
        return m.group(1)
    m2 = RE_VP_SEMI.search(s)
    if m2:
        return m2.group(1)
    return ""

def ipn_control_digit_first9(d9: list[int]) -> int:
    """RNOKPP checksum: weights [-1,5,7,9,4,6,10,5,7] then ((sum % 11) % 10)."""
    weights = [-1, 5, 7, 9, 4, 6, 10, 5, 7]
    s = sum(x * w for x, w in zip(d9, weights))
    return (s % 11) % 10

def is_valid_ipn(s: str) -> bool:
    if not (s and s.isdigit() and len(s) == 10):
        return False
    d = [int(ch) for ch in s]
    return d[9] == ipn_control_digit_first9(d[:9])

def extract_ipn(text: str) -> str:
    for m in RE_IPN_10.finditer(str(text)):
        cand = m.group(1)
        if is_valid_ipn(cand):
            return cand
    return ""

def extract_caseid(text: str) -> str:
    m = RE_CASEID.search(str(text))
    return m.group(1) if m else ""

def extract_name(text: str) -> str:
    s = str(text)
    m = NAME_AFTER_BORZHNIK.search(s)
    if not m:
        return ""
    # remove trailing digits stuck to the name
    return re.sub(r"\s*\d+\s*$", "", m.group(1)).strip()

def parse_amount(series: pd.Series) -> pd.Series:
    """Normalize amounts: remove NBSP/spaces, ',' -> '.', drop non-numeric, then to numeric."""
    amt = (
        series.astype(str)
        .str.replace("\u00a0", " ", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
    )
    return pd.to_numeric(amt, errors="coerce")

def format_amount_comma_decimal(series: pd.Series) -> pd.Series:
    """Format numeric amounts using a comma as decimal separator (e.g., 1234,56)."""
    def fmt(x):
        if pd.isna(x):
            return ""
        return f"{x:.2f}".replace(".", ",")
    return series.map(fmt)

def normalize_date(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, dayfirst=True, errors="coerce")
    return dt.dt.date.astype(str)

# ===== UI =====
st.title("📑 Bank Statement Convertor")

uploaded = st.file_uploader("Choose a statement file", type=["csv", "xls", "xlsx"])

if uploaded:
    try:
        name = uploaded.name.lower()

        # Read file
        if name.endswith(".csv"):
            df = pd.read_csv(uploaded, dtype=str)
        elif name.endswith(".xlsx"):
            df = pd.read_excel(uploaded, dtype=str, engine="openpyxl", header=0)
        else:  # .xls
            import xlrd  # ensure xlrd==2.0.1 in requirements
            df = pd.read_excel(uploaded, dtype=str, engine="xlrd", header=0)

        # Normalize headers (e.g., fix "Дата " with trailing spaces)
        df = df.rename(columns=_clean_header)

        # Pick required columns
        date_col = pick_col(df, ["Дата", "Дата операції"])
        credit_col = pick_col(df, ["Зараховано", "Кредит"])
        purpose_col = "Призначення платежу"

        missing = []
        if date_col is None:
            missing.append("Дата/Дата операції")
        if credit_col is None:
            missing.append("Зараховано/Кредит")
        if purpose_col not in df.columns:
            missing.append("Призначення платежу")

        if missing:
            st.error(f"Missing required column(s): {', '.join(missing)}")
            st.write("Detected headers:", list(df.columns))
            st.stop()

        # === Metrics base ===
        total_rows = len(df)

        # Keep rows where credit > 0
        amt_num = parse_amount(df[credit_col])
        df_pos = df.loc[amt_num > 0].copy()
        credit_pos_rows = len(df_pos)

        # Extract fields from purpose (within filtered rows)
        df_pos["Дата"] = normalize_date(df_pos[date_col])
        df_pos["ВД"] = df_pos[purpose_col].map(extract_vd)
        df_pos["ВП"] = df_pos[purpose_col].map(extract_vp)
        df_pos["ІПН"] = df_pos[purpose_col].map(extract_ipn)
        df_pos["CaseID"] = df_pos[purpose_col].map(extract_caseid)
        df_pos["ПІБ"] = df_pos[purpose_col].map(extract_name)

        # Counts (within credit > 0 subset)
        cnt_vp = (df_pos["ВП"] != "").sum()
        cnt_vd = (df_pos["ВД"] != "").sum()
        cnt_ipn = (df_pos["ІПН"] != "").sum()
        cnt_caseid_missing = (df_pos["CaseID"] == "").sum()
        cnt_nothing_found = ((df_pos[["ВП", "ВД", "ІПН", "CaseID"]] == "").all(axis=1)).sum()

        # Build result (no table shown on screen)
        result_cols = ["Дата", "ВД", "ВП", "ІПН", "CaseID", "ПІБ", purpose_col, credit_col]
        result = df_pos[result_cols].copy()

        # Format credit with comma decimal separator
        result[credit_col] = format_amount_comma_decimal(amt_num.loc[df_pos.index])

        # ---- Show only metrics (no table) ----
        st.subheader("Summary")
        st.write(f"Total rows in file: **{total_rows}**")
        st.write(f"Rows where Credit > 0: **{credit_pos_rows}**")
        st.write(f"Rows with VP found: **{cnt_vp}**")
        st.write(f"Rows with VD found: **{cnt_vd}**")
        st.write(f"Rows with IPN found: **{cnt_ipn}**")
        st.write(f"Rows with missing CaseID: **{cnt_caseid_missing}**")
        st.write(f"Rows where nothing found (VP/VD/IPN/CaseID): **{cnt_nothing_found}**")

        # ---- Downloads only ----
        csv_bytes = result.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ Download CSV", data=csv_bytes,
                           file_name="parsed_statement.csv", mime="text/csv")

        buf = BytesIO()
        result.to_excel(buf, index=False, engine="openpyxl")
        st.download_button("⬇️ Download Excel", data=buf.getvalue(),
                           file_name="parsed_statement.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except ModuleNotFoundError:
        st.error("Excel engine is missing. For .xlsx add 'openpyxl'; for .xls add 'xlrd==2.0.1' to requirements.txt.")
    except Exception as e:
        st.error(f"Error while processing the file: {e}")
else:
    st.info("Please upload a file with headers on the first row.")
