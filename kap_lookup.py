"""
kap_lookup.py
-------------
KAP lookup module for the EMA scanner. Fetches disclosures of ALL types
for signal tickers within the past N calendar days and adds raw context
columns.

Two parallel breakdowns are produced:
  1. By KAP's own disclosureType (ODA / CA / FR / DUY / DG / FON)
  2. By title-based category (YENI_IS / ESAS_SOZ / FR_BILANCO / ...)

The second is mechanical title classification — pure pattern matching
on titles ("Yeni İş İlişkisi" → YENI_IS), not a tier or edge judgment.
It just makes analysis on accumulated data easier by saving us from
re-running classifier code over historical CSVs.

Single-API-call strategy: when scan() finishes with N hits, this module
makes ONE KAP API request covering the date window, then filters in-memory
per ticker.

Columns added to each hit dict:
  kap_count_14d            — total disclosures in past 14 calendar days
                             (bedelsiz sermaye artırımı = mekanik split hariç)
  kap_oda_count_14d        — disclosureType == "ODA" only
  kap_signal_day           — disclosures on signal day itself
  kap_type_breakdown       — "ODA:3 CA:2 FR:1" (KAP's six native types)
  kap_category_breakdown   — "YENI_IS:2 ESAS_SOZ:1 OZEL_DURUM:1"
                             (title-based mechanical labels, sorted by
                             count descending; pure OTHER entries dropped)

Graceful degradation: if KAP API fails, hits get None for these fields
and the scanner continues. KAP enrichment is NOT critical to scan output.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import requests

KAP_API = "https://www.kap.org.tr/tr/api/disclosure/list/main"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Type ordering for breakdown output. ODA first (most informative for our
# hypotheses), then the rest in fixed order for stable string comparison.
TYPE_ORDER = ["ODA", "CA", "FR", "DUY", "DG", "FON"]

# Turkish-aware lowercase: Python's lower() breaks on Turkish 'İ' (turns
# into 'i̇' with combining dot above) and 'I' (stays uppercase). Use a
# translate table to match the way these characters appear in KAP titles.
_TR_LOWER = str.maketrans({'İ': 'i', 'I': 'ı', 'Ş': 'ş', 'Ğ': 'ğ',
                            'Ü': 'ü', 'Ö': 'ö', 'Ç': 'ç'})


def _tr_lower(s):
    if not s:
        return ''
    return str(s).translate(_TR_LOWER).lower()


def _is_bedelsiz_split(summary):
    """Bedelsiz sermaye artırımı = mekanik split. Bu duyurular hisse
    fiyatında %50-80'lik düşüş yaratır ama bilgi değeri yok — yalnız
    technical bölünme. Aralıkta sayılmaması için elenir."""
    if not summary:
        return False
    return 'bedelsiz' in str(summary).lower()


def classify_category(title, summary, disclosure_type):
    """Mechanical title-based category assignment. Returns a single
    category label (e.g. 'YENI_IS') or 'OTHER' if no rule matches.

    This is pure pattern matching — no tier/edge judgment. It exists to
    make downstream analysis easier (filter signals_log by category
    rather than re-classifying titles each time).

    Categories cluster around the title patterns we've seen in KAP data,
    not around our current hypotheses. Add new ones as they appear; do
    NOT prune ones just because their backtest is weak — categorisation
    is mechanical, edge assessment is a separate downstream step.
    """
    t = _tr_lower(title)
    s = _tr_lower(summary)

    # FR (Finansal Rapor) — title gives the sub-type cleanly
    if disclosure_type == 'FR':
        if 'finansal rapor' in t and 'sorumluluk' not in t:
            return 'FR_BILANCO'
        if 'faaliyet raporu' in t and 'sorumluluk' not in t:
            return 'FR_FAALIYET'
        if 'sorumluluk beyanı' in t:
            return 'FR_SORUMLULUK'
        return 'FR_DIGER'

    # DG (Düzeltme/Güncelleme) — rutin form güncellemeleri
    if disclosure_type == 'DG':
        if 'şirket genel bilgi formu' in t:
            return 'DG_GENEL_BILGI'
        if 'kurumsal yönetim' in t and 'form' in t:
            return 'DG_KURUMSAL'
        if 'katılım finansı' in t:
            return 'DG_KATILIM_FORM'
        if 'piyasa yapıcı' in t:
            return 'DG_PIYASA_YAPICI'
        if 'haftalık rapor' in t:
            return 'DG_HAFTALIK'
        if 'halka arz' in t:
            return 'DG_HALKA_ARZ'
        if 'sermaye artırımından elde' in t or 'fonun kullanım' in t:
            return 'DG_SERMAYE_FON'
        if 'izahname' in t:
            return 'DG_IZAHNAME'
        if 'değerleme raporu' in t:
            return 'DG_DEGERLEME'
        if 'yatırımcı raporu' in t:
            return 'DG_YATIRIMCI'
        if 'esas sözleşme' in t:
            return 'DG_ESAS_SOZ'
        if 'ihraç belgesi' in t or 'tertip ihraç' in t:
            return 'DG_IHRAC'
        return 'DG_DIGER'

    # ODA / CA — operasyonel & kurumsal aksiyonlar
    if 'payların geri alın' in t or 'geri alım' in s:
        return 'BUYBACK'
    if 'pay alım satım' in t:
        return 'PAY_ALIM_SATIM'
    if 'yeni iş ilişkis' in t:
        return 'YENI_IS'
    if 'ihale' in t:
        return 'IHALE'
    if 'birleşme' in t:
        return 'BIRLESME'
    if 'finansal duran varlık edin' in t:
        return 'FDV_ALIM'
    if 'finansal duran varlık sat' in t:
        return 'FDV_SATIM'
    if 'kar pay' in t:
        return 'TEMETTU'
    if 'pay alım teklif' in t:
        return 'TENDER'
    if 'olağan dışı' in t:
        return 'OLAGAN_DISI'
    if 'kredi derecelendir' in t:
        return 'KREDI_NOTU'
    if 'sermaye artırımı' in t:
        return 'SERMAYE_ART'
    if 'borçlanma' in t or 'finansman bonosu' in t:
        return 'BORCLANMA'
    if 'dava' in t:
        return 'DAVA'
    if 'ilişkili taraf' in t:
        return 'ILISKILI_TARAF'
    if 'esas sözleşme' in t:
        return 'ESAS_SOZ'
    if 'genel kurul' in t:
        return 'GENEL_KURUL'
    if 'bağımsız denetim' in t:
        return 'DENETIM'
    if 'yönetim kurulu' in t and 'komite' in t:
        return 'YK_KOMITE'
    if 'kayıtlı sermaye' in t:
        return 'KAYITLI_SERMAYE'
    if 'ihraç tavan' in t:
        return 'IHRAC_TAVAN'
    if 'pay dışında sermaye piyasası' in t:
        return 'SPV_BILDIRIM'
    if 'varant' in t or 'sertifika' in t:
        return 'VARANT'
    if 'özel durum açıklama' in t:
        # Özel durum has very heterogeneous content; peek at summary
        # for the highest-value sub-cases.
        if 'pay başına net aktif değer' in s or 'ağırlıklı ortalama fiyat' in s:
            return 'GMYO_ASIRI_FIYAT'
        if 'tahsili gecikmiş alacak' in s:
            return 'TGA_ALIM'
        if 'üst yönetim' in s or 'genel müdür' in s or 'üst düzey yönetici' in s:
            return 'UST_YONETIM'
        return 'OZEL_DURUM'

    # DUY (Duyurular) — BIST/SPK/MKK genel piyasa duyuruları, ticker
    # boyunca düşmüyor genelde; ama gelirse not edelim
    if disclosure_type == 'DUY':
        return 'DUY_OTHER'

    return 'OTHER'


def _fetch_kap_window(from_date, to_date, retries=3):
    """Single KAP API call covering a date range. Returns list of
    disclosure dicts, or None on failure."""
    payload = {
        "fromDate": from_date,
        "toDate": to_date,
        "memberTypes": ["IGS"],
        "mkkMemberOid": None,
    }
    backoff = 2.0
    for attempt in range(retries):
        try:
            r = requests.post(KAP_API, headers=HEADERS, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
        except (requests.RequestException, json.JSONDecodeError) as e:
            if attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2
            else:
                print(f"  KAP fetch failed: {e}")
                return None
    return None


def _parse_disclosure(raw):
    """Normalize a single KAP response row into a flat dict.
    Returns None if the row is malformed."""
    basic = raw.get("disclosureBasic", {})
    publish = basic.get("publishDate", "") or ""
    if " " not in publish:
        return None
    date_part = publish.split(" ", 1)[0]
    try:
        dd, mm, yyyy = date_part.split(".")
        iso_date = f"{yyyy}-{mm}-{dd}"
    except ValueError:
        return None

    title = (basic.get("title", "") or "").strip()
    summary = (basic.get("summary", "") or "").strip()
    dtype = basic.get("disclosureType", "") or ""

    return {
        "ticker": basic.get("stockCode", "") or "",
        "disclosure_date": iso_date,
        "disclosure_type": dtype,
        "title": title,
        "summary": summary,
        "category": classify_category(title, summary, dtype),
    }


def _format_type_breakdown(type_counts):
    """Format {'ODA': 3, 'CA': 2} -> 'ODA:3 CA:2'. ODA always first."""
    parts = []
    for t in TYPE_ORDER:
        n = type_counts.get(t, 0)
        if n > 0:
            parts.append(f"{t}:{n}")
    for t, n in type_counts.items():
        if t not in TYPE_ORDER and n > 0:
            parts.append(f"{t}:{n}")
    return " ".join(parts)


def _format_category_breakdown(cat_counts):
    """Format {'YENI_IS': 2, 'ESAS_SOZ': 1, 'OTHER': 3} ->
    'YENI_IS:2 OTHER:3 ESAS_SOZ:1'. Sorted by count descending, then
    alphabetical for ties. OTHER is kept (signal that there are
    unclassified disclosures), but only shown when there's also at
    least one named category — pure OTHER-only signals get an empty
    breakdown to avoid noise."""
    if not cat_counts:
        return ""
    named = [c for c in cat_counts if c != 'OTHER']
    if not named:
        return ""  # only generic OTHERs — no signal value
    items = sorted(cat_counts.items(), key=lambda x: (-x[1], x[0]))
    return " ".join(f"{c}:{n}" for c, n in items)


def enrich_hits(hits, target_date, n_days=14):
    """Add KAP context columns to each hit in-place. Returns the same list.

    Args:
        hits: list of hit dicts from scan(). Each must have 'ticker' and 'date'.
        target_date: ISO date string (YYYY-MM-DD) for the scan, or None.
        n_days: calendar days lookback window for context (default 14).

    On API failure, hits get None for KAP fields and a warning is printed.
    """
    if not hits:
        return hits

    if target_date:
        scan_dt = datetime.strptime(target_date, "%Y-%m-%d")
    else:
        scan_dt = max(datetime.strptime(h["date"], "%Y-%m-%d") for h in hits)

    from_dt = scan_dt - timedelta(days=n_days + 1)
    from_str = from_dt.strftime("%d.%m.%Y")
    to_str = scan_dt.strftime("%d.%m.%Y")

    print(f"  KAP fetch: {from_str} -> {to_str} for {len(hits)} signals...")
    raw_rows = _fetch_kap_window(from_str, to_str)

    if raw_rows is None:
        for h in hits:
            h["kap_count_14d"] = None
            h["kap_oda_count_14d"] = None
            h["kap_signal_day"] = None
            h["kap_type_breakdown"] = None
            h["kap_category_breakdown"] = None
        print("  ! KAP API unreachable; KAP columns left blank.")
        return hits

    # Parse, dedupe by disclosureIndex, split multi-ticker rows, drop
    # bedelsiz splits, index by ticker.
    by_ticker = {}
    seen_indices = set()
    for raw in raw_rows:
        idx = raw.get("disclosureBasic", {}).get("disclosureIndex")
        if idx in seen_indices:
            continue
        seen_indices.add(idx)
        parsed = _parse_disclosure(raw)
        if parsed is None or not parsed["ticker"]:
            continue
        if _is_bedelsiz_split(parsed["summary"]):
            continue
        for t in parsed["ticker"].split(","):
            t = t.strip()
            if t:
                by_ticker.setdefault(t, []).append({**parsed, "ticker": t})

    enriched_count = 0
    for h in hits:
        t = h["ticker"].replace(".IS", "").strip()
        signal_dt = datetime.strptime(h["date"], "%Y-%m-%d")
        window_start = signal_dt - timedelta(days=n_days)

        records = by_ticker.get(t, [])
        in_window = []
        for r in records:
            try:
                d = datetime.strptime(r["disclosure_date"], "%Y-%m-%d")
                if window_start <= d <= signal_dt:
                    in_window.append((d, r))
            except ValueError:
                continue

        if not in_window:
            h["kap_count_14d"] = 0
            h["kap_oda_count_14d"] = 0
            h["kap_signal_day"] = 0
            h["kap_type_breakdown"] = ""
            h["kap_category_breakdown"] = ""
            continue

        type_counts = {}
        cat_counts = {}
        oda_count = 0
        signal_day_count = 0
        for d, r in in_window:
            dt = r["disclosure_type"] or "UNKNOWN"
            cat = r["category"]
            type_counts[dt] = type_counts.get(dt, 0) + 1
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            if dt == "ODA":
                oda_count += 1
            if d.date() == signal_dt.date():
                signal_day_count += 1

        h["kap_count_14d"] = len(in_window)
        h["kap_oda_count_14d"] = oda_count
        h["kap_signal_day"] = signal_day_count
        h["kap_type_breakdown"] = _format_type_breakdown(type_counts)
        h["kap_category_breakdown"] = _format_category_breakdown(cat_counts)

        enriched_count += 1

    print(f"  KAP enrichment done: {enriched_count}/{len(hits)} signals have KAP context.")
    return hits


# Column names that should be added to SIGNAL_COLUMNS in the scanner
KAP_COLUMNS = [
    "kap_count_14d",
    "kap_oda_count_14d",
    "kap_signal_day",
    "kap_type_breakdown",
    "kap_category_breakdown",
]
