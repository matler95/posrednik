import streamlit as st
import pandas as pd
import requests
import json
import time

st.set_page_config(page_title="WREI Hunter | Snajper", layout="wide", page_icon="🎯")

# --- CSS PREMIIUM ---
st.markdown("""
<style>
/* Reset & Base */
.stApp { background-color: #0b0f19; color: #e2e8f0; font-family: 'Inter', sans-serif; }

/* Glassmorphism Cards */
.glass-card {
    background: rgba(255, 255, 255, 0.03);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 20px;
    transition: transform 0.2s, box-shadow 0.2s;
}
.glass-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 10px 30px -10px rgba(255, 75, 43, 0.3);
    border: 1px solid rgba(255, 75, 43, 0.3);
}

/* Typography */
h1, h2, h3 { color: #ffffff !important; }
.text-gradient {
    background: linear-gradient(90deg, #ff4b2b 0%, #ff416c 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
}

/* Metrics */
.metric-container {
    display: flex; gap: 15px; margin-top: 15px; flex-wrap: wrap;
}
.metric-box {
    background: rgba(0,0,0,0.2);
    border-radius: 10px;
    padding: 10px 15px;
    border: 1px solid rgba(255,255,255,0.05);
    flex: 1;
    min-width: 120px;
    text-align: center;
}
.metric-label { font-size: 0.7rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px;}

/* AI Box */
.ai-box {
    background: rgba(255, 75, 43, 0.05);
    border-left: 4px solid #ff4b2b;
    padding: 15px;
    border-radius: 0 10px 10px 0;
    margin-top: 15px;
    font-size: 0.9rem;
    line-height: 1.5;
}

/* Fix for links looking bad */
a.card-btn {
    text-decoration: none; 
    background: linear-gradient(90deg, #334155 0%, #1e293b 100%); 
    color: white !important; 
    padding: 8px 16px; 
    border-radius: 6px; 
    font-weight: bold; 
    display: inline-block;
    border: 1px solid #475569;
}
a.card-btn:hover {
    background: #475569;
}
</style>
""", unsafe_allow_html=True)

BACKEND = "http://backend:8000"

# --- API HELPERS ---
def get_config():
    try: 
        return requests.get(f"{BACKEND}/get-hunt-config", timeout=2).json()
    except: 
        return {"min_price":0, "max_price":430000, "min_area":0, "max_area":40, "districts":[], "city_slug":"warszawa"}

def save_config(cfg):
    try: 
        requests.post(f"{BACKEND}/set-hunt-config", json=cfg, timeout=2)
        return True
    except: 
        return False

def run_hunt():
    try: 
        requests.post(f"{BACKEND}/run-crawl", params={"pages": 5, "portals": "otodom"}, timeout=2)
        return True
    except: 
        return False

def get_listings(cfg):
    params = {
        "limit": 100,
        "min_price": cfg.get("min_price"),
        "max_price": cfg.get("max_price"),
        "min_area": cfg.get("min_area"),
        "max_area": cfg.get("max_area"),
    }
    try: 
        res = requests.get(f"{BACKEND}/listings", params=params, timeout=5).json()
        lst = res.get("listings", [])
        if cfg.get("districts") and len(cfg.get("districts")) > 0:
            lst = [l for l in lst if l.get("district") in cfg["districts"]]
        return lst
    except: 
        return []

# --- APP STATE ---
if "cfg" not in st.session_state:
    st.session_state.cfg = get_config()

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.markdown("<h2 class='text-gradient' style='text-align:center;'>WREI HUNTER</h2>", unsafe_allow_html=True)
    st.write("---")
    view = st.radio("Nawigacja", ["🎯 Mój Profil", "📊 Tablica Wyników"])
    st.write("---")
    if st.button("🚀 URUCHOM SKANOWANIE", use_container_width=True, type="primary"):
        if run_hunt():
            st.success("Skanowanie w tle rozpoczęte!")
            time.sleep(2)
            st.rerun()
        else:
            st.error("Błąd połączenia z backendem.")

