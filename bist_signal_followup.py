#!/usr/bin/env python3
"""
bist_signal_followup.py — Follow up on the most recent completed signal batch.

This script surfaces the most recent signal_date whose d1 has landed, splits
the signals by the sign of their d1 move (up vs down), and shows what XU100
did the same day. It is a plain data view — it does not rank signals or
recommend which to act on.

The signal_date shown is the most recent one with d1 filled — usually one
trading day ago, but it may be older (e.g. if the index had no qualifying
signals on the more recent day). The header shows how many trading days
have passed since the signal was generated.

When to run: after the close, AFTER you've run the scanner that day.
The scanner fills d1 for the previous session's signals; this script then
surfaces them.

Reads from: outcomes_xu*.csv and signals_log_xu*.csv next to this file.

Usage:
    python bist_signal_followup.py                  # XU100 (default)
    python bist_signal_followup.py -i xu030         # XU030 (BIST 30)
    python bist_signal_followup.py -i xu500         # XU500
    python bist_signal_followup.py -d 2026-05-13    # for a specific signal date
"""

import argparse
import csv
import statistics
import sys
from datetime import datetime, date
from pathlib import Path

HERE = Path(__file__).parent

INDEX_FILES = {
    "xu030": {
        "signals": HERE / "signals_log_xu030.csv",
        "outcomes": HERE / "outcomes_xu030.csv",
        "label": "XU030",
    },
    "xu100": {
        "signals": HERE / "signals_log_xu100.csv",
        "outcomes": HERE / "outcomes_xu100.csv",
        "label": "XU100",
    },
    "xu500": {
        "signals": HERE / "signals_log_xu500.csv",
        "outcomes": HERE / "outcomes_xu500.csv",
        "label": "XU500",
    },
}


def latest_signal_date_with_d1(outcomes_path: Path) -> str | None:
    """Return the most recent signal_date that has at least one filled d1_pct.
    This is typically yesterday's session (whose d1 = today's close)."""
    latest: str | None = None
    with outcomes_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("d1_pct") in ("", None):
                continue
            d = row["signal_date"]
            if latest is None or d > latest:
                latest = d
    return latest


def trading_days_since(signal_date_str: str) -> int:
    """Approximate count of trading days from signal_date to today.
    Excludes weekends. Does not exclude public holidays (small distortion)."""
    try:
        a = datetime.strptime(signal_date_str, "%Y-%m-%d").date()
    except ValueError:
        return 0
    b = date.today()
    if b <= a:
        return 0
    days = 0
    from datetime import timedelta
    cur = a
    while cur < b:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days


def load_signals_meta(signals_path: Path) -> dict[tuple[str, str], dict]:
    """Return {(signal_date, ticker): metadata dict}."""
    meta: dict[tuple[str, str], dict] = {}
    with signals_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["signal_date"], row["ticker"])
            meta[key] = row
    return meta


def load_followups(outcomes_path: Path, signals_path: Path, target_date: str):
    """Load signals for target_date from outcomes, joined with signals_log metadata.
    Only returns rows where d1_pct is filled."""
    meta = load_signals_meta(signals_path)
    rows = []
    with outcomes_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["signal_date"] != target_date:
                continue
            if row.get("d1_pct") in ("", None):
                continue
            key = (row["signal_date"], row["ticker"])
            sig = meta.get(key, {})
            rows.append({
                "ticker": row["ticker"],
                "trigger": row.get("trigger", ""),
                "signal_close": float(row["signal_close"]) if row.get("signal_close") else None,
                "d1_open": float(row["d1_open"]) if row.get("d1_open") not in ("", None) else None,
                "d1_close": float(row["d1_close"]) if row.get("d1_close") not in ("", None) else None,
                "d1_pct": float(row["d1_pct"]),
                "xu100_close": float(row["xu100_close"]) if row.get("xu100_close") not in ("", None) else None,
                "xu100_d1_close": float(row["xu100_d1_close"]) if row.get("xu100_d1_close") not in ("", None) else None,
                "at_limit": row.get("at_limit", ""),
                "break_pct": float(sig.get("break_pct") or 0),
                "vol_ratio": float(sig.get("vol_ratio") or 0),
            })
    return rows


