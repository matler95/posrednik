# dashboard/app.py

import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import time

# Konfiguracja strony
st.set_page_config(page_title="WREI Hunter | Snajper Inwestycyjny", layout="wide", page_icon="🎯")

# --- CSS dla Premium Look ---
st.markdown("""
    <style>
    .stApp { background-color: #0f1116; color: #e0e0e0; }
    
    .stButton>button { 
        background: linear-gradient(90deg, #ff4b2b 0%, #ff416c 100%); 
        color: white; border: none; font-weight: bold; border-radius: 8px;
    }

    /* Klasy dla danych */
    .metric-box {
        background: #232730;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        border: 1px solid #3d424d;
    }
    .metric-val-green { color: #2ecc71; font-weight: 800; font-size: 1.8rem; }
    .metric-val-red { color: #e74c3c; font-weight: 800; font-size: 1.8rem; }
    .metric-label { color: #888; font-size: 0.75rem; text-transform: uppercase; }
    
    .ai-box {
        background: #161920;
        padding: 15px;
        border-radius: 10px;
        border-left: 4px solid #ff4b2b;
        margin-top: 10px;
    }
    </style>
""", unsafe_allow_html=True)

BACKEND = "http://backend:8000"

# --- INICJALIZACJA DANYCH ---
def get_saved_config():
    try:
        return requests.get(f"{BACKEND}/get-hunt-config", timeout=1).json()
    except:
        return {"max_price": 430000, "max_area": 45, "city_slug": "warszawa"}

if "saved_cfg" not in st.session_state:
    st.session_state.saved_cfg = get_saved_config()

def fetch_listings(**params):
    try:
        r = requests.get(f"{BACKEND}/listings", params=params, timeout=5)
        return r.json().get("listings", [])
    except:
        return []

def run_hunt(params):
    try:
        requests.post(f"{BACKEND}/run-crawl", params=params, timeout=2)
        return True
    except:
        return False

# --- SIDEBAR ---
with st.sidebar:
    if st.button("🔄 ODŚWIEŻ WIDOK", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("<h1 style='text-align: center; color: #ff4b2b;'>🎯 HUNTER</h1>", unsafe_allow_html=True)
    
    city_slug = st.selectbox("Miasto", ["warszawa", "krakow", "wroclaw"], index=0)
    max_price = st.number_input("Cena do (PLN)", value=int(st.session_state.saved_cfg['max_price']), step=10000)
    max_area = st.number_input("Metraż do (m²)", value=int(st.session_state.saved_cfg['max_area']), step=1)
    
    if (max_price != st.session_state.saved_cfg['max_price'] or max_area != st.session_state.saved_cfg['max_area']):
        st.session_state.saved_cfg.update({"max_price": max_price, "max_area": max_area})
        try: requests.post(f"{BACKEND}/set-hunt-config", params=st.session_state.saved_cfg, timeout=1)
        except: pass

    if st.button("🚀 URUCHOM NOWE POLOWANIE", use_container_width=True):
        st.cache_data.clear()
        if run_hunt({"max_price": max_price, "max_area": max_area, "city_slug": city_slug, "pages": 50}):
            st.toast("🔥 Polowanie ruszyło!")
            time.sleep(1); st.rerun()

    st.divider()
    try:
        stats = requests.get(f"{BACKEND}/stats", timeout=1).json()
        st.caption(f"Baza: {stats['total']} | AI Czeka: {stats['pending_llm']}")
    except: pass

# --- MAIN AREA ---
st.title("🏆 Najlepsze Okazje")
st.caption(f"Filtry: {max_price:,.0f} PLN | {max_area} m²")

listings = fetch_listings(max_price=max_price, max_area=max_area, limit=50)

if not listings:
    st.info("Brak ofert. Kliknij 'URUCHOM NOWE POLOWANIE'.")
else:
    for l in listings:
        with st.container(border=True):
            # Nagłówek
            c1, c2 = st.columns([3, 1])
            with c1:
                st.subheader(l['title'])
                st.caption(f"📍 {l['district']} | {l['portal'].upper()}")
            with c2:
                st.markdown(f"<div style='text-align:right'><span style='color:#ff4b2b; font-size:1.5rem; font-weight:800;'>{l['price']:,.0f} PLN</span><br>{l['area']} m²</div>", unsafe_allow_html=True)
            
            # Wskaźniki
            gap = l.get('transaction_gap', 0)
            rcn_b = l.get('rcn_benchmark', 0)
            savings = (rcn_b * l['area']) - l['price'] if rcn_b and l['area'] else 0
            
            m1, m2, m3 = st.columns(3)
            with m1:
                color = "#2ecc71" if gap > 0 else "#e74c3c"
                st.markdown(f"<div class='metric-box'><div class='metric-label'>Luka rynkowa</div><div style='color:{color}; font-weight:800; font-size:1.8rem;'>{gap*100:+.1f}%</div></div>", unsafe_allow_html=True)
            with m2:
                st.markdown(f"<div class='metric-box'><div class='metric-label'>Zysk na starcie</div><div style='color:{color}; font-weight:800; font-size:1.8rem;'>{savings/1000:+.1f}k</div></div>", unsafe_allow_html=True)
            with m3:
                st.markdown(f"<div class='metric-box'><div class='metric-label'>Wycena Inwest.</div><div style='color:#fff; font-weight:800; font-size:1.8rem;'>{(rcn_b*l['area'])/1000:.0f}k</div></div>", unsafe_allow_html=True)
            
            # AI i Link
            with st.container():
                st.markdown("<div class='ai-box'><b>🧠 Rekomendacja AI:</b><br>" + (l.get('llm_analysis', {}).get('summary', 'Analiza w kolejce...') if l.get('llm_analysis') else 'Oczekiwanie na analizę...') + "</div>", unsafe_allow_html=True)
            
            st.markdown(f"<div style='margin-top:10px; display:flex; justify-content:space-between; align-items:center;'><span>⭐ Score: <b>{l.get('score', 0):.2f}</b></span><a href='{l['url']}' target='_blank'><button style='background:#3d424d; color:white; border:none; padding:8px 20px; border-radius:5px;'>Zobacz ogłoszenie ↗</button></a></div>", unsafe_allow_html=True)
