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

# Custom CSS for Premium Look
st.markdown("""
<style>
    .stApp { background: #0b0d17; color: white; }
    .metric-card { background: rgba(255,255,255,0.03); border: 1px solid #333; border-radius: 10px; padding: 15px; text-align: center; }
    h1 { color: #00f2fe; text-align: center; font-weight: 800; font-family: 'Inter', sans-serif; }
    .status-msg { font-size: 0.8rem; color: #888; text-align: center; }
</style>
""", unsafe_allow_html=True)

# NSE Constants
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
            with open(CACHE_FILE, 'w') as f:
                json.dump(data, f)
            return data, "LIVE NSE FEED"
        
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
            return data, f"REAL CACHED DATA (Last update: {datetime.fromtimestamp(os.path.getmtime(CACHE_FILE)).strftime('%Y-%m-%d %H:%M')})"
            
        return None, "CONNECTION BLOCKED - RUN LOCALLY TO INITIALIZE CACHE"
    except Exception as e:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
            return data, "REAL CACHED DATA (Fetch Error)"
        return None, f"Error: {str(e)}"

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
                    "oi": item[opt].get('openInterest', 0),
                    "bid": item[opt].get('bidprice', 0),
                    "ask": item[opt].get('askPrice', 0)
                })
    
    df = pd.DataFrame(rows)
    if df.empty:
        return None, spot, ts
        
    df['expiry_dt'] = pd.to_datetime(df['expiry'])
    df['days_to_expiry'] = (df['expiry_dt'] - pd.Timestamp.now().normalize()).dt.days
    df = df[df['days_to_expiry'] >= 0] # Remove past expiries
    return df, spot, ts

def main():
    st.markdown("<h1>NIFTY REAL-TIME VOLATILITY ANALYSIS</h1>", unsafe_allow_html=True)
    
    raw_data, status_label = fetch_data()
    df, spot, ts = process_data(raw_data)
    
    if df is None:
        st.error(f"❌ {status_label}")
        st.info("NSE blocks automated requests from cloud IPs. To fix this: Run this app once on your local computer to generate the real data cache.")
        return

    # Metrics Row
    c1, c2, c3 = st.columns(3)
    c1.markdown(f'<div class="metric-card"><h4>NIFTY Spot</h4><h2>{spot:,.2f}</h2></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="metric-card"><h4>Data Source</h4><h2>{status_label}</h2></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="metric-card"><h4>Last Fetch Time</h4><h2>{ts}</h2></div>', unsafe_allow_html=True)

    # --- SECTION 1: 2D SMILE (REAL VALUES) ---
    st.write("---")
    st.markdown("### 🎯 Raw IV Smile (Select Expiry)")
    
    all_expiries = sorted(df['expiry_dt'].unique())
    expiry_options = [e.strftime('%d-%b-%Y') for e in all_expiries]
    selected_expiry_str = st.selectbox("Choose Expiry Date:", expiry_options)
    
    selected_dt = all_expiries[expiry_options.index(selected_expiry_str)]
    df_near = df[df['expiry_dt'] == selected_dt]
    
    # Filter for strikes around spot for the smile plot
    df_near_filtered = df_near[(df_near.strike > spot * 0.85) & (df_near.strike < spot * 1.15)]

    fig2d = go.Figure()
    for opt, color in [("CE", "#00f2fe"), ("PE", "#ff00ff")]:
        sub = df_near_filtered[df_near_filtered['type'] == opt].sort_values('strike')
        fig2d.add_trace(go.Scatter(
            x=sub.strike, y=sub.iv, mode='markers+lines', name=f"Real {opt} IV",
            marker=dict(size=8, color=color), line=dict(color=color, width=1, dash='dot'),
            hovertemplate="Strike: %{x}<br>IV: %{y:.2f}%<extra></extra>"
        ))
    
    fig2d.update_layout(
        xaxis_title="Strike Price", yaxis_title="Implied Volatility (IV %)",
        height=450, template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', 
        margin=dict(l=0,r=0,b=0,t=20),
        legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center")
    )
    st.plotly_chart(fig2d, use_container_width=True)

    # --- SECTION 2: 3D ANOMALY SURFACE ---
    st.write("---")
    st.markdown("### 🗺️ 3D Real Market Surface & Anomaly Detection")
    
    # Range for 3D Surface
    df_p = df[(df.strike > spot*0.80) & (df.strike < spot*1.20)].copy()
    
    # Detect Local Anomalies (Real spikes)
    df_p['expiry_median'] = df_p.groupby('expiry')['iv'].transform(lambda x: x.rolling(window=5, center=True, min_periods=1).median())
    df_p['is_anomaly'] = abs(df_p['iv'] - df_p['expiry_median']) > 12
    
    anomalies = df_p[df_p['is_anomaly']]
    normal = df_p[~df_p['is_anomaly']]
    
    # Pivot for surface (Height is IV)
    pivot_df = df_p.pivot_table(index='days_to_expiry', columns='strike', values='iv', aggfunc='mean')
    
    fig3d = go.Figure()
    # Base Mesh
    fig3d.add_trace(go.Surface(
        x=pivot_df.columns, y=pivot_df.index, z=pivot_df.values,
        colorscale='Turbo', opacity=0.8, colorbar_title="IV %",
        hovertemplate="Strike: %{x}<br>Days: %{y}<br>IV: %{z:.2f}%<extra></extra>"
    ))
    
    # Spikes
    if not anomalies.empty:
        fig3d.add_trace(go.Scatter3d(
            x=anomalies.strike, y=anomalies.days_to_expiry, z=anomalies.iv,
            mode='markers', marker=dict(size=8, color='magenta', symbol='diamond', line=dict(color='white', width=2)),
            name="REAL ANOMALIES"
        ))

    fig3d.update_layout(
        scene=dict(
            xaxis_title="Strike Price", yaxis_title="Days to Expiry", zaxis_title="IV %",
            xaxis=dict(gridcolor='#444'), yaxis=dict(gridcolor='#444'), zaxis=dict(gridcolor='#444'),
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.2))
        ),
        height=800, template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0,r=0,b=0,t=0)
    )
    st.plotly_chart(fig3d, use_container_width=True)

    if not anomalies.empty:
        st.warning(f"⚠️ Market Insight: Detected {len(anomalies)} sharp volatility anomalies in the real exchange data. See magenta highlights.")

    if st.button("Force NSE Live Refresh"):
        st.cache_resource.clear()
        st.rerun()

    st.markdown('<p class="status-msg">Strict Real Data Policy: Every point above originates from the NSE. No synthetic curves or mock data generators are used.</p>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
