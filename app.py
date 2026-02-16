import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import time
from datetime import datetime

# Handle Scipy availability
try:
    from scipy.interpolate import griddata
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

# Page configuration
st.set_page_config(
    page_title="NIFTY Live IV Surface",
    page_icon="📈",
    layout="wide",
)

# Custom CSS
st.markdown("""
<style>
    .stApp { background: radial-gradient(circle at 50% 50%, #1a1c2c 0%, #0e1117 100%); color: white; }
    h1 { background: linear-gradient(90deg, #00f2fe 0%, #4facfe 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; }
    .metric-card { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(10px); border-radius: 15px; padding: 20px; border: 1px solid rgba(255, 255, 255, 0.1); text-align: center; }
</style>
""", unsafe_allow_html=True)

# NSE Constants
BASE_URL = "https://www.nseindia.com"
LANDING_URL = "https://www.nseindia.com/option-chain"
API_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"

@st.cache_resource
def get_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": LANDING_URL
    })
    return s

def fetch_nse_data():
    session = get_session()
    try:
        # Pre-warm
        session.get(BASE_URL, timeout=5)
        session.get(LANDING_URL, timeout=5)
        
        # API Call
        response = session.get(API_URL, timeout=10)
        if response.text.strip() == "{}":
            return None, "Blocked"
            
        data = response.json()
        records = data['records']['data']
        spot = data['records']['underlyingValue']
        ts = data['records']['timestamp']
        
        all_rows = []
        for item in records:
            if 'CE' in item and item['CE'].get('impliedVolatility', 0) > 0:
                all_rows.append({
                    "strike": item['CE']['strikePrice'],
                    "iv": item['CE']['impliedVolatility'],
                    "expiry": item['expiryDate']
                })
        
        df = pd.DataFrame(all_rows)
        if df.empty: return None, "Empty"
        
        df['expiry'] = pd.to_datetime(df['expiry'])
        df['days_to_expiry'] = (df['expiry'] - pd.Timestamp.now().normalize()).dt.days
        return (df, spot, ts), "Success"
    except Exception as e:
        return None, str(e)

def generate_mock_data():
    spot = 25539.0
    strikes = np.linspace(spot * 0.9, spot * 1.1, 30)
    days = [7, 14, 21, 30, 60, 90]
    rows = []
    for d in days:
        for s in strikes:
            moneyness = s/spot
            iv = 15 + (100/(d+15)) - 40*(moneyness-1) + 350*(moneyness-1)**2
            rows.append({"strike": s, "iv": max(iv, 8), "days_to_expiry": d})
    return pd.DataFrame(rows), spot, datetime.now().strftime("%d-%b-%Y")

def main():
    try:
        st.markdown("<h1>NIFTY Live 3D Volatility Surface</h1>", unsafe_allow_html=True)
        
        data_res, status = fetch_nse_data()
        
        if data_res:
            df, spot, ts = data_res
            mode = "LIVE"
        else:
            df, spot, ts = generate_mock_data()
            mode = f"MOCK ({status})"

        # Header Metrics
        m1, m2, m3 = st.columns(3)
        m1.markdown(f'<div class="metric-card"><h4>NIFTY Spot</h4><h2>{spot:,.2f}</h2></div>', unsafe_allow_html=True)
        m2.markdown(f'<div class="metric-card"><h4>Timestamp</h4><h2>{ts}</h2></div>', unsafe_allow_html=True)
        m3.markdown(f'<div class="metric-card"><h4>Data Mode</h4><h2>{mode}</h2></div>', unsafe_allow_html=True)
        
        st.write("---")

        if not SCIPY_AVAILABLE:
            st.error("Scipy not found. Please ensure it is in requirements.txt")
            return

        # Prepare 3D Plot
        df_p = df[(df.strike > spot*0.88) & (df.strike < spot*1.12)]
        
        grid_x, grid_z = np.meshgrid(
            np.linspace(df_p.strike.min(), df_p.strike.max(), 50),
            np.linspace(df_p.days_to_expiry.min(), df_p.days_to_expiry.max(), 50)
        )
        
        grid_y = griddata(
            (df_p.strike, df_p.days_to_expiry),
            df_p.iv,
            (grid_x, grid_z),
            method='cubic'
        )

        fig = go.Figure(data=[go.Surface(x=grid_x, y=grid_y, z=grid_z, colorscale='Turbo')])
        fig.update_layout(
            scene=dict(
                xaxis_title="Strike", yaxis_title="IV %", zaxis_title="Days",
                xaxis=dict(gridcolor='#444'), yaxis=dict(gridcolor='#444'), zaxis=dict(gridcolor='#444'),
                bgcolor='rgba(0,0,0,0)'
            ),
            paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0,r=0,b=0,t=0), height=700, template='plotly_dark'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        if st.button("Manual Refresh"):
            st.cache_resource.clear()
            st.rerun()

    except Exception as e:
        st.error(f"Critical App Error: {str(e)}")
        st.info("Check your repository for a valid requirements.txt containing: requests, pandas, plotly, numpy, scipy, streamlit, Brotli")

if __name__ == "__main__":
    main()
