import streamlit as st
from supabase import create_client, Client
import pandas as pd

# Połączenie z Supabase
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="Zarządzanie Magazynem", layout="wide")

# Stylizacja nagłówka
st.title("📦 System Zarządzania Magazynem")
st.markdown("---")

# --- SEKCJA 1: AKTUALNY STAN (GŁÓWNY WIDOK) ---
st.header("📊 Aktualny Stan Magazynowy")

# Pobieranie danych do tabeli głównej
try:
    res = supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(nazwa)").execute()
    if res.data:
        cleaned_data = []
        for item in res.data:
            cleaned_data.append({
                "Produkt": item.get("nazwa"),
                "Kategoria": item.get("kategoria", {}).get("nazwa") if item.get("kategoria") else "Brak",
                "Ilość (szt.)": item.get("liczba"),
                "Cena jednostkowa": f"{item.get('cena'):.2f} zł"
            })
        df = pd.DataFrame(cleaned_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Magazyn jest obecnie pusty.")
except Exception as e:
    st.error(f"Nie udało się załadować danych: {e}")

st.markdown("---")

# --- SEKCJA 2: PANEL OPERACYJNY (INTUICYJNE ZARZĄDZANIE) ---
st.header("⚙️ Panel Zarządzania")

# Podział na trzy główne obszary operacyjne
col_prod, col_kat, col_del = st.columns([2, 2, 2])

with col_prod:
    st.subheader("➕ Nowy Produkt")
    # Pobranie kategorii do listy rozwijanej
    k_res = supabase.table("kategoria").select("id, nazwa").execute()
    k_map = {k['nazwa']: k['id'] for k in k_res.data} if k_res.data else {}
    
    with st.container(border=True):
        p_nazwa = st.text_input("Nazwa przedmiotu", key="new_p_name")
        p_kat = st.selectbox("Wybierz kategorię", options=list(k_map.keys()))
        p_ilosc = st.number_input("Ilość", min_value=0, step=1)
        p_cena = st.number_input("Cena (zł)", min_value=0.0, format="%.2f")
        
        if st.button("Zatwierdź Produkt", use_container_width=True):
            if p_nazwa and p_kat:
                supabase.table("produkty").insert({
                    "nazwa": p_nazwa, "kategoria_id": k_map[p_kat], 
                    "liczba": p_ilosc, "cena": p_cena
                }).execute()
                st.success("Dodano!")
                st.rerun()

with col_kat:
    st.subheader("📂 Nowa Kategoria")
    with st.container(border=True):
        k_nazwa = st.text_input("Nazwa kategorii", key="new_k_name")
        k_opis = st.text_area("Krótki opis", height=115)
        
        if st.button("Utwórz Kategorię", use_container_width=True):
            if k_nazwa:
                supabase.table("kategoria").insert({"nazwa": k_nazwa, "opis": k_opis}).execute()
                st.success("Utworzono!")
                st.rerun()

with col_del:
    st.subheader("🗑️ Usuwanie")
    with st.container(border=True):
        st.write("Wybierz element do trwałego usunięcia:")
        
        # Usuwanie produktu
        p_to_del = st.selectbox("Produkt", options=["-- wybierz --"] + [p['nazwa'] for p in res.data] if res.data else ["Brak"])
        if st.button("Usuń Produkt", type="primary", use_container_width=True):
            if p_to_del != "-- wybierz --":
                prod_id = next(item['id'] for item in res.data if item['nazwa'] == p_to_del)
                supabase.table("produkty").delete().eq("id", prod_id).execute()
                st.rerun()
        
        st.markdown("---")
        
        # Usuwanie kategorii
        k_to_del = st.selectbox("Kategoria", options=["-- wybierz --"] + list(k_map.keys()) if k_map else ["Brak"])
        if st.button("Usuń Kategorię", type="primary", use_container_width=True):
            if k_to_del != "-- wybierz --":
                try:
                    supabase.table("kategoria").delete().eq("id", k_map[k_to_del]).execute()
                    st.rerun()
                except:
                    st.error("Nie można usunąć! Kategoria posiada produkty.")
