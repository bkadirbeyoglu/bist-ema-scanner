"""
dedup_signals.py  —  one-off cleanup for duplicate signal rows
--------------------------------------------------------------
Before the v1.15 dedup fix, re-running the scanner on a later day re-logged
the same trading session under a new scan_date, so some (signal_date, ticker)
pairs ended up with several rows. This removes them, keeping the row with the
most recent scan_date (which carries the most-populated columns). Writes a
.bak copy first. outcomes_*.csv is left alone — it never duplicated.

Usage:
    python dedup_signals.py            # both indices (xu100, xu500)
    python dedup_signals.py -i xu100   # one index
"""
import argparse
import shutil
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


def dedup(idx: str):
    path = HERE / f"signals_log_{idx}.csv"
    if not path.exists():
        print(f"{path.name} not found — skipping.")
        return
    df = pd.read_csv(path)
    before = len(df)
    if "scan_date" in df.columns:
        # most recent scan_date last, keep='last' -> keeps it
        df = df.sort_values("scan_date", kind="stable")
    df = df.drop_duplicates(["signal_date", "ticker"], keep="last")
    # restore chronological order by signal_date for readability
    df = df.sort_values(["signal_date", "ticker"], kind="stable").reset_index(drop=True)
    removed = before - len(df)
    if removed == 0:
        print(f"{path.name}: no duplicates ({before} rows) — unchanged.")
        return
    shutil.copy2(path, path.with_suffix(".csv.bak"))
    df.to_csv(path, index=False)
    print(f"{path.name}: {before} -> {len(df)} rows ({removed} duplicate rows removed). "
          f"Backup: {path.name}.bak")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--index", choices=["xu100", "xu500"], default=None,
                    help="Index to clean. Default: both.")
    args = ap.parse_args()
    for idx in ([args.index] if args.index else ["xu100", "xu500"]):
        dedup(idx)


if __name__ == "__main__":
    main()
