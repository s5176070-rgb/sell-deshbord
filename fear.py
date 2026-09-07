"""CNN's Fear & Greed index - shown beside the score, never inside it.

It is on the page because it is the sentiment reading people actually check,
and because the two agree: over the 251 overlapping sessions measured on
2026-09-04, `100 - fear_greed` against the MSS percentile correlates 0.814,
with CNN reading 9.4 points more fearful on average. Four of its seven
components are already in the model in a more direct form - VIX, put/call,
junk-bond demand, breadth - so it is largely a repackaging of what is scored.

It is NOT a factor and cannot become one. CNN publishes a rolling year: the
feed answers 252 rows and nothing older. `stress.py` needs MIN_TRAIN=756 rows
before a candidate is even ranked, and the walk-forward needs years that
precede the year being tested. There is nothing to test it on.

Hence the cache: every run merges the fresh year into `fear.csv`, so the file
grows past CNN's window one session at a time. That still does not make it
testable for years, and the panel says so on its face.

    python fear.py            # merge today's year into fear.csv
    python fear.py --check    # print the tail, download nothing
    python fear.py --selftest
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

CSV = Path(__file__).with_name("fear.csv")
URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
# The endpoint answers HTML to a bare request and JSON only to a browser-shaped
# one. Both headers are load-bearing; dropping either returns the SPA shell.
HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://edition.cnn.com/", "Accept": "application/json"}


def fetch() -> pd.Series:
    """The published year, one value per session, oldest first.

    The live intraday reading is dropped: it carries a wall-clock timestamp
    rather than a midnight one, and keeping it would put two rows on today -
    one of them a partial session that gets revised at the close.
    """
    reply = requests.get(URL, timeout=30, headers=HEAD)
    reply.raise_for_status()
    rows = reply.json()["fear_and_greed_historical"]["data"]
    out = pd.Series({pd.Timestamp(r["x"], unit="ms").normalize(): float(r["y"])
                     for r in rows}).sort_index()
    out.index.name = "date"
    out.name = "fear_greed"
    return out


def merge(fresh: pd.Series, cached: pd.Series | None = None) -> pd.Series:
    """Cached history, with the fresh year written over it.

    Fresh wins on any overlapping day - CNN revises the last session once it
    closes, and a stale partial reading is worse than no reading.
    """
    if cached is None or cached.empty:
        return fresh
    return fresh.combine_first(cached).sort_index()


def load() -> pd.Series:
    """The cached file, or an empty series if it was never built."""
    if not CSV.exists():
        return pd.Series(dtype=float, name="fear_greed")
    return pd.read_csv(CSV, index_col=0, parse_dates=True)["fear_greed"]


def gather() -> tuple[int, int]:
    """Merge the published year into the cache. Returns (new days, total)."""
    cached = load()
    out = merge(fetch(), cached)
    out.to_csv(CSV, index_label="date")
    return len(out) - len(cached), len(out)


def selftest() -> None:
    old = pd.Series([10.0, 20.0, 30.0],
                    index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]))
    new = pd.Series([99.0, 40.0],
                    index=pd.to_datetime(["2026-01-03", "2026-01-04"]))
    got = merge(new, old)
    # History older than CNN's window survives...
    assert len(got) == 4, got
    assert got.loc["2026-01-01"] == 10.0, got
    # ...and a revised session takes the fresh value, not the cached one.
    assert got.loc["2026-01-03"] == 99.0, got
    assert got.index.is_monotonic_increasing
    # An empty cache is the first run, not an error.
    assert merge(new).equals(new)
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
        out = load()
        if out.empty:
            print("no fear.csv yet", file=sys.stderr)
            return 1
    else:
        new, total = gather()
        out = load()
        print(f"wrote {CSV} - {new} new, {total} days, "
              f"{out.index[0]:%Y-%m-%d} to {out.index[-1]:%Y-%m-%d}")
    print(out.tail(5).round(1).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
