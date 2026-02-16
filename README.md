# NIFTY Live 3D IV Surface 📈

A professional-grade real-time Implied Volatility (IV) surface visualization tool for NIFTY options.

## Features
- **3D Interactive Surface**: Visualize IV across Strikes and Expiries.
- **Smooth Interpolation**: Uses cubic splines to generate a continuous volatility surface.
- **Hybrid Data Mode**: Automatically switches to a mathematical IV model if NSE API blocks cloud IPs, ensuring functionality in all environments.
- **Premium UI**: Built with Streamlit and Plotly with a sleek dark-mode aesthetic.

## Deployment Instructions (Streamlit Cloud)
1. Push this code to a public GitHub repository.
2. Go to [share.streamlit.io](https://share.streamlit.io/).
3. Connect your GitHub account and select this repository.
4. Set the main file path to `app.py`.
5. Deploy!

## Local Setup
1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   streamlit run app.py
   ```
