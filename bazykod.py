import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- 1. KONFIGURACJA STRONY ---
st.set_page_config(page_title="System Magazynowy Pro v3.3", page_icon="📦", layout="wide")

# --- 2. POŁĄCZENIE Z SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Problem z konfiguracją połączenia: {e}")
        return None

supabase = init_connection()

# --- 3. FUNKCJE POMOCNICZE ---
def log_history(produkt, typ, ilosc):
    """Zapisuje zdarzenie w historii."""
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
    """Generuje raport tekstowy."""
    output = io.StringIO()
    output.write("RAPORT HISTORII MAGAZYNOWEJ\n")
    output.write(f"Wygenerowano: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write("=" * 70 + "\n\n")
    output.write(f"{'Data':<20} | {'Produkt':<20} | {'Typ':<15} | {'Ilość':<10}\n")
    output.write("-" * 70 + "\n")
    for _, row in dataframe.iterrows():
        line = f"{str(row['Data']):<20} | {str(row['Produkt']):<20} | {str(row['Typ']):<15} | {str(row['Ilość']):<10}\n"
        output.write(line)
    return output.getvalue()

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
            st.sidebar.warning("⚠️ Brak tabeli historii.")
    except Exception as e:
        st.error(f"Błąd połączenia: {e}")

# --- 5. PRZYGOTOWANIE DATAFRAMES ---
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
st.title("📦 System Magazynowy Pro v3.3")

t1, t2, t3 = st.tabs(["📊 Stan", "🛠️ Operacje", "📜 Historia"])

with t1:
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Wartość", f"{df['Wartość'].sum():,.2f} zł")
        c2.metric("Sztuk", int(df['Ilość'].sum()))
        c3.metric("Produkty", len(df))
        st.dataframe(df[["Produkt", "Kategoria", "Ilość", "Cena"]], use_container_width=True, hide_index=True)
    else:
        st.info("Baza danych jest obecnie pusta.")

with t2:
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Wydaj / Przyjmij")
        if not df.empty:
            with st.container(border=True):
                target_p = st.selectbox("Wybierz towar", df["Produkt"].tolist())
                amount = st.number_input("Ilość", min_value=1, step=1)
                p_row = df[df["Produkt"] == target_p].iloc[0]
                p_id, current_qty = int(p_row["ID"]), int(p_row["Ilość"])
                
                b1, b2 = st.columns(2)
                if b1.button("📥 PRZYJMIJ", use_container_width=True, type="primary"):
                    supabase.table("produkty").update({"liczba": current_qty + int(amount)}).eq("id", p_id).execute()
                    log_history(target_p, "Przyjęcie", int(amount))
                    st.rerun()
                if b2.button("📤 WYDAJ", use_container_width=True):
                    if current_qty >= amount:
                        supabase.table("produkty").update({"liczba": current_qty - int(amount)}).eq("id", p_id).execute()
                        log_history(target_p, "Wydanie", int(amount))
                        st.rerun()
                    else:
                        st.error("Niewystarczająca ilość towaru!")

    with col_r:
        st.subheader("Zarządzanie strukturą")
        
        # 1. Dodawanie Produktu
        with st.container(border=True):
            st.write("**Dodaj Nowy Produkt**")
            n_name = st.text_input("Nazwa przedmiotu", key="new_p_name")
            n_kat = st.selectbox("Kategoria", list(k_map.keys()) if k_map else ["Brak"], key="new_p_kat")
            n_price = st.number_input("Cena", min_value=0.0, key="new_p_price")
            if st.button("Zapisz produkt", use_container_width=True):
                if n_name and n_kat != "Brak":
                    supabase.table("produkty").insert({"nazwa": str(n_name), "kategoria_id": int(k_map[n_kat]), "liczba": 0, "cena": float(n_price)}).execute()
                    log_history(n_name, "Utworzenie", 0)
                    st.rerun()

        # 2. Zarządzanie Kategoriami (Dodawanie / Edycja / Usuwanie)
        with st.container(border=True):
            st.write("**Zarządzaj Kategoriami**")
            
            # Sub-zakładki wewnątrz kontenera, aby nie psuć głównego GUI
            ck1, ck2 = st.tabs(["➕ Dodaj", "✏️ Edytuj / Usuń"])
            
            with ck1:
                new_cat_name = st.text_input("Nowa kategoria")
                if st.button("Dodaj", use_container_width=True):
                    if new_cat_name:
                        supabase.table("kategoria").insert({"nazwa": str(new_cat_name)}).execute()
                        st.rerun()
            
            with ck2:
                if k_map:
                    cat_to_mod = st.selectbox("Wybierz kategorię", list(k_map.keys()))
                    new_name_val = st.text_input("Nowa nazwa", value=cat_to_mod)
                    
                    be1, be2 = st.columns(2)
                    if be1.button("Zapisz zmianę", use_container_width=True):
                        supabase.table("kategoria").update({"nazwa": new_name_val}).eq("id", k_map[cat_to_mod]).execute()
                        st.rerun()
                    
                    if be2.button("Usuń", use_container_width=True):
                        # Sprawdzenie czy kategoria jest używana
                        is_used = not df[df["Kategoria"] == cat_to_mod].empty if not df.empty else False
                        if is_used:
                            st.error("Nie można usunąć kategorii, która ma przypisane produkty!")
                        else:
                            supabase.table("kategoria").delete().eq("id", k_map[cat_to_mod]).execute()
                            st.rerun()
                else:
                    st.info("Brak kategorii do edycji.")

with t3:
    if not df_hist.empty:
        st.subheader("Ostatnie operacje")
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        txt_report = generate_txt(df_hist)
        st.download_button(label="📄 Pobierz raport (TXT)", data=txt_report, file_name="raport.txt", mime="text/plain")
    else:
        st.info("Historia operacji jest pusta.")
