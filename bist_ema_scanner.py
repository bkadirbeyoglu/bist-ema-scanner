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
    "d1_open", "d1_close", "d1_pct",
    "d3_open", "d3_close", "d3_pct",
    "d5_open", "d5_close", "d5_pct",
    "d10_open", "d10_close", "d10_pct",
    "max_5d_close", "max_5d_pct",
    # Market-relative reference: XU100 close on signal day and d1 day.
    # Lets us compute "did this signal beat the index?" without re-fetching.
    "xu100_close", "xu100_d1_close",
]

# Yahoo Finance symbol for the BIST 100 index. Used as the market benchmark
# for relative-return analysis.
XU100_SYMBOL = "XU100.IS"


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


def print_results(hits: list[dict], target_date: str | None, label: str = "BIST100",
                  min_break: float = 0.0):
    # Threshold for the ★ "strong breakout" marker. Empirically, this combo
    # has shown a higher win rate than other signals in our outcomes data.
    STRONG_BREAK_PCT = 2.0
    STRONG_VOL_RATIO = 2.0

    header_date = target_date or datetime.now().strftime("%Y-%m-%d")
    print("=" * 95)
    print(f"{label} EMA Breakout Scan  |  Session: {header_date}  |  Scanned at: {datetime.now():%Y-%m-%d %H:%M}")
    print("Close above both EMAs, with either yesterday's close or today's open below the upper EMA")
    if min_break > 0:
        print(f"Marking signals with BREAK% >= {min_break}% (all signals are still logged)")
    print("=" * 95)

    if not hits:
        print("No matches.")
        return

    legend_parts = ["BRK=breakout", "GDN=gap-down recovery", "* = vol >= 1.5x"]
    if min_break > 0:
        legend_parts.append(f"✓ = BREAK% >= {min_break}%")
    legend_parts.append(f"★ = BREAK% >= {STRONG_BREAK_PCT}% AND VOL >= {STRONG_VOL_RATIO}x")
    print(f"{len(hits)} match(es):  [ {'  '.join(legend_parts)} ]\n")

    # Header — leading marker column is 2 chars wide
    print(f"{'':<2} {'TICKER':<10} {'DATE':<12} {'TYPE':<5} "
          f"{'Y-CLOSE':>8} {'Y-EMA20':>9} {'Y-EMA50':>9}  "
          f"{'OPEN':>7} {'CLOSE':>8} {'T-EMA20':>9} {'T-EMA50':>9} {'BREAK%':>8} {'VOL×':>7}")
    print("-" * 122)
    for h in sorted(hits, key=lambda x: -x["break_pct"]):
        vol_marker = "*" if h["vol_ratio"] >= 1.5 else " "
        vol_str = f"{h['vol_ratio']:.2f}{vol_marker}" if h["vol_ratio"] > 0 else "  n/a "
        # Pick the strongest applicable marker. ★ takes priority over ✓.
        if h["break_pct"] >= STRONG_BREAK_PCT and h["vol_ratio"] >= STRONG_VOL_RATIO:
            marker = "★ "
        elif min_break > 0 and h["break_pct"] >= min_break:
            marker = "✓ "
        else:
            marker = "  "
        print(f"{marker}{h['ticker']:<10} {h['date']:<12} {h['trigger']:<5} "
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

    # Step 3: pre-fetch the XU100 index series once. We'll use it to fill
    # the market-relative reference columns (xu100_close, xu100_d1_close).
    # On any given run, today's freshly-added signals get xu100_close right
    # away, and yesterday's signals get their xu100_d1_close.
    xu100_df = None
    if rows:
        try:
            xu100_df = yf.download(XU100_SYMBOL, period="6mo", interval="1d",
                                   progress=False, auto_adjust=True, threads=False)
            if isinstance(xu100_df.columns, pd.MultiIndex):
                xu100_df.columns = xu100_df.columns.get_level_values(0)
        except Exception as e:
            print(f"Warning: could not fetch {XU100_SYMBOL} ({e}); "
                  f"market-relative columns will be left blank.", file=sys.stderr)
            xu100_df = None

    def fill_xu100_for_row(r: dict, signal_date) -> bool:
        """Fill xu100_close and xu100_d1_close for a row if missing. Returns True if changed."""
        if xu100_df is None or xu100_df.empty:
            return False
        changed = False
        # xu100_close on the signal day itself
        if r.get("xu100_close") in ("", None):
            same_day = xu100_df[xu100_df.index.date == signal_date]
            if not same_day.empty:
                r["xu100_close"] = round(float(same_day.iloc[0]["Close"]), 4)
                changed = True
        # xu100_d1_close on the next trading day
        if r.get("xu100_d1_close") in ("", None):
            after_idx = xu100_df[xu100_df.index.date > signal_date]
            if not after_idx.empty:
                r["xu100_d1_close"] = round(float(after_idx.iloc[0]["Close"]), 4)
                changed = True
        return changed

    # Step 4: for each row, try to fill outcome columns from yfinance
    today = datetime.now().date()
    updated_count = 0
    price_cache: dict[str, pd.DataFrame] = {}  # one fetch per ticker per run

    for r in rows:
        # Parse the signal date once — we need it for both XU100 columns and outcome calc
        try:
            signal_date = datetime.strptime(r["signal_date"], "%Y-%m-%d").date()
        except ValueError:
            continue

        # XU100 columns: signal-day value goes in immediately on insert;
        # the d1 value gets filled on the NEXT day's run.
        if fill_xu100_for_row(r, signal_date):
            updated_count += 1

        # Skip rows where every outcome column is already filled. Include
        # the d{n}_open columns in this check — otherwise a row from before
        # we started capturing opens would be skipped here forever.
        if all(r.get(c) not in ("", None) for c in
               ("d1_pct", "d3_pct", "d5_pct", "d10_pct", "max_5d_pct",
                "d1_open", "d3_open", "d5_open", "d10_open")):
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
            if len(after) < n:
                continue
            bar = after.iloc[n - 1]
            # Fill d{n}_open if missing (independent of pct/close — covers
            # back-fill for rows logged before opens were tracked)
            if r.get(f"{label}_open") in ("", None):
                r[f"{label}_open"] = round(float(bar["Open"]), 4)
                changed = True
            # Fill d{n}_close + d{n}_pct if pct is missing
            if r.get(f"{label}_pct") in ("", None):
                close_n = float(bar["Close"])
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
    p.add_argument("-m", "--min-break", type=float, default=0.5,
                   help="Minimum BREAK%% threshold for marking signals as non-marginal "
                        "(default: 0.5). Signals at or above this %% get a marker in the "
                        "output. All signals are still logged. Set to 0 to disable.")
    p.add_argument("--no-log", action="store_true", help="Skip writing to log/outcomes CSVs")
    args = p.parse_args()

    dataset = DATASETS[args.index]

    hits = scan(args.date, dataset["tickers"], dataset["updater"])

    # All signals are written to logs. The min-break threshold only changes
    # the visual marker in the terminal output (>= threshold gets a marker)
    # so we can A/B-evaluate threshold choices on real data later.
    print_results(hits, args.date, dataset["label"], args.min_break)

    if not args.no_log:
        append_signals_log(hits, dataset["signals"])
        update_outcomes(hits, dataset["outcomes"])


if __name__ == "__main__":
    main()
