import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import io
import time  # Dodane do obsługi przerw przy błędach połączenia

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

# --- 3. FUNKCJE POMOCNICZE (Z RETRY) ---
def safe_execute(query_func):
    """Próbuje wykonać zapytanie 3 razy w przypadku błędu Errno 11."""
    for i in range(3):
        try:
            return query_func().execute()
        except Exception as e:
            if "11" in str(e) and i < 2:
                time.sleep(1)  # Czekaj sekundę przed kolejną próbą
                continue
            raise e

def log_history(produkt, typ, ilosc):
    if supabase:
        try:
            safe_execute(lambda: supabase.table("historia").insert({
                "produkt": str(produkt),
                "typ": str(typ),
                "ilosc": int(ilosc)
            }))
        except:
            pass 

# --- 4. POBIERANIE DANYCH ---
data, history_data, k_map = [], [], {}

if supabase:
    try:
        p_res = safe_execute(lambda: supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(id, nazwa)"))
        k_res = safe_execute(lambda: supabase.table("kategoria").select("id, nazwa"))
        
        data = p_res.data if p_res.data else []
        k_map = {k['nazwa']: int(k['id']) for k in k_res.data} if k_res.data else {}
        
        try:
            h_res = safe_execute(lambda: supabase.table("historia").select("*").order("created_at", desc=True).limit(50))
            history_data = h_res.data if h_res.data else []
        except:
            pass
            
    except Exception as e:
        st.error(f"Błąd pobierania danych: {e}")

# --- 5. PRZYGOTOWANIE TABEL ---
df = pd.DataFrame(data) if data else pd.DataFrame()
if not df.empty:
    df["Kategoria"] = df["kategoria"].apply(lambda x: x["nazwa"] if x else "Brak")
    df["kat_id"] = df["kategoria"].apply(lambda x: x["id"] if x else None)
    df = df.rename(columns={"nazwa": "Produkt", "liczba": "Ilość", "cena": "Cena", "id": "ID"})
    df["Wartość"] = df["Ilość"] * df["Cena"]

df_hist = pd.DataFrame([
    {"Data": i["created_at"][:16].replace("T", " "), "Produkt": i["produkt"], "Typ": i["typ"], "Ilość": i["ilosc"]}
    for i in history_data
]) if history_data else pd.DataFrame()

# --- 6. INTERFEJS ---
st.title("📦 Magazyn")
t1, t2, t3 = st.tabs(["📊 Stan", "🛠️ Operacje", "📜 Historia"])

with t1:
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Wartość", f"{df['Wartość'].sum():,.2f} zł")
        c2.metric("Sztuk", int(df['Ilość'].sum()))
        c3.metric("Produkty", len(df))
        st.dataframe(df[["Produkt", "Kategoria", "Ilość", "Cena"]], use_container_width=True, hide_index=True)
    else:
        st.info("Baza jest pusta.")

with t2:
    col_l, col_r = st.columns(2)
    
    with col_l:
        st.subheader("Ruch towaru")
        if not df.empty:
            with st.container(border=True):
                target_p = st.selectbox("Produkt", df["Produkt"].tolist())
                amount = st.number_input("Ilość", min_value=1, step=1)
                p_row = df[df["Produkt"] == target_p].iloc[0]
                
                b1, b2 = st.columns(2)
                if b1.button("📥 PRZYJMIJ", use_container_width=True):
                    safe_execute(lambda: supabase.table("produkty").update({"liczba": int(p_row["Ilość"]) + amount}).eq("id", p_row["ID"]))
                    log_history(target_p, "Przyjęcie", amount)
                    st.rerun()
                if b2.button("📤 WYDAJ", use_container_width=True):
                    if p_row["Ilość"] >= amount:
                        safe_execute(lambda: supabase.table("produkty").update({"liczba": int(p_row["Ilość"]) - amount}).eq("id", p_row["ID"]))
                        log_history(target_p, "Wydanie", amount)
                        st.rerun()
                    else:
                        st.error("Za mało towaru!")

    with col_r:
        st.subheader("Baza danych")
        with st.container(border=True):
            st.write("**Dodaj Produkt**")
            n_name = st.text_input("Nazwa")
            n_kat = st.selectbox("Kategoria", list(k_map.keys()) if k_map else ["Brak"])
            n_price = st.number_input("Cena", min_value=0.0)
            if st.button("Zapisz", use_container_width=True):
                if n_name and n_kat != "Brak":
                    safe_execute(lambda: supabase.table("produkty").insert({"nazwa": n_name, "kategoria_id": k_map[n_kat], "liczba": 0, "cena": n_price}))
                    log_history(n_name, "Utworzenie", 0)
                    st.rerun()

        with st.container(border=True):
            st.write("**Zarządzaj Kategoriami**")
            ck1, ck2 = st.tabs(["➕ Dodaj", "🗑️ Usuń"])
            with ck1:
                new_c = st.text_input("Nowa kategoria")
                if st.button("Utwórz"):
                    safe_execute(lambda: supabase.table("kategoria").insert({"nazwa": new_c}))
                    st.rerun()
            with ck2:
                if k_map:
                    c_to_del = st.selectbox("Usuń kategorię", list(k_map.keys()))
                    if st.button("USUŃ (WRAZ Z PRODUKTAMI)", type="primary"):
                        kid = k_map[c_to_del]
                        safe_execute(lambda: supabase.table("produkty").delete().eq("kategoria_id", kid))
                        safe_execute(lambda: supabase.table("kategoria").delete().eq("id", kid))
                        st.rerun()

with t3:
    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
