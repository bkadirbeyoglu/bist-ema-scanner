"""
edge_monitor.py
---------------
Forward "house edge" monitor for the H-ENTRY-ABS setup.

The casino discipline: freeze the rule, then verify the edge stays positive
over many forward trades. This script logs every setup-qualifying signal as a
paper trade, fills the outcome when d5 resolves, and reports cumulative EV
("hold %") split into a backtest phase (in-sample, before the tracking line)
and a forward phase (out-of-sample, on/after the tracking line).

SETUP (H-ENTRY-ABS), frozen:
    qualify : trigger == 'GDN'  OR  ema_gap_pct > 0   (post-cross)
    entry   : ~d2 open  (proxied by d1 close)
    exit    : d5 close
    hold    : to d5, no fast-cut
    return  : absolute (raw), costs EXCLUDED (per user preference)

REGIME GATE (live-computable, knowable before entry), context only — NOT a
filter yet (in-sample, single-instance confound; we are watching whether the
"index above EMA20 -> setup fades" direction holds forward):
    idx_above20 : XU100 close > its own EMA20, as of signal_date
    idx_ret5    : XU100 trailing 5-day return  (%)
    idx_ret10   : XU100 trailing 10-day return (%)

Two-file convention: reads the existing signals_log / outcomes CSVs and
writes a paper-ledger snapshot (append/upsert on signal_date x ticker,
last-write-wins).

Usage:
    python edge_monitor.py                 # XU100 (default)
    python edge_monitor.py -i xu030        # XU030 (BIST 30)
    python edge_monitor.py -i xu500        # XU500
    python edge_monitor.py --track-start 2026-06-24
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_TRACK_START = "2026-06-24"   # the out-of-sample line; freeze the rule here


def build_index_series(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct the XU100 daily series from the per-signal index close."""
    idx = (outcomes.groupby("signal_date").xu100_close.first()
           .reset_index().sort_values("signal_date").reset_index(drop=True))
    idx["ema20"] = idx.xu100_close.ewm(span=20, adjust=False).mean()
    idx["idx_ret5"] = idx.xu100_close.pct_change(5) * 100
    idx["idx_ret10"] = idx.xu100_close.pct_change(10) * 100
    idx["idx_above20"] = idx.xu100_close > idx.ema20
    return idx[["signal_date", "idx_above20", "idx_ret5", "idx_ret10"]]