# --- VIEW: PROFIL ---
if view == "🎯 Mój Profil":
    st.markdown("<h1 class='text-gradient'>Konfiguracja Polowania</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#94a3b8;'>Ustaw stałe parametry, według których system będzie szukał i analizował oferty.</p>", unsafe_allow_html=True)
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            cities = ["warszawa", "krakow", "wroclaw"]
            curr_city = st.session_state.cfg.get("city_slug", "warszawa")
            if curr_city not in cities: curr_city = "warszawa"
            
            st.session_state.cfg["city_slug"] = st.selectbox("Miasto", cities, index=cities.index(curr_city))
            
            warsaw_districts = ["Bemowo", "Białołęka", "Bielany", "Mokotów", "Ochota", "Praga-Południe", "Praga-Północ", "Rembertów", "Śródmieście", "Targówek", "Ursus", "Ursynów", "Wawer", "Wesoła", "Wilanów", "Włochy", "Wola", "Żoliborz"]
            current_districts = st.session_state.cfg.get("districts", [])
            st.session_state.cfg["districts"] = st.multiselect("Dzielnice (zostaw puste dla całego miasta)", warsaw_districts, default=[d for d in current_districts if d in warsaw_districts])
            
        with c2:
            st.session_state.cfg["min_price"] = st.number_input("Cena Od (PLN)", value=int(st.session_state.cfg.get("min_price", 0)), step=10000)
            st.session_state.cfg["max_price"] = st.number_input("Cena Do (PLN)", value=int(st.session_state.cfg.get("max_price", 430000)), step=10000)
            st.session_state.cfg["min_area"] = st.number_input("Metraż Od (m²)", value=int(st.session_state.cfg.get("min_area", 0)), step=1)
            st.session_state.cfg["max_area"] = st.number_input("Metraż Do (m²)", value=int(st.session_state.cfg.get("max_area", 45)), step=1)
            
    if st.button("💾 ZAPISZ PROFIL", type="primary"):
        if save_config(st.session_state.cfg):
            st.success("Profil zaktualizowany! AI będzie teraz priorytetyzować te ustawienia.")
        else:
            st.error("Nie udało się zapisać profilu.")

# --- VIEW: TABLICA WYNIKÓW ---
elif view == "📊 Tablica Wyników":
    st.markdown("<h1 class='text-gradient'>Aktywne Cele</h1>", unsafe_allow_html=True)
    
    listings = get_listings(st.session_state.cfg)
    
    if not listings:
        st.info("Brak ofert spełniających kryteria. Uruchom skanowanie w menu bocznym lub zmień profil.")
    else:
        st.markdown(f"<p style='color:#94a3b8;'>Znalazłem <b>{len(listings)}</b> wyselekcjonowanych ofert pod Twój profil.</p>", unsafe_allow_html=True)
        
        for l in listings:
            # Prepare image
            img_url = "https://via.placeholder.com/300x200?text=Brak+Zdjęcia"
            if l.get('images') and len(l['images']) > 0:
                img_url = l['images'][0]
                
            gap = l.get('transaction_gap', 0)
            rcn_b = l.get('rcn_benchmark', 0)
            savings = (rcn_b * l['area']) - l['price'] if rcn_b and l.get('area') else 0
            
            color_gap = "#10b981" if gap > 0 else "#ef4444"
            sign_gap = "+" if gap > 0 else ""
            
            ai_data = l.get('llm_analysis') or {}
            ai_text = ai_data.get('summary', 'Oczekuje na analizę modelu LLM...')
            
            # Bezpieczne formatowanie tekstu dla HTML
            ai_text = ai_text.replace("<", "&lt;").replace(">", "&gt;").replace("\\n", "<br>")
            
            html_card = f"""
            <div class="glass-card">
                <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                    <div style="flex: 0 0 280px;">
                        <img src="{img_url}" style="width: 100%; height: 200px; object-fit: cover; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);">
                    </div>
                    <div style="flex: 1; min-width: 300px;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div>
                                <h3 style="margin: 0; font-size: 1.3rem;">{l['title']}</h3>
                                <p style="color: #94a3b8; margin: 5px 0 0 0;">📍 {l['district']} | {l['portal'].upper()} {f'| 👤 <span style="color:#10b981">Bezpośrednio</span>' if l.get('direct_offer') else ''}</p>
                            </div>
                            <div style="text-align: right;">
                                <div style="font-size: 1.6rem; font-weight: 800; color: #ff4b2b;">{l['price']:,.0f} PLN</div>
                                <div style="color: #94a3b8;">{l['area']} m² ({l.get('price_per_m2', 0):,.0f} zł/m²)</div>
                            </div>
                        </div>
                        
                        <div class="metric-container">
                            <div class="metric-box">
                                <div class="metric-label">Luka Transakcyjna</div>
                                <div style="color: {color_gap}; font-weight: bold; font-size: 1.2rem;">{sign_gap}{gap*100:.1f}%</div>
                            </div>
                            <div class="metric-box">
                                <div class="metric-label">Zysk z Luki</div>
                                <div style="color: {color_gap}; font-weight: bold; font-size: 1.2rem;">{sign_gap}{savings/1000:.1f}k</div>
                            </div>
                            <div class="metric-box">
                                <div class="metric-label">AI Score</div>
                                <div style="color: #fff; font-weight: bold; font-size: 1.2rem;">⭐ {l.get('score', 0):.2f}</div>
                            </div>
                        </div>
                        
                        <div class="ai-box">
                            <b>🧠 Raport AI:</b> <span style="color:#cbd5e1;">{ai_text}</span>
                        </div>
                        
                        <div style="margin-top: 15px; text-align: right;">
                            <a href="{l['url']}" target="_blank" class="card-btn">
                                ZOBACZ OFERTĘ ↗
                            </a>
                        </div>
                    </div>
                </div>
            </div>
            """
            st.markdown(html_card, unsafe_allow_html=True)
