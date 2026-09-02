"""Federal debt outstanding, daily, from the Treasury that issues it.

The question asked of this: does a government borrowing faster precede a fall
in equities. It is a real claim and a common one - "huge issuance", "swelling
deficits" - and it has never been on the bench. `stress.py` carries credit
spreads and the yield curve, both of which *price* the debt, but nothing that
counts it.

FRED was the obvious source and is the wrong one. Its debt series are
quarterly, and worse, FRED stamps an observation with the period it describes
rather than the day it was published: the Q4 2008 figure carries 2008-10-01
and was not knowable until the following February. Building a factor on that
stamp reads the future.

Treasury's own Fiscal Data API has no such problem. "Debt to the Penny" is
daily, back to 1993, and each record is published the next business day - so a
one-session shift is the whole of the correction, and it is a fact rather than
an estimate of a release calendar.

The level is useless on its own: federal debt only ever rises, so ranked
against its own trailing year it reads ~100 every day and carries nothing.
What can move either way is the pace, which is also the thing actually being
claimed - `stress.py` builds those readings, this file only fetches.

    python debt.py            # build or refresh debt.csv
    python debt.py --check    # print the tail, download nothing
    python debt.py --selftest
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

CSV = Path(__file__).with_name("debt.csv")
URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
       "/v2/accounting/od/debt_to_penny")
FIELDS = "record_date,tot_pub_debt_out_amt,debt_held_public_amt"
PAGE = 10000  # the whole history since 1993 is about 8,400 rows


def fetch() -> pd.DataFrame:
    """Every daily record, oldest first, shifted to the day it was published.

    A record dated the 31st is posted on the next business day, so the reading
    is stamped there instead: on the 31st itself nobody outside Treasury had it.
    """
    rows, page = [], 1
    while True:
        reply = requests.get(URL, timeout=60, headers={"User-Agent": "market-stress"},
                             params={"fields": FIELDS, "sort": "record_date",
                                     "page[size]": PAGE, "page[number]": page})
        reply.raise_for_status()
        got = reply.json().get("data", [])
        rows += got
        if len(got) < PAGE:
            break
        page += 1
    frame = pd.DataFrame(rows)
    frame["record_date"] = pd.to_datetime(frame["record_date"])
    # `.values`, not the Series: the numeric columns still carry the frame's
    # RangeIndex, and pairing them with a date index by label instead of by
    # position reindexes every row to NaN. valuation.py has the same note.
    # "null" arrives as a string in the early years of debt_held_public_amt,
    # which coerces to NaN and is left as one - `how="all"` keeps those rows
    # for the sake of the total, which is present throughout.
    out = pd.DataFrame({
        "total": pd.to_numeric(frame["tot_pub_debt_out_amt"], errors="coerce").values,
        "public": pd.to_numeric(frame["debt_held_public_amt"], errors="coerce").values,
    }, index=pd.DatetimeIndex(frame["record_date"])).sort_index().dropna(how="all")
    out.index = out.index + pd.offsets.BDay(1)
    out.index.name = "date"
    return out


def load() -> pd.DataFrame:
    """The cached file, or an empty frame if it was never built."""
    if not CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(CSV, index_col=0, parse_dates=True)


def selftest() -> None:
    # The publication shift must move every stamp forward by a session, so a
    # day's figure is never available on the day it measures.
    idx = pd.DatetimeIndex(["2008-12-31", "2026-08-31"])
    moved = idx + pd.offsets.BDay(1)
    assert (moved > idx).all(), moved
    assert moved[0] == pd.Timestamp("2009-01-01"), moved[0]
    # A Friday record must land on the Monday, not on the Saturday.
    friday = pd.DatetimeIndex(["2026-08-28"]) + pd.offsets.BDay(1)
    assert friday[0] == pd.Timestamp("2026-08-31"), friday[0]
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
            print("no debt.csv yet", file=sys.stderr)
            return 1
    else:
        frame = fetch()
        frame.to_csv(CSV, index_label="date")
        print(f"wrote {CSV} - {len(frame)} rows, "
              f"{frame.index[0]:%Y-%m-%d} to {frame.index[-1]:%Y-%m-%d}")
    print((frame.tail(5) / 1e12).round(3).to_string() + "   (trillions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
