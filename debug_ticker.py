"""
Inspect the latest-day signal status of a single ticker. This tool applies
exactly the same logic as bist_ema_scanner.py:

  Today's close must be above both EMAs, AND at least one of:
    BRK — yesterday's close was below the upper EMA
    GDN — today's open was below the upper EMA

Usage: python debug_ticker.py HALKB
"""
import sys
import pandas as pd
import yfinance as yf

if len(sys.argv) < 2:
    print("Usage: python debug_ticker.py HALKB")
    sys.exit(1)

ticker = sys.argv[1].upper()
if not ticker.endswith(".IS"):
    ticker += ".IS"

# Aynı scanner parametreleri
df = yf.download(ticker, period="6mo", interval="1d",
                 progress=False, auto_adjust=True, threads=False)

if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)
df = df.dropna(subset=["Open", "Close"])

df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

print(f"\n=== {ticker} — Son 7 bar ===\n")
last = df.tail(7)[["Open", "High", "Low", "Close", "EMA20", "EMA50"]]
print(last.round(2).to_string())

today = df.iloc[-1]
yesterday = df.iloc[-2]

y_upper = max(yesterday["EMA20"], yesterday["EMA50"])
t_upper = max(today["EMA20"], today["EMA50"])

print(f"\n=== Sinyal koşulları ===")
print(f"Yesterday close:    {yesterday['Close']:.2f}")
print(f"Yesterday EMA20:    {yesterday['EMA20']:.2f}")
print(f"Yesterday EMA50:    {yesterday['EMA50']:.2f}")
print(f"Yesterday upper:    {y_upper:.2f}")
print()
print(f"Today open:         {today['Open']:.2f}")
print(f"Today close:        {today['Close']:.2f}")
print(f"Today EMA20:        {today['EMA20']:.2f}")
print(f"Today EMA50:        {today['EMA50']:.2f}")
print(f"Today upper:        {t_upper:.2f}")
print()

# Apply the same logic as bist_ema_scanner.matches_signal
close_above_both = (today['Close'] > today['EMA20']
                    and today['Close'] > today['EMA50'])
breakout = yesterday['Close'] < y_upper
gap_down_recovery = today['Open'] < t_upper

print(f"  → close above both EMAs?         {close_above_both}")
print(f"  → BRK (y_close < y_upper)?       {breakout}")
print(f"  → GDN (t_open  < t_upper)?       {gap_down_recovery}")
print()

signal = close_above_both and (breakout or gap_down_recovery)
if signal:
    trigger = "BRK" if breakout else "GDN"
    print(f"SIGNAL: True   (trigger: {trigger})")
else:
    print(f"SIGNAL: False")
