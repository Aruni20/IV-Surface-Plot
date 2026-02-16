import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import json
import os
from datetime import datetime

# NSE Constants
BASE_URL = "https://www.nseindia.com"
API_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
CACHE_FILE = "nifty_cache.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/option-chain",
    "X-Requested-With": "XMLHttpRequest"
}

class NSETracker:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.init_session()

    def init_session(self):
        try:
            self.session.get(BASE_URL, timeout=10)
            print("Session Initialized.")
        except Exception as e:
            print(f"Init Error: {e}")

    def fetch_real_data(self):
        try:
            response = self.session.get(API_URL, timeout=15)
            if response.status_code == 200 and response.text.strip() != "{}":
                data = response.json()
                with open(CACHE_FILE, 'w') as f:
                    json.dump(data, f)
                return data, "LIVE"
            
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r') as f:
                    return json.load(f), "CACHED"
            
            return None, "BLOCKED"
        except:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r') as f:
                    return json.load(f), "CACHED"
            return None, "ERROR"

def create_surface(df, spot, status):
    # Filter for strikes around spot
    df_p = df[(df.strike > spot * 0.8) & (df.strike < spot * 1.2)].copy()
    
    # Pivot for surface
    pivot_df = df_p.pivot_table(index='days_to_expiry', columns='strike', values='iv', aggfunc='mean')
    
    fig = go.Figure(data=[go.Surface(
        x=pivot_df.columns,
        y=pivot_df.index,
        z=pivot_df.values,
        colorscale='Turbo',
        colorbar_title="IV %"
    )])

    fig.update_layout(
        title=f"NIFTY REAL IV SURFACE - [{status} DATA] - Spot: {spot:.2f}",
        scene=dict(
            xaxis_title="Strike Price",
            yaxis_title="Days to Expiry",
            zaxis_title="Implied Volatility (IV %)",
            zaxis=dict(range=[0, max(df_p.iv)+10])
        ),
        template='plotly_dark'
    )
    return fig

def main():
    tracker = NSETracker()
    print("REAL DATA ONLY - Starting Tracker...")
    
    while True:
        raw_data, status = tracker.fetch_real_data()
        if raw_data:
            records = raw_data['records']['data']
            spot = raw_data['records']['underlyingValue']
            
            rows = []
            for item in records:
                expiry = item['expiryDate']
                for opt in ['CE', 'PE']:
                    if opt in item and item[opt].get('impliedVolatility', 0) > 0:
                        rows.append({
                            "strike": item[opt]['strikePrice'],
                            "iv": item[opt]['impliedVolatility'],
                            "expiry_dt": pd.to_datetime(expiry)
                        })
            
            df = pd.DataFrame(rows)
            df['days_to_expiry'] = (df['expiry_dt'] - pd.Timestamp.now().normalize()).dt.days
            df = df[df.days_to_expiry >= 0]
            
            print(f"Plotting {status} data from NSE. Spot: {spot}")
            fig = create_surface(df, spot, status)
            fig.show()
        else:
            print("Could not fetch data and no cache found. Please check internet or run from a local IP.")
            
        time.sleep(120)

if __name__ == "__main__":
    main()
