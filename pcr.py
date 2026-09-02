"""CBOE's own put/call ratios, one JSON file per session, no key and no cap.

alpha.py builds the SPY-chain ratio at twenty-five days a year of free-tier
calls; at that pace the series needs another month before stress.py may rank
it. CBOE publishes the whole market's ratios every evening at a public URL that
answers as fast as it is asked, back to December 2019. This gathers what is
missing into `cboe_putcall.csv` and stress.py reads the total ratio from here
first, falling back to the Alpha Vantage file only while this one is short.

    python pcr.py            # fetch every missing session
    python pcr.py --selftest
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).parent
CSV = HERE / "cboe_putcall.csv"
URL = "https://cdn.cboe.com/data/us/options/market_statistics/daily/{date}_daily_options"
FIRST = "2019-12-02"  # anything earlier answers 403
KEEP = {"TOTAL PUT/CALL RATIO": "total", "EQUITY PUT/CALL RATIO": "equity",
        "INDEX PUT/CALL RATIO": "index", "SPX + SPXW PUT/CALL RATIO": "spx"}
# A 403 on a recent date is a file not posted yet; on an old one it is a
# holiday. Only the old ones are written down (as an empty row) so they are
# not asked for again every evening.
SETTLED_AFTER = 5  # business days


def load() -> pd.DataFrame:
    """Ratios gathered so far, oldest first, holidays left out."""
    if not CSV.exists():
        return pd.DataFrame(columns=list(KEEP.values()), index=pd.DatetimeIndex([], name="date"))
    return pd.read_csv(CSV, index_col=0, parse_dates=True).sort_index().dropna(how="all")


def fetch_day(date: pd.Timestamp) -> dict | None:
    """One session's ratios, or None when CBOE has no file for that date."""
    reply = requests.get(URL.format(date=date.date()), timeout=20,
                         headers={"User-Agent": "market-stress"})
    if reply.status_code in (403, 404):
        return None
    reply.raise_for_status()
    got = {r["name"]: float(r["value"]) for r in reply.json().get("ratios", [])}
    return {col: got.get(name) for name, col in KEEP.items()}


def gather(note=print) -> tuple[int, int]:
    """Fetch every session not yet on disk. Returns (fetched, rows usable)."""
    have = pd.read_csv(CSV, index_col=0, parse_dates=True).index if CSV.exists() \
        else pd.DatetimeIndex([])
    today = pd.Timestamp.now(tz="America/New_York").normalize().tz_localize(None)
    sessions = pd.bdate_range(FIRST, today - pd.Timedelta(days=1))
    missing = sessions.difference(have)
    rows, fetched = [], 0
    for i, day in enumerate(missing):
        got = fetch_day(day)
        if got is not None:
            rows.append({"date": day, **got})
            fetched += 1
        elif day < today - pd.offsets.BDay(SETTLED_AFTER):
            rows.append({"date": day, **{c: None for c in KEEP.values()}})
        if i and i % 250 == 0:
            note(f"CBOE put/call: {fetched} fetched, {len(missing) - i} to go")
    if rows:
        new = pd.DataFrame(rows).set_index("date")
        old = pd.read_csv(CSV, index_col=0, parse_dates=True) if CSV.exists() else None
        pd.concat([old, new]).sort_index().to_csv(CSV, index_label="date")
    return fetched, len(load())


def selftest() -> None:
    # A settled 403 is a holiday and is recorded; a fresh one is retried later.
    today = pd.Timestamp("2026-09-02")
    assert pd.Timestamp("2026-08-20") < today - pd.offsets.BDay(SETTLED_AFTER)
    assert not pd.Timestamp("2026-09-01") < today - pd.offsets.BDay(SETTLED_AFTER)
    # load() hides the holiday rows but keeps them on disk for gather().
    frame = pd.DataFrame({"total": [0.9, None], "equity": [0.7, None]},
                         index=pd.DatetimeIndex(["2026-01-02", "2026-01-01"], name="date"))
    assert len(frame.sort_index().dropna(how="all")) == 1
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        fetched, rows = gather()
        print(f"{fetched} new, {rows} rows usable")
