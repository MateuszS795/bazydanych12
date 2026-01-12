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
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception as e:
        st.error("Brak konfiguracji secrets! Sprawdź SUPABASE_URL i SUPABASE_KEY.")
        return None

supabase = init_connection()

# --- 3. FUNKCJE POMOCNICZE ---
def log_history(produkt, typ, ilosc):
    """Zapisuje operację do tabeli historia w Supabase."""
    try:
        supabase.table("historia").insert({
            "produkt": produkt,
            "typ": typ,
            "ilosc": ilosc
        }).execute()
    except Exception as e:
        st.error(f"Nie udało się zapisać historii: {e}")

def generate_pdf(dataframe):
    """Tworzy dokument PDF z historii z obsługą polskich znaków."""
    pdf = FPDF()
    pdf.add_page()
    # Pobieranie czcionki z polskimi znakami
    pdf.add_font('DejaVu', '', 'https://github.com/reingart/pyfpdf/raw/master/font/DejaVuSans.ttf', uni=True)
    pdf.set_font('DejaVu', '', 16)
    pdf.cell(200, 10, txt="Raport Historii Magazynowej", ln=True, align='C')
    pdf.set_font('DejaVu', '', 10)
    pdf.ln(10)
    
    # Nagłówki tabeli
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(45, 10, "Data", border=1, fill=True)
    pdf.cell(65, 10, "Produkt", border=1, fill=True)
    pdf.cell(40, 10, "Typ", border=1, fill=True)
    pdf.cell(30, 10, "Ilość", border=1, fill=True, ln=True)
    
    # Dane
    for _, row in dataframe.iterrows():
        pdf.cell(45, 10, str(row['Data']), border=1)
        pdf.cell(65, 10, str(row['Produkt']), border=1)
        pdf.cell(40, 10, str(row['Typ']), border=1)
        pdf.cell(30, 10, str(row['Ilość']), border=1, ln=True)
    
    return pdf.output()

# --- 4. POBIERANIE DANYCH Z ZABEZPIECZENIEM ---
data = []
history_data = []
k_map = {} # Kluczowe: inicjalizacja przed try/except

if supabase:
    try:
        # Pobieranie produktów i kategorii
        p_res = supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(nazwa)").execute()
        k_res = supabase.table("kategoria").select("id, nazwa").execute()
        
        data = p_res.data if p_res.data else []
        k_map = {k['nazwa']: k['id'] for k in k_res.data} if k_res.data else {}
        
        # Próba pobrania historii (zabezpieczona, by brak tabeli nie psuł wszystkiego)
        try:
            h_res = supabase.table("historia").select("*").order("created_at", desc=True).limit(100).execute()
            history_data = h_res.data if h_res.data else []
        except Exception:
            st.warning("⚠️ Tabela 'historia' nie została znaleziona w Supabase. Uruchom skrypt SQL.")
            
    except Exception as e:
        st.error(f"Błąd połączenia z bazą: {e}")

# --- 5. PRZYGOTOWANIE DATAFRAMES ---
df = pd.DataFrame([
    {
        "ID": i["id"], 
        "Produkt": i["nazwa"], 
        "Kategoria": i.get("kategoria", {}).get("nazwa") if i.get("kategoria") else "Brak",
        "Ilość": i["liczba"], 
        "Cena": i["cena"], 
        "Wartość": i["liczba"] * i["cena"]
    } for i in data
]) if data else pd.DataFrame()

df_hist = pd.DataFrame([
    {
        "Data": i["created_at"][:16].replace("T", " "), 
        "Produkt": i["produkt"], 
        "Typ": i["typ"], 
        "Ilość": i["ilosc"]
    } for i in history_data
]) if history_data else pd.DataFrame()

# --- 6. INTERFEJS UŻYTKOWNIKA ---
st.title("📦 System ProMagazyn v3.0")
st.markdown("---")

