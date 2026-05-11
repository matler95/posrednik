"""
WREI Dashboard v2 — Streamlit z mapą, wykresami RCN i kartami okazji.
Uruchomienie: streamlit run dashboard/app.py
"""
import os
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="WREI — Real Estate Intelligence",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0f1117; }
[data-testid="stSidebar"] { background: #1a1d2e; }
.score-badge {
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    font-weight: bold; font-size: 14px; margin-bottom: 6px;
}
.score-high  { background: #1a472a; color: #51cf66; }
.score-med   { background: #3d2c00; color: #ffd43b; }
.score-low   { background: #3d1515; color: #ff6b6b; }
.card {
    background: #1e2130; border-radius: 12px; padding: 16px; margin-bottom: 12px;
    border: 1px solid #2d3250;
}
.rcn-tag { color: #74c0fc; font-size: 12px; }
.gap-pos  { color: #51cf66; }
.gap-neg  { color: #ff6b6b; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_listings(limit=200, min_score=None, portal=None, district=None, direct_only=False):
    params = {"limit": limit}
    if min_score:   params["min_score"] = min_score
    if portal:      params["portal"] = portal
    if district:    params["district"] = district
    if direct_only: params["direct_only"] = "true"
    try:
        r = requests.get(f"{BACKEND}/listings", params=params, timeout=10)
        return r.json().get("listings", [])
    except Exception:
        return []


@st.cache_data(ttl=600)
def fetch_market_trend(city_slug="warszawa", district=None):
    params = {"city_slug": city_slug}
    if district: params["district"] = district
    try:
        r = requests.get(f"{BACKEND}/market/trend", params=params, timeout=10)
        return r.json()
    except Exception:
        return {}


@st.cache_data(ttl=60)
def fetch_rcn_benchmark(city_slug="warszawa", district=None, rooms=None):
    params = {"city_slug": city_slug}
    if district: params["district"] = district
    if rooms:    params["rooms"] = rooms
    try:
        r = requests.get(f"{BACKEND}/market/rcn-benchmark", params=params, timeout=5)
        return r.json().get("benchmark_sqm")
    except Exception:
        return None


def score_badge(score: float) -> str:
    pct = round(score * 100)
    cls = "score-high" if score >= 0.25 else ("score-med" if score >= 0.15 else "score-low")
    return f'<span class="score-badge {cls}">⭐ {pct}%</span>'


def score_bar(score: float) -> str:
    filled = round(score * 10)
    return "█" * filled + "░" * (10 - filled)


# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("🏠 WREI")
    st.caption("Real Estate Intelligence")
    st.divider()

    city_slug = st.selectbox("Miasto", ["warszawa", "krakow", "wroclaw", "poznan", "gdansk"],
                              index=0, format_func=str.title)
    
    st.subheader("Filtry Ofert")
    min_score = st.slider("Min. Score", 0.0, 1.0, 0.10, 0.05)
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        f_min_price = st.number_input("Cena od (k)", value=0, step=50) * 1000
    with col_p2:
        f_max_price = st.number_input("Cena do (k)", value=5000, step=50) * 1000
        
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        f_min_area = st.number_input("Metraż od", value=0, step=5)
    with col_a2:
        f_max_area = st.number_input("Metraż do", value=200, step=5)

    direct_only = st.toggle("Tylko bezpośrednie", value=False)
    show_limit = st.slider("Liczba ofert", 10, 500, 100, 10)

    st.divider()
    page = st.radio("Widok", ["📊 Trendy RCN", "🏆 Okazje", "🗺️ Mapa", "🔔 Alerty"])

    st.divider()
    if st.button("🔄 Odśwież dane", use_container_width=True):
        st.cache_data.clear()

    if st.button("🕷️ Uruchom crawl", use_container_width=True):
        try:
            r = requests.post(f"{BACKEND}/run-crawl?portals=otodom,olx&pages=2", timeout=30)
            st.success(f"Zapisano {r.json().get('saved', 0)} ofert")
        except Exception as e:
            st.error(str(e))

    if st.button("📥 Załaduj dane RCN (30 dni)", use_container_width=True):
        try:
            requests.post(f"{BACKEND}/market/ingest?city_slug={city_slug}&days=30", timeout=5)
            st.info("Pobieranie RCN w tle...")
        except Exception as e:
            st.error(str(e))


# ─────────────────────────────────────────────
# Strona: Trendy RCN
# ─────────────────────────────────────────────
if page == "📊 Trendy RCN":
    st.title("📊 Trendy Rynkowe — Dane Transakcyjne (RCN)")

    trend_data = fetch_market_trend(city_slug)
    quarterly = trend_data.get("quarterly_trend", [])
    cagr = trend_data.get("cagr_5y")
    gap = trend_data.get("offer_vs_transaction_gap")

    # KPI row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("CAGR 5Y", f"{cagr*100:.1f}%/rok" if cagr else "brak danych",
                  delta="wzrost" if (cagr or 0) > 0.05 else None)
    with col2:
        rcn_bench = fetch_rcn_benchmark(city_slug)
        st.metric("Mediana RCN", f"{rcn_bench:,.0f} PLN/m²" if rcn_bench else "brak", help="Z ostatnich 2 kwartałów")
    with col3:
        if gap is not None:
            st.metric("Ofertowe vs RCN", f"+{gap*100:.1f}%" if gap > 0 else f"{gap*100:.1f}%",
                      help="Ile % droższe są oferty od realnych transakcji")
        else:
            st.metric("Ofertowe vs RCN", "brak danych")
    with col4:
        listings_count = len(fetch_listings(limit=1, min_score=0))
        st.metric("Ofert w DB", listings_count)

    # Trend chart
    if quarterly:
        df_q = pd.DataFrame(quarterly)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_q["label"], y=df_q["median_sqm"],
            mode="lines+markers",
            name="Mediana transakcyjna (PLN/m²)",
            line=dict(color="#74c0fc", width=3),
            marker=dict(size=8),
            hovertemplate="%{x}<br>%{y:,.0f} PLN/m²<extra></extra>",
        ))
        fig.update_layout(
            title="Mediana ceny transakcyjnej per kwartał (RCN)",
            xaxis_title="Kwartał", yaxis_title="PLN/m²",
            plot_bgcolor="#1e2130", paper_bgcolor="#1e2130",
            font=dict(color="white"),
            yaxis=dict(tickformat=","),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Tabela
        with st.expander("Dane kwartalne"):
            st.dataframe(df_q[["label", "median_sqm", "count"]].rename(columns={
                "label": "Kwartał", "median_sqm": "Mediana PLN/m²", "count": "Transakcji"
            }), use_container_width=True)
    else:
        st.info("Brak danych RCN. Kliknij '📥 Załaduj dane RCN' w sidebarze.")


# ─────────────────────────────────────────────
# Strona: Okazje
# ─────────────────────────────────────────────
elif page == "🏆 Okazje":
    st.title("🏆 Okazje Inwestycyjne")

    listings = fetch_listings(
        limit=show_limit, min_score=min_score, direct_only=direct_only,
        min_price=f_min_price, max_price=f_max_price,
        min_area=f_min_area, max_area=f_max_area
    )
    if not listings:
        st.warning("Brak ofert. Uruchom crawl lub obniż próg score.")
        st.stop()

    df = pd.DataFrame(listings)
    df["score"] = df["score"].fillna(0)
    df_sorted = df.sort_values("score", ascending=False)

    # Histogram
    col1, col2 = st.columns([2, 1])
    with col1:
        fig_hist = px.histogram(df_sorted, x="score", nbins=20, color_discrete_sequence=["#74c0fc"],
                                title="Rozkład Score", labels={"score": "Score"})
        fig_hist.update_layout(plot_bgcolor="#1e2130", paper_bgcolor="#1e2130",
                                font=dict(color="white"), showlegend=False)
        st.plotly_chart(fig_hist, use_container_width=True)

    with col2:
        st.metric("Łącznie ofert", len(df_sorted))
        st.metric("Śr. Score", f"{df_sorted['score'].mean()*100:.1f}%")
        if "price_per_m2" in df_sorted.columns:
            st.metric("Śr. cena/m²", f"{df_sorted['price_per_m2'].mean():,.0f} PLN")
        if "rcn_benchmark" in df_sorted.columns:
            rcn_vals = df_sorted["rcn_benchmark"].dropna()
            if not rcn_vals.empty:
                st.metric("Mediana RCN (oferty)", f"{rcn_vals.mean():,.0f} PLN/m²")

    # Scatter: cena vs score
    if "price_per_m2" in df_sorted.columns and "district" in df_sorted.columns:
        fig_sc = px.scatter(
            df_sorted.dropna(subset=["price_per_m2", "score"]),
            x="price_per_m2", y="score",
            color="district", size="area",
            hover_data=["title", "price", "rooms", "portal"],
            title="Cena/m² vs Score (wielkość = metraż)",
            labels={"price_per_m2": "PLN/m²", "score": "Score"},
            color_discrete_sequence=px.colors.qualitative.Plotly,
        )
        fig_sc.update_layout(plot_bgcolor="#1e2130", paper_bgcolor="#1e2130",
                             font=dict(color="white"))
        st.plotly_chart(fig_sc, use_container_width=True)

    # Karty okazji
    st.subheader(f"Top {min(10, len(df_sorted))} okazji")
    for _, row in df_sorted.head(10).iterrows():
        score = row.get("score", 0)
        rcn = row.get("rcn_benchmark")
        txn_gap = row.get("transaction_gap") or 0
        cagr = row.get("cagr_5y")

        gap_html = ""
        if rcn:
            gap_pct = abs(txn_gap * 100)
            gap_cls = "gap-pos" if txn_gap > 0 else "gap-neg"
            gap_sign = "taniej" if txn_gap > 0 else "drożej"
            gap_html = f'<span class="rcn-tag">RCN: {rcn:,.0f} PLN/m² </span><span class="{gap_cls}">({gap_pct:.1f}% {gap_sign})</span>'

        cagr_html = f'<br><span class="rcn-tag">📈 CAGR 5Y: {cagr*100:.1f}%/rok</span>' if cagr else ""

        llm = row.get("llm_analysis") or {}
        vision = row.get("photo_analysis") or {}
        summary = llm.get("summary", "") if isinstance(llm, dict) else ""
        
        # Elementy Vision
        photo_score = vision.get("photo_score")
        condition = vision.get("condition", "nieznany")
        pos_feat = vision.get("positive_features", [])
        neg_feat = vision.get("negative_features", [])

        condition_map = {
            "new": "✨ Nowe/Idealne", "good": "✅ Dobry stan", 
            "average": "🟡 Średni/Odświeżenie", "renovation_needed": "🛠️ Do remontu"
        }
        cond_label = condition_map.get(condition, "❓ Stan nieznany")

        st.markdown(f"""
<div class="card">
{score_badge(score)} {'🔒 Bezpośrednia' if row.get('direct_offer') else ''}
<span style="float:right; font-size:12px; color:#adb5bd">{cond_label}</span><br>
<b><a href="{row.get('url','#')}" target="_blank" style="color:#74c0fc">{row.get('title','?')[:70]}</a></b><br>
📍 {row.get('district','?')} | {row.get('portal','?').upper()} | {row.get('area','?')} m² | {row.get('rooms','?')} pok.<br>
💰 <b>{row.get('price', 0):,} PLN</b> ({row.get('price_per_m2', 0):,.0f} PLN/m²)
{f'<br>{gap_html}{cagr_html}' if gap_html else ''}
{f'<br><i style="color:#adb5bd">{summary[:300]}</i>' if summary else ''}
{''.join([f'<span style="background:#1a472a; color:#51cf66; padding:2px 6px; border-radius:4px; font-size:10px; margin-right:4px;">+ {f}</span>' for f in pos_feat])}
{''.join([f'<span style="background:#3d1515; color:#ff6b6b; padding:2px 6px; border-radius:4px; font-size:10px; margin-right:4px;">- {f}</span>' for f in neg_feat])}
<br><small style="color:#868e96">{score_bar(score)} Score: {round(score*100)}% {f'| Photo Quality: {round(photo_score*100)}%' if photo_score else ''}</small>
</div>
""", unsafe_allow_html=True)



# ─────────────────────────────────────────────
# Strona: Mapa
# ─────────────────────────────────────────────
elif page == "🗺️ Mapa":
    st.title("🗺️ Mapa Ofert")
    try:
        import folium
        from streamlit_folium import st_folium

        listings = fetch_listings(
            limit=show_limit, min_score=min_score,
            min_price=f_min_price, max_price=f_max_price,
            min_area=f_min_area, max_area=f_max_area
        )
        df = pd.DataFrame(listings)

        # Punkty z koordynatami (jeśli geocoder je dostarczył)
        if "lat" not in df.columns or df["lat"].isna().all():
            st.info("Brak danych geograficznych. Geocoder przypisuje dzielnice asynchronicznie — sprawdź ponownie za chwilę.")
            # Fallback: centrum Warszawy per dzielnica
            DISTRICT_COORDS = {
                "Śródmieście": (52.2297, 21.0122), "Mokotów": (52.1945, 21.0273),
                "Wola": (52.2382, 20.9785), "Praga Południe": (52.2395, 21.0621),
                "Ursynów": (52.1452, 21.0333), "Wilanów": (52.1609, 21.0881),
                "Bielany": (52.2976, 20.9632), "Bemowo": (52.2603, 20.9078),
                "Białołęka": (52.3380, 21.0508), "Targówek": (52.2763, 21.0611),
            }
            df["lat"] = df["district"].map(lambda d: DISTRICT_COORDS.get(d, (52.23, 21.01))[0])
            df["lon"] = df["district"].map(lambda d: DISTRICT_COORDS.get(d, (52.23, 21.01))[1])
        else:
            df = df.rename(columns={"lng": "lon"})

        df = df.dropna(subset=["lat", "lon"])
        if df.empty:
            st.warning("Brak ofert do wyświetlenia na mapie.")
            st.stop()

        m = folium.Map(location=[52.23, 21.01], zoom_start=12,
                       tiles="CartoDB dark_matter")

        for _, row in df.iterrows():
            score = row.get("score") or 0
            color = "#51cf66" if score >= 0.25 else ("#ffd43b" if score >= 0.15 else "#ff6b6b")
            popup_text = (
                f"<b>{row.get('title','?')[:60]}</b><br>"
                f"💰 {row.get('price',0):,} PLN | {row.get('price_per_m2',0):,.0f} PLN/m²<br>"
                f"⭐ Score: {round(score*100)}%<br>"
                f'<a href="{row.get("url","#")}" target="_blank">→ Otwórz</a>'
            )
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=8 + score * 10,
                color=color, fill=True, fill_color=color, fill_opacity=0.8,
                popup=folium.Popup(popup_text, max_width=300),
                tooltip=f"Score: {round(score*100)}%",
            ).add_to(m)

        st_folium(m, use_container_width=True, height=600)

    except ImportError:
        st.error("Zainstaluj: `pip install folium streamlit-folium`")


# ─────────────────────────────────────────────
# Strona: Alerty
# ─────────────────────────────────────────────
elif page == "🔔 Alerty":
    st.title("🔔 Zarządzanie Alertami")

    try:
        from backend.alerts.evaluator import get_watchlist_alerts
        alerts = get_watchlist_alerts()

        if alerts:
            st.subheader(f"Aktywne alerty ({len(alerts)})")
            for a in alerts:
                with st.expander(f"{'🟢' if a['active'] else '🔴'} {a['name']}"):
                    st.code(a.get("condition_expr") or "(brak warunku)", language="python")
                    st.caption(f"Min. score: {a.get('min_score', 0.15)} | Miasto: {a.get('city_slug', 'warszawa')}")
        else:
            st.info("Brak alertów. Dodaj przez API lub bezpośrednio do tabeli `watchlist` w DB.")

        st.divider()
        st.subheader("Przykładowe warunki alertów")
        examples = {
            "Okazja Mokotów": "score > 0.25 and district == 'Mokotów'",
            "RCN poniżej rynku": "transaction_gap > 0.10",
            "Bezpośrednia + tania": "direct_offer == True and price_per_m2 < 13000",
            "Rynek rosnący": "cagr_5y > 0.07 and score > 0.20",
        }
        for name, expr in examples.items():
            st.code(f"# {name}\n{expr}", language="python")

    except Exception as e:
        st.error(f"Błąd połączenia z backendem: {e}")
        st.info("Upewnij się że `docker-compose up -d` jest uruchomiony.")
