import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import io

# --- 1. KONFIGURACJA STRONY ---
# Zmieniono nazwę na "Magazyn"
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
def log_history(produkt, typ, ilosc):
    if supabase:
        try:
            supabase.table("historia").insert({
                "produkt": str(produkt),
                "typ": str(typ),
                "ilosc": int(ilosc)
            }).execute()
        except:
            pass 

def generate_txt(dataframe):
    output = io.StringIO()
    output.write(f"RAPORT MAGAZYNOWY - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n" + "="*50 + "\n")
    for _, row in dataframe.iterrows():
        output.write(f"{row['Data']} | {row['Produkt']} | {row['Typ']} | {row['Ilość']} szt.\n")
    return output.getvalue()

# --- 4. POBIERANIE DANYCH ---
data, history_data, k_map = [], [], {}
if supabase:
    try:
        p_res = supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(id, nazwa)").execute()
        k_res = supabase.table("kategoria").select("id, nazwa").execute()
        data = p_res.data or []
        k_map = {k['nazwa']: int(k['id']) for k in k_res.data} if k_res.data else {}
        h_res = supabase.table("historia").select("*").order("created_at", desc=True).limit(50).execute()
        history_data = h_res.data or []
    except Exception as e:
        st.error(f"Błąd danych: {e}")

df = pd.DataFrame(data) if data else pd.DataFrame()
if not df.empty:
    df["Kategoria"] = df["kategoria"].apply(lambda x: x["nazwa"] if x else "Brak")
    df["kat_id"] = df["kategoria"].apply(lambda x: x["id"] if x else None)
    df = df.rename(columns={"nazwa": "Produkt", "liczba": "Ilość", "cena": "Cena", "id": "ID"})
    df["Wartość"] = df["Ilość"] * df["Cena"]

df_hist = pd.DataFrame([{"Data": i["created_at"][:16].replace("T", " "), "Produkt": i["produkt"], "Typ": i["typ"], "Ilość": i["ilosc"]} for i in history_data]) if history_data else pd.DataFrame()

# --- 5. INTERFEJS ---
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
        st.subheader("Wydaj / Przyjmij")
        if not df.empty:
            with st.container(border=True):
                target_p = st.selectbox("Wybierz towar", df["Produkt"].tolist(), key="op_prod")
                amount = st.number_input("Ilość", min_value=1, step=1, key="op_amount")
                p_row = df[df["Produkt"] == target_p].iloc[0]
                p_id, current_qty = int(p_row["ID"]), int(p_row["Ilość"])
                
                b1, b2 = st.columns(2)
                if b1.button("📥 PRZYJMIJ", use_container_width=True, type="primary"):
                    supabase.table("produkty").update({"liczba": current_qty + int(amount)}).eq("id", p_id).execute()
                    log_history(target_p, "Przyjęcie", amount); st.rerun()
                
                if b2.button("📤 WYDAJ", use_container_width=True):
                    if current_qty >= int(amount):
                        supabase.table("produkty").update({"liczba": current_qty - int(amount)}).eq("id", p_id).execute()
                        log_history(target_p, "Wydanie", amount); st.rerun()
                    else:
                        st.error(f"Błąd! Masz tylko {current_qty} szt. na stanie.")
        
        st.subheader("Usuwanie produktów")
        if not df.empty:
            with st.container(border=True):
                del_p = st.selectbox("Wybierz produkt do usunięcia", df["Produkt"].tolist(), key="del_prod_sel")
                if st.button("❌ USUŃ PRODUKT Z BAZY", use_container_width=True):
                    p_id_del = int(df[df["Produkt"] == del_p].iloc[0]["ID"])
                    supabase.table("produkty").delete().eq("id", p_id_del).execute()
                    log_history(del_p, "Usunięcie produktu", 0); st.rerun()

    with col_r:
        st.subheader("Zarządzanie strukturą")
        with st.container(border=True):
            st.write("**Dodaj Nowy Produkt**")
            n_name = st.text_input("Nazwa", key="n_p_name")
            n_kat = st.selectbox("Kategoria", list(k_map.keys()) if k_map else ["Brak"], key="n_p_kat")
