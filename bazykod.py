import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px

# --- 1. KONFIGURACJA STRONY ---
st.set_page_config(
    page_title="System Magazynowy Pro",
    page_icon="📦",
    layout="wide"
)

# --- 2. POŁĄCZENIE Z SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("Błąd połączenia z Supabase. Sprawdź secrets!")
        return None

supabase = init_connection()

# --- 3. STYLIZACJA CSS ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 28px; color: #1f77b4; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #f0f2f6;
        border-radius: 5px 5px 0px 0px;
        padding: 10px 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 4. FUNKCJE POBIERANIA DANYCH ---
def get_data():
    # Pobieramy produkty wraz z ich kategoriami (join)
    res = supabase.table("produkty").select("id, nazwa, liczba, cena, kategoria(nazwa)").execute()
    k_res = supabase.table("kategoria").select("id, nazwa").execute()
    return res.data, k_res.data

data, raw_categories = get_data()

# Tworzenie mapowania nazw kategorii na ich ID dla formularzy
k_map = {k['nazwa']: k['id'] for k in raw_categories} if raw_categories else {}

# --- 5. SIDEBAR (FILTRY I EKSPORT) ---
st.sidebar.title("🔍 Nawigacja i Filtry")
search_query = st.sidebar.text_input("Szukaj produktu...", placeholder="Wpisz nazwę...")
category_filter = st.sidebar.multiselect("Filtruj wg kategorii", options=list(k_map.keys()))

# --- 6. PRZYGOTOWANIE DANYCH DO WYŚWIETLENIA ---
if data:
    df = pd.DataFrame([
        {
            "ID": i["id"],
            "Produkt": i["nazwa"],
            "Kategoria": i.get("kategoria", {}).get("nazwa") if i.get("kategoria") else "Brak",
            "Ilość": i["liczba"],
            "Cena": i["cena"],
            "Wartość": i["liczba"] * i["cena"]
        } for i in data
    ])
    
    # Aplikowanie filtrów z Sidebaru
    if search_query:
        df = df[df["Produkt"].str.contains(search_query, case=False)]
    if category_filter:
        df = df[df["Kategoria"].isin(category_filter)]
else:
    df = pd.DataFrame(columns=["ID", "Produkt", "Kategoria", "Ilość", "Cena", "Wartość"])

# --- 7. PANEL GŁÓWNY - KPI ---
st.title("📦 ProMagazyn 3000")

if not df.empty:
    m1, m2, m3, m4 = st.columns(4)
    total_val = df["Wartość"].sum()
    low_stock_df = df[df["Ilość"] < 5]
    
    m1.metric("Liczba SKU", len(df))
    m2.metric("Suma sztuk", int(df["Ilość"].sum()))
    m3.metric("Wartość ogółem", f"{total_val:,.2f} zł")
    m4.metric("Niskie stany", len(low_stock_df), delta=-len(low_stock_df) if len(low_stock_df) > 0 else 0, delta_color="inverse")

    st.markdown("---")

    # --- 8. WIZUALIZACJA I TABELA ---
    col_table, col_viz = st.columns([2, 1])

    with col_table:
        st.subheader("📋 Aktualny Stan")
        st.dataframe(
            df[["Produkt", "Kategoria", "Ilość", "Cena"]],
            column_config={
                "Ilość": st.column_config.ProgressColumn("Stan", min_value=0, max_value=100, format="%d"),
                "Cena": st.column_config.NumberColumn("Cena (zł)", format="%.2f")
            },
            hide_index=True,
            use_container_width=True
        )
        
        # Przycisk eksportu pod tabelą
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Pobierz raport CSV", data=csv, file_name="magazyn.csv", mime="text/csv")

    with col_viz:
        st.subheader("📊 Finanse")
        fig = px.pie(df, names='Kategoria', values='Wartość', hole=0.4, title="Wartość wg kategorii")
        fig.update_layout(margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)

else:
    st.warning("Brak danych do wyświetlenia. Dodaj produkty w panelu poniżej.")

st.markdown("---")

# --- 9. PANEL OPERACYJNY (ZAKŁADKI) ---
st.header("🛠️ Zarządzanie")
t1, t2, t3 = st.tabs(["✨ Dodaj Nowe", "📤 Wydaj / 📥 Przyjmij", "🗑️ Usuwanie"])

with t1:
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.subheader("Nowy Produkt")
            new_p_name = st.text_input("Nazwa")
            new_p_kat = st.selectbox("Kategoria", options=list(k_map.keys()))
            new_p_qty = st.number_input("Ilość startowa", min_value=0)
            new_p_price = st.number_input("Cena", min_value=0.0)
            if st.button("Zapisz produkt", type="primary"):
                if new_p_name:
                    supabase.table("produkty").insert({
                        "nazwa": new_p_name, "kategoria_id": k_map[new_p_kat],
                        "liczba": new_p_qty, "cena": new_p_price
                    }).execute()
                    st.toast(f"Dodano: {new_p_name}")
                    st.rerun()
    with c2:
        with st.container(border=True):
            st.subheader("Nowa Kategoria")
            new_k_name = st.text_input("Nazwa kategorii")
            if st.button("Utwórz kategorię"):
                if new_k_name:
                    supabase.table("kategoria").insert({"nazwa": new_k_name}).execute()
                    st.toast("Kategoria utworzona")
                    st.rerun()

with t2:
    if not df.empty:
        with st.container(border=True):
            target_p = st.selectbox("Wybierz towar", options=df["Produkt"].tolist())
            change_qty = st.number_input("Liczba sztuk", min_value=1, step=1)
            
            p_data = df[df["Produkt"] == target_p].iloc[0]
            
            b1, b2 = st.columns(2)
            with b1:
                if st.button("📥 PRZYJMIJ DOSTAWĘ", use_container_width=True):
                    new_val = p_data["Ilość"] + change_qty
                    supabase.table("produkty").update({"liczba": new_val}).eq("id", p_data["ID"]).execute()
                    st.toast(f"Przyjęto {change_qty} szt.")
                    st.rerun()
            with b2:
                if st.button("📤 WYDAJ TOWAR", use_container_width=True):
                    if p_data["Ilość"] >= change_qty:
                        new_val = p_data["Ilość"] - change_qty
                        supabase.table("produkty").update({"liczba": new_val}).eq("id", p_data["ID"]).execute()
                        st.toast(f"Wydano {change_qty} szt.")
                        st.rerun()
                    else:
                        st.error("Brak wystarczającej ilości na stanie!")

with t3:
    col_del_p, col_del_k = st.columns(2)
    with col_del_p:
        p_del = st.selectbox("Usuń produkt", options=["-- wybierz --"] + df["Produkt"].tolist() if not df.empty else ["Brak"])
        if st.button("POTWIERDŹ USUNIĘCIE PRODUKTU", type="primary"):
            if p_del != "-- wybierz --":
                id_to_del = df[df["Produkt"] == p_del]["ID"].values[0]
                supabase.table("produkty").delete().eq("id", id_to_del).execute()
                st.rerun()

    with col_del_k:
        k_del = st.selectbox("Usuń kategorię", options=["-- wybierz --"] + list(k_map.keys()) if k_map else ["Brak"])
        if st.button("USUŃ KATEGORIĘ"):
            if k_del != "-- wybierz --":
                try:
                    supabase.table("kategoria").delete().eq("id", k_map[k_del]).execute()
                    st.rerun()
                except:
                    st.error("Błąd: Kategoria prawdopodobnie nie jest pusta!")