def build_ledger(signals: pd.DataFrame, outcomes: pd.DataFrame,
                 track_start: str) -> pd.DataFrame:
    sig = signals.drop_duplicates(["signal_date", "ticker"])
    df = outcomes.merge(
        sig[["signal_date", "ticker", "trigger", "ema_gap_pct", "vol_ratio",
             "days_above_ema20"]],
        on=["signal_date", "ticker"], how="left", suffixes=("", "_sig"))

    # frozen setup definition
    trig = df["trigger"].fillna(df.get("trigger_sig"))
    df["setup"] = (trig == "GDN") | (df["ema_gap_pct"] > 0)
    df["setup_tag"] = np.where(trig == "GDN", "GDN",
                       np.where(df["ema_gap_pct"] > 0, "post-cross", ""))

    # --- ticker track record (computed over ALL signals, not just setup) ---
    # prior_alpha = mean rel_d5 of this ticker's PRIOR resolved signals (no lookahead).
    # expanding().mean() after shift() ignores NaN, so it averages only prior *resolved*
    # signals; expanding().count() gives how many priors that is.
    df["rel_all"] = df["d5_pct"] - (df["xu100_d5_close"] / df["xu100_close"] - 1) * 100
    df = df.sort_values(["ticker", "signal_date"])
    df["ticker_prior_alpha"] = df.groupby("ticker")["rel_all"].transform(
        lambda x: x.shift().expanding().mean())
    df["prior_n"] = df.groupby("ticker")["rel_all"].transform(
        lambda x: x.shift().expanding().count())

    led = df[df["setup"]].copy()

    # paper-trade return: entry ~d2 open (= d1 close), exit d5 close
    led["abs_ret"] = ((1 + led["d5_pct"] / 100) / (1 + led["d1_pct"] / 100) - 1) * 100
    # relative (alpha) over the same horizon: stock d5 minus index d5 (from signal_close)
    led["rel_ret"] = led["d5_pct"] - (led["xu100_d5_close"] / led["xu100_close"] - 1) * 100
    led["resolved"] = led["d5_pct"].notna()

    # --- entry-timing: captured alpha depends on WHEN you enter (Burak can act on d1) ---
    sc = pd.to_numeric(led["signal_close"], errors="coerce")
    d1o = pd.to_numeric(led["d1_open"], errors="coerce")
    d5c = sc * (1 + led["d5_pct"] / 100)
    led["gap_pct"] = (d1o / sc - 1) * 100          # overnight gap, visible AT d1 open (no lookahead)
    # captured rel entering at d1 OPEN (captures the d1 move): (stock d1o->d5) - (index d1o->d5)
    led["rel_d1open"] = (d5c / d1o - 1 - (led["xu100_d5_close"] / led["xu100_d1_open"] - 1)) * 100
    # captured rel entering at d2 OPEN = d1 close (skips d1): (stock d1c->d5) - (index d1c->d5)
    led["rel_d2open"] = ((1 + led["d5_pct"] / 100) / (1 + led["d1_pct"] / 100) - 1
                         - (led["xu100_d5_close"] / led["xu100_d1_close"] - 1)) * 100
    # gap-conditional rule: enter d1 open if gap<=0 (discount), else wait for d2 open
    led["rel_gaprule"] = np.where(led["gap_pct"] <= 0, led["rel_d1open"], led["rel_d2open"])

    # candidate dimensions to watch forward
    led["da20"] = pd.to_numeric(led["days_above_ema20"], errors="coerce")  # H-TREND-PERSIST
    led = led.merge(build_index_series(outcomes), on="signal_date", how="left")
    led["idx_weak"] = led["idx_above20"] == False  # H-SYNTH: index below its EMA20

    # phase line
    led["phase"] = np.where(led["signal_date"] >= track_start, "forward", "backtest")

    cols = ["signal_date", "ticker", "setup_tag", "phase",
            "idx_above20", "idx_weak", "idx_ret5", "idx_ret10", "da20",
            "ticker_prior_alpha", "prior_n",
            "gap_pct", "rel_d1open", "rel_d2open", "rel_gaprule",
            "d1_pct", "d5_pct", "abs_ret", "rel_ret", "resolved"]
    return led[cols].sort_values(["signal_date", "ticker"]).reset_index(drop=True)


