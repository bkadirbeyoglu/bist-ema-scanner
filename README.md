# BIST EMA Breakout Scanner

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: Active](https://img.shields.io/badge/status-active-success.svg)]()

A daily end-of-session scanner for Borsa İstanbul (BIST) stocks that flags EMA-20 / EMA-50 breakouts. Pulls index constituents from KAP (with Midas as fallback), price history from Yahoo Finance, and writes both the day's hits and a follow-up outcomes log to disk so you can analyse signal quality over time.

**[Türkçe README →](README.tr.md)**

---

## What it does

After the BIST close, run `bist_ema_scanner.py`. It walks every stock in the chosen index (XU100 by default, or XU500), fetches the last 6 months of daily candles from Yahoo Finance, computes EMA-20 and EMA-50, and prints the stocks where today's session matches one of two breakout patterns. Hits are appended to a CSV log, and the outcome of every past hit (return after 1, 3, 5, 10 days) is filled in automatically as more sessions pass.

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

BIST closes at 18:00 Istanbul time; Yahoo's daily bar settles ~15-30 min later.  Run the scanner around 18:30:

```bash
python bist_ema_scanner.py                    # XU100 (default)
python bist_ema_scanner.py -i xu500           # XU500
python bist_ema_scanner.py -d 2026-04-17      # specific historical session
python bist_ema_scanner.py -m 1.0             # raise the ✓ threshold to 1%
python bist_ema_scanner.py -m 0               # disable marginal-signal de-emphasis
python bist_ema_scanner.py --no-log           # don't write to log/outcomes
```

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

outcomes_xu100.csv         ← what happened d+1, d+3, d+5, d+10 after each signal
outcomes_xu500.csv
```

### `signals_log_xu*.csv`

Append-only history. Columns: `scan_date, signal_date, ticker, trigger, y_close, y_ema20, y_ema50, open, close, t_ema20, t_ema50, break_pct, vol_ratio`.

Duplicate-protected on `(scan_date, signal_date, ticker)` — running the scanner multiple times the same day is safe.

### `outcomes_xu*.csv`

Self-updating. New signals are inserted with empty outcome cells. On subsequent runs, the scanner fills in:

- `d{1,3,5,10}_open` / `d{1,3,5,10}_close` / `d{1,3,5,10}_pct` — the open and close on each follow-up bar, plus the close-to-close % return from `signal_close`. The `d{n}_open` columns let you measure the *real* return you'd capture if you bought at the next-day open instead of the (impossible-to-trade) signal-day close.
- `max_5d_close` / `max_5d_pct` — the highest close in the first 5 sessions after the signal.
- `xu100_close` / `xu100_d1_close` — the BIST 100 index close on the signal day and on d1. Lets you compute *market-relative* returns (signal d1 minus index d1) without re-fetching anything.

After a few weeks, this file is a goldmine for analysis: open it in Excel, pivot by `trigger`, by `vol_ratio` bucket, by `break_pct` quintile, by gap size (`d1_open - signal_close`), or by market relative performance, and see which conditions actually predict positive subsequent returns.

## Project structure

```
bist-ema-scanner/
├── bist_ema_scanner.py         # Main scanner
├── update_index.py         # Ticker list refresher (KAP + Midas fallback)
├── debug_ticker.py         # Single-ticker diagnostic
├── xu100.csv               # Ticker lists (generated)
├── xu500.csv
├── signals_log_xu*.csv     # Signal history (generated)
├── outcomes_xu*.csv        # Outcome tracking (generated)
├── requirements.txt
├── LICENSE
├── README.md
└── README.tr.md
```

## Data sources

- **Ticker lists:** [KAP (Public Disclosure Platform)](https://kap.org.tr/tr/Endeksler) — primary. [Midas](https://www.getmidas.com/canli-borsa/) — fallback.
- **Price history:** [Yahoo Finance](https://finance.yahoo.com/) via the `yfinance` library, with `auto_adjust=True` so EMAs are computed on dividend- and split-adjusted closes.

## Limitations and known issues

- **Yahoo data lag:** ~15-30 minutes after BIST close. Don't run the scanner before 18:30 Istanbul time, or today's bar will be missing.
- **Adjusted prices:** Yahoo's adjustment isn't always perfect for Turkish stocks that do bonus issues (`bedelsiz sermaye artırımı`). Spot-check signals against your broker's chart if a number looks off.
- **Delisted tickers:** A stock removed from BIST will print a "possibly delisted" warning from yfinance. Re-run `update_index.py` after a quarterly rebalance to refresh.
- **Not a buy/sell recommendation.** The signal has roughly coin-flip accuracy on its own (typical for crossover strategies). Real edge comes from combining it with position sizing, stop-losses, and market-regime filters — none of which this tool implements.

## Contributing

Issues and pull requests welcome. If you propose a strategy change (e.g. a new trigger type), please include a quick analysis of how it performs against historical `outcomes_xu*.csv` data.

## Disclaimer

This software is provided for educational and research purposes only. **It is not investment advice.** The author is not a licensed financial advisor. Trading carries the risk of loss; do your own research and consult a qualified professional before making investment decisions. Past performance — including any analysis produced by this tool — does not guarantee future results.

## License

MIT — see [LICENSE](LICENSE).
