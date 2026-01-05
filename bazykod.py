import streamlit as st
from supabase import create_client, Client

# Inicjalizacja połączenia z Supabase
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

st.title("📦 Zarządzanie Produktami")

# --- SEKCJA: DODAWANIE KATEGORII ---
st.header("Dodaj Nową Kategorię")
with st.form("category_form", clear_on_submit=True):
    category_name = st.text_input("Nazwa kategorii")
    submit_category = st.form_submit_button("Zapisz kategorię")
    
    if submit_category and category_name:
        data = supabase.table("categories").insert({"name": category_name}).execute()
        st.success(f"Dodano kategorię: {category_name}")

# --- SEKCJA: DODAWANIE PRODUKTU ---
st.divider()
st.header("Dodaj Nowy Produkt")

# Pobieranie listy kategorii do rozwijanego menu
def get_categories():
    response = supabase.table("categories").select("id, name").execute()
    return response.data

categories = get_categories()
category_options = {cat['name']: cat['id'] for cat in categories}

with st.form("product_form", clear_on_submit=True):
    product_name = st.text_input("Nazwa produktu")
    price = st.number_input("Cena", min_value=0.0, format="%.2f")
    selected_cat_name = st.selectbox("Wybierz kategorię", options=list(category_options.keys()))
    
    submit_product = st.form_submit_button("Dodaj produkt")
    
    if submit_product and product_name:
        product_data = {
            "name": product_name,
            "price": price,
            "category_id": category_options[selected_cat_name]
        }
        supabase.table("products").insert(product_data).execute()
        st.success(f"Produkt '{product_name}' został dodany!")

# --- PODGLĄD DANYCH ---
st.divider()
if st.checkbox("Pokaż listę produktów"):
    products = supabase.table("products").select("name, price, categories(name)").execute()
    st.table(products.data)
