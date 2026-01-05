import streamlit as st
from supabase import create_client, Client

# 1. Inicjalizacja połączenia
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

st.title("📦 System Zarządzania Produktami")

# --- SEKCJA: DODAWANIE KATEGORII ---
st.header("1. Dodaj nową kategorię")
with st.form("form_kategoria", clear_on_submit=True):
    # Zgodnie z Twoim schematem: id, nazwa, opis
    nowa_kat_nazwa = st.text_input("Nazwa kategorii")
    nowa_kat_opis = st.text_area("Opis kategorii")
    submit_kat = st.form_submit_button("Zapisz kategorię")
    
    if submit_kat and nowa_kat_nazwa:
        try:
            # Zmieniono na małe litery: 'kategoria'
            supabase.table("kategoria").insert({
                "nazwa": nowa_kat_nazwa,
                "opis": nowa_kat_opis
            }).execute()
            st.success(f"Dodano kategorię: {nowa_kat_nazwa}")
            st.rerun()
        except Exception as e:
            st.error(f"Błąd: {e}")

st.divider()

# --- SEKCJA: DODAWANIE PRODUKTU ---
st.header("2. Dodaj nowy produkt")

def get_categories():
    try:
        # Zmieniono na małe litery: 'kategoria'
        res = supabase.table("kategoria").select("id, nazwa").execute()
        return res.data
    except:
        return []

kategorie_dane = get_categories()

if kategorie_dane:
    kategorie_dict = {item['nazwa']: item['id'] for item in kategorie_dane}

    with st.form("form_produkt", clear_on_submit=True):
        # Zgodnie z Twoim schematem: id, nazwa, liczba, cena, kategoria_id
        nazwa_p = st.text_input("Nazwa produktu")
        liczba_p = st.number_input("Liczba sztuk", min_value=0, step=1)
        cena_p = st.number_input("Cena", min_value=0.0, format="%.2f")
        wybrana_kat = st.selectbox("Wybierz kategorię", options=list(kategorie_dict.keys()))
        
        submit_prod = st.form_submit_button("Dodaj produkt")
        
        if submit_prod and nazwa_p:
            try:
                # Zmieniono na małe litery: 'produkty', 'kategoria_id'
                supabase.table("produkty").insert({
                    "nazwa": nazwa_p,
                    "liczba": liczba_p,
                    "cena": cena_p,
                    "kategoria_id": kategorie_dict[wybrana_kat]
                }).execute()
                st.success(f"Dodano produkt: {nazwa_p}")
            except Exception as e:
                st.error(f"Błąd: {e}")
else:
    st.info("Najpierw dodaj kategorię.")
