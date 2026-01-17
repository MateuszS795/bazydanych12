import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import io
import time

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

# --- 3. FUNKCJE POMOCNICZE ---
def safe_execute(query_func):
    """Obsługa błędów połączenia Errno 11 (Retry)."""
    for i in range(3):
        try:
            return query_func().execute()
        except Exception as e:
            if "11" in str(e) and i < 2:
                time.sleep(1)
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
        p_res = safe_execute(lambda: supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(id, nazwa)"))
        k_res = safe_execute(lambda: supabase.table("kategoria").select("id, nazwa"))
        
        data = p_res.data if p_res.data else []
        k_map = {k['nazwa']: int(k['id']) for k in k_res.data} if k_res.data else {}
        
        try:
            h_res = safe_execute(lambda: supabase.table("historia").select("*").order("created_at", desc=True).limit(100))
            history_data = h_res.data if h_res.data else []
        except:
            pass
            
    except Exception as e:
        st.error(f"Błąd pobierania danych: {e}")

# --- 5. PRZYGOTOWANIE TABEL ---
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
st.title("📦 Magazyn")
t1, t2, t3 = st.tabs(["📊 Stan", "🛠️ Operacje", "📜 Historia"])

# --- ZAKŁADKA 1: STAN ---
with t1:
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Wartość", f"{df['Wartość'].sum():,.2f} zł")
        c2.metric("Sztuk", int(df['Ilość'].sum()))
        c3.metric("Produkty", len(df))
        st.dataframe(df[["Produkt", "Kategoria", "Ilość", "Cena"]], use_container_width=True, hide_index=True)
    else:
        st.info("Magazyn jest pusty.")

# --- ZAKŁADKA 2: OPERACJE ---
with t2:
    col_l, col_r = st.columns(2)
    
    with col_l:
        st.subheader("Ruch towaru")
        if not df.empty:
            with st.container(border=True):
                target_p = st.selectbox("Produkt", df["Produkt"].tolist(), key="move_p")
                amount = st.number_input("Ilość", min_value=1, step=1, key="move_a")
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
                        st.error("Za mało towaru na stanie!")
        else:
            st.info("Opcja niedostępna - dodaj najpierw produkty do bazy.")

    with col_r:
        st.subheader("Zarządzanie produktami")
        with st.container(border=True):
            pt1, pt2, pt3 = st.tabs(["➕ Dodaj", "✏️ Edytuj", "🗑️ Usuń"])
            
            with pt1:
                n_name = st.text_input("Nazwa nowego produktu")
                # Lista kategorii - jeśli pusta, zawiera tylko "Brak"
                available_cats = list(k_map.keys()) if k_map else ["Brak"]
                n_kat = st.selectbox("Kategoria", available_cats, key="add_p_kat")
                n_price = st.number_input("Cena", min_value=0.0, key="add_p_price")
                
                if st.button("Zapisz nowy produkt", use_container_width=True):
                    # --- KLUCZOWA POPRAWKA: Błąd przy braku kategorii ---
                    if n_kat == "Brak":
                        st.error("Błąd! Nie możesz dodać produktu do 'Brak'. Najpierw utwórz co najmniej jedną kategorię w panelu poniżej.")
                    elif not n_name:
                        st.warning("Podaj nazwę produktu.")
                    else:
                        if not df.empty and n_name.strip().lower() in df["Produkt"].str.lower().values:
                            st.error("Produkt o tej nazwie już istnieje!")
                        else:
                            safe_execute(lambda: supabase.table("produkty").insert({
                                "nazwa": n_name.strip(), 
                                "kategoria_id": k_map[n_kat], 
                                "liczba": 0, 
                                "cena": n_price
                            }))
                            log_history(n_name, "Utworzenie", 0)
                            st.rerun()
            
            with pt2:
                if not df.empty:
                    edit_p = st.selectbox("Produkt do edycji", df["Produkt"].tolist())
                    new_p_name = st.text_input("Nowa nazwa", value=edit_p)
                    if st.button("Zaktualizuj nazwę", use_container_width=True):
                        if new_p_name.strip().lower() in df["Produkt"].str.lower().values and new_p_name.strip().lower() != edit_p.lower():
                            st.error("Ta nazwa jest już zajęta!")
                        else:
                            p_id = df[df["Produkt"] == edit_p].iloc[0]["ID"]
                            safe_execute(lambda: supabase.table("produkty").update({"nazwa": new_p_name.strip()}).eq("id", p_id))
                            log_history(edit_p, f"Zmiana nazwy na: {new_p_name}", 0)
                            st.rerun()
                else:
                    st.write("Brak produktów.")

            with pt3:
                if not df.empty:
                    del_p = st.selectbox("Produkt do usunięcia", df["Produkt"].tolist())
                    if st.button("USUŃ PRODUKT", use_container_width=True, type="primary"):
                        p_id_del = df[df["Produkt"] == del_p].iloc[0]["ID"]
                        safe_execute(lambda: supabase.table("produkty").delete().eq("id", p_id_del))
                        log_history(del_p, "Usunięcie produktu", 0)
                        st.rerun()

        st.subheader("Zarządzanie kategoriami")
        with st.container(border=True):
            ct1, ct2 = st.tabs(["➕ Dodaj", "🗑️ Usuń"])
            with ct1:
                new_c = st.text_input("Nowa nazwa kategorii")
                if st.button("Utwórz kategorię", use_container_width=True):
                    if new_c:
                        if new_c.strip().lower() in [k.lower() for k in k_map.keys()]:
                            st.error("Kategoria już istnieje!")
                        else:
                            safe_execute(lambda: supabase.table("kategoria").insert({"nazwa": new_c.strip()}))
                            st.rerun()
            with ct2:
                if k_map:
                    c_to_del = st.selectbox("Usuń kategorię", list(k_map.keys()))
                    if st.button("USUŃ KATEGORIĘ I JEJ PRODUKTY", use_container_width=True, type="primary"):
                        kid = k_map[c_to_del]
                        safe_execute(lambda: supabase.table("produkty").delete().eq("kategoria_id", kid))
                        safe_execute(lambda: supabase.table("kategoria").delete().eq("id", kid))
                        st.rerun()

# --- ZAKŁADKA 3: HISTORIA ---
with t3:
    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        c_rep, c_del = st.columns(2)
        with c_rep:
            txt_report = generate_txt(df_hist)
            st.download_button("📄 Pobierz raport (TXT)", txt_report, f"raport_{datetime.now().strftime('%Y%m%d_%H%M')}.txt", "text/plain", use_container_width=True)
        with c_del:
            if st.button("🗑️ Wyczyść całą historię", type="secondary", use_container_width=True):
                safe_execute(lambda: supabase.table("historia").delete().gt("id", 0))
                st.rerun()
    else:
        st.info("Historia operacji jest pusta.")
