"""
BIST EMA Breakout Scanner (v1.13)
---------------------------------
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

v1.2 changes:
    - Outcome days (d1..d10) are now anchored to explicit BIST trading
      dates via bist_calendar.next_trading_day(), not to "the next row
      yfinance returned". This fixes a class of bugs where a holiday
      gap (e.g. Kurban Bayramı) could cause d1 to land on a closed day
      and silently inherit signal-day values as a placeholder.
    - Corrupt placeholder rows (d1_open == signal_close AND d1_high/low
      == 0) are detected on each update_outcomes pass, cleared, and
      re-fetched from yfinance.
    - Requires bist_calendar.py + bist_holidays.txt next to this file.

v1.3 changes:
    - Second corruption pattern caught: when d2..d_k_pct are all exactly
      equal to d1_pct (consequence of yfinance forward-filling closed
      holiday days and the pre-v1.2 positional reader treating those
      duplicate bars as legitimate d2..d_k). Those cells are now
      detected, cleared, and refetched. Also clears max_5d/min_5d for
      affected rows since they were computed over a corrupt window.

v1.4 changes:
    - Chain corruption detector generalized. Earlier versions only
      caught runs anchored at d1. v1.4 catches any run of 3+ identical
      consecutive d_n_pct values — including the "d3..d5 == d2" pattern
      that shows up when the holiday gap falls between d2 and d3 of an
      older signal (e.g. May 22 Friday signals whose d3 should be the
      post-bayram session). The first occurrence in the run is kept as
      the genuine value; duplicates from that point are cleared and
      refetched against BIST calendar dates.

v1.5 changes:
    - Future-date guard in the per-day fill loop: if d_n's calendar
      date is after today, stop. Prevents yfinance from poisoning
      outcome cells with placeholder bars for sessions that haven't
      happened yet.
    - Stale-bar guard: rejects any bar with zero volume AND zero
      intraday range (high == low). These are forward-fill artifacts
      yfinance has been observed to return; trusting them would refill
      cells that v1.4's detector just cleared.
    - Generalized zero-movement placeholder check now applies to d2..d5
      (not just d1), so the older corrupt fingerprint of pct=high=low=0
      is cleaned out wherever it appears.

v1.6 changes:
    - Two new derived columns: signal_close_in_range and
      d1_close_in_range. Both are [0, 1] positions of a day's close
      within its intraday range:
          (close - low) / (high - low)
      Empty when high == low (limit-locked, no range).
      signal_close_in_range is signal-time information (entry filter).
      d1_close_in_range is post-entry (hold/exit signal). The d1
      version is the one validated by analysis: monotonic d5 edge
      across quintiles with a +5.61pp spread.
    - scan() now captures signal-day high/low so the new outcome row
      can store signal_close_in_range at seed time.
    - update_outcomes() backfills both columns for existing rows:
      signal_close_in_range from the price cache, d1_close_in_range
      from the already-stored d1_high_pct / d1_low_pct / d1_pct.

v1.7 changes:
    - New split_suspect flag column. Set to "T" when |d1_high_pct| or
      |d1_low_pct| exceeds 30%, the fingerprint of a yfinance auto-adjust
      scale shift between when signal_close was captured and when d1
      OHLC was fetched (i.e., the underlying stock split or had a major
      corporate action). Affected rows have inconsistent scales across
      their own columns and should be excluded from analysis.
    - d1_close_in_range backfill now clamps results to [0, 1]; values
      that would fall outside that range (the scale-mismatch fingerprint)
      stay empty instead of being written as nonsense numbers.

v1.8 changes:
    - split_suspect detection broadened. v1.7 used a single threshold
      (|d1_high_pct| or |d1_low_pct| > 30%) and caught only the most
      extreme cases. v1.8 adds a sharper test: d1_pct must lie within
      [d1_low_pct, d1_high_pct] — close can't be outside the day's
      high/low range. The two tests run together; either firing marks
      the row T and clears d1_close_in_range (which would have been
      meaningless on inconsistent inputs).

v1.9 changes:
    - Two new signal-time columns: days_above_ema20 and days_above_ema50.
      Each counts consecutive trading days ending at signal_date
      (inclusive) where close finished above the named EMA. The signal
      day itself always counts as 1 because the trigger requires it.
        days_above_ema20  -> short-to-mid trend age. Distinguishes a
                             fresh cross-above (=1) from a stock that's
                             been riding above EMA20 for weeks (=15+).
        days_above_ema50  -> longer-term trend age. EMA50 acts as the
                             structural trend boundary.
      The difference (ema50_age minus ema20_age) reveals mature trends
      with shallow recent pullbacks: ema50_age=30, ema20_age=2 means a
      long-running uptrend that just reclaimed EMA20 after a brief dip.
      Both columns appear in signals_log and outcomes; the outcome row
      gets them seeded at signal time since the values are signal-day
      info that won't change as outcomes accumulate.

v1.10 changes:
    - New signal-time column: avg_tl_volume_20d. Twenty-day rolling mean
      of (close * volume), shifted by 1 so it reflects the average TL
      (Turkish lira) volume traded over the 20 sessions PRIOR to the
      signal day. Same convention as VOL_AVG20.
        Why TL volume, not share volume? Liquidity is monetary, not
        share-count. 1M shares of a 1 TL stock (1M TL/day) is very
        different liquidity from 1M shares of a 1000 TL stock (1B TL).
        TL volume is the industry-standard liquidity measure.
        Why a filter? Edge-cases like ISKPL (45 minutes without a single
        trade during BIST hours) silently dilute analysis cohorts.
        Filtering out the lowest decile by TL volume sharpens the
        statistics for the rest. The value is stored raw (in TL); analysis
        side decides where to put the cutoff.
      Stored in both signals_log and outcomes, seeded at signal time.

v1.11 changes:
    - Four new outcome columns: xu100_d2_close, xu100_d3_close,
      xu100_d4_close, xu100_d5_close. The XU100 index close for each
      of d2..d5 (anchored to the calendar, NOT yfinance row order, so
      bayram and weekend gaps are handled correctly).
        Why? Previously rel_d1 = d1_pct - mkt_d1 was the only
        market-relative return we could compute. d2..d5 outcomes were
        absolute returns — partly market drift, partly signal alpha,
        no way to separate. Many of our composite edges (Cuma+ema>2
        d5 +5.47%, super winner d5 trajectories, V-recovery patterns)
        were absolute. The new columns let analyses compute rel_d2..d5
        and isolate true signal alpha from market beta.
        The opens of d2..d5 are intentionally NOT stored — we use them
        as a once-per-day base for cumulative return (signal_close to
        each subsequent close); the opens would be unused. d1 keeps
        both open and close (existing schema, preserved for backward
        compatibility).
      Filled progressively by update_outcomes() each day as the d2..d5
      trading days actually occur, in the same way d1_close was already
      being filled — empty cells on existing rows get populated on the
      next scan that runs after that trading day.

v1.12 changes:
    - KAP disclosure context enrichment via optional kap_lookup.py module.
      Fetches ALL disclosure types (ÖDA, CA, FR, DUY, DG, FON) — not just
      ÖDA — since financial reports, corporate actions, and general
      announcements can all carry information relevant to a breakout.
      After scan() detects hits, a single KAP API call covering the past
      ~14 calendar days is made; each hit is then filtered against its
      ticker's disclosures and tagged with five new context columns:
        kap_count_14d         — total disclosures in past 14 calendar days
                                (bedelsiz sermaye artırımı = mekanik split
                                 duyuruları hariç tutulur — fiyat jumps
                                 mislead the count)
        kap_oda_count_14d     — disclosureType == "ODA" only (headline
                                category, surfaced separately for filter)
        kap_signal_day        — disclosures on signal day itself
        kap_type_breakdown    — compact "ODA:3 CA:2 FR:1" summary, using
                                KAP's six native disclosureTypes (ODA
                                first when present, others in fixed order)
        kap_category_breakdown — compact "YENI_IS:2 ESAS_SOZ:1 ..." summary
                                using mechanical Turkish-aware title
                                pattern matching (classify_category() in
                                kap_lookup.py), sorted by count desc then
                                alphabetical. KAP's six types are too
                                coarse — "ODA" alone covers YENI_IS through
                                UST_YONETIM through TEMETTU — so this
                                second breakdown surfaces title sub-types
                                for easier downstream filtering.
      No edge classification or tier labelling at scan time. Reasoning:
      our current hypotheses (YENI_IS pozitif, UST_YONETIM negatif, etc.)
      come from a 3-4 month sample and are not yet validated on
      out-of-sample data. Baking them into the operational pipeline
      would create circularity when we later try to confirm them.
      Counts are mechanical; category-to-outcome mapping is a separate
      analysis step on accumulated signals_log × kap_*.csv.
      print_results() prints two indented lines per signal when both
      breakdowns are present:
        └─ KAP:      ODA:3 CA:1 FR:1 [signal-günü: 2]
        └─ Kategori: YENI_IS:2 ESAS_SOZ:1 OZEL_DURUM:1
      The Kategori line is omitted when only OTHER classifications exist
      (no useful information). The signal-day tag appears only when at
      least one disclosure landed on the signal date itself.
      Graceful degradation: if kap_lookup.py is missing or the KAP API
      is unreachable, the five columns are written as empty strings and
      the scanner continues normally — no exceptions propagate to scan()
      or update_outcomes().
      _migrate_log_schema() handles the column addition automatically on
      the next scan; existing rows get empty values for the new columns.

v1.13 changes:
    - Two new signal-time columns: ema20_slope and ema50_slope. Each is
      the percent change of that EMA over the prior EMA_SLOPE_LOOKBACK
      (=5) trading days, measured at the signal day:
          (ema_now / ema_5_ago - 1) * 100
      Positive = EMA rising (trend strengthening up), negative = falling.
        Why? ema_gap_pct tells us the EMAs are stacked bullishly
        (post-cross), but not whether that structure is accelerating or
        going flat. Empirically our single strongest entry-knowable edge
        is post-cross (ema_gap>0). Slope is meant to refine it: a breakout
        into a rising EMA stack should carry differently from one into a
        flat/rolling-over stack with the same instantaneous gap.
        Why a %, not a raw price slope? Comparability across the universe
        — a 2 TL/day rise means nothing without the price level. Same
        rationale as ema_gap_pct. Total move over the window; per-bar
        slope is simply this / EMA_SLOPE_LOOKBACK. ATR-normalisation is a
        deliberate later step (waits on the ATR feature) — for now this is
        a plain, interpretable % so it can be analysed on its own first.
      Stored in both signals_log and outcomes, seeded once at signal time
      (same seed-once semantics as days_above_ema / avg_tl_volume_20d).
      Empty string when there isn't enough history before the signal day.
      _migrate_log_schema() adds the columns automatically on next scan.

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

from bist_calendar import (
    load_holidays,
    next_trading_day,
    nth_trading_day_after,
    trading_days_between,
)

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

try:
    import kap_lookup
    _KAP_AVAILABLE = True
except ImportError:
    _KAP_AVAILABLE = False
    print("Note: kap_lookup.py not found — KAP enrichment disabled.")


SIGNAL_COLUMNS = [
    "scan_date", "signal_date", "ticker", "trigger",
    "y_close", "y_ema20", "y_ema50",
    "open", "close", "t_ema20", "t_ema50",
    "break_pct", "vol_ratio",
    # Day of week of the signal_date (Mon/Tue/...) — useful for spotting
    # weekday effects without re-parsing the date in every analysis.
    "day_of_week",
    # Spread between EMA-20 and EMA-50 on the signal day, as a % of EMA-50:
    #   (t_ema20 - t_ema50) / t_ema50 * 100
    # Positive  -> EMA-20 above EMA-50 (post-golden-cross / uptrend stack)
    # Negative  -> EMA-20 below EMA-50 (pre-golden-cross / downtrend stack)
    # The magnitude shows how far apart the averages are. This is known at
    # signal time, so it can serve as an entry filter (unlike post-signal
    # golden-cross timing, which is circular).
    "ema_gap_pct",
    # Consecutive trading days ending at signal_date (inclusive) where
    # close finished above each EMA. Signal day itself counts as 1 by
    # definition of the trigger.
    #   days_above_ema20 -> short/mid trend age. 1 = fresh cross-above,
    #                        higher = stock has been above EMA20 a while.
    #   days_above_ema50 -> longer trend age. EMA50 = structural boundary.
    # The difference (ema50 - ema20) reveals mature trends with shallow
    # recent EMA20 pullbacks (long uptrend that just reclaimed EMA20).
    "days_above_ema20", "days_above_ema50",
    # 20-day rolling mean of (close * volume), shifted by 1. Represents
    # the monetary liquidity of the stock — what a trader could
    # realistically move per session — using the 20 sessions BEFORE the
    # signal day. Stored in TL (raw integer); analysis side decides
    # cutoffs (e.g. exclude lowest decile for clean cohort statistics).
    "avg_tl_volume_20d",
    # KAP disclosure context — populated by kap_lookup.enrich_hits() if available.
    # Looks at the past 14 calendar days of disclosures for the signal ticker
    # (all KAP types: ODA, CA, FR, DUY, DG, FON). Two parallel breakdowns:
    #   1. By KAP's own disclosureType
    #   2. By title-based mechanical category (YENI_IS, ESAS_SOZ, FR_BILANCO, ...)
    # The second is pattern matching on titles — no tier/edge judgment.
    # Tier and hypothesis testing happen on accumulated data, not at scan time.
    "kap_count_14d",         # int: total disclosures in past 14 days (bedelsiz hariç)
    "kap_oda_count_14d",     # int: disclosureType == "ODA" only
    "kap_signal_day",        # int: disclosures on signal day itself
    "kap_type_breakdown",    # str: "ODA:3 CA:2 FR:1" (KAP's six native types)
    "kap_category_breakdown",# str: "YENI_IS:2 ESAS_SOZ:1" (title-based labels)
    # EMA slope = % change of each EMA over the prior EMA_SLOPE_LOOKBACK
    # trading days, measured at the signal day. Positive = rising EMA.
    # ema_gap_pct says the stack is bullish; slope says whether it's
    # accelerating or going flat. Comparable across price levels (a %,
    # like ema_gap_pct). Empty when history before the signal is too short.
    "ema20_slope", "ema50_slope",
]

OUTCOME_COLUMNS = [
    "signal_date", "ticker", "trigger", "signal_close",
    # Where the signal-day close sat within the signal-day intraday range:
    #   (signal_close - signal_low) / (signal_high - signal_low)
    # Range [0, 1]: 0 = closed at the day's low (weak), 1 = closed at the
    # day's high (strong). Empty when high == low (limit-locked / no range).
    # This is signal-time information — usable as an entry filter.
    "signal_close_in_range",
    # Daily outcomes for the 10 trading days after the signal.
    # Only d1 keeps open + close: d1_open is needed for gap analysis (you
    # enter at the next open, not the signal close). Every other day carries
    # just _pct — the close-to-close return vs signal_close — which is enough
    # to reconstruct the full day-by-day path. d_n close prices, if ever
    # needed, are signal_close * (1 + d_n_pct / 100).
    "d1_open", "d1_close", "d1_pct",
    # Where d1's close sat within d1's intraday range (same formula as
    # signal_close_in_range, applied to the d1 bar). Hold/exit signal —
    # known after d1's close. A "toxic close" (low position in range
    # after pushing above signal close) is associated with continued
    # underperformance through d5.
    "d1_close_in_range",
    "d2_pct", "d3_pct", "d4_pct", "d5_pct",
    "d6_pct", "d7_pct", "d8_pct", "d9_pct", "d10_pct",
    # High / low for the first 5 days after the signal. Together with the
    # derivable open/close, these give full OHLC for d1-d5 — enough for
    # candlestick analysis and intraday-range questions. Stored as % moves
    # vs signal_close, same basis as the _pct columns.
    "d1_high_pct", "d1_low_pct",
    "d2_high_pct", "d2_low_pct",
    "d3_high_pct", "d3_low_pct",
    "d4_high_pct", "d4_low_pct",
    "d5_high_pct", "d5_low_pct",
    # Volume ratio for the first 5 days after the signal: each day's volume
    # divided by the 20-day average volume BEFORE the signal (a fixed base,
    # the same pre-signal normal used for the signal-day vol_ratio). Lets us
    # see whether post-breakout advances are confirmed by volume or drifting
    # on thin trade.
    "d1_vol_ratio", "d2_vol_ratio", "d3_vol_ratio",
    "d4_vol_ratio", "d5_vol_ratio",
    # Best close over the first 5 trading days after the signal — the upside
    # the position offered to a short-term trader aiming to take profit.
    "max_5d_close", "max_5d_pct",
    # Worst close over the first 5 trading days — the drawdown a trader would
    # have sat through before any peak. max_5d shows the opportunity; min_5d
    # shows the pain along the way.
    "min_5d_close", "min_5d_pct",
    # Market-relative reference: XU100 open and close on signal day and
    # the d1 day, plus XU100 close on each of d2..d5. The d1 opens let
    # us see XU100's own intraday direction; the closes (signal day +
    # d1..d5) give the multi-day index trajectory needed for rel_d1..d5
    # calculations. d2..d5 opens are intentionally omitted — rel returns
    # only need close-to-close, and adding 4 unused columns would bloat
    # the schema. d1 keeps both open and close (existing schema).
    "xu100_open", "xu100_close",
    "xu100_d1_open", "xu100_d1_close",
    "xu100_d2_close", "xu100_d3_close",
    "xu100_d4_close", "xu100_d5_close",
    # at_limit = "T" if d1_pct hit the BIST daily price limit (±10%), else "F".
    # Used to mark clamped outcomes that aren't free-market prices.
    "at_limit",
    # split_suspect = "T" if the row's d1 data appears scale-inconsistent
    # with signal_close (likely a stock split between signal_date and the
    # outcome update). Flagged when |d1_high_pct| > 30 or |d1_low_pct| > 30
    # — normal BIST intraday moves cannot reach that magnitude; values that
    # large signal a yfinance auto-adjust scale change that signal_close
    # didn't follow. Excluded from clean analysis; left in the file for
    # later manual handling.
    "split_suspect",
    # Mirrors of the signals_log columns of the same name. Signal-day
    # information, seeded at signal time, never refilled by update_outcomes.
    # Available here so analyses joining outcomes don't need to merge
    # against signals_log just to access trend age.
    "days_above_ema20", "days_above_ema50",
    # Mirror of signals_log avg_tl_volume_20d — 20-day rolling mean TL
    # volume (close * volume) at signal time. Same seed-once semantics
    # as days_above_ema. Use for liquidity filtering in analysis.
    "avg_tl_volume_20d",
    # Mirror of signals_log ema20_slope / ema50_slope — % change of each
    # EMA over the prior EMA_SLOPE_LOOKBACK trading days at signal time.
    # Seeded once, never refilled. Here so outcome-side analyses don't
    # need to merge against signals_log to access trend slope.
    "ema20_slope", "ema50_slope",
]

# Yahoo Finance symbol for the BIST 100 index. Used as the market benchmark
# for relative-return analysis.
XU100_SYMBOL = "XU100.IS"

# BIST daily price-move limit. Closes within LIMIT_TOLERANCE of ±LIMIT_PCT
# are flagged as at_limit — the price would likely have moved further if
# the exchange permitted it.
LIMIT_PCT = 10.0
LIMIT_TOLERANCE = 0.05  # so 9.95% counts as 'at limit'

# Lookback (in trading days) for the EMA slope columns. One trading week:
# responsive enough to register a change in EMA20, while still meaningful
# for the slower EMA50 structural drift. Matches the 3-15 day swing horizon
# the scanner serves. Change here propagates to both ema20_slope/ema50_slope.
EMA_SLOPE_LOOKBACK = 5


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
    # 20-day average TL (Turkish lira) volume = close * volume, rolling mean,
    # same shift(1) convention as VOL_AVG20. This is the monetary liquidity
    # of the stock — what a trader could realistically move per session.
    # Share-volume alone is misleading because price scales differ wildly
    # across the universe (e.g. 1M shares of 1 TL vs 1M shares of 1000 TL).
    df["TL_VOL_AVG20"] = (df["Close"] * df["Volume"]).rolling(window=20).mean().shift(1)
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


def days_above_ema(df: pd.DataFrame, signal_idx: int, ema_col: str) -> int:
    """Count consecutive trading days, ending at signal_idx (inclusive),
    where Close > the named EMA column. Walks backward from signal_idx
    and stops at the first day where close <= ema. Returns 0 if even
    the signal day itself is not above (shouldn't happen for valid hits;
    the trigger requires close > both EMAs)."""
    count = 0
    for j in range(signal_idx, -1, -1):
        if df.iloc[j]["Close"] > df.iloc[j][ema_col]:
            count += 1
        else:
            break
    return count


def ema_slope_pct(df: pd.DataFrame, signal_idx: int, ema_col: str,
                  lookback: int = EMA_SLOPE_LOOKBACK) -> float | None:
    """Percent change of the named EMA over the `lookback` trading days
    ending at signal_idx:  (ema_now / ema_past - 1) * 100.

    Positive -> EMA rising (trend strengthening up); negative -> falling.
    Expressed as a % so it is comparable across stocks at any price level
    (same rationale as ema_gap_pct). This is the total move over the
    window; the per-bar slope is simply the return / lookback.

    Returns None when there isn't enough history before signal_idx, or the
    past EMA value is non-positive / NaN — the caller writes "" for these.
    """
    past_idx = signal_idx - lookback
    if past_idx < 0:
        return None
    now = df.iloc[signal_idx][ema_col]
    past = df.iloc[past_idx][ema_col]
    if pd.isna(now) or pd.isna(past) or past <= 0:
        return None
    return (now / past - 1) * 100


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
                signal_idx = idx
            else:
                today = df.iloc[-1]
                yesterday = df.iloc[-2]
                signal_idx = len(df) - 1

            if matches_signal(today, yesterday):
                t_upper = max(float(today["EMA20"]), float(today["EMA50"]))
                y_upper = max(float(yesterday["EMA20"]), float(yesterday["EMA50"]))
                close = float(today["Close"])
                vol = float(today["Volume"])
                vol_avg = float(today["VOL_AVG20"]) if pd.notna(today["VOL_AVG20"]) else 0.0
                vol_ratio = vol / vol_avg if vol_avg > 0 else 0.0
                # 20-day average TL volume — the stock's recent monetary
                # liquidity. Stored raw (in TL) so analysis can choose
                # cutoffs (e.g. exclude bottom decile). 0 when insufficient
                # history (first 20 bars) or all-NaN — same fallback as
                # vol_avg above.
                tl_vol_avg = float(today["TL_VOL_AVG20"]) if pd.notna(today["TL_VOL_AVG20"]) else 0.0
                # Classify: BRK (yesterday closed below upper) takes priority;
                # otherwise GDN (today's open was below upper).
                trigger = "BRK" if float(yesterday["Close"]) < y_upper else "GDN"
                # Trend age: how long has close stayed above each EMA?
                # Signal day counts as 1 (the trigger requires close > both
                # EMAs); we walk back until close <= ema.
                ema20_age = days_above_ema(df, signal_idx, "EMA20")
                ema50_age = days_above_ema(df, signal_idx, "EMA50")
                hits.append({
                    "ticker": ticker,
                    "date": today.name.strftime("%Y-%m-%d") if hasattr(today.name, "strftime") else str(today.name),
                    "trigger": trigger,
                    "y_close": float(yesterday["Close"]),
                    "y_ema20": float(yesterday["EMA20"]),
                    "y_ema50": float(yesterday["EMA50"]),
                    "open": float(today["Open"]),
                    "close": close,
                    # high/low captured here even though they're not in
                    # SIGNAL_COLUMNS — they're used to seed the new outcome
                    # row's signal_close_in_range. Storing them on the hit
                    # avoids a second yfinance round-trip for the same bar.
                    "high": float(today["High"]),
                    "low": float(today["Low"]),
                    "t_ema20": float(today["EMA20"]),
                    "t_ema50": float(today["EMA50"]),
                    "break_pct": (close - t_upper) / t_upper * 100,
                    "vol_ratio": vol_ratio,
                    "avg_tl_volume_20d": tl_vol_avg,
                    "days_above_ema20": ema20_age,
                    "days_above_ema50": ema50_age,
                    # Trend slope: % change of each EMA over the prior
                    # EMA_SLOPE_LOOKBACK days. None when history is short
                    # (write time converts None -> "").
                    "ema20_slope": ema_slope_pct(df, signal_idx, "EMA20"),
                    "ema50_slope": ema_slope_pct(df, signal_idx, "EMA50"),
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
        # KAP context on indented lines: types (top) and categories (bottom).
        # Categories line is omitted when empty (e.g. only OTHER classifications).
        count = h.get("kap_count_14d")
        type_bd = h.get("kap_type_breakdown") or ""
        cat_bd = h.get("kap_category_breakdown") or ""
        if count and type_bd:
            sd_count = h.get("kap_signal_day") or 0
            sd_tag = f" [signal-günü: {sd_count}]" if sd_count else ""
            print(f"   └─ KAP:      {type_bd}{sd_tag}")
            if cat_bd:
                print(f"   └─ Kategori: {cat_bd}")


def _weekday_name(date_str: str) -> str:
    """Return short English weekday name for an ISO date string."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()]
    except ValueError:
        return ""


