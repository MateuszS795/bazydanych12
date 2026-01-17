import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import io

# --- 1. KONFIGURACJA STRONY ---
st.set_page_config(page_title="System Magazynowy Pro v3.4", page_icon="📦", layout="wide")

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
    """Bezpieczne zapisywanie zdarzenia w historii."""
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
    """Generuje raport tekstowy (TXT) obsługujący polskie znaki."""
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
        # Pobieranie produktów i kategorii w jednym rzucie
        p_res = supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(id, nazwa)").execute()
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
    df["kat_id"] = df["kategoria"].apply(lambda x: x["id"] if x else None)
    df = df.rename(columns={"nazwa": "Produkt", "liczba": "Ilość", "cena": "Cena", "id": "ID"})
    df["Wartość"] = df["Ilość"] * df["Cena"]

df_hist = pd.DataFrame([
    {"Data": i["created_at"][:16].replace("T", " "), "Produkt": i["produkt"], "Typ": i["typ"], "Ilość": i["ilosc"]}
    for i in history_data
]) if history_data else pd.DataFrame()

# --- 6. INTERFEJS ---
st.title("📦 System Magazynowy Pro v3.4")

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
                target_p = st.selectbox("Wybierz towar", df["Produkt"].tolist(), key="sel_op_prod")
                amount = st.number_input("Ilość", min_value=1, step=1, key="num_op_amount")
                p_row = df[df["Produkt"] == target_p].iloc[0]
                p_id, current_qty = int(p_row["ID"]), int(p_row["Ilość"])
                
                b1, b2 = st.columns(2)
                if b1.button("📥 PRZYJMIJ", use_container_width=True, type="primary", key="btn_in"):
                    with st.spinner("Przetwarzanie..."):
                        supabase.table("produkty").update({"liczba": current_qty + int(amount)}).eq("id", p_id).execute()
                        log_history(target_p, "Przyjęcie", int(amount))
                        st.rerun()
                if b2.button("📤 WYDAJ", use_container_width=True, key="btn_out"):
                    if current_qty >= amount:
                        with st.spinner("Przetwarzanie..."):
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
            if st.button("Zapisz produkt", use_container_width=True, key="btn_save_p"):
                if n_name and n_kat != "Brak":
                    with st.spinner("Zapisywanie..."):
                        supabase.table("produkty").insert({"nazwa": str(n_name), "kategoria_id": int(k_map[n_kat]), "liczba": 0, "cena": float(n_price)}).execute()
                        log_history(n_name, "Utworzenie", 0)
                        st.rerun()

        # 2. Zarządzanie Kategoriami
        with st.container(border=True):
            st.write("**Zarządzaj Kategoriami**")
            ck1, ck2 = st.tabs(["➕ Dodaj", "✏️ Edytuj / Usuń"])
            
            with ck1:
                new_cat_name = st.text_input("Nazwa nowej kategorii", key="add_cat_in")
                if st.button("Utwórz", use_container_width=True, key="btn_add_cat"):
                    if new_cat_name:
                        with st.spinner("Dodawanie..."):
                            supabase.table("kategoria").insert({"nazwa": str(new_cat_name)}).execute()
                            st.rerun()
            
            with ck2:
                if k_map:
                    cat_sel = st.selectbox("Wybierz kategorię", list(k_map.keys()), key="sel_cat_mod")
                    new_name_val = st.text_input("Zmień nazwę", value=cat_sel, key="edit_cat_in")
                    
                    be1, be2 = st.columns(2)
                    if be1.button("Zapisz", use_container_width=True, key="btn_update_cat"):
                        with st.spinner("Aktualizacja..."):
                            supabase.table("kategoria").update({"nazwa": new_name_val}).eq("id", k_map[cat_sel]).execute()
                            st.rerun()
                    
                    if be2.button("Usuń", use_container_width=True, key="btn_del_cat"):
                        # Sprawdzanie lokalnie w df, czy kategoria jest pusta
                        is_used = not df[df["kat_id"] == k_map[cat_sel]].empty if not df.empty else False
                        if is_used:
                            st.warning("Kategoria zawiera produkty! Przenieś je najpierw.")
                            # Opcjonalne: Tutaj można dodać selectbox do przenoszenia, 
                            # ale na razie blokujemy usuwanie pełnych kategorii dla bezpieczeństwa.
                        else:
                            with st.spinner("Usuwanie..."):
                                supabase.table("kategoria").delete().eq("id", k_map[cat_sel]).execute()
                                st.rerun()
                else:
                    st.info("Brak kategorii.")

with t3:
    if not df_hist.empty:
        st.subheader("Ostatnie operacje")
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        txt_report = generate_txt(df_hist)
        st.download_button(label="📄 Pobierz raport (TXT)", data=txt_report, file_name="raport.txt", mime="text/plain", key="btn_dl_txt")
    else:
        st.info("Historia operacji jest pusta.")
