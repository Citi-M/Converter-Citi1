import streamlit as st
import pandas as pd
import re
from io import BytesIO
from datetime import datetime

# ===== Простая авторизация =====
CREDENTIALS = {
    "User": "1",
}

def login():
    st.title("🔐 Авторизация")
    with st.form("login_form"):
        username = st.text_input("Login")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")
        if submitted:
            if username in CREDENTIALS and CREDENTIALS[username] == password:
                st.session_state["auth"] = True
                st.session_state["user"] = username
            else:
                st.error("Неверный логин или пароль")

if "auth" not in st.session_state or not st.session_state["auth"]:
    login()
    st.stop()


# ===== Вспомогательные функции =====

def extract_bank_account(text):
    match = re.search(r'\b\d{20}\b', str(text))
    return match.group(0) if match else ""

def extract_is_from_bailiff(text):
    text = str(text).lower().replace('\n', ' ')
    keywords = [
        "уфк", "росп", "осп", "уфссп", "гуссп", "гуфссп",
        "фссп", "фссп россии", "государственная служба судебных приставов"
    ]
    return "Y" if any(kw in text for kw in keywords) else "N"

def extract_court_order_number(text):
    text = str(text).lower()
    priority_match = re.search(r'\b(вс|фс)\s?(\d{9})\b', text)
    if priority_match:
        return f"{priority_match.group(1).upper()} {priority_match.group(2)}"

    match_id_direct = re.search(r'\bид\s+([\d\-]+/\d{4}(?:-\d{1,3})?)\b', text)
    if match_id_direct:
        return match_id_direct.group(1)

    patterns = [
        r'№[а-яa-z]+[\d\-]*-([\d\-]+/\d{4}(?:-\d{1,3})?)',
        r'(?:судебный приказ|суд\.? приказ|с/пр)[^\d]{0,3}([\d]{1,2}-\d{1,4}-\d{1,5}/\d{4})',
        r'(?:судебный приказ|суд\.? приказ|с/пр)\s*(?:№|:)?\s*([\d\-/]+)',
        r'взыскание по ид от \d{2}\.\d{2}\.\d{4} ?№([\d\-/]+)',
        r'по и/д\s*№?\s*([\d\-/]+)',
        r'\bи/д\s*№?\s*([\d\-/]+)',
        r'(?:по\s+)?и/л\s*(?:№|n)?\s*([\d\-/]+)',
        r'\b(?:ид n|ид|n)\s*(?:№|n)?\s*([\d\-]+/\d{4}(?:-\d{1,3})?)\b',
        r'№\s*([\d\-]+/\d{4}(?:-\d{1,3})?)',
        r'суд\.пр\s*([\d\-]+/[\d\-]+)',
        r'исполнительный лист\s*([\d\-]+/\d{4})',
        r'\bил\s+([\d\-]+/\d{4})',
        r'и/л\s*(?:№|n)?\s*([\w\-]+/\d{4})',
        r'по документу\s+([\d\-]+/\d{4})',
        r'с/п\s*([\д\-]+/\d{4})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = match.group(1)
            if len(value.strip()) < 5:
                continue
            before = text[:match.start()]
            if re.search(r'(ип|\bисп\w*)\s*$', before.strip()[-20:]):
                continue
            if re.search(r'-ип$', value):
                continue
            return value

    return ""

def extract_court_order_date(text, court_number):
    text = str(text).lower()
    court_number = court_number.strip().lower()
    if not court_number or len(court_number) < 5:
        return ""
    text_clean = re.sub(r'[()\[\]]', ' ', text)
    match_pos = text_clean.find(court_number)
    if match_pos == -1:
        return ""
    context = text_clean[max(0, match_pos - 50): match_pos + 50]
    date_patterns = [
        r'от\s*(\d{2}\.\d{2}\.\d{4})',
        r'от\s*(\d{4}-\d{2}-\d{2})',
        r'(\d{2}\.\d{2}\.\d{4})',
        r'(\d{4}-\d{2}-\d{2})'
    ]
    for pattern in date_patterns:
        match = re.search(pattern, context)
        if match:
            return match.group(1)
    return ""

def extract_ip_number(text):
    text = str(text).lower()
    match1 = re.search(r'(?:и/п|ип)?[ №:]*([0-9]{4,8}/[0-9]{2}/[0-9]{4,8}-ип)\b', text)
    if match1:
        return match1.group(1)
    match2 = re.search(r'(?:и/п|ип)?[ №:]*([0-9]{4,8}/[0-9]{2}/[0-9]{4,8})\b', text)
    if match2:
        before = text[:match2.start()]
        if "ид" not in before[-20:]:
            return match2.group(1)
    match3 = re.search(r'\(ип\s+([\w\-\/]+)', text)
    if match3:
        return match3.group(1)
    return ""

def extract_fio(text):
    text = str(text)
    patterns = [
        r'\bс\s+([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+)',
        r'\bдолг[а]?:\s*([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+)',
        r'\bдолжника:\s*([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+)',
        r'с должника\s+([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+)',
        r'долга взыскателю\s*:\s*([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+)',
        r'\bс:\s*([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).title().strip()
    return ""


# ===== Обработка данных =====

def process_bank_statement(df):
    df = df[pd.to_numeric(df["Сумма по кредиту"], errors="coerce") > 0].copy()
    result = pd.DataFrame()
    result["CaseID"] = ""
    result["TransactionType"] = "Оплата"
    result["Sum"] = df["Сумма по кредиту"]
    result["PaymentDate"] = pd.to_datetime(df["Дата проводки"], errors="coerce").dt.date
    result["BookingDate"] = datetime.now().date()
    result["BankAccount"] = df["Кредит"].apply(extract_bank_account)
    result["InvoiceNum"] = ""
    result["InvoiceID"] = ""
    result["PaymentProvider"] = ""
    result["IsFromBailiff"] = df["Счет"].apply(extract_is_from_bailiff)
    result["CourtOrderNumber"] = df["Назначение платежа"].apply(extract_court_order_number)
    result["Дата приказа"] = df.apply(lambda row: extract_court_order_date(row["Назначение платежа"], extract_court_order_number(row["Назначение платежа"])), axis=1)
    result["Номер ИП"] = df["Назначение платежа"].apply(extract_ip_number)
    result["ФИО"] = df["Назначение платежа"].apply(extract_fio)
    result["Назначение платежа"] = df["Назначение платежа"]
    return result

# ===== Интерфейс Streamlit =====

st.set_page_config(page_title="Обработка выписки", layout="centered")
st.title("📄 Анализ банковской выписки")

# === История и подсчёты закомментированы ===
# import os, json ...
# st.markdown("### 🧾 История обработок (последние 5):") ...

uploaded_file = st.file_uploader("Загрузите файл выписки (Excel)", type=["xlsx", "xls"])

if uploaded_file:
    try:
        df_raw = pd.read_excel(uploaded_file, skiprows=2)
        df_raw.columns.values[1] = "Дата проводки"
        df_raw.columns.values[4] = "Счет"
        df_raw.columns.values[6] = "Дебет"
        df_raw.columns.values[8] = "Кредит"
        df_raw.columns.values[13] = "Сумма по кредиту"
        df_raw.columns.values[14] = "№ документа"
        df_raw.columns.values[20] = "Назначение платежа"

        df = df_raw.copy()
        st.success("Файл успешно загружен и распознан!")
        df_result = process_bank_statement(df)

        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader("✅ Результат")
        with col2:
            output = BytesIO()
            df_result.to_excel(output, index=False, engine='openpyxl')
            st.download_button("📥 Скачать результат (Excel)", data=output.getvalue(), file_name="результат.xlsx")

        st.dataframe(df_result)

    except Exception as e:
        st.error(f"Ошибка при обработке: {e}")
