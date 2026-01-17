import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
import time

# --- 1. KONFIGURACJA STRONY ---
st.set_page_config(page_title="Magazyn Pro v5.0", page_icon="📦", layout="wide")

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

# --- 2. FUNKCJE POMOCNICZE I BAZODANOWE ---
def safe_execute(query_func):
    """Odporność na Errno 11 i błędy połączenia."""
    for i in range(5):
        try: return query_func().execute()
        except Exception as e:
            if ("11" in str(e) or "temporarily unavailable" in str(e).lower()) and i < 4:
                time.sleep(2)
                continue
            raise e

def get_lowest_free_id(table_name):
    try:
        res = safe_execute(lambda: supabase.table(table_name).select("id"))
        ids = [int(item['id']) for item in res.data] if res.data else []
        new_id = 0
        while new_id in ids: new_id += 1
        return new_id
    except: return 0

def get_settings():
    """Pobiera progi alarmowe z nowej tabeli 'ustawienia'."""
    try:
        res = safe_execute(lambda: supabase.table("ustawienia").select("*"))
        return {item['klucz']: item['wartosc'] for item in res.data}
    except:
        return {"prog_niski": 5, "prog_sredni": 15}

def update_setting(klucz, wartosc):
    """Aktualizuje progi w bazie danych."""
    safe_execute(lambda: supabase.table("ustawienia").update({"wartosc": wartosc}).eq("klucz", klucz))

def log_history(p, t, q):
    if supabase:
        try:
            h_id = get_lowest_free_id("historia")
            safe_execute(lambda: supabase.table("historia").insert({"id": h_id, "produkt": str(p), "typ": str(t), "ilosc": int(q)}))
        except: pass 

def generate_txt(dataframe):
    output = io.StringIO()
    output.write(f"RAPORT MAGAZYNOWY - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n" + "="*50 + "\n")
    for _, row in dataframe.iterrows():
        output.write(f"{row['Data']} | {row['Produkt']:<20} | {row['Typ']:<12} | {row['Ilość']} szt.\n")
    return output.getvalue()

# --- 3. POBIERANIE DANYCH ---
p_raw, k_raw, h_raw, settings = [], [], [], {"prog_niski": 5, "prog_sredni": 15}
k_map = {}

