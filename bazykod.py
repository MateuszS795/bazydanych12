import streamlit as st
from supabase import create_client, Client
import pandas as pd

# Połączenie z Supabase
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="Zarządzanie Magazynem", layout="wide")

st.title("📦 System Zarządzania Magazynem")
st.markdown("---")

# --- SEKCJA 1: AKTUALNY STAN (Zawsze na górze) ---
st.header("📊 Aktualny Stan Magazynowy")

try:
    # Pobieramy ID, żeby móc później identyfikować produkty przy wydawaniu
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

# --- SEKCJA 2: PANEL OPERACYJNY ---
st.header("⚙️ Panel Zarządzania i Wydawania")

# Dodajemy czwartą kolumnę specjalnie dla wydawania towaru
col_issue, col_prod, col_kat, col_del = st.columns([2, 2, 2, 2])

# --- NOWOŚĆ: WYDAWANIE TOWARU ---
with col_issue:
    st.subheader("📤 Wydaj Towar")
    with st.container(border=True):
        if res.data:
            # Tworzymy mapę produktów, aby wiedzieć ile jest sztuk przed wydaniem
            prod_info = {p['nazwa']: {"id": p['id'], "current": p['liczba']} for p in res.data}
            
            p_to_issue = st.selectbox("Wybierz towar", options=list(prod_info.keys()), key="issue_select")
            amount = st.number_input("Ile sztuk wydać?", min_value=1, step=1)
            
            current_stock = prod_info[p_to_issue]["current"]
            st.caption(f"Dostępne: {current_stock} szt.")
            
            if st.button("Zatwierdź wydanie", use_container_width=True, type="secondary"):
                if amount <= current_stock:
                    new_count = current_stock - amount
                    try:
                        supabase.table("produkty").update({"liczba": new_count}).eq("id", prod_info[p_to_issue]["id"]).execute()
                        st.success(f"Wydano {amount} szt. {p_to_issue}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Błąd bazy: {e}")
                else:
                    st.error("Brak wystarczającej ilości towaru!")
        else:
            st.write("Brak produktów.")

with col_prod:
    st.subheader("➕ Nowy Produkt")
    k_res = supabase.table("kategoria").select("id, nazwa").execute()
    k_map = {k['nazwa']: k['id'] for k in k_res.data} if k_res.data else {}
    
    with st.container(border=True):
        p_nazwa = st.text_input("Nazwa przedmiotu")
        p_kat = st.selectbox("Kategoria", options=list(k_map.keys()))
        p_ilosc = st.number_input("Ilość startowa", min_value=0, step=1)
        p_cena = st.number_input("Cena (zł)", min_value=0.0, format="%.2f")
        
        if st.button("Dodaj Produkt", use_container_width=True):
            if p_nazwa and p_kat:
                supabase.table("produkty").insert({
                    "nazwa": p_nazwa, "kategoria_id": k_map[p_kat], 
                    "liczba": p_ilosc, "cena": p_cena
                }).execute()
                st.rerun()

with col_kat:
    st.subheader("📂 Nowa Kategoria")
    with st.container(border=True):
        k_nazwa = st.text_input("Nazwa kategorii")
        k_opis = st.text_area("Opis", height=115)
        
        if st.button("Utwórz Kategorię", use_container_width=True):
            if k_nazwa:
                supabase.table("kategoria").insert({"nazwa": k_nazwa, "opis": k_opis}).execute()
                st.rerun()

with col_del:
    st.subheader("🗑️ Usuwanie")
    with st.container(border=True):
        p_to_del_name = st.selectbox("Usuń produkt", options=["-- wybierz --"] + [p['nazwa'] for p in res.data] if res.data else ["Brak"])
        if st.button("Usuń Produkt", type="primary", use_container_width=True):
            if p_to_del_name != "-- wybierz --":
                p_id = next(i['id'] for i in res.data if i['nazwa'] == p_to_del_name)
                supabase.table("produkty").delete().eq("id", p_id).execute()
                st.rerun()
        
        st.markdown("---")
        k_to_del_name = st.selectbox("Usuń kategorię", options=["-- wybierz --"] + list(k_map.keys()) if k_map else ["Brak"])
        if st.button("Usuń Kategorię", type="primary", use_container_width=True):
            if k_to_del_name != "-- wybierz --":
                try:
                    supabase.table("kategoria").delete().eq("id", k_map[k_to_del_name]).execute()
                    st.rerun()
                except:
                    st.error("Kategoria ma produkty!")
