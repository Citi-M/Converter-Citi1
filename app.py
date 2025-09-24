import streamlit as st
import pandas as pd
import re
from io import BytesIO
from typing import Optional, List

# ---- Page config (place before any other Streamlit calls) ----
st.set_page_config(page_title="Bank Statement Analyzer", layout="wide")

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

# ==========================
# Extraction helpers (UA/RU)
# ==========================

WS_RE = re.compile(r"\s+")

# Court order number (ВД): priority rule "ВС/ФС + 9 digits"
RE_VD_VS_FS = re.compile(r"(?<!\w)(?:ВС|ФС)\s*[-:]?\s*(\d{9})(?!\d)", re.IGNORECASE | re.U)

# "по и/д № 12-34/567" (common pattern from court doc references)
RE_VD_PO_ID = re.compile(r"по\s+и/д\s*№?\s*([\d\-\/]+)", re.IGNORECASE | re.U)

# Generic VD after keywords (avoid mixing with IP/VP markers nearby)
RE_VD_GENERIC = re.compile(
    r"(?:(?:судов(?:ий|ого)\s+наказ|судебн(?:ый|ого)\s+приказ|виконавч(?:ий|ого)\s+документ|"
    r"исполнительн(?:ый|ого)\s+лист|ВД|В[\. ]?Д\.?)\s*[:№#]?\s*|№\s*)"
    r"([\d]{1,4}(?:[-\/]\d{1,4}){0,4})",
    re.IGNORECASE | re.U,
)

# Markers that indicate enforcement proceeding context (to avoid misclassifying as VD)
RE_IP_MARKER = re.compile(r"(?<!\w)(?:іп|ип|исп|исп\.?|вп)\b", re.IGNORECASE | re.U)

# Enforcement proceeding number (ВП/ІП/ИП)
RE_VP = re.compile(
    r"(?:(?:ВП|ІП|ИП)\s*[:№#]?\s*([0-9]{2,5}(?:[-/][0-9]{1,4}){1,5}|[0-9]{6,20}))",
    re.IGNORECASE | re.U,
)

# Extra VP shape often seen: e.g. 2-02-2266/26/2021
RE_VP_COMPLEX = re.compile(r"\b\d{1,2}-\d{2}-\d{3,6}/\d{2}/\d{4}\b")

# Explicit name markers (UA)
RE_NAME_EXPLICIT = re.compile(
    r"(?:ПІБ|Боржник|Платник|Стягувач|Отримувач)\s*[:\-]\s*"
    r"([А-ЯЇІЄҐ][а-яіїєґ']+\s+[А-ЯЇІЄҐ][а-яіїєґ']+(?:\s+[А-ЯЇІЄҐ][а-яіїєґ']+)?)",
    re.U,
)

# Generic Ukrainian full name (2–3 parts), excluding common company markers
RE_NAME_GENERIC = re.compile(
    r"\b(?!ТОВ\b|АТ\b|ПРАТ\b|ДП\b|ФОП\b)"
    r"([А-ЯЇІЄҐ][а-яіїєґ']+\s+[А-ЯЇІЄҐ][а-яіїєґ']+(?:\s+[А-ЯЇІЄҐ][а-яіїєґ']+)?)\b",
    re.U,
)
COMPANY_MARKERS = re.compile(r"\b(ТОВ|АТ|ПРАТ|ДП|ФОП|ПРИВАТБАНК|MONOBANK|БАНК)\b", re.U | re.IGNORECASE)

def clean_text(s: str) -> str:
    """Normalize whitespace."""
    return WS_RE.sub(" ", (s or "").strip())

def extract_vd(text: str) -> Optional[str]:
    """Extract court order number (Номер ВД)."""
    if not text:
        return None
    t = clean_text(text)
    # Priority: VS/FS + 9 digits
    m = RE_VD_VS_FS.search(t)
    if m:
        # Return with prefix for clarity (e.g., "ВС 123456789")
        prefix = re.search(r"(ВС|ФС)", t, flags=re.IGNORECASE)
        return f"{prefix.group(1).upper()} {m.group(1)}" if prefix else m.group(1)
    # "по и/д № ..."
    m = RE_VD_PO_ID.search(t)
    if m:
        val = m.group(1)
        if val and not val.lower().endswith("-ип"):
            return val
    # Generic VD; skip if IP/VP markers appear in close context
    m = RE_VD_GENERIC.search(t)
    if m:
        span = m.span(1)
        context = t[max(0, span[0]-10): span[1]+10]
        if not RE_IP_MARKER.search(context):
            return m.group(1)
    return None

