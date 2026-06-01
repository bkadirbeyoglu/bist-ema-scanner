#!/usr/bin/env python3
"""
morning_snapshot.py — Capture an intraday snapshot of yesterday's signals.

Run this in the morning (Burak runs it ~10:45-11:15 local time) AFTER the
evening scan has logged the previous day's signals. For each ticker that
signalled on the most recent signal_date, it fetches today's 5-minute
intraday bars from Yahoo Finance and records, from market open up to "now":

  open_price   - today's opening price (first 5-min bar's open)
  last_price   - most recent price seen (last bar's close)
  high_so_far  - highest price since open
  low_so_far   - lowest price since open
  volume_sofar - total volume traded since open
  bars         - how many 5-minute bars are in the snapshot
  minutes      - approximate minutes of trading captured (bars * 5)
  run_time     - the local time the snapshot was taken

IMPORTANT — this script ONLY COLLECTS DATA. It does not give buy/sell advice.
The intraday morning signal is unproven: we have no historical intraday data
to test it against. This script builds that history going forward. After a
few weeks, the snapshots can be joined with the d2-d5 outcomes to test
whether any morning feature actually predicts the later rise. Only then would
advice make sense.

Caveats baked in by reality:
  - Yahoo intraday data for BIST is delayed (~15 min) and not always reliable.
  - The first 30-60 minutes of trading is the noisiest part of the day.
  - Treat this as an experiment, not a tool, until the data says otherwise.

Output: appends rows to morning_snapshots_<index>.csv next to this script.
Safe to run more than once on the same day — each run appends a new snapshot
row (with its own run_time), so multiple runs just give multiple snapshots.

Usage (run on your own machine, where yfinance can reach Yahoo):
    python morning_snapshot.py                # xu100 (default)
    python morning_snapshot.py -i xu500
    python morning_snapshot.py --date 2026-05-18   # force a signal_date

Requires: yfinance, pandas  (same environment the scanner already uses)
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    sys.exit("This script needs yfinance and pandas:  pip install yfinance pandas")

HERE = Path(__file__).parent

SNAPSHOT_COLUMNS = [
    "snapshot_date",   # the calendar date the snapshot was taken
    "run_time",        # local clock time of this run (HH:MM:SS)
    "signal_date",     # the signal_date these tickers belong to
    "ticker",
    "signal_close",    # close on the signal day (from signals_log)
    "open_price",      # today's open
    "last_price",      # most recent intraday price
    "high_so_far",     # intraday high since open
    "low_so_far",      # intraday low since open
    "volume_sofar",    # cumulative volume since open
    "bars",            # number of 5-min bars captured
    "minutes",         # approximate minutes of trading captured
    "status",          # OK / NO_DATA / ERROR
]


def load_latest_signals(signals_path: Path, forced_date: str | None):
    """Return (signal_date, [tickers]) for the most recent signal_date in the
    signals log, or for forced_date if given."""
    if not signals_path.exists():
        sys.exit(f"Signals log not found: {signals_path}")
    rows = []
    with signals_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    if not rows:
        sys.exit(f"{signals_path.name} is empty.")
    target = forced_date or max(r["signal_date"] for r in rows)
    todays = [r for r in rows if r["signal_date"] == target]
    return target, todays


def fetch_intraday(ticker: str):
    """Fetch today's 5-minute bars. Returns a dict of snapshot fields, or a
    dict with status NO_DATA / ERROR."""
    try:
        df = yf.download(ticker, period="1d", interval="5m",
                         progress=False, auto_adjust=True, threads=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df is None or df.empty:
            return {"status": "NO_DATA"}
        # Keep only bars from the most recent calendar date present, in case
        # the 1d window straddles two sessions.
        last_day = df.index[-1].date()
        df = df[df.index.date == last_day]
        if df.empty:
            return {"status": "NO_DATA"}
        bars = len(df)
        return {
            "status": "OK",
            "open_price": round(float(df["Open"].iloc[0]), 4),
            "last_price": round(float(df["Close"].iloc[-1]), 4),
            "high_so_far": round(float(df["High"].max()), 4),
            "low_so_far": round(float(df["Low"].min()), 4),
            "volume_sofar": int(df["Volume"].sum()),
            "bars": bars,
            "minutes": bars * 5,
        }
    except Exception as e:
        return {"status": "ERROR"}


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-i", "--index", choices=["xu100", "xu500"], default="xu100",
                   help="Which index's signals to snapshot (default: xu100)")
    p.add_argument("--date", default=None,
                   help="Force a specific signal_date (YYYY-MM-DD) instead of "
                        "the most recent one in the log")
    p.add_argument("--force", action="store_true",
                   help="Skip the safety checks (stale signal_date, duplicate "
                        "run within the same minute) and write the rows anyway.")
    args = p.parse_args()

    signals_path = HERE / f"signals_log_{args.index}.csv"
    out_path = HERE / f"morning_snapshots_{args.index}.csv"

    signal_date, signals = load_latest_signals(signals_path, args.date)
    now = datetime.now()
    snapshot_date = now.strftime("%Y-%m-%d")
    run_time = now.strftime("%H:%M:%S")
    run_minute = run_time[:5]  # HH:MM

    # --- Safety check 1: has this signal_date already been snapshotted on a
    # PREVIOUS calendar day? If so, the signals_log hasn't advanced — likely
    # because the latest scanner run produced no new signals for this index
    # (common on big down days, or in xu100's smaller universe). Warn the
    # user so they know they're capturing a stale signal batch.
    prior_snapshot_dates = set()
    prior_same_minute = set()  # (snapshot_date, run_minute) seen for this signal_date
    if out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("signal_date") == signal_date:
                    prior_snapshot_dates.add(row.get("snapshot_date", ""))
                    rt = row.get("run_time", "")
                    if rt:
                        prior_same_minute.add((row.get("snapshot_date", ""), rt[:5]))

    stale = bool(prior_snapshot_dates - {snapshot_date})
    same_minute = (snapshot_date, run_minute) in prior_same_minute

    print(f"Morning snapshot — {snapshot_date} {run_time}")
    print(f"Signals from {signal_date}: {len(signals)} tickers")
    if snapshot_date == signal_date:
        print("NOTE: snapshot date equals signal date — you may be running")
        print("this before the market has moved past the signal day. The")
        print("snapshot is meant for the day AFTER the signal (d1).")

    if stale and not args.force:
        prior = sorted(prior_snapshot_dates - {snapshot_date})
        print()
        print(f"WARNING: signal_date {signal_date} has already been snapshotted")
        print(f"on: {', '.join(prior)}")
        print(f"The signals_log hasn't advanced — the most recent scan probably")
        print(f"produced no new signals for {args.index}. Capturing this same")
        print(f"signal batch again is usually not useful.")
        print(f"Use --force to snapshot anyway, or --date YYYY-MM-DD for another date.")
        return

    if same_minute and not args.force:
        print()
        print(f"WARNING: a snapshot for signal_date {signal_date} was already")
        print(f"written today during the {run_minute} minute. This looks like")
        print(f"an accidental re-run. Use --force to snapshot anyway, or wait")
        print(f"a minute for a fresh run_time.")
        return

    print("Fetching 5-minute intraday data...\n")

    results = []
    ok = 0
    for n, sig in enumerate(signals, 1):
        ticker = sig["ticker"]
        snap = fetch_intraday(ticker)
        row = {c: "" for c in SNAPSHOT_COLUMNS}
        row.update({
            "snapshot_date": snapshot_date,
            "run_time": run_time,
            "signal_date": signal_date,
            "ticker": ticker,
            "signal_close": sig.get("close", ""),
        })
        row.update({k: v for k, v in snap.items()})
        results.append(row)
        if snap["status"] == "OK":
            ok += 1
            print(f"  {ticker:<12} open={snap['open_price']:>9} "
                  f"last={snap['last_price']:>9} "
                  f"({snap['minutes']} min, {snap['bars']} bars)")
        else:
            print(f"  {ticker:<12} {snap['status']}")

    # Append to the snapshot file (create with header if new)
    is_new = not out_path.exists()
    with out_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SNAPSHOT_COLUMNS)
        if is_new:
            w.writeheader()
        for row in results:
            w.writerow(row)

    print(f"\nWrote {len(results)} snapshot rows ({ok} OK) to {out_path.name}")
    print("Reminder: this is data collection only — no buy advice yet.")


if __name__ == "__main__":
    main()
