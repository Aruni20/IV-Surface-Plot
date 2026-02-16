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
            expiry = item['expiryDate']
            # Fetch both CE and PE for 'Real Value' analysis
            if 'CE' in item and item['CE'].get('impliedVolatility', 0) > 0:
                all_rows.append({
                    "strike": item['CE']['strikePrice'],
                    "iv": item['CE']['impliedVolatility'],
                    "expiry": expiry,
                    "type": "CE"
                })
            if 'PE' in item and item['PE'].get('impliedVolatility', 0) > 0:
                all_rows.append({
                    "strike": item['PE']['strikePrice'],
                    "iv": item['PE']['impliedVolatility'],
                    "expiry": expiry,
                    "type": "PE"
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
    days = [3, 7, 14, 21, 30, 60, 90]
    rows = []
    for d in days:
        # Create a unique mock expiry label for the dropdown
        expiry_label = f"MOCK - {d} Days"
        for s in strikes:
            moneyness = s/spot
            base_iv = 15 + (100/(d+15))
            # Real skew: PE IV usually trades higher than CE IV for OTM
            iv_ce = max(base_iv - 35*(moneyness-1) + 300*(moneyness-1)**2, 8)
            iv_pe = max(base_iv - 45*(moneyness-1) + 400*(moneyness-1)**2 + 1, 9)
            
            rows.append({"strike": s, "iv": iv_ce, "days_to_expiry": d, "type": "CE", "expiry": expiry_label})
            rows.append({"strike": s, "iv": iv_pe, "days_to_expiry": d, "type": "PE", "expiry": expiry_label})
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

        # --- NEW 2D REAL VALUE PLOT ABOVE ---
        st.markdown("### 🎯 Raw IV Smile (Select Expiry - Real Values)")
        
        # Get all unique expiries for the dropdown
        # Convert to string for display, but keep track of sorting
        unique_expiries = sorted(df['expiry'].unique())
        expiry_options = [str(pd.to_datetime(e).date()) if not isinstance(e, str) else e for e in unique_expiries]
        
        col_exp, col_stat = st.columns([1, 2])
        with col_exp:
            selected_expiry_str = st.selectbox("Select Expiry for Raw Smile:", expiry_options, index=0)
            selected_expiry = unique_expiries[expiry_options.index(selected_expiry_str)]
        
        # Filter for the selected expiry
        df_near = df[df['expiry'] == selected_expiry]

        fig_smile = go.Figure()
        
        # Plot CE and PE separately to show "Real Values" not average
        for opt_type, color in [("CE", "#00f2fe"), ("PE", "#ff00ff")]:
            df_type = df_near[df_near['type'] == opt_type]
            if not df_type.empty:
                fig_smile.add_trace(go.Scatter(
                    x=df_type['strike'], 
                    y=df_type['iv'], 
                    mode='markers+lines',
                    name=f"Real {opt_type} IV",
                    line=dict(color=color, width=1, dash='dot'),
                    marker=dict(size=8, color=color, symbol='circle' if opt_type == "CE" else 'x'),
                    hovertemplate=f"{opt_type} Strike: %{{x}}<br>IV: %{{y:.2f}}%<extra></extra>"
                ))

        fig_smile.update_layout(
            title=f"Actual IV for Expiry: {selected_expiry_str} (No Averaging)",
            xaxis_title="Strike Price",
            yaxis_title="Implied Volatility (IV %)",
            height=400,
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(10,10,25,0.5)',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=0, r=0, b=0, t=50)
        )
        st.plotly_chart(fig_smile, use_container_width=True)
        st.write("---")

        if not SCIPY_AVAILABLE:
            st.error("Scipy not found. Please ensure it is in requirements.txt")
            return

        # Prepare 3D Plot - QUANT STANDARD COORDINATES
        # Expand range to see tail-risk anomalies (25% range)
        df_p = df[(df.strike > spot*0.80) & (df.strike < spot*1.20)].copy()
        
        # --- REFINED ANOMALY DETECTION ---
        # Compare IV to a rolling median within its own expiry to handle Skew naturally
        df_p = df_p.sort_values(['days_to_expiry', 'strike'])
        df_p['expiry_median'] = df_p.groupby('days_to_expiry')['iv'].transform(lambda x: x.rolling(window=5, center=True, min_periods=1).median())
        df_p['is_anomaly'] = abs(df_p['iv'] - df_p['expiry_median']) > 12 # 12% absolute deviation from neighbor
        
        anomalies = df_p[df_p['is_anomaly']]
        normal_data = df_p[~df_p['is_anomaly']]
        # ----------------------------------

        # Create pivot for the surface
        pivot_df = df_p.pivot_table(index='days_to_expiry', columns='strike', values='iv')
        
        x_strikes = pivot_df.columns.values
        y_exp_days = pivot_df.index.values
        z_iv_matrix = pivot_df.values # Height is now the IV values

        fig = go.Figure()

        # 1. Base Surface (X=Strike, Y=Time, Z=IV)
        fig.add_trace(go.Surface(
            x=x_strikes, 
            y=y_exp_days, 
            z=z_iv_matrix,
            colorscale='Turbo', 
            opacity=0.85, 
            colorbar_title="IV %",
            hovertemplate="Strike: %{x}<br>Days: %{y}<br>IV: %{z:.2f}%<extra></extra>"
        ))

        # 2. Normal Data Markers (Z is height)
        fig.add_trace(go.Scatter3d(
            x=normal_data['strike'], 
            y=normal_data['days_to_expiry'], 
            z=normal_data['iv'],
            mode='markers',
            marker=dict(size=2, color='white', opacity=0.3),
            name="Normal Points"
        ))

        # 3. ANOMALY HIGHLIGHTS (Magenta Diamonds on Height)
        if not anomalies.empty:
            fig.add_trace(go.Scatter3d(
                x=anomalies['strike'], 
                y=anomalies['days_to_expiry'], 
                z=anomalies['iv'],
                mode='markers',
                marker=dict(size=7, color='magenta', symbol='diamond', line=dict(color='white', width=1)),
                name="Spikes Detected",
                hovertemplate="<b>ANOMALY</b><br>Strike: %{x}<br>Days: %{y}<br>IV: %{z:.2f}%<extra></extra>"
            ))

        fig.update_layout(
            title=dict(
                text=f"NIFTY IV Surface - Standard Height Mapping ({len(anomalies)} Outliers Detected)",
                x=0.5, font=dict(size=20, color='#00f2fe')
            ),
            scene=dict(
                xaxis_title="Strike Price",
                yaxis_title="Days to Expiry",
                zaxis_title="Implied Volatility (IV %)",
                xaxis=dict(gridcolor='#444', spikecolor="#00f2fe"),
                yaxis=dict(gridcolor='#444', spikecolor="#00f2fe"),
                zaxis=dict(gridcolor='#444', spikecolor="#00f2fe", range=[min(df_p.iv)-5, max(df_p.iv)+10]),
                camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)) # Better initial angle
            ),
            paper_bgcolor='rgba(0,0,0,0)', 
            margin=dict(l=0, r=0, b=0, t=60), 
            height=800, 
            template='plotly_dark'
        )
        
        st.plotly_chart(fig, use_container_width=True)

        if not anomalies.empty:
            st.warning(f"Detected {len(anomalies)} sharp IV anomalies. High spikes in magenta often indicate illiquidity or arbitrage gap.")

        st.write("---")
        st.markdown("### 📉 2D Term Structure Analysis (IV vs Expiry)")
        
        # Get unique strikes for the dropdown
        unique_strikes = sorted(df['strike'].unique())
        
        # Find strike closest to spot to set as default
        closest_strike = min(unique_strikes, key=lambda x:abs(x-spot))
        
        col_sel, col_info = st.columns([1, 2])
        with col_sel:
            selected_strike = st.selectbox("Select Strike Price for Term Structure:", unique_strikes, index=unique_strikes.index(closest_strike))
        
        with col_info:
            st.info(f"Visualizing how Implied Volatility changes over time for Strike {selected_strike:,.0f}.")

        # Filter for selected strike
        df_strike = df[df['strike'] == selected_strike].sort_values('days_to_expiry')

        if not df_strike.empty:
            fig2d = go.Figure()
            
            # Add line + markers
            fig2d.add_trace(go.Scatter(
                x=df_strike['days_to_expiry'],
                y=df_strike['iv'],
                mode='lines+markers',
                line=dict(color='#00f2fe', width=3),
                marker=dict(size=10, color='#4facfe', symbol='diamond'),
                hovertemplate="Days: %{x}<br>IV: %{y:.2f}%<extra></extra>"
            ))

            fig2d.update_layout(
                xaxis_title="Days to Expiry",
                yaxis_title="Implied Volatility (IV %)",
                height=450,
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(10,10,25,0.5)',
                xaxis=dict(gridcolor='#333', zeroline=False),
                yaxis=dict(gridcolor='#333', zeroline=False),
                margin=dict(l=0, r=0, b=0, t=20)
            )
            
            st.plotly_chart(fig2d, use_container_width=True)
        else:
            st.warning(f"No specific data points available for strike {selected_strike}.")

        if st.button("Refresh Live Data"):
            st.cache_resource.clear()
            st.rerun()

    except Exception as e:
        st.error(f"Critical App Error: {str(e)}")
        st.info("Check your repository for a valid requirements.txt containing: requests, pandas, plotly, numpy, scipy, streamlit, Brotli")

if __name__ == "__main__":
    main()
