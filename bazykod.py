import streamlit as st
from supabase import create_client, Client

# 1. Inicjalizacja połączenia z Supabase
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

st.set_page_config(page_title="Magazyn Supabase", layout="wide")
st.title("📦 System Zarządzania Magazynem")

# --- PANEL BOCZNY: DODAWANIE DANYCH ---
st.sidebar.header("Dodaj do bazy")

# Formularz Kategorii
with st.sidebar.expander("➕ Nowa Kategoria"):
    with st.form("form_kat", clear_on_submit=True):
        n_kat = st.text_input("Nazwa")
        o_kat = st.text_area("Opis")
        if st.form_submit_button("Zapisz"):
            if n_kat:
                supabase.table("kategoria").insert({"nazwa": n_kat, "opis": o_kat}).execute()
                st.success("Dodano!")
                st.rerun()

# Formularz Produktu
def get_cats():
    try:
        res = supabase.table("kategoria").select("id, nazwa").execute()
        return res.data
    except: return []

kategorie_dane = get_cats()
if kategorie_dane:
    kat_dict = {item['nazwa']: item['id'] for item in kategorie_dane}
    with st.sidebar.expander("➕ Nowy Produkt"):
        with st.form("form_prod", clear_on_submit=True):
            p_nazwa = st.text_input("Nazwa produktu")
            p_liczba = st.number_input("Ilość", min_value=0, step=1)
            p_cena = st.number_input("Cena", min_value=0.0)
            p_kat = st.selectbox("Kategoria", options=list(kat_dict.keys()))
            if st.form_submit_button("Dodaj"):
                supabase.table("produkty").insert({
                    "nazwa": p_nazwa, "liczba": p_liczba, 
                    "cena": p_cena, "kategoria_id": kat_dict[p_kat]
                }).execute()
                st.success("Dodano produkt!")
                st.rerun()

# --- GŁÓWNA CZĘŚĆ: WYDAWANIE PRODUKTÓW ---
st.header("📉 Wydawanie produktów z magazynu")

def get_prods():
    try:
        res = supabase.table("produkty").select("id, nazwa, liczba").execute()
        return res.data
    except: return []

produkty_lista = get_prods()

if produkty_lista:
    prod_options = {f"{p['nazwa']} (Dostępne: {p['liczba']})": p for p in produkty_lista}
    
    col1, col2 = st.columns(2)
    with col1:
        wybrany_label = st.selectbox("Wybierz produkt do wydania", options=list(prod_options.keys()))
        wybrany_prod = prod_options[wybrany_label]
    
    with col2:
        ilosc_wydanie = st.number_input("Ile sztuk wydać?", min_value=1, max_value=int(wybrany_prod['liczba']), step=1)
    
    if st.button("Zatwierdź wydanie"):
        nowa_liczba = wybrany_prod['liczba'] - ilosc_wydanie
        try:
            supabase.table("produkty").update({"liczba": nowa_liczba}).eq("id", wybrany_prod['id']).execute()
            st.success(f"Wydano {ilosc_wydanie} szt. produktu {wybrany_prod['nazwa']}. Pozostało: {nowa_liczba}")
            st.rerun()
        except Exception as e:
            st.error(f"Błąd wydania: {e}")
else:
    st.info("Brak produktów w magazynie.")

# --- SEKCJA: STAN MAGAZYNOWY (TABELA) ---
st.divider()
st.header("📊 Aktualny stan magazynowy")

try:
    # Pobieranie danych z relacją do kategorii (małe litery zgodnie ze schematem)
    res = supabase.table("produkty").select("nazwa, liczba, cena, kategoria(nazwa)").execute()
    
    if res.data:
        formatted = []
        for i in res.data:
            formatted.append({
                "Produkt": i.get("nazwa"),
                "Ilość": i.get("liczba"),
                "Cena (zł)": i.get("cena"),
                "Kategoria": i.get("kategoria", {}).get("nazwa") if i.get("kategoria") else "Brak"
            })
        st.dataframe(formatted, use_container_width=True)
    else:
        st.write("Magazyn jest pusty.")
except Exception as e:
    st.error(f"Błąd wyświetlania: {e}")
