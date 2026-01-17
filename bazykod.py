import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
import time

# --- 1. KONFIGURACJA STRONY ---
st.set_page_config(page_title="Magazyn Pro v5.1", page_icon="📦", layout="wide")

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

# --- 2. FUNKCJE POMOCNICZE ---
def safe_execute(query_func):
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
    try:
        res = safe_execute(lambda: supabase.table("ustawienia").select("*"))
        default = {"prog_brak": 0, "prog_niski": 5, "prog_sredni": 15}
        if res.data:
            for item in res.data:
                default[item['klucz']] = item['wartosc']
        return default
    except:
        return {"prog_brak": 0, "prog_niski": 5, "prog_sredni": 15}

def update_setting(klucz, wartosc):
    safe_execute(lambda: supabase.table("ustawienia").upsert({"klucz": klucz, "wartosc": wartosc}, on_conflict="klucz"))

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
p_raw, k_raw, h_raw, settings = [], [], [], {}
k_map = {}

if supabase:
    try:
        p_res = safe_execute(lambda: supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(id, nazwa)"))
        k_res = safe_execute(lambda: supabase.table("kategoria").select("id, nazwa"))
        h_res = safe_execute(lambda: supabase.table("historia").select("*").order("created_at", desc=True).limit(100))
        p_raw, k_raw, h_raw = p_res.data or [], k_res.data or [], h_res.data or []
        k_map = {k['nazwa']: int(k['id']) for k in k_raw}
        settings = get_settings()
    except Exception as e: st.error(f"Błąd danych: {e}")

# --- 4. PRZETWARZANIE ---
df = pd.DataFrame(p_raw) if p_raw else pd.DataFrame()
if not df.empty:
    df["Kategoria"] = df["kategoria"].apply(lambda x: x["nazwa"] if x else "Brak")
    df = df.rename(columns={"nazwa": "Produkt", "liczba": "Ilość", "cena": "Cena", "id": "ID"})
    df["Wartość"] = df["Ilość"] * df["Cena"]

df_hist = pd.DataFrame([
    {"Data": i["created_at"][:16].replace("T", " "), "Produkt": i["produkt"], "Typ": i["typ"], "Ilość": i["ilosc"]}
    for i in h_raw
]) if h_raw else pd.DataFrame()

# --- 5. INTERFEJS ---
st.title("📦 System Magazynowy Pro v5.1")
t1, t_an, t2, t3 = st.tabs(["📊 Stan", "📈 Analiza", "🛠️ Operacje", "📜 Historia"])

# --- ZAKŁADKA 1: STAN ---
with t1:
    if not df.empty:
        with st.expander("⚙️ Konfiguracja poziomów zapasów", expanded=False):
            st.write("Wpisz wartości progowe dla statusów wizualnych:")
            c_cfg1, c_cfg2, c_cfg3 = st.columns(3)
            n_brak = c_cfg1.number_input("KRYTYCZNY (🔴) poniżej lub równe:", value=int(settings.get('prog_brak', 0)))
            n_low = c_cfg2.number_input("NISKI (🟡) poniżej:", value=int(settings.get('prog_niski', 5)))
            n_med = c_cfg3.number_input("ŚREDNI (🔵) poniżej:", value=int(settings.get('prog_sredni', 15)))
            
            if st.button("Zapisz progi w bazie"):
                update_setting('prog_brak', n_brak)
                update_setting('prog_niski', n_low)
                update_setting('prog_sredni', n_med)
                st.success("Zapisano!"); time.sleep(0.5); st.rerun()

        c_h1, c_h2 = st.columns([2, 1])
        search = c_h1.text_input("🔍 Szukaj...", "")
        sort_by = c_h2.selectbox("Sortuj:", ["Nazwa", "Wartość", "Stan"])

        f_df = df.copy()
        if search: f_df = f_df[f_df['Produkt'].str.contains(search, case=False) | f_df['Kategoria'].str.contains(search, case=False)]
        
        def get_stat(q):
            if q <= n_brak: return "🔴 Brak/Krytyczny"
            if q < n_low: return "🟡 Niski"
            if q < n_med: return "🔵 Średni"
            return "🟢 OK"
        f_df['Status'] = f_df['Ilość'].apply(get_stat)

        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Wycena", f"{f_df['Wartość'].sum():,.2f} zł")
        m2.metric("Sztuk", int(f_df['Ilość'].sum()))
        m3.metric("Niskie (🟡)", len(f_df[(f_df['Ilość'] > n_brak) & (f_df['Ilość'] < n_low)]))
        m4.metric("Krytyczne (🔴)", len(f_df[f_df['Ilość'] <= n_brak]), delta_color="inverse")

        st.dataframe(f_df[["Status", "Produkt", "Kategoria", "Ilość", "Cena", "Wartość"]], use_container_width=True, hide_index=True,
            column_config={
                "Cena": st.column_config.NumberColumn(format="%.2f zł"),
                "Wartość": st.column_config.NumberColumn(format="%.2f zł"),
                "Ilość": st.column_config.ProgressColumn(min_value=0, max_value=int(max(f_df['Ilość'].max(), n_med)))
            })
    else: st.info("Magazyn pusty.")

# --- ZAKŁADKA 2: ANALIZA ---
with t_an:
    if not df.empty:
        ca1, ca2 = st.columns(2)
        with ca1: st.plotly_chart(px.pie(df, values='Ilość', names='Produkt', title='Udział ilościowy', hole=0.3), use_container_width=True)
        with ca2: st.plotly_chart(px.bar(df.sort_values('Wartość', ascending=False), x='Produkt', y='Wartość', title='Wartość produktów', color='Wartość'), use_container_width=True)
        st.divider()
        cat_v = df.groupby('Kategoria')['Wartość'].sum().reset_index()
        st.plotly_chart(px.bar(cat_v.sort_values('Wartość'), x='Wartość', y='Kategoria', orientation='h', title='Wartość wg Kategorii', color='Kategoria'), use_container_width=True)

# --- ZAKŁADKA 3: OPERACJE ---
with t2:
    cl, cr = st.columns(2)
    with cl:
        st.subheader("Ruch towaru")
        if not df.empty:
            with st.container(border=True):
                tp = st.selectbox("Produkt", df["Produkt"].tolist())
                am = st.number_input("Ilość", min_value=1, step=1, key="move_val")
                row = df[df["Produkt"] == tp].iloc[0]
                b1, b2 = st.columns(2)
                if b1.button("📥 PRZYJMIJ", use_container_width=True):
                    safe_execute(lambda: supabase.table("produkty").update({"liczba": int(row["Ilość"]) + am}).eq("id", row["ID"]))
                    log_history(tp, "Przyjęcie", am); st.rerun()
                if b2.button("📤 WYDAJ", use_container_width=True):
                    if row["Ilość"] >= am:
                        safe_execute(lambda: supabase.table("produkty").update({"liczba": int(row["Ilość"]) - am}).eq("id", row["ID"]))
                        log_history(tp, "Wydanie", am); st.rerun()
                    else: st.error("Mało towaru!")

    with cr:
        st.subheader("Baza")
        with st.container(border=True):
            it1, it2, it3 = st.tabs(["➕ Dodaj", "✏️ Edytuj", "🗑️ Usuń"])
            with it1:
                nn = st.text_input("Nazwa")
                nk = st.selectbox("Kategoria", list(k_map.keys()) if k_map else ["Brak"])
                np = st.number_input("Cena", min_value=0.0)
                if st.button("Zapisz", use_container_width=True):
                    if nn and nk != "Brak":
                        safe_execute(lambda: supabase.table("produkty").insert({"id": get_lowest_free_id("produkty"), "nazwa": nn, "kategoria_id": k_map[nk], "liczba": 0, "cena": np}))
                        log_history(nn, "Nowy", 0); st.rerun()
            with it2:
                if not df.empty:
                    ep = st.selectbox("Edytuj produkt", df["Produkt"].tolist())
                    en = st.text_input("Nowa nazwa", value=ep)
                    if st.button("Zaktualizuj"):
                        eid = df[df["Produkt"] == ep].iloc[0]["ID"]
                        safe_execute(lambda: supabase.table("produkty").update({"nazwa": en}).eq("id", eid)); st.rerun()
            with it3:
                if not df.empty:
                    dp = st.selectbox("Usuń produkt", df["Produkt"].tolist())
                    if st.button("USUŃ DEFINITYWNIE", type="primary"):
                        did = df[df["Produkt"] == dp].iloc[0]["ID"]
                        safe_execute(lambda: supabase.table("produkty").delete().eq("id", did)); st.rerun()

# --- ZAKŁADKA 4: HISTORIA ---
with t3:
    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        ch1, ch2 = st.columns(2)
        with ch1: st.download_button("📄 Raport TXT", generate_txt(df_hist), f"raport_{datetime.now().strftime('%Y%m%d')}.txt", use_container_width=True)
        with ch2:
            if st.button("🗑️ Czyść Historię", use_container_width=True):
                safe_execute(lambda: supabase.table("historia").delete().gt("id", -1)); st.rerun()
