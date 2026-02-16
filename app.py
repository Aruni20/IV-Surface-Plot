import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import time
from datetime import datetime
from scipy.interpolate import griddata

# Page configuration
st.set_page_config(
    page_title="NIFTY Live IV Surface",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for Premium Look
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
        color: #ffffff;
    }
    .stApp {
        background: radial-gradient(circle at 50% 50%, #1a1c2c 0%, #0e1117 100%);
    }
    h1 {
        font-family: 'Inter', sans-serif;
        font-weight: 800;
        background: linear-gradient(90deg, #00f2fe 0%, #4facfe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding-bottom: 20px;
    }
    .metric-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        padding: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        text-align: center;
    }
    .status-msg {
        font-size: 0.8rem;
        color: #888;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# NSE API configuration
BASE_URL = "https://www.nseindia.com"
LANDING_URL = "https://www.nseindia.com/option-chain"
API_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/option-chain",
    "X-Requested-With": "XMLHttpRequest"
}

class NSETracker:
    def __init__(self):
        if 'session' not in st.session_state:
            st.session_state.session = requests.Session()
            st.session_state.session.headers.update(headers)
            self.refresh_session()

    def refresh_session(self):
        try:
            # Visit homepage and landing page to get cookies
            st.session_state.session.get(BASE_URL, timeout=10)
            st.session_state.session.get(LANDING_URL, timeout=10)
        except:
            pass

    def fetch_data(self):
        try:
            response = st.session_state.session.get(API_URL, timeout=15)
            
            # If response is empty, it's likely a cloud-IP block by Akamai
            if response.text.strip() == "{}" or response.status_code == 401:
                self.refresh_session()
                response = st.session_state.session.get(API_URL, timeout=15)
                
            if response.text.strip() == "{}":
                return None, None, None, "API Blocked (Cloud IP Detection)"
                
            response.raise_for_status()
            data = response.json()
            
            if 'records' not in data:
                return None, None, None, "No 'records' key found"
                
            records = data['records']['data']
            price = data['records']['underlyingValue']
            timestamp = data['records']['timestamp']
            
            all_rows = []
            for item in records:
                expiry = item['expiryDate']
                if 'CE' in item:
                    ce = item['CE']
                    if ce.get('impliedVolatility', 0) > 0:
                        all_rows.append({
                            "strike": ce['strikePrice'],
                            "iv": ce['impliedVolatility'],
                            "expiry": expiry
                        })
            
            df = pd.DataFrame(all_rows)
            df['expiry'] = pd.to_datetime(df['expiry'])
            today = pd.Timestamp.now().normalize()
            df['days_to_expiry'] = (df['expiry'] - today).dt.days
            
            return df, price, timestamp, "Live Data Active"
        except Exception as e:
            return None, None, None, f"Error: {str(e)}"

def generate_fallback_data():
    """Generates realistic synthetic IV surface data for demonstration if API is blocked."""
    spot = 23500.0  # Estimated spot
    strikes = np.linspace(spot * 0.90, spot * 1.10, 30)
    expiries = np.array([7, 14, 21, 30, 60, 90])
    
    rows = []
    for exp in expiries:
        for strike in strikes:
            # Simplified IV Smile model: IV = base + (strike - spot)^2 * curvature
            # Plus some term structure: IV is higher for shorter expiries
            dist = (strike - spot) / spot
            base_iv = 12 + (100 / (exp + 10))
            iv = base_iv + 500 * (dist ** 2) - 10 * dist  # Smile + Skew
            rows.append({
                "strike": strike,
                "iv": iv,
                "days_to_expiry": exp
            })
    
    return pd.DataFrame(rows), spot, datetime.now().strftime("%d-%b-%Y %H:%M:%S")

def main():
    st.markdown("<h1>NIFTY Live 3D Volatility Surface</h1>", unsafe_allow_html=True)
    
    tracker = NSETracker()
    
    metrics_placeholder = st.empty()
    chart_placeholder = st.empty()
    status_placeholder = st.empty()
    
    # Try fetching real data
    df, spot_price, ts, status = tracker.fetch_data()
    
    is_fallback = False
    if df is None or df.empty:
        df, spot_price, ts = generate_fallback_data()
        is_fallback = True
        status += " | Using Synthetic Fallback (Cloud IP Detected)"

    with metrics_placeholder.container():
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f'<div class="metric-card"><h3>NIFTY Spot</h3><h2>{spot_price:,.2f}</h2></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card"><h3>Last Updated</h3><h2>{ts}</h2></div>', unsafe_allow_html=True)
        with col3:
            st.markdown(f'<div class="metric-card"><h3>Mode</h3><h2>{"MOCK" if is_fallback else "LIVE"}</h2></div>', unsafe_allow_html=True)
    
    status_placeholder.markdown(f'<p class="status-msg">{status}</p>', unsafe_allow_html=True)

    # Filter range for strike prices near spot
    strike_range = 0.15
    df_filtered = df[(df['strike'] > spot_price * (1-strike_range)) & (df['strike'] < spot_price * (1+strike_range))]
    
    # Interpolation
    grid_x, grid_z = np.meshgrid(
        np.linspace(df_filtered.strike.min(), df_filtered.strike.max(), 60),
        np.linspace(df_filtered.days_to_expiry.min(), df_filtered.days_to_expiry.max(), 60)
    )

    grid_y = griddata(
        (df_filtered.strike, df_filtered.days_to_expiry),
        df_filtered.iv,
        (grid_x, grid_z),
        method='cubic'
    )

    fig = go.Figure(data=[go.Surface(
        x=grid_x,
        y=grid_y,
        z=grid_z,
        colorscale='Turbo',
        colorbar_title="IV %",
        hovertemplate="Strike: %{x}<br>Days: %{z}<br>IV: %{y:.2f}%<extra></extra>"
    )])

    fig.update_layout(
        scene=dict(
            xaxis_title="Strike Price",
            yaxis_title="Implied Volatility (IV %)",
            zaxis_title="Days to Expiry",
            xaxis=dict(gridcolor='#444', title_font=dict(size=14)),
            yaxis=dict(gridcolor='#444', title_font=dict(size=14)),
            zaxis=dict(gridcolor='#444', title_font=dict(size=14)),
            bgcolor='rgba(0,0,0,0)'
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0, r=0, b=0, t=0),
        height=700,
        template='plotly_dark'
    )
    
    with chart_placeholder:
        st.plotly_chart(fig, use_container_width=True)
        
    if st.button("Manual Refresh"):
        st.rerun()
        
    st.info("Note: NSE often blocks automated requests from cloud environments. If 'MOCK' mode is active, the data shown is a realistic simulation of the current market volatility smile. Run this locally for live NSE connectivity.")

if __name__ == "__main__":
    main()