def upsert(ledger: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Append/upsert on signal_date x ticker, last-write-wins."""
    if path.exists():
        old = pd.read_csv(path)
        combined = pd.concat([old, ledger], ignore_index=True)
        combined = combined.drop_duplicates(["signal_date", "ticker"], keep="last")
    else:
        combined = ledger
    combined = combined.sort_values(["signal_date", "ticker"]).reset_index(drop=True)
    combined.to_csv(path, index=False)
    return combined


def _hold(sub: pd.DataFrame) -> str:
    a = sub["abs_ret"].dropna().to_numpy(float)
    r = sub["rel_ret"].dropna().to_numpy(float)
    if len(a) == 0:
        return "  (no resolved trades yet)"
    sh = a.mean() / a.std() if a.std() > 0 else float("nan")
    return (f"ABS {a.mean():+5.2f}% | REL {r.mean():+5.2f}% | n {len(a):4d} | "
            f"win %{100 * (a > 0).mean():2.0f} | Sharpe {sh:+.2f} | cumABS {a.sum():+6.1f}%")


def report(ledger: pd.DataFrame, track_start: str):
    res = ledger[ledger.resolved]
    bt, fw = res[res.phase == "backtest"], res[res.phase == "forward"]
    line = "=" * 82
    print(line)
    print(f"  EDGE MONITOR — H-ENTRY-ABS   (tracking line: {track_start})")
    print(f"  setup: GDN or post-cross | entry ~d2 open | exit d5 close | abs+rel, no costs")
    print(line)
    print(f"  BACKTEST (in-sample, < {track_start}):  {_hold(bt)}")
    print(f"  FORWARD  (out-of-sample, >= line):     {_hold(fw)}")
    print(f"  unresolved setup trades on the books: {len(ledger[~ledger.resolved])}")

    print("\n  -- watched candidate dimensions (do these hold forward?) --")
    for ph, g in [("backtest", bt), ("forward", fw)]:
        if not len(g):
            continue
        cells = [
            ("idx>EMA20 (strong) ", g[g.idx_above20 == True]),
            ("idx<=EMA20 (weak)  ", g[g.idx_weak == True]),
            ("da20>=4 (persist)  ", g[g.da20 >= 4]),
            ("H-SYNTH da20>=4&wk ", g[(g.da20 >= 4) & (g.idx_weak == True)]),
            ("ticker rec >0       ", g[g.ticker_prior_alpha > 0]),
            ("ticker rec <0       ", g[g.ticker_prior_alpha < 0]),
            ("ticker rec >0 (n>=3)", g[(g.ticker_prior_alpha > 0) & (g.prior_n >= 3)]),
        ]
        for label, sub in cells:
            if len(sub):
                print(f"    {ph:8s} {label}: {_hold(sub)}")

    # -- entry-timing: captured alpha by WHEN you enter (Burak can act on d1) --
    def _avg(col, sub):
        v = sub[col].dropna().to_numpy(float)
        return f"REL {v.mean():+5.2f}% | n {len(v):4d}" if len(v) else "(none)"
    print("\n  -- entry timing: captured REL by entry point (d1 acting allowed) --")
    for ph, g in [("backtest", bt), ("forward", fw)]:
        if not len(g):
            continue
        print(f"    {ph:8s} d1-open all      : {_avg('rel_d1open', g)}")
        print(f"    {ph:8s} d1-open if gap<=0: {_avg('rel_d1open', g[g.gap_pct <= 0])}")
        print(f"    {ph:8s} d2-open (default): {_avg('rel_d2open', g)}")
        print(f"    {ph:8s} gap rule         : {_avg('rel_gaprule', g)}  (gap<=0->d1open, gap>0->d2)")

    print(line)
    print("  NOTE: forward is the real test. Edge unproven until forward ABS *and* REL")
    print("  stay positive across regimes. Big ABS with flat REL = mostly beta, not edge.")
    print("  If forward decays to ~0, the backtest was a sample artifact -- stop.")
    print(line)


def main():
    ap = argparse.ArgumentParser(description="Forward house-edge monitor for H-ENTRY-ABS.")
    ap.add_argument("-i", "--index", default="xu100", choices=["xu030", "xu100", "xu500"])
    ap.add_argument("--track-start", default=DEFAULT_TRACK_START,
                    help="Out-of-sample line (YYYY-MM-DD). Freeze the rule here.")
    ap.add_argument("--signals", type=Path, default=None)
    ap.add_argument("--outcomes", type=Path, default=None)
    ap.add_argument("--ledger", type=Path, default=None)
    args = ap.parse_args()

    sig_path = args.signals or HERE / f"signals_log_{args.index}.csv"
    out_path = args.outcomes or HERE / f"outcomes_{args.index}.csv"
    led_path = args.ledger or HERE / f"paper_ledger_{args.index}.csv"

    signals = pd.read_csv(sig_path)
    outcomes = pd.read_csv(out_path)

    ledger = build_ledger(signals, outcomes, args.track_start)
    ledger = upsert(ledger, led_path)
    report(ledger, args.track_start)
    print(f"\nLedger written to {led_path} ({len(ledger)} setup trades, "
          f"{int(ledger.resolved.sum())} resolved).")


if __name__ == "__main__":
    main()
