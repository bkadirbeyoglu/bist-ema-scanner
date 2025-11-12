# scripts/download_sample_data.py
"""Download sample market data for testing strategies"""

import yfinance as yf
import pandas as pd
from pathlib import Path

def download_sample_data():
    """Download 1 year of daily data for testing"""
    
    # Create data directory
    data_dir = Path("data/market")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Symbols to download
    symbols = ["AAPL", "GOOGL", "MSFT", "SPY"]  # SPY as market benchmark
    
    for symbol in symbols:
        print(f"Downloading {symbol}...")
        
        # Download 1 year of daily data
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y", interval="1d")
        
        # Save to CSV
        file_path = data_dir / f"{symbol}.csv"
        df.to_csv(file_path)
        print(f"  Saved to {file_path}")
        print(f"  Shape: {df.shape}, Date range: {df.index[0]} to {df.index[-1]}")
    
    print("\n✅ Sample data downloaded successfully!")

if __name__ == "__main__":
    download_sample_data()