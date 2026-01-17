import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
import time

# --- 1. KONFIGURACJA STRONY ---
st.set_page_config(page_title="Magazyn", page_icon="📦", layout="wide")

# --- 2. POŁĄCZENIE Z SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Błąd połączenia: {e}")
        return None

supabase = init_connection()

# --- 3. FUNKCJE POMOCNICZE ---
def safe_execute(query_func):
    for i in range(3):
        try: return query_func().execute()
        except Exception as e:
            if "11" in str(e) and i < 2: time.sleep(1); continue
            raise e

def get_lowest_free_id(table_name):
    try:
        res = safe_execute(lambda: supabase.table(table_name).select("id"))
        ids = [int(item['id']) for item in res.data] if res.data else []
        new_id = 0
        while new_id in ids: new_id += 1
        return new_id
    except: return 0

def log_history(p, t, q):
    if supabase:
        try:
            h_id = get_lowest_free_id("historia")
            safe_execute(lambda: supabase.table("historia").insert({"id": h_id, "produkt": str(p), "typ": str(t), "ilosc": int(q)}))
        except: pass 

def generate_txt(dataframe):
    output = io.StringIO()
    output.write(f"RAPORT MAGAZYNOWY - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n" + "="*50 + "\n")
    for _, row in dataframe.iterrows():
        output.write(f"{row['Data']} | {row['Produkt']:<20} | {row['Typ']:<12} | {row['Ilość']} szt.\n")
    return output.getvalue()

# --- 4. POBIERANIE DANYCH ---
data, history_data, k_map = [], [], {}
if supabase:
    try:
        p_res = safe_execute(lambda: supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(id, nazwa)"))
        k_res = safe_execute(lambda: supabase.table("kategoria").select("id, nazwa"))
        data = p_res.data if p_res.data else []
        k_map = {k['nazwa']: int(k['id']) for k in k_res.data} if k_res.data else {}
        h_res = safe_execute(lambda: supabase.table("historia").select("*").order("created_at", desc=True).limit(100))
        history_data = h_res.data if h_res.data else []
    except Exception as e: st.error(f"Błąd: {e}")

# --- 5. PRZYGOTOWANIE TABEL ---
df = pd.DataFrame(data) if data else pd.DataFrame()
if not df.empty:
    df["Kategoria"] = df["kategoria"].apply(lambda x: x["nazwa"] if x else "Brak")
    df = df.rename(columns={"nazwa": "Produkt", "liczba": "Ilość", "cena": "Cena", "id": "ID"})
    df["Wartość"] = df["Ilość"] * df["Cena"]

df_hist = pd.DataFrame([
    {"Data": i["created_at"][:16].replace("T", " "), "Produkt": i["produkt"], "Typ": i["typ"], "Ilość": i["ilosc"]}
    for i in history_data
]) if history_data else pd.DataFrame()

# --- 6. INTERFEJS ---
st.title("📦 System Magazynowy")
t1, t_an, t2, t3 = st.tabs(["📊 Stan", "📈 Analiza Stanu", "🛠️ Operacje", "📜 Historia"])

# ZAKŁADKA 1: STAN
with t1:
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Wartość Łączna", f"{df['Wartość'].sum():,.2f} zł")
        c2.metric("Suma Produktów", int(df['Ilość'].sum()))
        c3.metric("Liczba SKU", len(df))
        st.dataframe(df[["Produkt", "Kategoria", "Ilość", "Cena"]], use_container_width=True, hide_index=True)
    else: st.info("Magazyn jest pusty.")

# ZAKŁADKA 2: ANALIZA STANU
with t_an:
    if not df.empty:
        st.subheader("Wizualizacja Magazynu")
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            fig_pie = px.pie(df, values='Ilość', names='Produkt', title='Udział ilościowy produktów', hole=0.3)
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_chart2:
            fig_bar = px.bar(df.sort_values('Wartość', ascending=False), x='Produkt', y='Wartość', 
                             title='Wartość rynkowa produktów (zł)', color='Wartość')
            st.plotly_chart(fig_bar, use_container_width=True)
        st.divider()
        cat_val = df.groupby('Kategoria')['Wartość'].sum().reset_index()
        fig_cat = px.bar(cat_val.sort_values('Wartość'), x='Wartość', y='
