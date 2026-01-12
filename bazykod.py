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
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# --- 3. FUNKCJE POMOCNICZE ---
def log_history(produkt, typ, ilosc):
    """Zapisuje operację do tabeli historia w Supabase."""
    supabase.table("historia").insert({
        "produkt": produkt,
        "typ": typ,
        "ilosc": ilosc
    }).execute()

def generate_pdf(dataframe):
    """Tworzy prosty dokument PDF z historii."""
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font('DejaVu', '', 'https://github.com/reingart/pyfpdf/raw/master/font/DejaVuSans.ttf', uni=True)
    pdf.set_font('DejaVu', '', 16)
    pdf.cell(200, 10, txt="Raport Historii Magazynowej", ln=True, align='C')
    pdf.set_font('DejaVu', '', 10)
    pdf.ln(10)
    
    # Nagłówki
    pdf.cell(40, 10, "Data", border=1)
    pdf.cell(70, 10, "Produkt", border=1)
    pdf.cell(40, 10, "Typ", border=1)
    pdf.cell(30, 10, "Ilość", border=1, ln=True)
    
    # Dane
    for _, row in dataframe.iterrows():
        pdf.cell(40, 10, str(row['Data']), border=1)
        pdf.cell(70, 10, str(row['Produkt']), border=1)
        pdf.cell(40, 10, str(row['Typ']), border=1)
        pdf.cell(30, 10, str(row['Ilość']), border=1, ln=True)
    
    return pdf.output()

# --- 4. POBIERANIE DANYCH ---
try:
    p_res = supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(nazwa)").execute()
    k_res = supabase.table("kategoria").select("id, nazwa").execute()
    h_res = supabase.table("historia").select("*").order("created_at", desc=True).limit(50).execute()
    
    data = p_res.data
    k_map = {k['nazwa']: k['id'] for k in k_res.data} if k_res.data else {}
    history_data = h_res.data
except Exception as e:
    st.error(f"Błąd danych: {e}")
    data, history_data = [], []

# --- 5. PRZYGOTOWANIE DF ---
df = pd.DataFrame([
    {"ID": i["id"], "Produkt": i["nazwa"], "Kategoria": i.get("kategoria", {}).get("nazwa") if i.get("kategoria") else "Brak",
     "Ilość": i["liczba"], "Cena": i["cena"], "Wartość": i["liczba"] * i["cena"]} for i in data
]) if data else pd.DataFrame()

df_hist = pd.DataFrame([
    {"Data": i["created_at"][:16].replace("T", " "), "Produkt": i["produkt"], "Typ": i["typ"], "Ilość": i["ilosc"]}
    for i in history_data
]) if history_data else pd.DataFrame()

# --- 6. INTERFEJS ---
st.title("📦 Magazyn z Historią Operacji")

# Widok główny (Tabela i Wykresy - tak jak wcześniej)
tab_stan, tab_operacje, tab_historia = st.tabs(["📊 Stan Magazynu", "🛠️ Operacje", "📜 Historia i PDF"])

with tab_stan:
    if not df.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Wartość towaru", f"{df['Wartość'].sum():,.2f} zł")
        m2.metric("Suma sztuk", int(df['Ilość'].sum()))
        m3.metric("Liczba SKU", len(df))
        st.dataframe(df[["Produkt", "Kategoria", "Ilość", "Cena"]], use_container_width=True, hide_index=True)
    else:
        st.info("Brak danych.")

with tab_operacje:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Wydaj / Przyjmij")
        if not df.empty:
            p_sel = st.selectbox("Produkt", df["Produkt"].tolist(), key="op_p")
            ile = st.number_input("Ilość", min_value=1, step=1)
            p_row = df[df["Produkt"] == p_sel].iloc[0]
            
            c_in, c_out = st.columns(2)
            if c_in.button("📥 PRZYJMIJ", use_container_width=True):
                new_q = p_row["Ilość"] + ile
                supabase.table("produkty").update({"liczba": new_q}).eq("id", p_row["ID"]).execute()
                log_history(p_sel, "Przyjęcie", ile) # LOGOWANIE
                st.toast("Zaksięgowano przyjęcie")
                st.rerun()
            
            if c_out.button("📤 WYDAJ", use_container_width=True):
                if p_row["Ilość"] >= ile:
                    new_q = p_row["Ilość"] - ile
                    supabase.table("produkty").update({"liczba": new_q}).eq("id", p_row["ID"]).execute()
                    log_history(p_sel, "Wydanie", ile) # LOGOWANIE
                    st.toast("Zaksięgowano wydanie")
                    st.rerun()
                else:
                    st.error("Brak towaru!")
    
    with col2:
        st.subheader("Nowy Produkt")
        n_p = st.text_input("Nazwa")
        n_k = st.selectbox("Kategoria", list(k_map.keys()))
        if st.button("Dodaj produkt"):
            supabase.table("produkty").insert({"nazwa": n_p, "kategoria_id": k_map[n_k], "liczba": 0, "cena": 0}).execute()
            log_history(n_p, "Nowy produkt", 0)
            st.rerun()

with tab_historia:
    st.subheader("Ostatnie operacje")
    if not df_hist.empty:
        st.table(df_hist.head(15)) # Wyświetlamy 15 ostatnich
        
        # Sekcja PDF
        st.markdown("---")
        if st.button("📄 Generuj raport PDF (Ostatnie 50 operacji)"):
            try:
                pdf_bytes = generate_pdf(df_hist)
                st.download_button(
                    label="💾 Pobierz PDF",
                    data=pdf_bytes,
                    file_name=f"raport_magazyn_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Błąd generowania PDF: {e}. Upewnij się, że masz zainstalowane fpdf2.")
    else:
        st.info("Brak historii operacji.")
