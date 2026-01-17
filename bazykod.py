import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import io

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
        st.error(f"Błąd połączenia z bazą: {e}")
        return None

supabase = init_connection()

# --- 3. FUNKCJE POMOCNICZE ---
def log_history(produkt, typ, ilosc):
    """Zapisuje zdarzenie w historii. Teraz pokazuje błędy w panelu bocznym."""
    if supabase:
        try:
            supabase.table("historia").insert({
                "produkt": str(produkt),
                "typ": str(typ),
                "ilosc": int(ilosc)
            }).execute()
        except Exception as e:
            # Wyświetlamy błąd, żebyś wiedział dlaczego historia nie działa
            st.sidebar.error(f"Błąd zapisu historii: {e}")

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
        # Pobieranie produktów i kategorii
        p_res = supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(id, nazwa)").execute()
        k_res = supabase.table("kategoria").select("id, nazwa").execute()
        
        data = p_res.data if p_res.data else []
        k_map = {k['nazwa']: int(k['id']) for k in k_res.data} if k_res.data else {}
        
        # Pobieranie historii
        try:
            h_res = supabase.table("historia").select("*").order("created_at", desc=True).limit(50).execute()
            history_data = h_res.data if h_res.data else []
        except Exception as e:
            st.sidebar.warning(f"Problem z pobraniem historii: {e}")
            
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

# --- ZAKŁADKA 1: STAN ---
with t1:
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Wartość całkowita", f"{df['Wartość'].sum():,.2f} zł")
        c2.metric("Liczba sztuk", int(df['Ilość'].sum()))
        c3.metric("Liczba produktów", len(df))
        st.dataframe(df[["Produkt", "Kategoria", "Ilość", "Cena"]], use_container_width=True, hide_index=True)
    else:
        st.info("Baza danych jest pusta. Dodaj produkty w zakładce Operacje.")

# --- ZAKŁADKA 2: OPERACJE ---
with t2:
    col_l, col_r = st.columns(2)
    
    # LEWA KOLUMNA: Ruch towaru
    with col_l:
        st.subheader("Ruch towaru")
        if not df.empty:
            with st.container(border=True):
                target_p = st.selectbox("Wybierz produkt", df["Produkt"].tolist(), key="op_prod")
                amount = st.number_input("Ilość", min_value=1, step=1, key="op_amount")
                
                # Pobranie danych wybranego produktu
                p_row = df[df["Produkt"] == target_p].iloc[0]
                p_id = int(p_row["ID"])
                current_qty = int(p_row["Ilość"])
                
                b1, b2 = st.columns(2)
                if b1.button("📥 PRZYJMIJ", use_container_width=True, type="primary"):
                    with st.spinner("Zapisywanie..."):
                        supabase.table("produkty").update({"liczba": current_qty + int(amount)}).eq("id", p_id).execute()
                        log_history(target_p, "Przyjęcie", amount)
                        st.rerun()
                
                if b2.button("📤 WYDAJ", use_container_width=True):
                    if current_qty >= int(amount):
                        with st.spinner("Zapisywanie..."):
                            supabase.table("produkty").update({"liczba": current_qty - int(amount)}).eq("id", p_id).execute()
                            log_history(target_p, "Wydanie", amount)
                            st.rerun()
                    else:
                        st.error(f"Błąd! Masz tylko {current_qty} szt. na stanie.")
        
        st.subheader("Usuwanie")
        if not df.empty:
            with st.container(border=True):
                del_p = st.selectbox("Produkt do usunięcia", df["Produkt"].tolist(), key="del_prod_sel")
                if st.button("❌ USUŃ PRODUKT", use_container_width=True):
                    with st.spinner("Usuwanie..."):
                        p_id_del = int(df[df["Produkt"] == del_p].iloc[0]["ID"])
                        supabase.table("produkty").delete().eq("id", p_id_del).execute()
                        log_history(del_p, "Usunięcie produktu", 0)
                        st.rerun()

    # PRAWA KOLUMNA: Zarządzanie bazą
    with col_r:
        st.subheader("Baza produktów")
        
        # 1. Dodawanie nowego produktu
        with st.container(border=True):
            st.write("**Dodaj Nowy Produkt**")
            n_name = st.text_input("Nazwa", key="n_p_name")
            n_kat = st.selectbox("Kategoria", list(k_map.keys()) if k_map else ["Brak"], key="n_p_kat")
            n_price = st.number_input("Cena (zł)", min_value=0.0, key="n_p_price")
            
            if st.button("Zapisz produkt", use_container_width=True):
                if n_name and n_kat != "Brak":
                    with st.spinner("Dodawanie..."):
                        supabase.table("produkty").insert({
                            "nazwa": n_name, 
                            "kategoria_id": k_map[n_kat], 
                            "liczba": 0, 
                            "cena": n_price
                        }).execute()
                        log_history(n_name, "Utworzenie", 0)
                        st.rerun()
                else:
                    st.warning("Wpisz nazwę i wybierz kategorię.")

        # 2. Zarządzanie kategoriami (TO OKIENKO ZNIKNĘŁO, TERAZ JEST NAPRAWIONE)
        with st.container(border=True):
            st.write("**Zarządzaj Kategoriami**")
            ck1, ck2 = st.tabs(["➕ Dodaj", "✏️ Edytuj / Usuń"])
            
            # Zakładka Dodawania
            with ck1:
                new_cat = st.text_input("Nowa nazwa kategorii", key="n_c_name")
                if st.button("Utwórz kategorię", use_container_width=True):
                    if new_cat:
                        if new_cat.strip() in k_map:
                            st.error("Taka kategoria już istnieje!")
                        else:
                            with st.spinner("Tworzenie..."):
                                supabase.table("kategoria").insert({"nazwa": new_cat.strip()}).execute()
                                st.rerun()
            
            # Zakładka Edycji / Usuwania (NAPRAWIONA LOGIKA)
            with ck2:
                if k_map:
                    cat_sel = st.selectbox("Wybierz kategorię", list(k_map.keys()), key="c_sel")
                    new_name = st.text_input("Zmień nazwę na", value=cat_sel, key="c_edit")
                    
                    col_e1, col_e2 = st.columns(2)
                    
                    if col_e1.button("Zmień nazwę", use_container_width=True):
                        if new_name.strip() in k_map and new_name.strip() != cat_sel:
                            st.error("Nazwa zajęta!")
                        else:
                            with st.spinner("Aktualizacja..."):
                                supabase.table("kategoria").update({"nazwa": new_name.strip()}).eq("id", k_map[cat_sel]).execute()
                                st.rerun()
                    
                    if col_e2.button("Usuń", use_container_width=True):
                        # Sprawdzamy, czy w kategorii są produkty
                        is_not_empty = not df[df["kat_id"] == k_map[cat_sel]].empty if not df.empty else False
                        
                        if is_not_empty:
                            st.error("Nie można usunąć: Kategoria zawiera produkty!")
                        else:
                            with st.spinner("Usuwanie..."):
                                supabase.table("kategoria").delete().eq("id", k_map[cat_sel]).execute()
                                st.rerun()
                else:
                    st.info("Brak kategorii do edycji. Dodaj pierwszą kategorię w zakładce obok.")

# --- ZAKŁADKA 3: HISTORIA ---
with t3:
    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        
        txt_report = generate_txt(df_hist)
        st.download_button(
            label="📄 Pobierz raport (TXT)",
            data=txt_report,
            file_name=f"raport_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain"
        )
    else:
        st.info("Historia operacji jest pusta.")