def _migrate_log_schema(log_path: Path, expected_columns: list[str]):
    """If log_path's columns don't match expected_columns, rewrite the file
    with the new schema. Adds missing columns (empty for old rows) and drops
    any columns no longer in the schema.

    Idempotent: if the file already matches expected_columns exactly, does
    nothing.
    """
    if not log_path.exists():
        return
    with log_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_cols = list(reader.fieldnames or [])
        rows = list(reader)
    missing = [c for c in expected_columns if c not in existing_cols]
    extra = [c for c in existing_cols if c not in expected_columns]
    if not missing and not extra:
        return
    if missing:
        print(f"Migrating {log_path.name}: adding columns {missing}")
    if extra:
        print(f"Migrating {log_path.name}: dropping columns {extra}")
    with log_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=expected_columns)
        w.writeheader()
        for row in rows:
            # Keep only the expected columns; missing cells become empty.
            new_row = {c: row.get(c, "") for c in expected_columns}
            w.writerow(new_row)


def append_signals_log(hits: list[dict], signals_path: Path):
    """Append today's signals to the given signals CSV (never overwrites).
    Skips rows that match an existing (scan_date, signal_date, ticker)
    triple — safe to re-run the scanner multiple times on the same day."""
    if not hits:
        return
    scan_date = datetime.now().strftime("%Y-%m-%d")

    # Migrate to current schema if columns are missing (idempotent)
    _migrate_log_schema(signals_path, SIGNAL_COLUMNS)

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
            # EMA-20/EMA-50 spread as % of EMA-50. Guard against a zero EMA-50.
            t_ema50 = h["t_ema50"]
            ema_gap = ((h["t_ema20"] - t_ema50) / t_ema50 * 100) if t_ema50 else 0.0
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
                "day_of_week": _weekday_name(h["date"]),
                "ema_gap_pct": round(ema_gap, 4),
                "days_above_ema20": h["days_above_ema20"],
                "days_above_ema50": h["days_above_ema50"],
                "avg_tl_volume_20d": round(h["avg_tl_volume_20d"]),
                # KAP context (may be missing if kap_lookup not available
                # or API call failed — fields default to empty string).
                "kap_count_14d": h.get("kap_count_14d", ""),
                "kap_oda_count_14d": h.get("kap_oda_count_14d", ""),
                "kap_signal_day": h.get("kap_signal_day", ""),
                "kap_type_breakdown": h.get("kap_type_breakdown", "") or "",
                "kap_category_breakdown": h.get("kap_category_breakdown", "") or "",
                # EMA slopes — None (insufficient history) becomes "".
                "ema20_slope": round(h["ema20_slope"], 4) if h.get("ema20_slope") is not None else "",
                "ema50_slope": round(h["ema50_slope"], 4) if h.get("ema50_slope") is not None else "",
            })
    print(f"Logged {len(new_rows)} signal(s) to {signals_path.name}")


