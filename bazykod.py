import streamlit as st
from supabase import create_client, Client

# 1. Inicjalizacja połączenia z Supabase
@st.cache_resource
def init_connection():
    # Pobieranie danych z Streamlit Secrets
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

st.set_page_config(page_title="Magazyn Supabase", layout="centered")
st.title("📦 System Zarządzania Produktami")

# --- SEKCJA: DODAWANIE KATEGORII ---
st.header("1. Dodaj nową kategorię")
with st.form("form_kategoria", clear_on_submit=True):
    nowa_kat_nazwa = st.text_input("Nazwa kategorii (np. Elektronika)")
    nowa_kat_opis = st.text_area("Opis kategorii")
    submit_kat = st.form_submit_button("Zapisz kategorię")
    
    if submit_kat:
        if nowa_kat_nazwa:
            try:
                # Zgodnie ze schematem: tabela 'Kategoria', kolumny 'nazwa', 'opis'
                supabase.table("Kategoria").insert({
                    "nazwa": nowa_kat_nazwa,
                    "opis": nowa_kat_opis
                }).execute()
                st.success(f"Dodano kategorię: {nowa_kat_nazwa}")
                st.rerun() # Odświeżamy, aby kategoria pojawiła się na liście produktów
            except Exception as e:
                st.error(f"Błąd podczas dodawania: {e}")
        else:
            st.warning("Nazwa kategorii jest wymagana.")

st.divider()

# --- SEKCJA: DODAWANIE PRODUKTU ---
st.header("2. Dodaj nowy produkt")

# Pobieranie listy kategorii do rozwijanego menu (selectbox)
def get_categories():
    try:
        # Pobieramy id i nazwa z tabeli Kategoria
        response = supabase.table("Kategoria").select("id, nazwa").execute()
        return response.data
    except Exception:
        return []

kategorie_dane = get_categories()

if not kategorie_dane:
    st.info("Dodaj najpierw przynajmniej jedną kategorię, aby móc dodać produkt.")
else:
    # Tworzymy słownik { "Nazwa": id }, aby użytkownik widział tekst, a baza dostała numer ID
    kategorie_dict = {item['nazwa']: item['id'] for item in kategorie_dane}

    with st.form("form_produkt", clear_on_submit=True):
        nazwa_p = st.text_input("Nazwa produktu")
        liczba_p = st.number_input("Liczba sztuk", min_value=0, step=1)
        cena_p = st.number_input("Cena (PLN)", min_value=0.0, format="%.2f")
        wybrana_kat_nazwa = st.selectbox("Wybierz kategorię", options=list(kategorie_dict.keys()))
        
        submit_prod = st.form_submit_button("Dodaj produkt do bazy")
        
        if submit_prod:
            if nazwa_p:
                try:
                    # Zgodnie ze schematem: tabela 'produkty', kolumny 'nazwa', 'liczba', 'cena', 'Kategoria_id'
                    supabase.table("produkty").insert({
                        "nazwa": nazwa_p,
                        "liczba": liczba_p,
                        "cena": cena_p,
                        "Kategoria_id": kategorie_dict[wybrana_kat_nazwa]
                    }).execute()
                    st.success(f"Produkt '{nazwa_p}' został pomyślnie dodany!")
                except Exception as e:
                    st.error(f"Błąd: {e}")
            else:
                st.warning("Nazwa produktu nie może być pusta.")

# --- PODGLĄD TABELI ---
st.divider()
if st.checkbox("Pokaż listę wszystkich produktów"):
    try:
        # Pobieramy dane z produktów oraz nazwę kategorii poprzez relację
        res = supabase.table("produkty").select("nazwa, liczba, cena, Kategoria(nazwa)").execute()
        if res.data:
            st.write("Aktualny stan magazynowy:")
            st.table(res.data)
        else:
            st.write("Brak produktów w bazie.")
    except Exception as e:
        st.error(f"Nie udało się pobrać danych: {e}")
