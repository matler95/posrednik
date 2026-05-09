import os
import streamlit as st
import pandas as pd
import requests

BACKEND_URL = os.getenv("WREI_BACKEND_URL", "http://backend:8000")

st.set_page_config(
    page_title="WREI Warszawa",
    page_icon="🏙️",
    layout="wide",
)

st.title("WREI Warszawa — wyszukiwanie i analiza okazji nieruchomości")
st.write(
    "Aplikacja analizująca bezpośrednie oferty sprzedaży w Warszawie i znajdująca prawdziwe okazje cenowe. Użyj Otodom jako źródła danych." 
)

service = st.selectbox("Serwis wyszukiwania", ["Otodom"])
query_url = st.text_input("Wklej adres wyszukiwania Otodom dla Warszawy", "")

portals = st.multiselect("Portale", ["Otodom"], default=["Otodom"])
pages = st.number_input("Liczba stron do przeszukania na portalu", min_value=1, max_value=10, value=1, step=1)

col1, col2, col3 = st.columns(3)
with col1:
    min_price = st.number_input("Minimalna cena (PLN)", min_value=0, value=0, step=50000)
    max_price = st.number_input("Maksymalna cena (PLN)", min_value=0, value=0, step=50000)
with col2:
    min_area = st.number_input("Minimalny metraż (m²)", min_value=0, value=0, step=5)
    max_area = st.number_input("Maksymalny metraż (m²)", min_value=0, value=0, step=5)
with col3:
    rooms = st.text_input("Liczba pokoi", "")
    direct_only = st.checkbox("Tylko bezpośrednie oferty (bez biur nieruchomości)", value=False)
    threshold = st.slider("Minimalna okazja (%)", min_value=0, max_value=50, value=15)

search_button = st.button("Szukaj i analizuj")
crawl_button = st.button("Uruchom crawl teraz")

params = {
    "query_url": query_url or None,
    "portals": ",".join([p.lower() for p in portals]),
    "pages": pages,
    "min_price": min_price or None,
    "max_price": max_price or None,
    "min_area": min_area or None,
    "max_area": max_area or None,
    "rooms": rooms or None,
    "direct_only": direct_only,
    "threshold": threshold / 100.0,
}

if search_button:
    response = requests.get(f"{BACKEND_URL}/search", params=params, timeout=60)
    if response.status_code != 200:
        st.error(f"Błąd backendu: {response.status_code} - {response.text}")
    else:
        data = response.json()
        listings = data.get("listings", [])
        opportunities = data.get("opportunities", [])

        st.metric("Znalezione oferty", len(listings))
        st.metric("Okazje", len(opportunities))

        if opportunities:
            st.subheader("Najważniejsze okazje")
            top = pd.DataFrame(opportunities)
            top = top[[
                "title",
                "district",
                "rooms",
                "area",
                "price",
                "price_per_m2",
                "price_gap_pct",
                "market_position",
                "direct_offer",
                "keywords",
                "estimated_value",
                "score",
                "url",
            ]]
            top["keywords"] = top["keywords"].apply(lambda k: ", ".join(k) if isinstance(k, list) else k)
            top["link"] = top["url"].apply(lambda u: f'<a href="{u}" target="_blank">otwórz</a>')
            st.write(top.to_html(escape=False, index=False), unsafe_allow_html=True)
            st.bar_chart(top.set_index("title")["score"])

        if listings:
            st.subheader("Wszystkie oferty")
            df = pd.DataFrame(listings)
            df["keywords"] = df["keywords"].apply(lambda k: ", ".join(k) if isinstance(k, list) else k)
            df["link"] = df["url"].apply(lambda u: f'<a href="{u}" target="_blank">otwórz</a>')
            st.write(df[[
                "title",
                "district",
                "rooms",
                "area",
                "price",
                "price_per_m2",
                "price_gap_pct",
                "market_position",
                "direct_offer",
                "keywords",
                "estimated_value",
                "score",
                "link",
            ]].to_html(escape=False, index=False), unsafe_allow_html=True)
        else:
            st.warning("Brak wyników. Sprawdź parametry wyszukiwania lub adres URL Otodom.")

if crawl_button:
    crawl_params = {
        "query_url": query_url or None,
        "portals": ",".join([p.lower() for p in portals]),
        "pages": pages,
        "min_price": min_price or None,
        "max_price": max_price or None,
        "min_area": min_area or None,
        "max_area": max_area or None,
        "rooms": rooms or None,
        "direct_only": direct_only,
    }
    crawl_response = requests.post(f"{BACKEND_URL}/run-crawl", params=crawl_params, timeout=120)
    if crawl_response.status_code != 200:
        st.error(f"Błąd crawlowania: {crawl_response.status_code} - {crawl_response.text}")
    else:
        result = crawl_response.json()
        st.success(f"Crawl zakończony, zapisano {result.get('saved', 0)} ofert.")
        st.json(result)

with st.expander("Jak korzystać"):
    st.markdown(
        """
        - Wklej adres wyszukiwania z Otodom dla Warszawy lub pozostaw pole puste i użyj filtrów.
        - Podaj zakres cen i metrażu oraz opcjonalnie liczbę pokoi.
        - Aplikacja pobierze oferty i porówna cenę z rynkowym metrem kwadratowym.
        - Oferty z najwyższym wynikiem `score` to potencjalne okazje cenowe.
        """
    )
