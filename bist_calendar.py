"""
bist_calendar.py
----------------
Lightweight BIST trading-day helper, backed by a hand-maintained
holidays file. Replaces calendar-day arithmetic in the scanner so
bayram tatilleri, half-day arifeler, and weekends are handled correctly.

The holidays file lives next to this module:
    bist_holidays.txt

Format (whitespace-separated, # for comments):
    2026-05-27   closed     Kurban Bayramı 1. Gün
    2026-05-26   half_day   Kurban Bayramı Arifesi

Only the first token (the date) is required. Second token is
'closed' (default) or 'half_day'. Half-days are still trading days
for calendar purposes; the tag is preserved so callers that care
(e.g. volume-ratio analysis) can treat them specially.

Usage:
    from bist_calendar import next_trading_day, trading_days_between
    d1 = next_trading_day(signal_date)
    elapsed = trading_days_between(signal_date, today)
"""

from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOLIDAYS_FILE = HERE / "bist_holidays.txt"

# Cache: avoid re-reading the file on every helper call within a process
_CACHE: dict[date, str] | None = None


def load_holidays(force_reload: bool = False) -> dict[date, str]:
    """Return {date: 'closed' | 'half_day'} from bist_holidays.txt.

    Returns an empty dict if the file is missing — the script still
    works, weekends are still skipped, but bayram days will be missed."""
    global _CACHE
    if _CACHE is not None and not force_reload:
        return _CACHE

    holidays: dict[date, str] = {}
    if not HOLIDAYS_FILE.exists():
        _CACHE = holidays
        return holidays

    for line_no, raw in enumerate(
        HOLIDAYS_FILE.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        try:
            d = date.fromisoformat(parts[0])
        except (ValueError, IndexError):
            print(f"bist_holidays.txt:{line_no}: skipping unparseable line: {raw!r}")
            continue
        # Second token tags the day. Default is 'closed'.
        tag = parts[1].lower() if len(parts) >= 2 else "closed"
        if tag not in ("closed", "half_day"):
            print(f"bist_holidays.txt:{line_no}: unknown tag {tag!r}, treating as 'closed'")
            tag = "closed"
        holidays[d] = tag

    _CACHE = holidays
    return holidays


def is_trading_day(d: date, holidays: dict[date, str] | None = None) -> bool:
    """True if d is a weekday and not marked as 'closed' in the holidays file.

    Half-day arifeler ARE trading days here — the market is open, prices
    exist, and analysis should include them. Callers that want to flag
    half-days separately should check is_half_day(d)."""
    if holidays is None:
        holidays = load_holidays()
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return holidays.get(d) != "closed"


def is_half_day(d: date, holidays: dict[date, str] | None = None) -> bool:
    """True if d is a tagged half-day (e.g. bayram arifesi)."""
    if holidays is None:
        holidays = load_holidays()
    return holidays.get(d) == "half_day"


def next_trading_day(d: date, holidays: dict[date, str] | None = None) -> date:
    """Return the first BIST trading day strictly after d."""
    if holidays is None:
        holidays = load_holidays()
    nxt = d + timedelta(days=1)
    # Hard cap on the search — guards against a runaway loop if the
    # holidays file ever marks an entire year as closed.
    for _ in range(30):
        if is_trading_day(nxt, holidays):
            return nxt
        nxt = nxt + timedelta(days=1)
    raise RuntimeError(f"No trading day found within 30 days after {d} — "
                       f"check bist_holidays.txt for over-tagging.")


def prev_trading_day(d: date, holidays: dict[date, str] | None = None) -> date:
    """Return the first BIST trading day strictly before d."""
    if holidays is None:
        holidays = load_holidays()
    prv = d - timedelta(days=1)
    for _ in range(30):
        if is_trading_day(prv, holidays):
            return prv
        prv = prv - timedelta(days=1)
    raise RuntimeError(f"No trading day found within 30 days before {d}.")


def trading_days_between(start: date, end: date,
                         holidays: dict[date, str] | None = None) -> int:
    """Count BIST trading days in (start, end] — exclusive of start, inclusive of end.

    Returns 0 if end <= start. Used by the scanner to decide whether
    enough sessions have passed since a signal to expect outcome data."""
    if end <= start:
        return 0
    if holidays is None:
        holidays = load_holidays()
    count = 0
    d = start + timedelta(days=1)
    while d <= end:
        if is_trading_day(d, holidays):
            count += 1
        d = d + timedelta(days=1)
    return count


def nth_trading_day_after(d: date, n: int,
                          holidays: dict[date, str] | None = None) -> date:
    """Return the n-th trading day after d.

    nth_trading_day_after(d, 1) == next_trading_day(d).
    Useful for explicit d_n date lookup in outcomes filling."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if holidays is None:
        holidays = load_holidays()
    cur = d
    for _ in range(n):
        cur = next_trading_day(cur, holidays)
    return cur


if __name__ == "__main__":
    # Quick sanity check — useful when adding new dates to the holidays file
    import sys
    holidays = load_holidays(force_reload=True)
    print(f"Loaded {len(holidays)} holiday entries from {HOLIDAYS_FILE}")
    closed = sorted(d for d, t in holidays.items() if t == "closed")
    halfd = sorted(d for d, t in holidays.items() if t == "half_day")
    if closed:
        print(f"  Closed days ({len(closed)}): {closed[0]} ... {closed[-1]}")
    if halfd:
        print(f"  Half days ({len(halfd)}): {halfd}")
    # If a date was given on the command line, dump its next trading day
    if len(sys.argv) > 1:
        try:
            d = date.fromisoformat(sys.argv[1])
            print(f"\n{d} ({d.strftime('%A')}):")
            print(f"  is_trading_day:    {is_trading_day(d)}")
            print(f"  is_half_day:       {is_half_day(d)}")
            print(f"  next_trading_day:  {next_trading_day(d)}")
            print(f"  d1..d5: {[nth_trading_day_after(d, n) for n in range(1, 6)]}")
        except ValueError:
            print(f"Cannot parse {sys.argv[1]!r} as YYYY-MM-DD")
