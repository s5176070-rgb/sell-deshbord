"""S&P 500 trailing P/E, monthly, from Robert Shiller's data (shillerdata.com).

Yardeni's forward-earnings tape (price against consensus forward EPS x15) is
LSEG data behind a paywall - not available here. Shiller's workbook answers
the same shape of question with real trailing twelve-month earnings instead of
an analyst estimate: is price stretched above what the index is actually
earning. Monthly, not daily, and that is the honest cost of a free source -
`stress.py` forward-fills it like it does every other slow feed.

Until 2026-11 this read multpl.com's monthly table. multpl refused every
connection from 2026-11-24 on (port 443 and 80, from here and from an
independent network), and its history is Shiller's: measured 2026-11-28, the
two series agree to within 0.04% on every month from 1871 to 2019. From 2020
they differ by up to 9% because the stored multpl copy carried preliminary
earnings that Shiller has since replaced with reported ones.

The series keeps multpl's shape: one row per month with both price (monthly
average close) and earnings, plus one current estimate after the last
earnings month - the latest price over the latest trailing earnings, which is
how multpl computed its own top row.

    python valuation.py            # build or refresh valuation.csv
    python valuation.py --check    # print the tail, download nothing
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

CSV = Path(__file__).with_name("valuation.csv")
PAGE = "https://shillerdata.com/"
# The download link carries a per-upload GUID, so it is read off the page on
# every run. The fixed copies still answer 200 but stopped updating: the Yale
# one ends 2023-09, an older shillerdata upload 2024-09 (both read 2026-11-28).
LINK = re.compile(r'href="((?:https:)?//img1\.wsimg\.com/[^"]*/ie_data\.xls[^"]*)"')
# Shiller adds a quarter's earnings once S&P has them, so the newest earnings
# month trails today by about three to five months (2026-11-28: September).
# Older than this means the workbook stopped updating, not a normal lag.
MAX_EARNINGS_AGE_DAYS = 183


def parse(raw: pd.DataFrame, latest: pd.Series | None = None,
          today: pd.Timestamp | None = None) -> pd.DataFrame:
    """Shiller's Data sheet (first four columns, header rows dropped) to a P/E frame.

    `latest` is an optional daily close series; when given, the current
    estimate uses its last close instead of Shiller's last monthly price.
    """
    d = raw.iloc[:, :4].copy()
    d.columns = ["date", "P", "D", "E"]
    # Dates are year.month decimals; October is 2026.1, so the month is read
    # off two decimals, not off the string. Note rows have no number here.
    num = pd.to_numeric(d["date"], errors="coerce")
    d, num = d[num.notna()], num[num.notna()]
    year = np.floor(num + 1e-9).astype(int)
    month = np.rint((num - year) * 100).astype(int)
    d.index = pd.to_datetime(pd.DataFrame({"year": year, "month": month, "day": 1}))
    price = pd.to_numeric(d["P"], errors="coerce")
    earnings = pd.to_numeric(d["E"], errors="coerce").dropna()
    if earnings.empty:
        raise RuntimeError("Shiller workbook has no earnings column values")

    today = pd.Timestamp.today().normalize() if today is None else today
    age = (today - earnings.index[-1]).days
    if age > MAX_EARNINGS_AGE_DAYS:
        raise RuntimeError(f"newest Shiller earnings are for {earnings.index[-1]:%Y-%m}, "
                           f"{age} days old - the workbook has stopped updating")

    pe = (price / earnings).dropna()
    if latest is not None and len(latest.dropna()):
        last = latest.dropna()
        when, close = last.index[-1].normalize(), float(last.iloc[-1])
    else:
        after = price[price.index > pe.index[-1]].dropna()
        when, close = (after.index[-1], float(after.iloc[-1])) if len(after) else (None, None)
    if when is not None and when > pe.index[-1]:
        pe.loc[when] = close / float(earnings.iloc[-1])

    out = pe.sort_index().to_frame("pe")
    out.index.name = "date"
    return out


def fetch(latest: pd.Series | None = None) -> pd.DataFrame:
    """The monthly P/E series, oldest first, indexed by date."""
    page = requests.get(PAGE, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    page.raise_for_status()
    found = LINK.search(page.text)
    if not found:
        raise RuntimeError(f"no ie_data.xls link on {PAGE} - the page layout changed")
    url = found.group(1)
    url = "https:" + url if url.startswith("//") else url
    book = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    book.raise_for_status()
    # The first eight rows are titles and the column header.
    raw = pd.read_excel(io.BytesIO(book.content), sheet_name="Data", header=None,
                        skiprows=8, engine="calamine")
    return parse(raw, latest)


def load() -> pd.DataFrame:
    """The cached P/E history, or an empty frame if it was never built."""
    if not CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(CSV, index_col=0, parse_dates=True)


def selftest() -> None:
    nan = float("nan")
    raw = pd.DataFrame([
        [2025.1, 6735.69, 78.36, 235.44],   # October with earnings: must not read as January
        [2026.08, 7711.32, 81.67, 284.54],
        [2026.09, 7669.41, 81.99, 295.52],
        [2026.1, 7726.69, nan, nan],        # October, written as a float
        [2026.11, 7619.38, nan, nan],
        [nan, "Nov price is Nov 12th close", nan, nan],
    ])
    today = pd.Timestamp("2026-11-28")
    out = parse(raw, today=today)
    assert list(out.index) == [pd.Timestamp(s) for s in
                               ("2025-10-01", "2026-08-01", "2026-09-01", "2026-11-01")], out
    assert abs(out["pe"].iloc[1] - 7711.32 / 284.54) < 1e-9, "a month with earnings is price over earnings"
    assert abs(out["pe"].iloc[-1] - 7619.38 / 295.52) < 1e-9, \
        "the estimate is the last price over the last earnings, months without earnings dropped"
    assert out["pe"].notna().all(), out

    closes = pd.Series([7300.0, 7296.0], index=pd.to_datetime(["2026-11-26", "2026-11-27"]))
    live = parse(raw, latest=closes, today=today)
    assert live.index[-1] == pd.Timestamp("2026-11-27"), live
    assert abs(live["pe"].iloc[-1] - 7296.0 / 295.52) < 1e-9, "a daily close replaces the monthly price"
    assert pd.Timestamp("2026-11-01") not in live.index, "only one estimate row"

    try:
        parse(raw, today=pd.Timestamp("2027-06-01"))
    except RuntimeError as e:
        assert "stopped updating" in str(e)
    else:
        raise AssertionError("earnings nine months old must fail loudly")

    assert LINK.search('<a href="//img1.wsimg.com/blobby/go/x/downloads/y/ie_data.xls?ver=1">')
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