def print_section(title: str, rows: list[dict]):
    """Print one bucket of follow-up rows."""
    print(title)
    if not rows:
        print("  (none)")
        print()
        return

    print(f"  {'TICKER':<11} {'TRIG':<4} {'BREAK%':>7} {'VOL':>6} "
          f"{'gap%':>7} {'d1%':>8} {'real_d1%':>10}")
    for r in sorted(rows, key=lambda x: -x["d1_pct"]):
        # gap: signal_close → d1_open
        gap_str = "      ?"
        real_str = "         ?"
        if r["d1_open"] and r["signal_close"]:
            gap = (r["d1_open"] - r["signal_close"]) / r["signal_close"] * 100
            gap_str = f"{gap:>+6.2f}%"
            if r["d1_close"]:
                real = (r["d1_close"] - r["d1_open"]) / r["d1_open"] * 100
                real_str = f"{real:>+9.2f}%"
        limit_flag = " (LIMIT)" if r["at_limit"] == "T" else ""
        print(f"  {r['ticker']:<11} {r['trigger']:<4} "
              f"{r['break_pct']:>+6.2f} {r['vol_ratio']:>5.2f}x "
              f"{gap_str} {r['d1_pct']:>+7.2f}% {real_str}{limit_flag}")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-i", "--index", choices=["xu030", "xu100", "xu500"], default="xu100",
                   help="Which index to check (default: xu100)")
    p.add_argument("-d", "--date",
                   help="Specific signal_date to check (default: latest date with d1 filled)")
    args = p.parse_args()

    dataset = INDEX_FILES[args.index]
    if not dataset["outcomes"].exists():
        sys.exit(f"Outcomes file not found: {dataset['outcomes']}")
    if not dataset["signals"].exists():
        sys.exit(f"Signals log not found: {dataset['signals']}")

    # Determine which signal_date to inspect
    if args.date:
        target_date = args.date
    else:
        target_date = latest_signal_date_with_d1(dataset["outcomes"])
        if not target_date:
            sys.exit(f"No signals with filled d1_pct found in {dataset['outcomes'].name}")

    rows = load_followups(dataset["outcomes"], dataset["signals"], target_date)
    if not rows:
        sys.exit(f"No signals with d1 outcome for signal_date={target_date}")

    # Header — multi-line, labeled for clarity.
    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        weekday = weekday_names[target_dt.weekday()]
    except ValueError:
        weekday = "?"

    today = date.today()
    today_weekday = weekday_names[today.weekday()]

    days_ago = trading_days_since(target_date)
    if days_ago <= 0:
        ago_str = "today"
    elif days_ago == 1:
        ago_str = "1 trading day ago — d1 outcome filled today"
    else:
        ago_str = f"{days_ago} trading days ago — no newer signals available for this index"

    print("=" * 90)
    print(f"{dataset['label']} Signal Follow-Up")
    print(f"  Today:           {today.isoformat()} ({today_weekday})")
    print(f"  Signal date:     {target_date} ({weekday})")
    print(f"  Time elapsed:    {ago_str}")
    print(f"  Signal count:    {len(rows)}")

    # XU100 d1 — the index move from signal day's close to d1's close
    if rows[0]["xu100_close"] and rows[0]["xu100_d1_close"]:
        xu_d1 = (rows[0]["xu100_d1_close"] - rows[0]["xu100_close"]) / rows[0]["xu100_close"] * 100
        print(f"  XU100 d1 move:   {xu_d1:+.2f}% (signal day close → d1 close)")
    print("=" * 90)
    print()

    up = [r for r in rows if r["d1_pct"] > 0]
    down = [r for r in rows if r["d1_pct"] <= 0]

    print_section(
        f"d1 UP ({len(up)} signals — closed above signal price on day 1)",
        up,
    )

    print_section(
        f"d1 DOWN ({len(down)} signals — closed at or below signal price on day 1)",
        down,
    )

    # Summary stats
    print("-" * 90)
    d1_all = [r["d1_pct"] for r in rows]
    print(f"d1 mean: {statistics.mean(d1_all):+.2f}%  median: {statistics.median(d1_all):+.2f}%")
    if rows[0]["xu100_close"] and rows[0]["xu100_d1_close"]:
        xu_d1 = (rows[0]["xu100_d1_close"] - rows[0]["xu100_close"]) / rows[0]["xu100_close"] * 100
        rel = [r["d1_pct"] - xu_d1 for r in rows]
        beat = sum(1 for v in rel if v > 0)
        print(f"Market-relative d1 mean: {statistics.mean(rel):+.2f}%  "
              f"  Beat XU100: {beat}/{len(rows)} = {beat/len(rows)*100:.0f}%")


if __name__ == "__main__":
    main()
