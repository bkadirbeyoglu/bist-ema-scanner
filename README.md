# BIST EMA Breakout Scanner

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: Active](https://img.shields.io/badge/status-active-success.svg)]()

A daily end-of-session scanner for Borsa İstanbul (BIST) stocks that flags EMA-20 / EMA-50 breakouts. Pulls index constituents from KAP (with Midas as fallback), price history from Yahoo Finance, and writes both the day's hits and a follow-up outcomes log to disk so you can analyse signal quality over time.

**[Türkçe README →](README.tr.md)**

---

## What it does

After the BIST close, run `bist_ema_scanner.py`. It walks every stock in the chosen index (XU100 by default, or XU500), fetches the last 6 months of daily candles from Yahoo Finance, computes EMA-20 and EMA-50, and prints the stocks where today's session matches one of two breakout patterns. Hits are appended to a CSV log, and the outcome of every past hit (1-10 day follow-up returns, intraday range, volume continuity, market-relative performance, trend age, liquidity profile) is filled in automatically as more sessions pass.

## The signal

A stock is flagged when **today's close is above both EMA-20 and EMA-50** AND at least one of the following holds:

- **BRK — Breakout.** Yesterday's close was below the upper EMA. Covers classic crossovers and gap-up breakouts.
- **GDN — Gap-down recovery.** Today's open was below the upper EMA, but the close finished above both EMAs. Catches the case where a stock in an uptrend gaps down on news and recovers within the session.

The relative order of EMA-20 and EMA-50 doesn't matter — only the upper one matters for the open/yesterday-close test, and the close must be above both.

### Why this signal

The combination of a price already above both moving averages plus a recent dip below one of them implies that a buyer who reads charts at end-of-day is looking at a stock that just reclaimed its trend line. Two practical limitations to keep in mind:

- **Whipsaws.** In sideways markets, breakouts reverse the next day. A volume confirmation column (`VOL×`, today vs. 20-day average) helps filter the obviously weak ones.
- **Late entry risk.** EMAs are lagging indicators. By the time a signal fires, much of the move may already be in the past. The scanner is a *first filter*, not an entry signal.

This tool does not give buy/sell recommendations. Read the [Disclaimer](#disclaimer).

## Sample output

```
===============================================================================================
XU500 EMA Breakout Scan  |  Session: 2026-04-27  |  Scanned at: 2026-04-27 18:35
Close above both EMAs, with either yesterday's close or today's open below the upper EMA
Marking signals with BREAK% >= 0.5% (all signals are still logged)
===============================================================================================
59 match(es):  [ BRK=breakout  GDN=gap-down recovery  * = vol >= 1.5x  ✓ = BREAK% >= 0.5%  ★ = BREAK% >= 2.0% AND VOL >= 2.0x ]

   TICKER     DATE         TYPE   Y-CLOSE   Y-EMA20   Y-EMA50     OPEN    CLOSE   T-EMA20   T-EMA50   BREAK%    VOL×
--------------------------------------------------------------------------------------------------------------------------
★ EUPWR.IS   2026-04-27   BRK      40.58     40.65     39.16    41.20    44.62     41.02     39.37   +8.76%   2.50*
★ TATGD.IS   2026-04-27   BRK      16.55     16.70     16.35    16.55    17.57     16.79     16.40   +4.66%   2.97*
✓ OYYAT.IS   2026-04-27   BRK      56.10     56.30     55.93    56.15    58.80     56.53     56.04   +4.01%   0.44 
✓ KFEIN.IS   2026-04-27   BRK       8.76      8.63      8.77     8.79     9.05      8.67      8.78   +3.12%   1.59*
✓ ADGYO.IS   2026-04-27   BRK      58.50     58.62     57.66    59.00    60.60     58.81     57.77   +3.05%   0.66 
...
  TUPRS.IS   2026-04-27   BRK     253.00    254.90    241.18   260.25   255.00    254.91    241.72   +0.04%   0.65 
Logged 59 signal(s) to signals_log_xu500.csv
```

Markers:

- **`★`** — Strong breakout: BREAK% ≥ 2% AND volume ≥ 2× the 20-day average. Empirically the highest-conviction category.
- **`✓`** — Above the marginal threshold (BREAK% ≥ `--min-break`, default 0.5%). Default-on; pass `-m 0` to disable.
- (no marker) — Marginal signal. Logged but visually de-emphasised; historically these have shown the lowest follow-through.

All signals — including marginal ones — are written to the log file. The markers only change how the rows are presented in the terminal, so you can experiment with different thresholds without losing data.

Columns:

| Column      | Meaning                                                                  |
|-------------|--------------------------------------------------------------------------|
| `TYPE`      | `BRK` = breakout, `GDN` = gap-down recovery                              |
| `Y-CLOSE`   | Yesterday's close                                                        |
| `Y-EMA20/50`| Yesterday's EMA values                                                   |
| `OPEN`      | Today's open                                                             |
| `CLOSE`     | Today's close                                                            |
| `T-EMA20/50`| Today's EMA values                                                       |
| `BREAK%`    | How far close finished above the upper EMA — bigger is a stronger break  |
| `VOL×`      | Today's volume / 20-day avg. `*` marker means ≥ 1.5× (volume confirmed)  |

Rows are sorted by `BREAK%` descending — the most decisive breaks are at the top.

## Installation

Requires Python 3.10+.

```bash
git clone https://github.com/bkadirbeyoglu/bist-ema-scanner.git
cd bist-ema-scanner
pip install -r requirements.txt
```

`requirements.txt`:

```
yfinance
pandas
requests
```

### Trading calendar setup

The scanner uses an explicit BIST trading calendar to correctly skip weekends and Turkish public holidays when computing outcome dates (d1..d10). Two files are required:

- **`bist_calendar.py`** — calendar helper module (no setup needed; imported by the scanner).
- **`bist_holidays.txt`** — manually maintained list of closed and half-day sessions. Format: one entry per line, `YYYY-MM-DD <closed|half_day> # optional comment`. Update this once a year when the official BIST calendar publishes.

Verify the calendar with:

```bash
python bist_calendar.py 2026-05-26
# Expected output includes the date's trading-day status, half-day flag,
# next trading day (bayram/weekend-aware), and the d1..d5 sequence.
```

## Usage

The workflow is two steps: refresh the ticker list (occasionally), then run the scanner (daily after market close).

### 1. Refresh ticker list

Indices rebalance quarterly. Re-run when needed:

```bash
python update_index.py                    # XU100 → xu100.csv  (default)
python update_index.py -i xu500           # XU500 → xu500.csv
python update_index.py -i xu500 -s midas  # use Midas as fallback if KAP is down
```

### 2. Run the scanner

BIST closes at 18:00 Istanbul time; Yahoo's daily bar settles ~15-30 min later. Run the scanner around 18:30:

```bash
python bist_ema_scanner.py                    # XU100 (default)
python bist_ema_scanner.py -i xu500           # XU500
python bist_ema_scanner.py -d 2026-04-17      # specific historical session
python bist_ema_scanner.py -m 1.0             # raise the ✓ threshold to 1%
python bist_ema_scanner.py -m 0               # disable marginal-signal de-emphasis
python bist_ema_scanner.py --no-log           # don't write to log/outcomes
```

Each run also updates outcomes for all older signals — older rows get their d_n columns filled as new sessions become available.

### 3. Inspect a single ticker

If you want to understand why a particular stock did or didn't fire:

```bash
python debug_ticker.py HALKB
```

## Output files

Each index has its own pair of log files; results never mix:

```
xu100.csv                  ← ticker list (regenerated by update_index.py)
xu500.csv

signals_log_xu100.csv      ← every signal ever fired
signals_log_xu500.csv

outcomes_xu100.csv         ← post-signal d1..d10 returns + intraday + market-rel
outcomes_xu500.csv
```

### `signals_log_xu*.csv`

Append-only history. Columns:

| Column | Meaning |
|--------|---------|
| `scan_date`, `signal_date`, `ticker`, `trigger` | When the scan ran, the session date, ticker, BRK/GDN |
| `y_close`, `y_ema20`, `y_ema50` | Yesterday's close and EMA values |
| `open`, `close`, `t_ema20`, `t_ema50` | Today's open/close and EMA values |
| `break_pct`, `vol_ratio` | Distance above upper EMA; today's volume vs 20-day average |
| `day_of_week` | Day name (Mon/Tue/…) for easy weekday analysis |
| `ema_gap_pct` | EMA20-EMA50 spread as % of EMA50; sign indicates trend stack |
| `days_above_ema20`, `days_above_ema50` | Trend age — consecutive trading days ending at signal_date (inclusive) where close finished above each EMA |
| `avg_tl_volume_20d` | 20-day average TL volume (close × volume), shifted by 1; the monetary liquidity of the stock |
| `kap_count_14d`, `kap_oda_count_14d`, `kap_signal_day` | KAP disclosure counts (v1.12): total in the past 14 calendar days, ODA-type only, and on the signal day itself |
| `kap_type_breakdown`, `kap_category_breakdown` | KAP disclosure summaries (v1.12): compact counts by KAP's native type (`ODA:3 CA:1 …`) and by title-based category (`YENI_IS:2 …`) |
| `ema20_slope`, `ema50_slope` | EMA trend slope (v1.13): % change of each EMA over the prior 5 trading days; sign/magnitude show whether the stack is rising and how fast |

Duplicate-protected on `(scan_date, signal_date, ticker)` — running the scanner multiple times the same day is safe.

**KAP disclosure context (v1.12, signals_log only).** The five `kap_*` columns tag each signal with its recent Borsa İstanbul disclosure activity, fetched via an optional `kap_lookup.py` module. All disclosure types are counted (ODA, CA, FR, DUY, DG, FON) — not just material events — since financial reports, corporate actions, and announcements can all bear on a breakout; mechanical bonus-issue (bedelsiz) split notices are excluded so they don't mislead the count. The two breakdown strings give a count by KAP's six native types and a finer count by title-based category. No edge/tier label is applied at scan time — counts are mechanical, and category-to-outcome mapping is a separate analysis step on accumulated data, to avoid baking unvalidated hypotheses into the pipeline. Graceful degradation: if `kap_lookup.py` is missing or the KAP API is unreachable, the five columns are written empty and the scan continues normally.

### `outcomes_xu*.csv`

Self-updating. New signals are inserted with empty outcome cells. On subsequent runs, the scanner fills in:

**Daily returns (d1..d10).** Close-to-close percentage return vs `signal_close` for each of the first 10 trading days after the signal. `d1` is additionally stored with full open and close prices so the *real* return you'd capture buying at the next-day open can be measured.

**Intraday range (d1..d5).** `d_n_high_pct` and `d_n_low_pct` give the high and low of each day as a percentage of `signal_close`. Together with the daily close, full OHLC for the first 5 sessions can be reconstructed.

**Volume continuity (d1..d5).** `d_n_vol_ratio` is each day's volume divided by the 20-day pre-signal average. The same base volume the signal-day `vol_ratio` used, so post-signal trade can be compared apples-to-apples.

**5-day extremes.** `max_5d_close` / `max_5d_pct` — best close in the 5-session window. `min_5d_close` / `min_5d_pct` — worst close, showing the drawdown a trader would have sat through.

**Close-in-range positions.** `signal_close_in_range` and `d1_close_in_range` — where each day's close sat within its intraday range, on a [0, 1] scale. 0 = closed at the day's low (weak), 1 = closed at the day's high (strong). Empty when the bar has no intraday range (limit-locked). The d1 version is a hold/exit signal known after the next day's close; the signal version is entry-time information.

**Market-relative reference.** `xu100_open` and `xu100_close` on the signal day, `xu100_d1_open` and `xu100_d1_close` on the next trading day, plus `xu100_d2_close`, `xu100_d3_close`, `xu100_d4_close`, `xu100_d5_close` — the BIST 100 index close on each of d2..d5. Together they let you compute the signal's market-relative return on every horizon from d1 to d5 without re-fetching the index. The d1 reference gives `rel_d1 = d1_pct − mkt_d1`, where `mkt_d1 = (xu100_d1_close / xu100_close − 1) × 100`; the d2..d5 closes extend the same calculation through the full outcome window. The opens for d2..d5 are intentionally omitted: cumulative returns only need close-to-close from the signal day, so the opens would be unused columns. All d_n dates are anchored to the BIST trading calendar (NOT to whatever row yfinance returns N positions later), so bayram and weekend gaps don't cause off-by-N errors.

**Trend age.** `days_above_ema20` and `days_above_ema50` — count of consecutive trading days ending at signal_date (inclusive) where close finished above each EMA. Mirrors the columns of the same name in `signals_log_*.csv`; seeded at signal time and never refilled by outcome updates. The signal day itself always counts as 1 because the trigger requires close > both EMAs. Lets analyses distinguish fresh crosses (=1) from mature trends, and lets the difference `days_above_ema50 − days_above_ema20` flag mature uptrends with shallow recent EMA20 pullbacks.

**Trend slope (v1.13).** `ema20_slope` and `ema50_slope` — percent change of each EMA over the prior 5 trading days (`EMA_SLOPE_LOOKBACK`), measured at the signal day: positive means the EMA is rising. Mirrors the signals_log columns of the same name; seeded once at signal time, never refilled. Where `ema_gap_pct` shows that the EMA stack is bullish (post-cross), the slope shows whether that structure is accelerating or going flat — meant to refine the post-cross edge by separating breakouts into a rising stack from breakouts into a flattening one. Expressed as a % so it is comparable across price levels (same rationale as `ema_gap_pct`). Empty when there isn't enough history before the signal day.

**Liquidity.** `avg_tl_volume_20d` — 20-day rolling mean of (close × volume), shifted by 1. Mirror of the signals_log column of the same name; seeded at signal time, never refilled. Represents the stock's recent monetary liquidity in Turkish lira — what a trader could realistically move per session. TL-denominated rather than share-count because price scales differ wildly across the universe (1M shares of a 1 TL stock and 1M shares of a 1000 TL stock are very different liquidities). Use for filtering out micro-liquid edge cases that would otherwise dilute cohort statistics.

**Status flags.** `at_limit` — "T" if d1 hit the BIST ±10% price limit. `split_suspect` — "T" when d1 OHLC shows a scale inconsistency with `signal_close` (the fingerprint of a stock split between signal time and the outcome update). Split-suspect rows should be excluded from analysis: `df[df['split_suspect'] != 'T']`.

After a few weeks, this file is a goldmine for analysis: open it in Excel or pandas, pivot by `trigger`, by `vol_ratio` bucket, by `break_pct` quintile, by gap size (`d1_open - signal_close`), by `close_in_range` position, by `day_of_week`, by `days_above_ema20` band, by `ema20_slope` sign/magnitude, by `avg_tl_volume_20d` decile, by KAP activity (`kap_signal_day`, `kap_category_breakdown`, joined from signals_log), or by market-relative performance at any horizon from d1 through d5, and see which conditions actually predict positive subsequent returns.

## Data quality and robustness

The scanner self-heals from several yfinance data quirks that can otherwise corrupt the outcomes log silently:

- **Holiday-gap d1 placeholder** — when `signal_date == today` and a holiday gap intervenes, yfinance can return a fake d1 bar with `open == close == signal_close` and zero high/low. Detected and cleared on subsequent runs.
- **Forward-fill duplicate chains** — yfinance sometimes returns duplicate bars for closed market days (bayram, weekends if not stripped). Without calendar awareness, these get stored as legitimate d2, d3, … values. The scanner detects runs of 3+ identical consecutive `d_n_pct` values and clears them.
- **Future-date placeholder** — yfinance can return placeholder bars for dates that haven't traded yet. A future-date guard in the per-day fill loop prevents these from being written.
- **Stale forward-fill bars** — bars with zero volume AND zero intraday range are forward-fill artifacts; rejected during refill.
- **Split scale mismatch** — when a stock splits between signal_date and a later outcome update, `signal_close` (captured at signal time) and d1 OHLC (re-fetched as adjusted) end up in different scales. Flagged via `split_suspect = "T"` and excluded from analysis filters.

## Schema migrations

Both log files automatically migrate to the current schema when the scanner runs. If new columns have been added between versions (e.g. `signal_close_in_range` in v1.6, `split_suspect` in v1.7, `days_above_ema20` / `days_above_ema50` in v1.9, `avg_tl_volume_20d` in v1.10, `xu100_d2_close` / `xu100_d3_close` / `xu100_d4_close` / `xu100_d5_close` in v1.11, the `kap_*` columns in v1.12, and `ema20_slope` / `ema50_slope` in v1.13), the scanner prints a "Migrating … adding columns […]" line on the next run and rewrites the file with the new headers; existing rows get empty values for the new columns. Pre-migration data is preserved untouched. For the v1.11 columns specifically, the new market-reference cells get populated progressively as the scanner runs on subsequent trading days — every signal whose d2..d5 dates have already passed at the time of the next run gets filled in a single pass. The v1.12 and v1.13 columns are signal-time information, seeded only on newly detected signals; pre-existing rows keep empty values (a one-off backfill from yfinance history can populate them retroactively if needed).

## Companion tools

Optional scripts that produce data adjacent to the main scanner. Each has its own log file and can be run independently.

### `morning_snapshot.py` — intraday early-read

Captures the first ~50 minutes of trading for the previous session's signals. Useful for testing whether gap-up direction and first-hour volume confirm the next-day outcome before the close. Output: `morning_snapshots_xu*.csv`.

Run shortly after market open (around 10:50 Istanbul time):

```bash
python morning_snapshot.py            # XU100
python morning_snapshot.py -i xu500   # XU500
```

### `bist_signal_followup.py` — quick stats on latest signals

Prints day-1 outcomes for the most recent signal date, sorted by performance, with a market-relative summary. No log file; pure display tool.

```bash
python bist_signal_followup.py            # XU100
python bist_signal_followup.py -i xu500   # XU500
```

### `bist_mean_reversion_scanner.py` — alternate strategy

A second scanner that flags significant deviations of close from EMA20/EMA50 (above or below). Has its own log structure and tracks 5-day outcomes via `mr_outcomes_xu*.csv`. Useful for cross-validating signals against a mean-reversion lens rather than a breakout lens.

```bash
python bist_mean_reversion_scanner.py            # XU100
python bist_mean_reversion_scanner.py -i xu500   # XU500
```

## Project structure

```
bist-ema-scanner/
├── bist_ema_scanner.py             # Main scanner
├── bist_calendar.py                # BIST trading-day calendar helper
├── bist_holidays.txt               # Manually maintained holiday list
├── update_index.py                 # Ticker list refresher (KAP + Midas fallback)
├── debug_ticker.py                 # Single-ticker diagnostic
│
├── morning_snapshot.py             # Intraday early-read (companion)
├── bist_signal_followup.py         # Latest-signal quick stats (companion)
├── bist_mean_reversion_scanner.py  # Mean-reversion scanner (companion)
│
├── xu100.csv                       # Ticker lists (generated)
├── xu500.csv
├── signals_log_xu*.csv             # Signal history (generated)
├── outcomes_xu*.csv                # Outcome tracking (generated)
├── morning_snapshots_xu*.csv       # Intraday snapshots (generated)
├── mr_outcomes_xu*.csv             # Mean-reversion outcomes (generated)
│
├── requirements.txt
├── LICENSE
├── README.md
└── README.tr.md
```

## Data sources

- **Ticker lists:** [KAP (Public Disclosure Platform)](https://kap.org.tr/tr/Endeksler) — primary. [Midas](https://www.getmidas.com/canli-borsa/) — fallback.
- **Price history:** [Yahoo Finance](https://finance.yahoo.com/) via the `yfinance` library, with `auto_adjust=True` so EMAs are computed on dividend- and split-adjusted closes.
- **Trading calendar:** maintained manually in `bist_holidays.txt`.

## Limitations and known issues

- **Yahoo data lag:** ~15-30 minutes after BIST close. Don't run the scanner before 18:30 Istanbul time, or today's bar will be missing.
- **Adjusted prices and splits:** When a stock splits between when a signal was recorded and a later outcome update, `signal_close` and d1 OHLC end up scaled differently. The scanner detects this and sets `split_suspect = "T"`; downstream analysis should filter these out.
- **Delisted tickers:** A stock removed from BIST will print a "possibly delisted" warning from yfinance. Re-run `update_index.py` after a quarterly rebalance to refresh.
- **Holiday calendar maintenance:** `bist_holidays.txt` must be updated annually when the official BIST calendar is published; otherwise outcomes around new holidays will silently fall back to forward-filled bars.
- **Empty cells for pre-migration data:** Signals logged before a given column was introduced will have empty values in that column. Filter or impute accordingly when joining across schema generations.
- **Not a buy/sell recommendation.** The base signal has roughly coin-flip accuracy on its own (typical for crossover strategies). Real edge comes from combining it with filters (gap direction, intraday close position, volume continuity, market regime, signal sequence, trend age, liquidity, multi-day market-relative performance) and discipline around position sizing and stops — none of which this tool implements.

## Contributing

Issues and pull requests welcome. If you propose a strategy change (e.g. a new trigger type or a new outcome column), please include a quick analysis of how it performs against historical `outcomes_xu*.csv` data, and a falsifiable hypothesis statement (a pre-specified threshold the result should beat).

## Disclaimer

This software is provided for educational and research purposes only. **It is not investment advice.** The author is not a licensed financial advisor. Trading carries the risk of loss; do your own research and consult a qualified professional before making investment decisions. Past performance — including any analysis produced by this tool — does not guarantee future results.

## License

MIT — see [LICENSE](LICENSE).
