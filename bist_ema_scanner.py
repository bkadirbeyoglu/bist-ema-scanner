"""
BIST EMA Breakout Scanner (v1.1)
--------------------------------
Scans BIST stocks for an EMA breakout pattern. Fires when today's close
is above both EMA20 and EMA50, AND at least one of:

  BRK — Breakout:           Yesterday's close was below the upper EMA.
                            (Covers classic crossovers and gap-up breakouts.)
  GDN — Gap-down recovery:  Today's open was below the upper EMA, but
                            close finished above both. (Yesterday's position
                            doesn't matter here — this catches the case
                            where a trending stock gaps down and recovers.)

The relative order of EMA20 and EMA50 doesn't matter.

Two index datasets are supported: XU100 (default) and XU500. Each has its
own ticker list + log/outcome files so analyses stay distinct.

Refresh ticker lists with:
    python update_index.py -i xu100
    python update_index.py -i xu500

Usage:
    python bist_ema_scanner.py                          # XU100, latest session
    python bist_ema_scanner.py -i xu500                 # XU500
    python bist_ema_scanner.py -d 2026-04-17            # specific session
    python bist_ema_scanner.py -i xu500 --no-log        # no logging

Requirements:
    pip install yfinance pandas
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path
import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
STALE_DAYS = 100  # BIST 100 rebalances quarterly — warn if CSV is older than this

# Two separate datasets: XU100 (default) or XU500. Each has its own ticker
# list + log/outcome files so analyses stay distinct.
DATASETS = {
    "xu100": {
        "tickers": HERE / "xu100.csv",
        "signals": HERE / "signals_log_xu100.csv",
        "outcomes": HERE / "outcomes_xu100.csv",
        "label": "XU100",
        "updater": "update_index.py -i xu100",
    },
    "xu500": {
        "tickers": HERE / "xu500.csv",
        "signals": HERE / "signals_log_xu500.csv",
        "outcomes": HERE / "outcomes_xu500.csv",
        "label": "XU500",
        "updater": "update_index.py -i xu500",
    },
}

SIGNAL_COLUMNS = [
    "scan_date", "signal_date", "ticker", "trigger",
    "y_close", "y_ema20", "y_ema50",
    "open", "close", "t_ema20", "t_ema50",
    "break_pct", "vol_ratio",
]

OUTCOME_COLUMNS = [
    "signal_date", "ticker", "trigger", "signal_close",
    "d1_close", "d1_pct",
    "d3_close", "d3_pct",
    "d5_close", "d5_pct",
    "d10_close", "d10_pct",
    "max_5d_close", "max_5d_pct",
]


def load_tickers(tickers_path: Path, updater_hint: str) -> list[str]:
    """Load Yahoo Finance symbols from the given CSV."""
    if not tickers_path.exists():
        sys.exit(
            f"{tickers_path.name} not found next to this script.\n"
            f"Run:  python {updater_hint}"
        )

    age_days = (time.time() - tickers_path.stat().st_mtime) / 86400
    if age_days > STALE_DAYS:
        print(
            f"Warning: {tickers_path.name} is {int(age_days)} days old. "
            f"Consider re-running {updater_hint}.",
            file=sys.stderr,
        )

    with tickers_path.open(encoding="utf-8") as f:
        symbols = [row["yf_symbol"] for row in csv.DictReader(f) if row.get("yf_symbol")]

    if not symbols:
        sys.exit(f"{tickers_path.name} has no usable 'yf_symbol' rows.")
    return symbols


def fetch_history(ticker: str, period: str = "6mo") -> pd.DataFrame | None:
    """Fetch daily OHLC for a ticker. Returns None if data is missing.
    auto_adjust=True returns Open/High/Low/Close already adjusted for splits
    and dividends, which is what we want for EMA-based technical signals."""
    df = yf.download(
        ticker,
        period=period,
        interval="1d",
        progress=False,
        auto_adjust=True,
        threads=False,
    )
    if df is None or df.empty:
        return None
    # yfinance sometimes returns a MultiIndex even for single tickers
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna(subset=["Open", "Close"])


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    # 20-day average volume, shifted by 1 so today's volume is compared to
    # the average of the PREVIOUS 20 days (today's volume isn't in its own avg).
    df["VOL_AVG20"] = df["Volume"].rolling(window=20).mean().shift(1)
    return df


def matches_signal(today: pd.Series, yesterday: pd.Series) -> bool:
    """
    Fires when today's close is above BOTH EMAs, AND at least one of:

      BRK — Breakout: yesterday's close was below the upper EMA
            (today's open can be below OR above the EMAs — includes gap-ups)
      GDN — Gap-down recovery: today's open was below the upper EMA
            (even if yesterday closed above it), and close finished above both

    Together these cover: classic crossover, gap-up breakout after a close
    below the line, and intraday recovery from a weak open.
    """
    y_upper = max(yesterday["EMA20"], yesterday["EMA50"])
    t_upper = max(today["EMA20"], today["EMA50"])

    close_above_both = (today["Close"] > today["EMA20"]
                        and today["Close"] > today["EMA50"])
    if not close_above_both:
        return False

    breakout = yesterday["Close"] < y_upper
    gap_down_recovery = today["Open"] < t_upper
    return bool(breakout or gap_down_recovery)


def scan(target_date: str | None, tickers_path: Path, updater_hint: str) -> list[dict]:
    tickers = load_tickers(tickers_path, updater_hint)
    hits = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        sys.stdout.write(f"\r[{i:>3}/{total}] {ticker:<10}  ")
        sys.stdout.flush()
        try:
            df = fetch_history(ticker)
            if df is None or len(df) < 50:
                continue

            df = add_indicators(df)

            if target_date:
                dates = df.index.strftime("%Y-%m-%d").tolist()
                if target_date not in dates:
                    continue
                idx = dates.index(target_date)
                if idx == 0:  # need a prior bar for yesterday's EMAs
                    continue
                today = df.iloc[idx]
                yesterday = df.iloc[idx - 1]
            else:
                today = df.iloc[-1]
                yesterday = df.iloc[-2]

            if matches_signal(today, yesterday):
                t_upper = max(float(today["EMA20"]), float(today["EMA50"]))
                y_upper = max(float(yesterday["EMA20"]), float(yesterday["EMA50"]))
                close = float(today["Close"])
                vol = float(today["Volume"])
                vol_avg = float(today["VOL_AVG20"]) if pd.notna(today["VOL_AVG20"]) else 0.0
                vol_ratio = vol / vol_avg if vol_avg > 0 else 0.0
                # Classify: BRK (yesterday closed below upper) takes priority;
                # otherwise GDN (today's open was below upper).
                trigger = "BRK" if float(yesterday["Close"]) < y_upper else "GDN"
                hits.append({
                    "ticker": ticker,
                    "date": today.name.strftime("%Y-%m-%d") if hasattr(today.name, "strftime") else str(today.name),
                    "trigger": trigger,
                    "y_close": float(yesterday["Close"]),
                    "y_ema20": float(yesterday["EMA20"]),
                    "y_ema50": float(yesterday["EMA50"]),
                    "open": float(today["Open"]),
                    "close": close,
                    "t_ema20": float(today["EMA20"]),
                    "t_ema50": float(today["EMA50"]),
                    "break_pct": (close - t_upper) / t_upper * 100,
                    "vol_ratio": vol_ratio,
                })
        except Exception as e:
            sys.stdout.write(f"\r[{i:>3}/{total}] {ticker:<10}  ERROR: {e}\n")
    sys.stdout.write("\r" + " " * 60 + "\r")
    return hits


def print_results(hits: list[dict], target_date: str | None, label: str = "BIST100"):
    header_date = target_date or datetime.now().strftime("%Y-%m-%d")
    print("=" * 95)
    print(f"{label} EMA Breakout Scan  |  Session: {header_date}  |  Scanned at: {datetime.now():%Y-%m-%d %H:%M}")
    print("Close above both EMAs, with either yesterday's close or today's open below the upper EMA")
    print("=" * 95)

    if not hits:
        print("No matches.")
        return

    print(f"{len(hits)} match(es):  [ BRK=breakout  GDN=gap-down recovery  * = vol >= 1.5x ]\n")
    print(f"{'TICKER':<10} {'DATE':<12} {'TYPE':<5} "
          f"{'Y-CLOSE':>8} {'Y-EMA20':>9} {'Y-EMA50':>9}  "
          f"{'OPEN':>7} {'CLOSE':>8} {'T-EMA20':>9} {'T-EMA50':>9} {'BREAK%':>8} {'VOL×':>7}")
    print("-" * 120)
    for h in sorted(hits, key=lambda x: -x["break_pct"]):
        vol_marker = "*" if h["vol_ratio"] >= 1.5 else " "
        vol_str = f"{h['vol_ratio']:.2f}{vol_marker}" if h["vol_ratio"] > 0 else "  n/a "
        print(f"{h['ticker']:<10} {h['date']:<12} {h['trigger']:<5} "
              f"{h['y_close']:>8.2f} {h['y_ema20']:>9.2f} {h['y_ema50']:>9.2f}  "
              f"{h['open']:>7.2f} {h['close']:>8.2f} {h['t_ema20']:>9.2f} {h['t_ema50']:>9.2f} "
              f"{h['break_pct']:>+7.2f}% {vol_str:>7}")


def append_signals_log(hits: list[dict], signals_path: Path):
    """Append today's signals to the given signals CSV (never overwrites).
    Skips rows that match an existing (scan_date, signal_date, ticker)
    triple — safe to re-run the scanner multiple times on the same day."""
    if not hits:
        return
    scan_date = datetime.now().strftime("%Y-%m-%d")

    # Load existing keys to avoid duplicates
    existing_keys: set[tuple[str, str, str]] = set()
    if signals_path.exists():
        with signals_path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing_keys.add((row["scan_date"], row["signal_date"], row["ticker"]))

    new_rows = [h for h in hits
                if (scan_date, h["date"], h["ticker"]) not in existing_keys]
    if not new_rows:
        print(f"Signals already logged today — nothing new to append")
        return

    file_exists = signals_path.exists()
    with signals_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SIGNAL_COLUMNS)
        if not file_exists:
            w.writeheader()
        for h in new_rows:
            w.writerow({
                "scan_date": scan_date,
                "signal_date": h["date"],
                "ticker": h["ticker"],
                "trigger": h["trigger"],
                "y_close": round(h["y_close"], 4),
                "y_ema20": round(h["y_ema20"], 4),
                "y_ema50": round(h["y_ema50"], 4),
                "open": round(h["open"], 4),
                "close": round(h["close"], 4),
                "t_ema20": round(h["t_ema20"], 4),
                "t_ema50": round(h["t_ema50"], 4),
                "break_pct": round(h["break_pct"], 4),
                "vol_ratio": round(h["vol_ratio"], 4),
            })
    print(f"Logged {len(new_rows)} signal(s) to {signals_path.name}")


def update_outcomes(new_hits: list[dict], outcomes_path: Path):
    """
    Add new signals as rows (with blank outcome cells), then fill in
    outcome columns for any existing rows that now have enough data.
    """
    # Step 1: load existing rows (if any)
    rows: list[dict] = []
    if outcomes_path.exists():
        with outcomes_path.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    # Step 2: add new signals (skip if already present)
    existing_keys = {(r["signal_date"], r["ticker"]) for r in rows}
    for h in new_hits:
        key = (h["date"], h["ticker"])
        if key in existing_keys:
            continue
        rows.append({
            "signal_date": h["date"],
            "ticker": h["ticker"],
            "trigger": h["trigger"],
            "signal_close": round(h["close"], 4),
            **{col: "" for col in OUTCOME_COLUMNS if col not in
               ("signal_date", "ticker", "trigger", "signal_close")},
        })

    # Step 3: for each row with unfilled outcomes, try to fill them from yfinance
    today = datetime.now().date()
    updated_count = 0
    price_cache: dict[str, pd.DataFrame] = {}  # one fetch per ticker per run

    for r in rows:
        # Skip rows where all outcome cells are filled already
        if all(r.get(c) not in ("", None) for c in
               ("d1_pct", "d3_pct", "d5_pct", "d10_pct", "max_5d_pct")):
            continue

        try:
            signal_date = datetime.strptime(r["signal_date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        days_elapsed = (today - signal_date).days
        if days_elapsed < 1:
            continue  # no outcome yet, not even one day later

        ticker = r["ticker"]
        if ticker not in price_cache:
            # Fetch ~3 weeks after signal to cover d10 with weekends/holidays
            df = yf.download(ticker, period="2mo", interval="1d",
                             progress=False, auto_adjust=True, threads=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            price_cache[ticker] = df

        df = price_cache[ticker]
        if df is None or df.empty:
            continue

        # Find rows AFTER signal_date
        after = df[df.index.date > signal_date]
        if after.empty:
            continue

        try:
            signal_close = float(r["signal_close"])
        except (ValueError, TypeError):
            continue

        changed = False
        for n, label in [(1, "d1"), (3, "d3"), (5, "d5"), (10, "d10")]:
            if r.get(f"{label}_pct") in ("", None) and len(after) >= n:
                close_n = float(after.iloc[n - 1]["Close"])
                r[f"{label}_close"] = round(close_n, 4)
                r[f"{label}_pct"] = round((close_n - signal_close) / signal_close * 100, 4)
                changed = True

        # max over the first 5 bars after signal
        if r.get("max_5d_pct") in ("", None) and len(after) >= 5:
            window = after.iloc[:5]
            max_close = float(window["Close"].max())
            r["max_5d_close"] = round(max_close, 4)
            r["max_5d_pct"] = round((max_close - signal_close) / signal_close * 100, 4)
            changed = True

        if changed:
            updated_count += 1

    # Step 4: write everything back
    with outcomes_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTCOME_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({col: r.get(col, "") for col in OUTCOME_COLUMNS})

    if updated_count:
        print(f"Updated outcomes for {updated_count} older signal(s)")


def main():
    p = argparse.ArgumentParser(description="BIST EMA scanner")
    p.add_argument("-d", "--date",
                   help="Session date to evaluate (YYYY-MM-DD). Defaults to the latest available session.")
    p.add_argument("-i", "--index", choices=list(DATASETS.keys()), default="xu100",
                   help="Which BIST index to scan. Default: xu100. "
                        "Each index has its own log/outcome files.")
    p.add_argument("--no-log", action="store_true", help="Skip writing to log/outcomes CSVs")
    args = p.parse_args()

    dataset = DATASETS[args.index]

    hits = scan(args.date, dataset["tickers"], dataset["updater"])
    print_results(hits, args.date, dataset["label"])

    if not args.no_log:
        append_signals_log(hits, dataset["signals"])
        update_outcomes(hits, dataset["outcomes"])


if __name__ == "__main__":
    main()