def update_outcomes(new_hits: list[dict], outcomes_path: Path):
    """
    Add new signals as rows (with blank outcome cells), then fill in
    outcome columns for any existing rows that now have enough data.
    """
    # Migrate to current schema if columns are missing (idempotent)
    _migrate_log_schema(outcomes_path, OUTCOME_COLUMNS)

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
        # Compute signal_close_in_range from the signal-day OHLC. Empty
        # when the bar has no intraday range (high == low, e.g. limit-locked).
        sig_rng = h["high"] - h["low"]
        sig_cir = round((h["close"] - h["low"]) / sig_rng, 4) if sig_rng > 0 else ""
        rows.append({
            "signal_date": h["date"],
            "ticker": h["ticker"],
            "trigger": h["trigger"],
            "signal_close": round(h["close"], 4),
            "signal_close_in_range": sig_cir,
            "days_above_ema20": h["days_above_ema20"],
            "days_above_ema50": h["days_above_ema50"],
            "avg_tl_volume_20d": round(h["avg_tl_volume_20d"]),
            "ema20_slope": round(h["ema20_slope"], 4) if h.get("ema20_slope") is not None else "",
            "ema50_slope": round(h["ema50_slope"], 4) if h.get("ema50_slope") is not None else "",
            **{col: "" for col in OUTCOME_COLUMNS if col not in
               ("signal_date", "ticker", "trigger",
                "signal_close", "signal_close_in_range",
                "days_above_ema20", "days_above_ema50",
                "avg_tl_volume_20d", "ema20_slope", "ema50_slope")},
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
        """Fill XU100 open/close for signal day, plus d1 open/close and
        d2..d5 closes if missing. Returns True if any cell changed.

        Every d_n date is anchored to the BIST trading calendar via
        nth_trading_day_after — NOT to 'whatever index row yfinance
        returned n days later'. That distinction matters across bayram
        and weekend gaps where yfinance might otherwise hand back a
        stale earlier bar."""
        if xu100_df is None or xu100_df.empty:
            return False
        changed = False
        # Signal day — open and close
        same_day = xu100_df[xu100_df.index.date == signal_date]
        if not same_day.empty:
            bar = same_day.iloc[0]
            if r.get("xu100_open") in ("", None):
                r["xu100_open"] = round(float(bar["Open"]), 4)
                changed = True
            if r.get("xu100_close") in ("", None):
                r["xu100_close"] = round(float(bar["Close"]), 4)
                changed = True
        # d1 — open and close (existing behavior preserved)
        d1_date = next_trading_day(signal_date, holidays)
        d1_match = xu100_df[xu100_df.index.date == d1_date]
        if not d1_match.empty:
            bar = d1_match.iloc[0]
            if r.get("xu100_d1_open") in ("", None):
                r["xu100_d1_open"] = round(float(bar["Open"]), 4)
                changed = True
            if r.get("xu100_d1_close") in ("", None):
                r["xu100_d1_close"] = round(float(bar["Close"]), 4)
                changed = True
        # d2..d5 — close only. Each anchored via the trading calendar so
        # bayram and weekend gaps don't cause off-by-N errors. Loop
        # rather than unrolled so adding d6..d10 later (if ever needed)
        # would be a one-line change to range().
        for n in range(2, 6):
            d_date = nth_trading_day_after(signal_date, n, holidays)
            col = f"xu100_d{n}_close"
            if r.get(col) not in ("", None):
                continue
            d_match = xu100_df[xu100_df.index.date == d_date]
            if d_match.empty:
                continue
            r[col] = round(float(d_match.iloc[0]["Close"]), 4)
            changed = True
        return changed

    # Step 4: for each row, try to fill outcome columns from yfinance.
    # BIST holidays are loaded once and shared across the loop + the
    # XU100 reference filler defined above.
    today = datetime.now().date()
    holidays = load_holidays()
    updated_count = 0
    corrupt_count = 0
    chain_corrupt_count = 0
    price_cache: dict[str, pd.DataFrame] = {}  # one fetch per ticker per run

    # Outcome cells that participate in the corrupt-placeholder pattern.
    # When d1 has been filled but every visible cell is exactly signal_close
    # (open == close == signal_close, high == low == 0%), the data is fake —
    # almost certainly the symptom of a pre-v1.2 run that crossed a holiday
    # gap and grabbed the signal-day bar instead of d1. Wipe and re-fetch.
    _PLACEHOLDER_CELLS = (
        "d1_open", "d1_close", "d1_pct",
        "d1_high_pct", "d1_low_pct", "d1_vol_ratio",
    )

    def _is_placeholder_d1(r: dict) -> bool:
        """Detect the corrupt 'd1 == signal day' fingerprint."""
        try:
            sc = float(r["signal_close"])
            cells = [r.get(k) for k in
                     ("d1_open", "d1_close", "d1_pct",
                      "d1_high_pct", "d1_low_pct")]
            if any(c in ("", None) for c in cells):
                return False
            d1o, d1c, d1p, d1h, d1l = (float(c) for c in cells)
            # All five tell the same fake story: signal_close as both d1
            # open and close, with zero pct/high/low. Real-world chance of
            # this is effectively nil — flag and clear.
            return (
                abs(d1o - sc) < 1e-6
                and abs(d1c - sc) < 1e-6
                and abs(d1p) < 1e-6
                and abs(d1h) < 1e-6
                and abs(d1l) < 1e-6
            )
        except (ValueError, TypeError, KeyError):
            return False

    def _zero_movement_dn(r: dict, n: int) -> bool:
        """Detect zero-movement placeholder for any d_n where 1 <= n <= 5.

        Symptom: d_n_pct == 0 AND d_n_high_pct == 0 AND d_n_low_pct == 0,
        with d_n_vol_ratio either 0 or missing. A real trading day has
        non-zero intraday range; this exact-zero fingerprint is the
        signature of yfinance returning a placeholder bar for a date
        that doesn't exist (e.g. future dates, holidays without the
        calendar correctly excluding them)."""
        if not (1 <= n <= 5):
            return False
        try:
            pct = r.get(f"d{n}_pct")
            high = r.get(f"d{n}_high_pct")
            low = r.get(f"d{n}_low_pct")
            if pct in ("", None) or high in ("", None) or low in ("", None):
                return False
            return (
                abs(float(pct)) < 1e-6
                and abs(float(high)) < 1e-6
                and abs(float(low)) < 1e-6
            )
        except (ValueError, TypeError):
            return False

    def _detect_corrupt_dn_chain(r: dict) -> int:
        """Detect any run of 3+ consecutive identical d_n_pct values —
        the fingerprint of yfinance forward-filling closed-market days
        (bayram, weekends) into the price history.

        v1.4 generalization: catches both
          - 'd2 == d1 chain' (May 25 cohort post-bayram pattern), and
          - 'd_n == d_{n-1} chain' starting at any index ≥ 2 (May 22
            cohort pattern, where d3..d5 ended up equal to d2).

        Returns the smallest n that's part of an identical run of length
        ≥ 3, indicating the SECOND occurrence in the run (so the FIRST
        occurrence — presumably the real value — is preserved). Returns
        0 if no corruption.

        Concretely:
          d1=9.96, d2=9.96, d3=9.96, d4=9.96, d5=20.93  → returns 2
          d1=-0.94, d2=-1.58, d3=-1.58, d4=-1.58, d5=-1.58  → returns 3

        The 4-decimal precision of stored percentages makes a chance
        run of 3 identical values astronomically unlikely outside a
        bug — exact matches are not a realistic noise pattern."""
        # Pull a tight list of (n, pct) pairs up to the first empty
        try:
            vals: list[tuple[int, float]] = []
            for n in range(1, 11):
                v = r.get(f"d{n}_pct")
                if v in ("", None):
                    break
                vals.append((n, float(v)))
            if len(vals) < 3:
                return 0  # need at least 3 entries to detect a run of 3

            # Walk forward, looking for the start of a duplicate run
            for i in range(1, len(vals)):
                if abs(vals[i][1] - vals[i - 1][1]) > 1e-6:
                    continue
                # Found a duplicate at i; measure the full run length
                run_end = i
                while (run_end + 1 < len(vals)
                       and abs(vals[run_end + 1][1] - vals[i][1]) < 1e-6):
                    run_end += 1
                run_length = run_end - (i - 1) + 1  # incl. the anchor at i-1
                if run_length >= 3:
                    return vals[i][0]  # clear from the FIRST duplicate
            return 0
        except (ValueError, TypeError):
            return 0

    for r in rows:
        # Parse the signal date once — we need it for both XU100 columns and outcome calc
        try:
            signal_date = datetime.strptime(r["signal_date"], "%Y-%m-%d").date()
        except ValueError:
            continue

        # XU100 columns: signal-day value goes in immediately on insert;
        # the d1 value gets filled on the NEXT trading day's run.
        if fill_xu100_for_row(r, signal_date):
            updated_count += 1

        # Corrupt-placeholder detection: clear d1 cells if they match the
        # fingerprint left by the holiday-gap bug. Subsequent code will re-fetch.
        if _is_placeholder_d1(r):
            corrupt_count += 1
            for cell in _PLACEHOLDER_CELLS:
                r[cell] = ""

        # Corrupt d_n chain detection: when d2..d_k are exact copies of d1
        # (pre-v1.2 yfinance-duplicate-bar artifact), clear them from d_k
        # onward. The next per-day loop will refill them correctly using
        # the BIST trading calendar.
        first_bad = _detect_corrupt_dn_chain(r)
        if first_bad:
            chain_corrupt_count += 1
            for n in range(first_bad, 11):
                for suffix in ("_pct", "_high_pct", "_low_pct", "_vol_ratio"):
                    cell = f"d{n}{suffix}"
                    if cell in r:
                        r[cell] = ""
            # max/min over 5d are now untrustworthy too — they were computed
            # over a window containing duplicate bars. Clear and recompute.
            for cell in ("max_5d_close", "max_5d_pct",
                         "min_5d_close", "min_5d_pct"):
                if cell in r:
                    r[cell] = ""

        # Generalized zero-movement placeholder check for d2..d5. Same
        # zero-pct + zero-high + zero-low fingerprint as the d1 detector
        # above, but applied to any later day. Catches the case where
        # yfinance returned a fake placeholder bar for a future date
        # (e.g. an outcome being filled for d2 = tomorrow when "tomorrow"
        # hasn't traded yet) and the per-day loop trusted it.
        for n in range(2, 6):
            if _zero_movement_dn(r, n):
                chain_corrupt_count += 1
                for suffix in ("_pct", "_high_pct", "_low_pct", "_vol_ratio"):
                    cell = f"d{n}{suffix}"
                    if cell in r:
                        r[cell] = ""
                # Also wipe later days; if d_n is a placeholder, later
                # days computed from this row's price cache are suspect.
                for m in range(n + 1, 11):
                    for suffix in ("_pct", "_high_pct", "_low_pct", "_vol_ratio"):
                        cell = f"d{m}{suffix}"
                        if cell in r:
                            r[cell] = ""
                for cell in ("max_5d_close", "max_5d_pct",
                             "min_5d_close", "min_5d_pct"):
                    if cell in r:
                        r[cell] = ""
                break  # one detection is enough; the cascade clears the rest

        # Skip rows where every outcome column is already filled.
        if all(r.get(c) not in ("", None) for c in
               ("d1_pct", "d2_pct", "d3_pct", "d4_pct", "d5_pct", "d6_pct",
                "d7_pct", "d8_pct", "d9_pct", "d10_pct",
                "d1_high_pct", "d5_high_pct", "d1_vol_ratio", "d5_vol_ratio",
                "max_5d_pct", "min_5d_pct", "d1_open",
                "signal_close_in_range", "d1_close_in_range",
                "xu100_open", "xu100_close", "xu100_d1_open", "xu100_d1_close",
                "at_limit", "split_suspect")):
            continue

        # Trading-day check using the BIST calendar — bayram and weekends
        # don't count. If zero trading days have passed since the signal,
        # there's no d1 yet and yfinance has nothing useful for us.
        if trading_days_between(signal_date, today, holidays) < 1:
            continue

        ticker = r["ticker"]
        if ticker not in price_cache:
            # Fetch 3 months: enough to cover the 20-day pre-signal volume
            # window AND the 10-day post-signal outcome window, with room
            # for weekends/holidays even for the oldest signals in the log.
            df = yf.download(ticker, period="3mo", interval="1d",
                             progress=False, auto_adjust=True, threads=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            price_cache[ticker] = df

        df = price_cache[ticker]
        if df is None or df.empty:
            continue

        try:
            signal_close = float(r["signal_close"])
        except (ValueError, TypeError):
            continue

        # Pre-signal 20-day average volume — the fixed base for post-signal
        # volume ratios. Uses bars strictly before the signal day, so it's
        # the same "pre-breakout normal" the signal-day vol_ratio used.
        before = df[df.index.date < signal_date]
        pre_vol_avg = 0.0
        if len(before) >= 1:
            pre_vol_avg = float(before["Volume"].tail(20).mean())

        changed = False

        # Backfill signal_close_in_range for rows seeded before this column
        # existed. The signal-day bar is in the price cache; compute from
        # its OHLC directly. Empty stays empty if the bar isn't found or has
        # no intraday range (limit-locked).
        if r.get("signal_close_in_range") in ("", None):
            sig_bar = df[df.index.date == signal_date]
            if not sig_bar.empty:
                try:
                    s_h = float(sig_bar.iloc[0]["High"])
                    s_l = float(sig_bar.iloc[0]["Low"])
                    s_c = float(sig_bar.iloc[0]["Close"])
                    rng = s_h - s_l
                    if rng > 0:
                        r["signal_close_in_range"] = round((s_c - s_l) / rng, 4)
                        changed = True
                except (ValueError, TypeError, KeyError):
                    pass

        # Backfill d1_close_in_range from existing d1_high_pct / d1_low_pct
        # / d1_pct when present but the new column is empty. No fetch
        # needed — derived purely from data we already have.
        if (r.get("d1_close_in_range") in ("", None)
                and r.get("d1_high_pct") not in ("", None)
                and r.get("d1_low_pct") not in ("", None)
                and r.get("d1_pct") not in ("", None)):
            try:
                hp = float(r["d1_high_pct"])
                lp = float(r["d1_low_pct"])
                pp = float(r["d1_pct"])
                rng = hp - lp
                if rng > 0:
                    cir = (pp - lp) / rng
                    # Sanity clamp: values outside [0, 1] mean d1_pct fell
                    # outside d1's reported high/low range — a scale
                    # inconsistency (split-affected row). Leave the cell
                    # empty rather than store a meaningless number; the
                    # split_suspect flag below also catches this case.
                    if 0 <= cir <= 1:
                        r["d1_close_in_range"] = round(cir, 4)
                        changed = True
            except (ValueError, TypeError):
                pass

        # Split-suspect detection: catches scale mismatches between
        # signal_close and the d1 OHLC fields. Two complementary signals:
        #   (a) |d1_high_pct| > 30 or |d1_low_pct| > 30 — BIST daily
        #       limits are ±10% (±20% on a few special bands), so a 30%+
        #       move is impossible under normal trading.
        #   (b) d1_pct falls outside [d1_low_pct, d1_high_pct] — close
        #       can't be lower than the low or higher than the high; if
        #       it is, the close was recorded under one price scale and
        #       the high/low under another (yfinance auto-adjust shift).
        # (b) is the sharper test — it catches modest scale shifts that
        # (a) would miss.
        if r.get("split_suspect") in ("", None):
            try:
                hp = r.get("d1_high_pct")
                lp = r.get("d1_low_pct")
                pp = r.get("d1_pct")
                if all(v not in ("", None) for v in (hp, lp, pp)):
                    hp_f, lp_f, pp_f = float(hp), float(lp), float(pp)
                    big_move = abs(hp_f) > 30 or abs(lp_f) > 30
                    out_of_range = pp_f < lp_f - 1e-6 or pp_f > hp_f + 1e-6
                    if big_move or out_of_range:
                        r["split_suspect"] = "T"
                        # Also wipe d1_close_in_range — the value computed
                        # from inconsistent inputs is meaningless.
                        r["d1_close_in_range"] = ""
                        changed = True
                    else:
                        r["split_suspect"] = "F"
                        changed = True
            except (ValueError, TypeError):
                pass

        # Resolve d1..d10 to explicit BIST trading dates. Each d_n is then
        # looked up by *exact date* — not by "the n-th row yfinance happened
        # to return". This is the v1.2 fix for the holiday-gap bug.
        dn_dates = [
            nth_trading_day_after(signal_date, n, holidays) for n in range(1, 11)
        ]

        d1_to_d5_closes: list[float] = []  # collect for max_5d/min_5d below

        for n, dn_date in enumerate(dn_dates, 1):
            # Future-date guard: refuse to fill cells for sessions that
            # haven't happened yet. yfinance has been observed to return
            # placeholder/forward-fill bars for dates beyond the latest
            # trading day; trusting those scribbles fake data into the
            # outcome columns.
            if dn_date > today:
                break

            bar_match = df[df.index.date == dn_date]
            if bar_match.empty:
                # Data for this d_n isn't available yet (the session hasn't
                # closed, or yfinance hasn't caught up). Stop here; we'd
                # rather leave subsequent days empty than scribble guesses.
                break

            bar = bar_match.iloc[0]

            # Stale-bar guard: a bar with literally zero volume AND
            # high == low is almost certainly a forward-fill artifact
            # for a closed market (a stock that genuinely traded would
            # have *some* volume and at least 1-tick of intraday range).
            # Skip and break — subsequent days from this cache are suspect.
            try:
                bar_volume = float(bar["Volume"])
                bar_high = float(bar["High"])
                bar_low = float(bar["Low"])
                is_fake_bar = (
                    bar_volume <= 0
                    and abs(bar_high - bar_low) < 1e-9
                )
                if is_fake_bar:
                    break
            except (ValueError, TypeError, KeyError):
                pass  # if we can't read those fields, fall through to fill

            close_n = float(bar["Close"])
            pct_n = round((close_n - signal_close) / signal_close * 100, 4)
            label = f"d{n}"

            if n == 1:
                # d1 is "rich": open + close + pct. open and pct are filled
                # independently — either may already exist without the other
                # (e.g. open captured before pct landed).
                if r.get("d1_open") in ("", None):
                    r["d1_open"] = round(float(bar["Open"]), 4)
                    changed = True
                if r.get("d1_pct") in ("", None):
                    r["d1_close"] = round(close_n, 4)
                    r["d1_pct"] = pct_n
                    changed = True
                # d1_close_in_range: where the close sat within d1's range
                # [0, 1]. Computed from the raw bar (cleaner than going via
                # the percent-of-signal_close columns and avoiding a divide
                # by zero on limit-locked days where high == low).
                if r.get("d1_close_in_range") in ("", None):
                    try:
                        h_n = float(bar["High"])
                        l_n = float(bar["Low"])
                        rng = h_n - l_n
                        if rng > 0:
                            r["d1_close_in_range"] = round((close_n - l_n) / rng, 4)
                            changed = True
                    except (ValueError, TypeError, KeyError):
                        pass
            else:
                if r.get(f"{label}_pct") in ("", None):
                    r[f"{label}_pct"] = pct_n
                    changed = True

            # d1-d5: high/low as % vs signal_close, and volume ratio
            if n <= 5:
                d1_to_d5_closes.append(close_n)
                if r.get(f"{label}_high_pct") in ("", None):
                    high_n = float(bar["High"])
                    low_n = float(bar["Low"])
                    r[f"{label}_high_pct"] = round((high_n - signal_close) / signal_close * 100, 4)
                    r[f"{label}_low_pct"] = round((low_n - signal_close) / signal_close * 100, 4)
                    changed = True
                if r.get(f"{label}_vol_ratio") in ("", None) and pre_vol_avg > 0:
                    vol_n = float(bar["Volume"])
                    r[f"{label}_vol_ratio"] = round(vol_n / pre_vol_avg, 4)
                    changed = True

        # max/min across the first 5 trading days — only when we got the
        # full window, to avoid biased best/worst from partial data.
        if len(d1_to_d5_closes) == 5:
            if r.get("max_5d_pct") in ("", None):
                max_close = max(d1_to_d5_closes)
                r["max_5d_close"] = round(max_close, 4)
                r["max_5d_pct"] = round((max_close - signal_close) / signal_close * 100, 4)
                changed = True
            if r.get("min_5d_pct") in ("", None):
                min_close = min(d1_to_d5_closes)
                r["min_5d_close"] = round(min_close, 4)
                r["min_5d_pct"] = round((min_close - signal_close) / signal_close * 100, 4)
                changed = True

        # at_limit: T if d1_pct hit (or essentially hit) the daily price limit.
        # Filled whenever d1_pct is known and at_limit isn't.
        # We mark T only when |d1_pct| is within a small band around LIMIT_PCT —
        # values far beyond (like -78%) are corporate-action artifacts, not
        # limit hits, and stay F.
        if r.get("at_limit") in ("", None) and r.get("d1_pct") not in ("", None):
            try:
                d1_abs = abs(float(r["d1_pct"]))
                hit = (LIMIT_PCT - LIMIT_TOLERANCE) <= d1_abs <= (LIMIT_PCT + LIMIT_TOLERANCE)
                r["at_limit"] = "T" if hit else "F"
                changed = True
            except (ValueError, TypeError):
                pass

        if changed:
            updated_count += 1

    if corrupt_count:
        print(f"Detected and cleared {corrupt_count} corrupt placeholder "
              f"d1 row(s); they will be re-fetched on this run.")
    if chain_corrupt_count:
        print(f"Detected and cleared d_n chain corruption on {chain_corrupt_count} "
              f"row(s) (d2..d_k were duplicates of d1 from forward-filled holiday bars).")

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

    # KAP disclosure enrichment (single API call, filters per-ticker in memory).
    # Fetches all disclosure types (ÖDA, CA, FR, DUY, DG, FON) so the context
    # surfaces financial reports and announcements alongside ÖDA, not just one type.
    # Graceful: failure leaves columns empty and scan continues.
    if hits and _KAP_AVAILABLE:
        try:
            kap_lookup.enrich_hits(hits, args.date)
        except Exception as e:
            print(f"  KAP enrichment error (skipping): {e}")

    # All signals are written to logs. The min-break threshold only changes
    # the visual marker in the terminal output (>= threshold gets a marker)
    # so we can A/B-evaluate threshold choices on real data later.
    print_results(hits, args.date, dataset["label"], args.min_break)

    if not args.no_log:
        append_signals_log(hits, dataset["signals"])
        update_outcomes(hits, dataset["outcomes"])


if __name__ == "__main__":
    main()
