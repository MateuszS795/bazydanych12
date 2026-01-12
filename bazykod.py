import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px
from fpdf import FPDF
from datetime import datetime

# --- 1. KONFIGURACJA STRONY ---
st.set_page_config(page_title="ProMagazyn v3.0", page_icon="📦", layout="wide")

# --- 2. POŁĄCZENIE Z SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Problem z secrets: {e}")
        return None

supabase = init_connection()

# --- 3. FUNKCJE POMOCNICZE ---
def log_history(produkt, typ, ilosc):
    """Zapisuje operację do bazy, rzutując dane na typy natywne Python."""
    if supabase:
        try:
            supabase.table("historia").insert({
                "produkt": str(produkt),
                "typ": str(typ),
                "ilosc": int(ilosc) # Kluczowe dla JSON serializable
            }).execute()
        except:
            pass 

def generate_pdf(dataframe):
    """Generuje PDF z obsługą polskich znaków."""
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font('DejaVu', '', 'https://github.com/reingart/pyfpdf/raw/master/font/DejaVuSans.ttf', uni=True)
    pdf.set_font('DejaVu', '', 16)
    pdf.cell(200, 10, txt="Raport Historii Magazynowej", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font('DejaVu', '', 10)
    
    # Nagłówki
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(45, 10, "Data", border=1, fill=True)
    pdf.cell(65, 10, "Produkt", border=1, fill=True)
    pdf.cell(40, 10, "Typ", border=1, fill=True)
    pdf.cell(30, 10, "Ilość", border=1, fill=True, ln=True)
    
    for _, row in dataframe.iterrows():
        pdf.cell(45, 10, str(row['Data']), border=1)
        pdf.cell(65, 10, str(row['Produkt']), border=1)
        pdf.cell(40, 10, str(row['Typ']), border=1)
        pdf.cell(30, 10, str(row['Ilość']), border=1, ln=True)
    return pdf.output()

# --- 4. POBIERANIE DANYCH ---
data, history_data, k_map = [], [], {}

if supabase:
    try:
        p_res = supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(nazwa)").execute()
        k_res = supabase.table("kategoria").select("id, nazwa").execute()
        
        data = p_res.data if p_res.data else []
        k_map = {k['nazwa']: int(k['id']) for k in k_res.data} if k_res.data else {}
        
        try:
            h_res = supabase.table("historia").select("*").order("created_at", desc=True).limit(50).execute()
            history_data = h_res.data if h_res.data else []
        except:
            st.warning("Tabela 'historia' nie jest dostępna.")
    except Exception as e:
        st.error(f"Błąd połączenia: {e}")

# --- 5. PRZYGOTOWANIE DATAFRAME ---
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
st.title("📦 System Magazynowy Pro v3.1")

t_stan, t_oper, t_hist = st.tabs(["📊 Stan", "🛠️ Operacje", "📜 Historia"])

with t_stan:
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Wartość", f"{df['Wartość'].sum():,.2f} zł")
        c2.metric("Sztuk", int(df['Ilość'].sum()))
        c3.metric("Produkty", len(df))
        st.dataframe(df[["Produkt", "Kategoria", "Ilość", "Cena"]], use_container_width=True, hide_index=True)
    else:
        st.info("Baza jest pusta.")

with t_oper:
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Wydaj / Przyjmij")
        if not df.empty:
            with st.container(border=True):
                target_p = st.selectbox("Produkt", df["Produkt"].tolist())
                amount = st.number_input("Ilość", min_value=1, step=1)
                
                # Pobranie wiersza i rzutowanie na typy Python
                p_row = df[df["Produkt"] == target_p].iloc[0]
                p_id = int(p_row["ID"]) 
                current_qty = int(p_row["Ilość"])
                
                b1, b2 = st.columns(2)
                if b1.button("📥 PRZYJMIJ", use_container_width=True):
                    new_val = current_qty + int(amount)
                    supabase.table("produkty").update({"liczba": new_val}).eq("id", p_id).execute()
                    log_history(target_p, "Przyjęcie", amount)
                    st.rerun()
                
                if b2.button("📤 WYDAJ", use_container_width=True):
                    if current_qty >= amount:
                        new_val = current_qty - int(amount)
                        supabase.table("produkty").update({"liczba": new_val}).eq("id", p_id).execute()
                        log_history(target_p, "Wydanie", amount)
                        st.rerun()
                    else:
                        st.error("Brak towaru!")

    with col_r:
        st.subheader("Nowy Produkt")
        with st.container(border=True):
            n_name = st.text_input("Nazwa")
            n_kat = st.selectbox("Kategoria", list(k_map.keys()) if k_map else ["Brak"])
            n_price = st.number_input("Cena", min_value=0.0)
            if st.button("Dodaj produkt", use_container_width=True):
                if n_name and n_kat != "Brak":
                    supabase.table("produkty").insert({
                        "nazwa": n_name, "kategoria_id": int(k_map[n_kat]), 
                        "liczba": 0, "cena": float(n_price)
                    }).execute()
                    log_history(n_name, "Utworzenie", 0)
                    st.rerun()

with t_hist:
    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        if st.button("📄 Pobierz PDF"):
            pdf_bytes = generate_pdf(df_hist)
            st.download_button("💾 Zapisz plik", data=pdf_bytes, file_name="historia.pdf", mime="application/pdf")
    else:
        st.info("Brak wpisów w historii.")
