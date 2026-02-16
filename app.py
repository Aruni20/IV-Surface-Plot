import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import json
import os
from datetime import datetime

# Page configuration
st.set_page_config(page_title="NIFTY Real IV Tracker", page_icon="🏦", layout="wide")

# Custom CSS
st.markdown("""
<style>
    .stApp { background: #0b0d17; color: white; }
    .metric-card { background: rgba(255,255,255,0.03); border: 1px solid #333; border-radius: 10px; padding: 15px; text-align: center; }
    h1 { color: #00f2fe; text-align: center; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

# NSE Hardened Config
BASE_URL = "https://www.nseindia.com"
API_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
CACHE_FILE = "nifty_cache.json"

@st.cache_resource
def get_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/option-chain",
        "X-Requested-With": "XMLHttpRequest"
    })
    return s

def fetch_data():
    session = get_session()
    try:
        # Session warming
        session.get(BASE_URL, timeout=5)
        response = session.get(API_URL, timeout=10)
        
        if response.status_code == 200 and response.text.strip() != "{}":
            data = response.json()
            # Save to cache for offline/blocked fallback
            with open(CACHE_FILE, 'w') as f:
                json.dump(data, f)
            return data, "LIVE"
        
        # If blocked, try loading from cache
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
            return data, "REAL CACHED (NSE Blocked)"
            
        return None, "API BLOCKED & NO CACHE"
    except Exception as e:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
            return data, "REAL CACHED (Error)"
        return None, str(e)

def process_data(data):
    if not data or 'records' not in data:
        return None, None, None
    
    records = data['records']['data']
    spot = data['records']['underlyingValue']
    ts = data['records']['timestamp']
    
    rows = []
    for item in records:
        expiry = item['expiryDate']
        for opt in ['CE', 'PE']:
            if opt in item and item[opt].get('impliedVolatility', 0) > 0:
                rows.append({
                    "strike": item[opt]['strikePrice'],
                    "iv": item[opt]['impliedVolatility'],
                    "expiry": expiry,
                    "type": opt,
                    "oi": item[opt].get('openInterest', 0)
                })
    
    df = pd.DataFrame(rows)
    df['expiry_dt'] = pd.to_datetime(df['expiry'])
    df['days_to_expiry'] = (df['expiry_dt'] - pd.Timestamp.now().normalize()).dt.days
    return df, spot, ts

def main():
    st.markdown("<h1>NIFTY REAL-TIME VOLATILITY ANALYSIS</h1>", unsafe_allow_html=True)
    
    raw_data, status_label = fetch_data()
    df, spot, ts = process_data(raw_data)
    
    if df is None:
        st.error("🚫 Connection Failed: NSE is blocking cloud-based requests. Please run the app on your local machine to fetch live data.")
        st.info("The manager will see an empty screen unless you run this locally first to generate a 'nifty_cache.json' file.")
        return

    # Metrics
    c1, c2, c3 = st.columns(3)
    c1.markdown(f'<div class="metric-card"><h4>Spot Price</h4><h2>{spot:,.2f}</h2></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="metric-card"><h4>Market Time</h4><h2>{ts}</h2></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="metric-card"><h4>Data Hub</h4><h2>{status_label}</h2></div>', unsafe_allow_html=True)

    # --- SECTION 1: 2D SMILE (REAL VALUES ONLY) ---
    st.write("---")
    st.markdown("### 🎯 Raw IV Smile (Select Expiry)")
    
    expiries = sorted(df['expiry_dt'].unique())
    expiry_options = [str(e.date()) for e in expiries]
    selected_expiry_str = st.selectbox("Market Expiry Date:", expiry_options)
    
    df_near = df[df['expiry_dt'] == pd.to_datetime(selected_expiry_str)]
    
    fig2d = go.Figure()
    for opt, color in [("CE", "#00f2fe"), ("PE", "#ff00ff")]:
        sub = df_near[df_near['type'] == opt]
        fig2d.add_trace(go.Scatter(
            x=sub.strike, y=sub.iv, mode='markers+lines', name=f"Real {opt} IV",
            marker=dict(size=8, color=color), line=dict(color=color, width=1, dash='dot')
        ))
    
    fig2d.update_layout(height=400, template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0,r=0,b=0,t=20))
    st.plotly_chart(fig2d, use_container_width=True)

    # --- SECTION 2: 3D ANOMALY SURFACE ---
    st.write("---")
    st.markdown("### 🗺️ 3D Real Anomaly Mapping")
    
    # Filter for strikes closer to action
    df_p = df[(df.strike > spot*0.8) & (df.strike < spot*1.2)].copy()
    
    # Detect Local Anomalies (Real spikes)
    # Group by expiry and check for spikes > 3 standard deviations or 15% jump
    df_p['expiry_mean'] = df_p.groupby('expiry')['iv'].transform('mean')
    df_p['is_anomaly'] = abs(df_p['iv'] - df_p['expiry_mean']) > 15
    
    anomalies = df_p[df_p['is_anomaly']]
    normal = df_p[~df_p['is_anomaly']]
    
    # Pivot for surface (X=Strike, Y=Time, Z=IV)
    # Using 'mean' IV of CE/PE for the base mesh to avoid overlapping planes
    pivot_df = df_p.pivot_table(index='days_to_expiry', columns='strike', values='iv', aggfunc='mean')
    
    fig3d = go.Figure()
    # Base Mesh
    fig3d.add_trace(go.Surface(
        x=pivot_df.columns, y=pivot_df.index, z=pivot_df.values,
        colorscale='Turbo', opacity=0.7, colorbar_title="IV %"
    ))
    # Spikes
    if not anomalies.empty:
        fig3d.add_trace(go.Scatter3d(
            x=anomalies.strike, y=anomalies.days_to_expiry, z=anomalies.iv,
            mode='markers', marker=dict(size=8, color='magenta', symbol='diamond', line=dict(color='white', width=2)),
            name="REAL ANOMALIES (SPIKES)"
        ))

    fig3d.update_layout(
        scene=dict(xaxis_title="Strike", yaxis_title="Days", zaxis_title="IV %", bgcolor='rgba(0,0,0,0)'),
        height=700, template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0,r=0,b=0,t=0)
    )
    st.plotly_chart(fig3d, use_container_width=True)

    if st.button("Force Update from NSE"):
        st.cache_resource.clear()
        st.rerun()

if __name__ == "__main__":
    main()
