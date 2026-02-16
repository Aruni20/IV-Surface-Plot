import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
from datetime import datetime
from scipy.interpolate import griddata

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

class NSEOptionChain:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(headers)
        self.init_session()

    def init_session(self):
        """Initializes the session to get cookies from NSE."""
        try:
            self.session.get(BASE_URL, timeout=10)
            self.session.get(LANDING_URL, timeout=10)
            print("Session initialized successfully.")
        except Exception as e:
            print(f"Error initializing session: {e}")

    def fetch_data(self):
        """Fetches the NIFTY option chain data."""
        try:
            response = self.session.get(API_URL, timeout=15)
            
            # Check for empty response (cloud IP block)
            if response.text.strip() == "{}" or response.status_code == 401:
                print("Session expired or block detected. Re-initializing...")
                self.init_session()
                response = self.session.get(API_URL, timeout=15)
            
            if response.text.strip() == "{}":
                return None, None
            
            response.raise_for_status()
            data = response.json()
            
            records = data['records']['data']
            price = data['records']['underlyingValue']
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
            if df.empty:
                return None, price
                
            df['expiry'] = pd.to_datetime(df['expiry'])
            today = pd.Timestamp.now().normalize()
            df['days_to_expiry'] = (df['expiry'] - today).dt.days
            
            return df, price
        except Exception as e:
            print(f"Error fetching data: {e}")
            return None, None

def generate_mock_data():
    """Generates realistic synthetic IV surface data if the live API is blocked."""
    spot = 23500.0
    strikes = np.linspace(spot * 0.90, spot * 1.10, 30)
    expiries = np.array([7, 14, 21, 30, 60, 90])
    rows = []
    for exp in expiries:
        for strike in strikes:
            dist = (strike - spot) / spot
            base_iv = 12 + (100 / (exp + 10))
            iv = base_iv + 500 * (dist ** 2) - 10 * dist 
            rows.append({"strike": strike, "iv": iv, "days_to_expiry": exp})
    return pd.DataFrame(rows), spot

def create_smooth_surface(df, spot, is_mock=False):
    """Interpolates the sparse data into a smooth 3D surface."""
    # Filter for strikes around spot
    df = df[(df.strike > spot * 0.85) & (df.strike < spot * 1.15)]
    
    grid_x, grid_z = np.meshgrid(
        np.linspace(df.strike.min(), df.strike.max(), 100),
        np.linspace(df.days_to_expiry.min(), df.days_to_expiry.max(), 100)
    )

    grid_y = griddata(
        (df.strike, df.days_to_expiry),
        df.iv,
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

    mode_text = "MOCK - API Blocked" if is_mock else "LIVE NSE DATA"
    fig.update_layout(
        title={
            'text': f"NIFTY Implied Volatility Surface ({mode_text})",
            'y':0.95, 'x':0.5, 'xanchor': 'center', 'yanchor': 'top',
            'font': dict(size=24, color='white')
        },
        scene=dict(
            xaxis_title="Strike Price", yaxis_title="IV %", zaxis_title="Days to Expiry",
            xaxis=dict(gridcolor='grey', title_font=dict(color='white'), tickfont=dict(color='white')),
            yaxis=dict(gridcolor='grey', title_font=dict(color='white'), tickfont=dict(color='white')),
            zaxis=dict(gridcolor='grey', title_font=dict(color='white'), tickfont=dict(color='white')),
            bgcolor='rgb(20, 20, 40)'
        ),
        paper_bgcolor='rgb(10, 10, 25)',
        margin=dict(l=0, r=0, b=0, t=100),
        template='plotly_dark'
    )

    return fig

def main():
    print("Initializing NIFTY IV Surface Tracker...")
    nse = NSEOptionChain()
    
    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching data...")
        df, spot = nse.fetch_data()
        
        is_mock = False
        if df is None or df.empty:
            print("API Block detected (common for cloud IPs). Using synthetic fallback...")
            df, spot = generate_mock_data()
            is_mock = True
        else:
            print(f"Live data received: {len(df)} records.")

        fig = create_smooth_surface(df, spot, is_mock)
        fig.show()
        
        print("Surface generated. Waiting 60 seconds...")
        time.sleep(60)

if __name__ == "__main__":
    main()
