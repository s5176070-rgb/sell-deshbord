"""S&P 500 trailing P/E, monthly, from multpl.com.

Yardeni's forward-earnings tape (price against consensus forward EPS x15) is
LSEG data behind a paywall - not available here. multpl.com publishes the
same shape of question with real trailing twelve-month earnings instead of
an analyst estimate: is price stretched above what the index is actually
earning. Monthly, not daily, and that is the honest cost of a free source -
`stress.py` forward-fills it like it does every other slow feed.

    python valuation.py            # build or refresh valuation.csv
    python valuation.py --check    # print the tail, download nothing
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

import pandas as pd
import requests

CSV = Path(__file__).with_name("valuation.csv")
URL = "https://www.multpl.com/s-p-500-pe-ratio/table/by-month"


def fetch() -> pd.DataFrame:
    """The monthly P/E table, oldest first, indexed by date."""
    html = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text
    table = pd.read_html(io.StringIO(html))[0]
    table["Date"] = pd.to_datetime(table["Date"], format="%b %d, %Y")
    # The latest row is an in-progress estimate flagged with a leading glyph
    # ("estimate"); stripping to the numeric characters keeps the value and
    # drops the flag rather than dropping the row.
    pe = table["Value"].astype(str).str.replace(r"[^0-9.]", "", regex=True)
    # `pe` keeps table's original RangeIndex; pairing it with the date index
    # below by position (`.values`), not by label, is what avoids an all-NaN
    # reindex against dates that share none of those integer labels.
    out = pd.DataFrame({"pe": pd.to_numeric(pe).values}, index=table["Date"]).sort_index()
    out.index.name = "date"
    return out


def load() -> pd.DataFrame:
    """The cached P/E history, or an empty frame if it was never built."""
    if not CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(CSV, index_col=0, parse_dates=True)


def selftest() -> None:
    html = """<table><tr><th>Date</th><th>Value</th></tr>
    <tr><td>Aug 28, 2026</td><td>&#9679; 29.72</td></tr>
    <tr><td>Jul 1, 2026</td><td>28.71</td></tr></table>"""
    table = pd.read_html(io.StringIO(html))[0]
    table["Date"] = pd.to_datetime(table["Date"], format="%b %d, %Y")
    pe = table["Value"].astype(str).str.replace(r"[^0-9.]", "", regex=True)
    values = pd.to_numeric(pe).tolist()
    assert values == [29.72, 28.71], f"the estimate glyph must not survive: {values}"
    out = pd.DataFrame({"pe": pd.to_numeric(pe).values}, index=table["Date"]).sort_index()
    assert out["pe"].notna().all(), f"pairing by position must not reindex to NaN: {out}"
    print("selftest ok")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="print the tail, download nothing")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        selftest()
        return 0

    if a.check:
        frame = load()
        if frame.empty:
            print("valuation.csv does not exist yet - run without --check", file=sys.stderr)
            return 1
        print(frame.tail(10).to_string())
        return 0

    frame = fetch()
    frame.to_csv(CSV)
    print(f"wrote {CSV} - {len(frame)} months, {frame.index[0]:%Y-%m-%d} to {frame.index[-1]:%Y-%m-%d}")
    print(frame.tail(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