def extract_vp(text: str) -> Optional[str]:
    """Extract enforcement proceeding number (Номер ВП)."""
    if not text:
        return None
    t = clean_text(text)
    m = RE_VP.search(t)
    if m:
        return m.group(1)
    m2 = RE_VP_COMPLEX.search(t)
    if m2:
        return m2.group(0)
    return None

def extract_name(text: str) -> Optional[str]:
    """Extract a personal full name (ПІБ) using explicit markers first, then generic heuristics."""
    if not text:
        return None
    t = clean_text(text)
    m = RE_NAME_EXPLICIT.search(t)
    if m:
        name = m.group(1).strip()
        if not COMPANY_MARKERS.search(name) and not re.search(r"\d", name):
            return name
    # Fallback: generic 2–3-component name
    candidates = RE_NAME_GENERIC.findall(t)
    for cand in candidates:
        if not COMPANY_MARKERS.search(cand) and not re.search(r"\d", cand):
            return cand.strip()
    return None

def normalize_date(val) -> Optional[str]:
    """Parse and normalize date to ISO (YYYY-MM-DD)."""
    if pd.isna(val):
        return None
    try:
        dt = pd.to_datetime(val, dayfirst=True, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.date().isoformat()
    except Exception:
        return None

def find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Find a column by exact/loose match among candidates."""
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    for c in df.columns:
        lc = c.lower()
        for cand in candidates:
            if cand.lower() in lc:
                return c
    return None

def process_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build the result table:
    Columns: 'Дата', 'Номер ВД', 'Номер ВП', 'ПІБ'
    - Date is taken from 'Дата' (or close equivalents) if present.
    - Other fields are extracted from 'Призначення платежу'.
    """
    col_date = find_column(df, ["Дата", "Date", "Дата операції", "Дата транзакції"])
    col_purpose = find_column(df, ["Призначення платежу", "Призначення", "Description", "Призначення платежа"])

    if not col_purpose:
        raise ValueError("Could not find the 'Призначення платежу' column.")

    # If no clear date column, fill with None
    if not col_date:
        df["_DATE_FALLBACK"] = None
        col_date = "_DATE_FALLBACK"

    out = pd.DataFrame()
    out["Дата"] = df[col_date].map(normalize_date)
    purposes = df[col_purpose].astype(str).fillna("")

    out["Номер ВД"] = purposes.map(extract_vd)
    out["Номер ВП"] = purposes.map(extract_vp)
    out["ПІБ"] = purposes.map(extract_name)

    # Keep only rows where at least one extracted field is present
    mask_any = out[["Номер ВД", "Номер ВП", "ПІБ"]].notna().any(axis=1)
    return out[mask_any].reset_index(drop=True)

# ===============
# Streamlit UI
# ===============

st.title("📑 Bank Statement Analyzer")
st.write("Upload a statement (CSV/XLS/XLSX). The app will parse the **'Призначення платежу'** column and produce a table with columns: **Дата, Номер ВД, Номер ВП, ПІБ**.")

uploaded_file = st.file_uploader("Choose a statement file", type=["csv", "xls", "xlsx"])

if uploaded_file:
    try:
        # Try reading CSV first by extension; otherwise read as Excel.
        filename = uploaded_file.name.lower()
        if filename.endswith(".csv"):
            # Attempt default CSV; if it fails, try semicolon-delimited
            try:
                df_raw = pd.read_csv(uploaded_file, dtype=str)
            except Exception:
                uploaded_file.seek(0)
                df_raw = pd.read_csv(uploaded_file, dtype=str, sep=";")
        else:
            # For .xls you need xlrd; for .xlsx you need openpyxl (add both to requirements.txt)
            df_raw = p_