if supabase:
    try:
        p_res = safe_execute(lambda: supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(id, nazwa)"))
        k_res = safe_execute(lambda: supabase.table("kategoria").select("id, nazwa"))
        h_res = safe_execute(lambda: supabase.table("historia").select("*").order("created_at", desc=True).limit(100))
        
        p_raw = p_res.data or []
        k_raw = k_res.data or []
        h_raw = h_res.data or []
        k_map = {k['nazwa']: int(k['id']) for k in k_raw}
        settings = get_settings()
    except Exception as e: 
        st.error(f"Błąd danych: {e}")

# --- 4. PRZETWARZANIE DANYCH ---
df = pd.DataFrame(p_raw) if p_raw else pd.DataFrame()
if not df.empty:
    df["Kategoria"] = df["kategoria"].apply(lambda x: x["nazwa"] if x else "Brak")
    df = df.rename(columns={"nazwa": "Produkt", "liczba": "Ilość", "cena": "Cena", "id": "ID"})
    df["Wartość"] = df["Ilość"] * df["Cena"]

df_hist = pd.DataFrame([
    {"Data": i["created_at"][:16].replace("T", " "), "Produkt": i["produkt"], "Typ": i["typ"], "Ilość": i["ilosc"]}
    for i in h_raw
]) if h_raw else pd.DataFrame()

# --- 5. INTERFEJS UŻYTKOWNIKA ---
st.title("📦 System Magazynowy Pro v5.0")
t1, t_an, t2, t3 = st.tabs(["📊 Stan", "📈 Analiza", "🛠️ Operacje", "📜 Historia"])

# --- ZAKŁADKA 1: STAN ---
with t1:
    if not df.empty:
        with st.expander("⚙️ Konfiguracja progów alarmowych (Zapisane w bazie)", expanded=False):
            c_cfg1, c_cfg2 = st.columns(2)
            n_low = c_cfg1.slider("Próg NISKIEGO stanu (🟡)", 1, 50, int(settings.get('prog_niski', 5)))
            n_med = c_cfg2.slider("Próg ŚREDNIEGO stanu (🔵)", n_low + 1, 200, int(settings.get('prog_sredni', 15)))
            if n_low != settings.get('prog_niski') or n_med != settings.get('prog_sredni'):
                update_setting('prog_niski', n_low)
                update_setting('prog_sredni', n_med)
                st.success("Zapisano progi w bazie!")
                time.sleep(0.5)
                st.rerun()

        c_h1, c_h2 = st.columns([2, 1])
        search = c_h1.text_input("🔍 Szukaj produktu lub kategorii...", "")
        sort_by = c_h2.selectbox("Sortuj według:", ["Nazwa", "Wartość", "Stan"])

        f_df = df.copy()
        if search:
            f_df = f_df[f_df['Produkt'].str.contains(search, case=False) | f_df['Kategoria'].str.contains(search, case=False)]
        
        if sort_by == "Wartość": f_df = f_df.sort_values("Wartość", ascending=False)
        elif sort_by == "Stan": f_df = f_df.sort_values("Ilość", ascending=True)
        else: f_df = f_df.sort_values("Produkt")

        def get_stat(q):
            if q <= 0: return "🔴 Brak"
            if q < n_low: return "🟡 Niski"
            if q < n_med: return "🔵 Średni"
            return "🟢 OK"
        f_df['Status'] = f_df['Ilość'].apply(get_stat)

        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Wycena Całkowita", f"{f_df['Wartość'].sum():,.2f} zł")
        m2.metric("Suma Sztuk", int(f_df['Ilość'].sum()))
        m3.metric("Niskie stany (🟡)", len(f_df[f_df['Ilość'] < n_low]))
        m4.metric("Braki (🔴)", len(f_df[f_df['Ilość'] <= 0]))

        st.dataframe(
            f_df[["Status", "Produkt", "Kategoria", "Ilość", "Cena", "Wartość"]],
            use_container_width=True, hide_index=True,
            column_config={
                "Cena": st.column_config.NumberColumn(format="%.2f zł"),
                "Wartość": st.column_config.NumberColumn(format="%.2f zł"),
                "Ilość": st.column_config.ProgressColumn(
                    min_value=0, 
                    max_value=int(max(f_df['Ilość'].max(), n_med)),
                    format="%d szt."
                )
            }
        )
    else:
        st.info("Magazyn jest pusty.")

# --- ZAKŁADKA 2: ANALIZA ---
with t_an:
    if not df.empty:
        ca1, ca2 = st.columns(2)
        with ca1:
            st.plotly_chart(px.pie(df, values='Ilość', names='Produkt', title='Udział ilościowy produktów', hole=0.3), use_container_width=True)
        with ca2:
            st.plotly_chart(px.bar(df.sort_values('Wartość', ascending=False), x='Produkt', y='Wartość', title='Wartość rynkowa produktów', color='Wartość'), use_container_width=True)
        
        st.divider()
        cat_v = df.groupby('Kategoria')['Wartość'].sum().reset_index()
        st.plotly_chart(px.bar(cat_v.sort_values('Wartość'), x='Wartość', y='Kategoria', orientation='h', title='Wartość magazynu wg Kategorii', color='Kategoria'), use_container_width=True)
    else:
        st.info("Brak danych do analizy.")

# --- ZAKŁADKA 3: OPERACJE ---
with t2:
    cl, cr = st.columns(2)
    with cl:
        st.subheader("Ruch towaru")
        if not df.empty:
            with st.container(border=True):
                tp = st.selectbox("Wybierz produkt", df["Produkt"].tolist(), key="move_p")
                am = st.number_input("Ilość sztuk", min_value=1, step=1)
                row = df[df["Produkt"] == tp].iloc[0]
                
                b1, b2 = st.columns(2)
                if b1.button("📥 PRZYJMIJ DOSTAWĘ", use_container_width=True):
                    safe_execute(lambda: supabase.table("produkty").update({"liczba": int(row["Ilość"]) + am}).eq("id", row["ID"]))
                    log_history(tp, "Przyjęcie", am)
                    st.rerun()
                if b2.button("📤 WYDAJ TOWAR", use_container_width=True):
                    if row["Ilość"] >= am:
                        safe_execute(lambda: supabase.table("produkty").update({"liczba": int(row["Ilość"]) - am}).eq("id", row["ID"]))
                        log_history(tp, "Wydanie", am)
                        st.rerun()
                    else:
                        st.error("Błąd: Niewystarczająca ilość towaru w magazynie!")
        else:
            st.info("Brak produktów w bazie.")

    with cr:
        st.subheader("Zarządzanie Bazą")
        with st.container(border=True):
            it1, it2, it3 = st.tabs(["➕ Dodaj Produkt", "✏️ Edytuj", "🗑️ Usuń"])
            
            with it1:
                nn = st.text_input("Nazwa nowego produktu")
                nk = st.selectbox("Kategoria", list(k_map.keys()) if k_map else ["Brak"])
                np = st.number_input("Cena sprzedaży", min_value=0.0, step=0.01)
                if st.button("Zapisz nowy produkt", use_container_width=True):
                    if nn and nk != "Brak":
                        new_id = get_lowest_free_id("produkty")
                        safe_execute(lambda: supabase.table("produkty").insert({
                            "id": new_id, "nazwa": nn, "kategoria_id": k_map[nk], "liczba": 0, "cena": np
                        }))
                        log_history(nn, "Nowy Produkt", 0)
                        st.rerun()
                    else: st.warning("Uzupełnij nazwę i kategorię!")

            with it2:
                if not df.empty:
                    ep = st.selectbox("Produkt do edycji", df["Produkt"].tolist(), key="edit_p")
                    en = st.text_input("Nowa nazwa produktu", value=ep)
                    if st.button("Zaktualizuj nazwę", use_container_width=True):
                        eid = df[df["Produkt"] == ep].iloc[0]["ID"]
                        safe_execute(lambda: supabase.table("produkty").update({"nazwa": en}).eq("id", eid))
                        st.rerun()

            with it3:
                if not df.empty:
                    dp = st.selectbox("Produkt do usunięcia", df["Produkt"].tolist(), key="del_p")
                    if st.button("USUŃ DEFINITYWNIE", type="primary", use_container_width=True):
                        did = df[df["Produkt"] == dp].iloc[0]["ID"]
                        safe_execute(lambda: supabase.table("produkty").delete().eq("id", did))
                        st.rerun()

        with st.container(border=True):
            st.write("**Kategorie**")
            ck1, ck2 = st.tabs(["➕ Dodaj", "🗑️ Usuń"])
            with ck1:
                nck = st.text_input("Nowa nazwa kategorii")
                if st.button("Utwórz kategorię", use_container_width=True):
                    if nck and nck not in k_map:
                        safe_execute(lambda: supabase.table("kategoria").insert({"id": get_lowest_free_id("kategoria"), "nazwa": nck}))
                        st.rerun()
            with ck2:
                if k_map:
                    dk = st.selectbox("Wybierz kategorię do usunięcia", list(k_map.keys()))
                    if st.button("USUŃ KATEGORIĘ (I JEJ PRODUKTY)", use_container_width=True):
                        kid = k_map[dk]
                        safe_execute(lambda: supabase.table("produkty").delete().eq("kategoria_id", kid))
                        safe_execute(lambda: supabase.table("kategoria").delete().eq("id", kid))
                        st.rerun()

# --- ZAKŁADKA 4: HISTORIA ---
with t3:
    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        ch1, ch2 = st.columns(2)
        with ch1:
            st.download_button(
                label="📄 Pobierz pełny raport (TXT)",
                data=generate_txt(df_hist),
                file_name=f"raport_magazyn_{datetime.now().strftime('%Y%m%d')}.txt",
                use_container_width=True
            )
        with ch2:
            if st.button("🗑️ Wyczyść całą historię", use_container_width=True, type="secondary"):
                safe_execute(lambda: supabase.table("historia").delete().gt("id", -1))
                st.rerun()
    else:
        st.info("Brak zarejestrowanych ruchów w historii.")
