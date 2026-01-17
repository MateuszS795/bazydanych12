import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
import time

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="Magazyn Pro", page_icon="📦", layout="wide")

# Stylizacja dla "fancy" efektu
st.markdown("""
    <style>
    .stMetric { border: 1px solid #e6e9ef; padding: 10px; border-radius: 10px; background: white; }
    div[data-testid="stExpander"] { border: none !important; box-shadow: none !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. POŁĄCZENIE ---
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

# --- 3. LOGIKA BIZNESOWA (ID, EXECUTOR, RAPORT) ---
def safe_execute(query_func):
    for i in range(3):
        try: return query_func().execute()
        except Exception as e:
            if "11" in str(e) and i < 2: time.sleep(1); continue
            raise e

def get_lowest_free_id(table_name):
    res = safe_execute(lambda: supabase.table(table_name).select("id"))
    ids = [int(i['id']) for i in res.data] if res.data else []
    n = 0
    while n in ids: n += 1
    return n

def log_history(p, t, q):
    if supabase:
        try:
            h_id = get_lowest_free_id("historia")
            safe_execute(lambda: supabase.table("historia").insert({"id": h_id, "produkt": str(p), "typ": str(t), "ilosc": int(q)}))
        except: pass

def generate_txt(df_h):
    out = io.StringIO()
    out.write(f"RAPORT MAGAZYNOWY PRO - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n" + "="*55 + "\n")
    for _, r in df_h.iterrows():
        out.write(f"{r['Data']} | {r['Produkt']:<20} | {r['Typ']:<12} | {r['Ilość']} szt.\n")
    return out.getvalue()

# --- 4. POBIERANIE DANYCH ---
p_raw, k_raw, h_raw, k_map = [], [], [], {}
if supabase:
    try:
        p_res = safe_execute(lambda: supabase.table("produkty").select("id, nazwa, liczba, cena, koszt, kategoria(id, nazwa)"))
        k_res = safe_execute(lambda: supabase.table("kategoria").select("id, nazwa"))
        h_res = safe_execute(lambda: supabase.table("historia").select("*").order("created_at", desc=True).limit(50))
        p_raw, k_raw, h_raw = p_res.data or [], k_res.data or [], h_res.data or []
        k_map = {k['nazwa']: int(k['id']) for k in k_raw}
    except Exception as e: st.error(f"Dane: {e}")

# --- 5. PRZETWARZANIE ---
df = pd.DataFrame(p_raw) if p_raw else pd.DataFrame()
if not df.empty:
    df["Kategoria"] = df["kategoria"].apply(lambda x: x["nazwa"] if x else "Brak")
    df = df.rename(columns={"nazwa": "Produkt", "liczba": "Ilość", "cena": "Sprzedaż", "koszt": "Zakup", "id": "ID"})
    df["Wartość"] = df["Ilość"] * df["Sprzedaż"]
    df["Koszt"] = df["Ilość"] * df["Zakup"]
    df["Zysk"] = df["Wartość"] - df["Koszt"]
    df["Marża %"] = ((df["Sprzedaż"] - df["Zakup"]) / df["Sprzedaż"] * 100).fillna(0)

df_h = pd.DataFrame([
    {"Data": i["created_at"][:16].replace("T", " "), "Produkt": i["produkt"], "Typ": i["typ"], "Ilość": i["ilosc"]}
    for i in h_raw
]) if h_raw else pd.DataFrame()

# --- 6. INTERFEJS ---
st.title("📦 Magazyn Pro v5.1")
t1, t_an, t2, t3 = st.tabs(["📊 Stan", "📈 Analiza", "🛠️ Operacje", "📜 Historia"])

with t1:
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Wycena", f"{df['Wartość'].sum():,.2f} zł")
        c2.metric("Inwestycja", f"{df['Koszt'].sum():,.2f} zł")
        c3.metric("Zysk", f"{df['Zysk'].sum():,.2f} zł", f"{df['Marża %'].mean():.1f}%")
        c4.metric("SKU", len(df))
        st.dataframe(df[["Produkt", "Kategoria", "Ilość", "Zakup", "Sprzedaż", "Marża %"]], use_container_width=True, hide_index=True)
    else: st.info("Magazyn jest pusty.")

with t_an:
    if not df.empty:
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            st.plotly_chart(px.pie(df, values='Wartość', names='Kategoria', title='Udział Kategorii', hole=.4), use_container_width=True)
        with col_a2:
            st.plotly_chart(px.bar(df.nlargest(5, 'Zysk'), x='Produkt', y='Zysk', title='Top 5 - Najbardziej Dochodowe', color='Zysk'), use_container_width=True)
        st.plotly_chart(px.scatter(df, x="Ilość", y="Sprzedaż", size="Wartość", color="Kategoria", hover_name="Produkt", title="Mapa Kapitału"), use_container_width=True)
    else: st.info("Brak danych do analizy.")

with t2:
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Ruch towaru")
        if not df.empty:
            with st.container(border=True):
                target_p = st.selectbox("Produkt", df["Produkt"].tolist())
                qty = st.number_input("Ilość", min_value=1)
                p_row = df[df["Produkt"] == target_p].iloc[0]
                b1, b2 = st.columns(2)
                if b1.button("📥 PRZYJMIJ", use_container_width=True, type="primary"):
                    safe_execute(lambda: supabase.table("produkty").update({"liczba": int(p_row["Ilość"]) + qty}).eq("id", p_row["ID"]))
                    log_history(target_p, "Przyjęcie", qty); st.rerun()
                if b2.button("📤 WYDAJ", use_container_width=True):
                    if p_row["Ilość"] >= qty:
                        safe_execute(lambda: supabase.table("produkty").update({"liczba": int(p_row["Ilość"]) - qty}).eq("id", p_row["ID"]))
                        log_history(target_p, "Wydanie", qty); st.rerun()
                    else: st.error("Mało towaru!")
        else: st.warning("Dodaj najpierw produkty.")

    with col_r:
        st.subheader("Baza")
        with st.container(border=True):
            it1, it2 = st.tabs(["🎁 Produkty", "📂 Kategorie"])
            with it1:
                with st.expander("➕ Dodaj nowy", expanded=True):
                    n_n = st.text_input("Nazwa")
                    n_k = st.selectbox("Kategoria", list(k_map.keys()) if k_map else ["Brak"])
                    c_p1, c_p2 = st.columns(2)
                    n_zak = c_p1.number_input("Cena Zakupu", min_value=0.0)
                    n_spr = c_p2.number_input("Cena Sprzedaży", min_value=0.0)
                    if st.button("Zapisz", use_container_width=True):
                        if n_k == "Brak": st.error("Dodaj kategorię!")
                        elif not n_n: st.warning("Podaj nazwę.")
                        elif not df.empty and n_n.lower() in df["Produkt"].str.lower().values: st.error("Już jest!")
                        else:
                            new_id = get_lowest_free_id("produkty")
                            safe_execute(lambda: supabase.table("produkty").insert({"id": new_id, "nazwa": n_n, "kategoria_id": k_map[n_k], "liczba": 0, "cena": n_spr, "koszt": n_zak}))
                            log_history(n_n, "Nowy", 0); st.rerun()
                if not df.empty:
                    with st.expander("✏️ Edytuj / 🗑️ Usuń"):
                        e_p = st.selectbox("Wybierz", df["Produkt"].tolist())
                        e_row = df[df["Produkt"] == e_p].iloc[0]
                        new_name = st.text_input("Nowa nazwa", value=e_p)
                        cb1, cb2 = st.columns(2)
                        if cb1.button("Zmień"):
                            safe_execute(lambda: supabase.table("produkty").update({"nazwa": new_name}).eq("id", e_row["ID"]))
                            st.rerun()
                        if cb2.button("USUŃ", type="primary"):
                            safe_execute(lambda: supabase.table("produkty").delete().eq("id", e_row["ID"]))
                            st.rerun()
            with it2:
                n_kat_name = st.text_input("Nazwa kategorii")
                if st.button("Utwórz"):
                    if n_kat_name and n_kat_name not in k_map:
                        safe_execute(lambda: supabase.table("kategoria").insert({"id": get_lowest_free_id("kategoria"), "nazwa": n_kat_name}))
                        st.rerun()
                if k_map:
                    d_k = st.selectbox("Usuń", list(k_map.keys()))
                    if st.button("USUŃ KASKADOWO"):
                        kid = k_map[d_k]
                        safe_execute(lambda: supabase.table("produkty").delete().eq("kategoria_id", kid))
                        safe_execute(lambda: supabase.table("kategoria").delete().eq("id", kid))
                        st.rerun()

with t3:
    if not df_h.empty:
        st.dataframe(df_h, use_container_width=True, hide_index=True)
        rep = generate_txt(df_h)
        st.download_button("📄 Raport TXT", rep, "raport.txt", use_container_width=True)
        if st.button("🗑️ Czyść Historię", use_container_width=True, type="secondary"):
            safe_execute(lambda: supabase.table("historia").delete().gt("id", -1))
            st.rerun()