tab_stan, tab_operacje, tab_historia = st.tabs(["📊 Stan Magazynu", "🛠️ Operacje", "📜 Historia i PDF"])

# --- TAB 1: STAN MAGAZYNU ---
with tab_stan:
    if not df.empty:
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Wartość towaru", f"{df['Wartość'].sum():,.2f} zł")
        col_m2.metric("Suma sztuk", int(df['Ilość'].sum()))
        col_m3.metric("Liczba SKU", len(df))
        
        st.subheader("Aktualne zapasy")
        st.dataframe(
            df[["Produkt", "Kategoria", "Ilość", "Cena"]], 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Ilość": st.column_config.ProgressColumn("Stan", min_value=0, max_value=100)
            }
        )
    else:
        st.info("Magazyn jest obecnie pusty.")

# --- TAB 2: OPERACJE ---
with tab_operacje:
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📥 Przyjęcie / 📤 Wydanie")
        with st.container(border=True):
            if not df.empty:
                target_p = st.selectbox("Wybierz produkt", df["Produkt"].tolist())
                amount = st.number_input("Ilość sztuk", min_value=1, step=1)
                p_row = df[df["Produkt"] == target_p].iloc[0]
                
                c1, c2 = st.columns(2)
                if c1.button("PRZYJMIJ", use_container_width=True, type="primary"):
                    new_qty = p_row["Ilość"] + amount
                    supabase.table("produkty").update({"liczba": new_qty}).eq("id", p_row["ID"]).execute()
                    log_history(target_p, "Przyjęcie", amount)
                    st.toast(f"Przyjęto {amount} szt. {target_p}")
                    st.rerun()
                
                if c2.button("WYDAJ", use_container_width=True):
                    if p_row["Ilość"] >= amount:
                        new_qty = p_row["Ilość"] - amount
                        supabase.table("produkty").update({"liczba": new_qty}).eq("id", p_row["ID"]).execute()
                        log_history(target_p, "Wydanie", amount)
                        st.toast(f"Wydano {amount} szt. {target_p}")
                        st.rerun()
                    else:
                        st.error("Błąd: Niewystarczająca ilość towaru!")
            else:
                st.info("Brak produktów do edycji.")

    with col_right:
        st.subheader("✨ Nowe zasoby")
        with st.container(border=True):
            sub_tab1, sub_tab2 = st.tabs(["Produkt", "Kategoria"])
            with sub_tab1:
                p_name = st.text_input("Nazwa przedmiotu")
                p_kat = st.selectbox("Kategoria", list(k_map.keys()) if k_map else ["Brak"])
                p_price = st.number_input("Cena jedn.", min_value=0.0)
                if st.button("Dodaj produkt", use_container_width=True):
                    if p_name and p_kat != "Brak":
                        supabase.table("produkty").insert({
                            "nazwa": p_name, "kategoria_id": k_map[p_kat], "liczba": 0, "cena": p_price
                        }).execute()
                        log_history(p_name, "Utworzenie", 0)
                        st.rerun()
            with sub_tab2:
                k_name = st.text_input("Nowa kategoria")
                if st.button("Dodaj kategorię", use_container_width=True):
                    if k_name:
                        supabase.table("kategoria").insert({"nazwa": k_name}).execute()
                        st.rerun()

# --- TAB 3: HISTORIA I PDF ---
with tab_historia:
    if not df_hist.empty:
        st.subheader("Ostatnie zdarzenia")
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("Generowanie Raportu")
        if st.button("📄 Pobierz historię jako PDF", type="secondary"):
            with st.spinner("Generowanie pliku..."):
                pdf_output = generate_pdf(df_hist)
                st.download_button(
                    label="💾 Zapisz plik PDF",
                    data=pdf_output,
                    file_name=f"raport_magazyn_{datetime.now().strftime('%d_%m_%Y')}.pdf",
                    mime="application/pdf"
                )
    else:
        st.info("Historia jest pusta. Wykonaj pierwsze operacje, aby zobaczyć logi.")
