"""Real market breadth: what share of the S&P 500 is above its own moving average.

S5FI and S5TH exist on TradingView and not on yfinance, and pulling twenty
years of them through a chart means dozens of scroll-and-read round trips plus
a dashboard that only runs while an app is open. Counting the constituents
directly costs one slow download, caches to CSV, and leaves the daily script
standing on its own.

Two things this is not:

  * It is not survivorship-free. The membership list is today's, applied
    backwards, so the 2008 reading is "how did the companies that survived to
    2026 look in 2008" - which flatters the past. Every history built this way
    has the bias; naming it is the difference between a limitation and a lie.

    How much it flatters was measured rather than assumed. Restricting the
    count to the 333 names already trading in 1999 and comparing against the
    full list moves the reading by +0.03pp on average, and by -0.10pp on the
    days under 20% above the 50-day - the two series correlate 0.9951. The
    reason is that this is a share of names above *their own* average, which is
    scale-free: a company that later halved still crossed its own mean about as
    often on the way. That test cannot see the companies that are gone
    entirely, so it bounds the composition effect, not the whole bias, and the
    dot-com bust is where the missing names would have hurt most.
  * It is not identical to S5FI. That index uses the membership of the day.
    Recent values should still line up closely, and `--check` prints today's
    number so it can be held against the live one.

    python breadth.py            # build or refresh breadth.csv
    python breadth.py --check    # print the last rows to compare with S5FI
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

CSV = Path(__file__).with_name("breadth.csv")
WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# 1996, not 2005: 337 of today's members were already trading in 1999, above
# the MIN_NAMES floor, so the breadth factors can be candidates from 1999 like
# everything else on the bench instead of waiting until 2008. The two hundred
# sessions before that are the 200-day warm-up.
START = "1996-01-01"
WINDOWS = {"s5fi": 50, "s5th": 200}
# CNN Fear & Greed's "stock price strength" leg: not distance from an average
# (that's s5th) but how many names are printing fresh 52-week highs against
# how many are printing fresh 52-week lows. A year of trading sessions.
HILO_WINDOW = 252
# Below this many reporting names a day is a data artefact, not a market.
MIN_NAMES = 300
# A day is also rejected when its universe shrinks against its own recent norm.
# On 2026-08-11 the count fell from 499 to 472 - twenty-seven names stopped
# reporting - and a percentage measured over a different set of companies than
# the day before is not comparable to it, however plausible the number looks.
# 0.97 keeps ordinary index turnover and rejects a feed dropping out.
MIN_SHARE_OF_NORM = 0.97
NORM_WINDOW = 60


def members() -> list[str]:
    """Today's S&P 500 tickers, in Yahoo's spelling.

    Fetched through requests rather than handed to read_html directly, because
    Wikipedia answers urllib's default user agent with a 403.
    """
    html = requests.get(WIKI, headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text
    table = pd.read_html(io.StringIO(html))[0]
    return [str(s).replace(".", "-") for s in table["Symbol"]]


def build(tickers: list[str], start: str) -> pd.DataFrame:
    """Download the members, then count them. The counting is `shares`."""
    raw = yf.download(tickers, start=start, auto_adjust=True, progress=False,
                      group_by="column", threads=True)
    px = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    return usable(shares(px.dropna(axis=1, how="all")))


def shares(px: pd.DataFrame) -> pd.DataFrame:
    """Share of names trading above their own 50- and 200-day average, daily.

    The denominator is the names that actually printed that day *and* have an
    average to be measured against, not the full list, so a ticker that had not
    listed yet neither counts nor drags.
    """
    out = {}
    for name, window in WINDOWS.items():
        above = px > px.rolling(window, min_periods=window).mean()
        # `above` is False both for a name under its average and for one with no
        # price at all, so the denominator has to come from the prices instead.
        reporting = px.notna() & px.rolling(window, min_periods=window).mean().notna()
        out[name] = above.sum(axis=1) / reporting.sum(axis=1) * 100
        out[f"{name}_n"] = reporting.sum(axis=1)

    roll_max = px.rolling(HILO_WINDOW, min_periods=HILO_WINDOW).max()
    roll_min = px.rolling(HILO_WINDOW, min_periods=HILO_WINDOW).min()
    reporting_hilo = px.notna() & roll_max.notna()
    at_high = (px >= roll_max) & reporting_hilo
    at_low = (px <= roll_min) & reporting_hilo
    n_hilo = reporting_hilo.sum(axis=1)
    out["s5nh"] = at_high.sum(axis=1) / n_hilo * 100
    out["s5nl"] = at_low.sum(axis=1) / n_hilo * 100
    out["s5nh_n"] = n_hilo
    return pd.DataFrame(out).round(2)


def usable(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop the days whose universe cannot be compared with its neighbours'.

    Two rejections, and neither is about the percentage looking wrong: too few
    names reporting at all, and a universe that shrank against its own recent
    norm. A share measured over a different set of companies than the day before
    is not comparable to it, however plausible the number looks.
    """
    frame = frame[frame["s5th_n"] >= MIN_NAMES]
    # Trailing median, so a day is judged against the universe that preceded it
    # rather than against one that includes itself and the days after it.
    norm = frame["s5th_n"].rolling(NORM_WINDOW, min_periods=10).median().shift(1)
    keep = norm.isna() | (frame["s5th_n"] >= norm * MIN_SHARE_OF_NORM)
    dropped = int((~keep).sum())
    if dropped:
        print(f"dropped {dropped} days where the universe shrank against its own norm "
              f"(last: {frame.index[~keep][-1]:%Y-%m-%d})")
    return frame[keep]


def load() -> pd.DataFrame:
    """The cached breadth history, or an empty frame if it was never built."""
    if not CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(CSV, index_col=0, parse_dates=True)


def selftest() -> None:
    idx = pd.bdate_range("2020-01-01", periods=260)
    # Two names above their average and one below, for every day once the
    # 200-day window fills. Anything that lists late must not drag the number
    # down while it has no average of its own.
    px = pd.DataFrame({
        "UP1": range(260), "UP2": range(260),
        "DOWN": [100.0] * 259 + [1.0],
        "LATE": [float("nan")] * 250 + [5.0] * 10,
    }, index=idx, dtype=float)
    last = shares(px).iloc[-1]
    assert last["s5th_n"] == 3, f"LATE has no 200-day average yet: {last['s5th_n']}"
    assert abs(last["s5th"] - 200 / 3) < 0.1, last["s5th"]
    # UP1/UP2 are strictly rising - always their own 252-day high. DOWN's one-day
    # drop to 1.0 is a new low against the flat 100.0 that preceded it. LATE still
    # has no 252-day window and must not count in either share.
    assert abs(last["s5nh"] - 2 / 3 * 100) < 0.1, last["s5nh"]
    assert abs(last["s5nl"] - 1 / 3 * 100) < 0.1, last["s5nl"]

    # A day whose universe collapses is rejected, not averaged over a different
    # set of companies than the day before it.
    n = [500] * 80 + [400]
    frame = pd.DataFrame({"s5fi": 60.0, "s5th": 70.0, "s5fi_n": n, "s5th_n": n},
                         index=pd.bdate_range("2020-01-01", periods=81))
    kept = usable(frame)
    assert len(kept) == 80, f"the collapsed day must go: {len(kept)}"
    assert kept.index[-1] == frame.index[-2]
    print("selftest ok")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=START)
    ap.add_argument("--check", action="store_true", help="print the tail, download nothing")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        selftest()
        return 0

    if a.check:
        frame = load()
        if frame.empty:
            print("breadth.csv does not exist yet - run without --check", file=sys.stderr)
            return 1
        print(frame.tail(10).to_string())
        return 0

    tickers = members()
    print(f"{len(tickers)} members, downloading from {a.start}...")
    frame = build(tickers, a.start)
    if frame.empty:
        print("nothing came back", file=sys.stderr)
        return 1
    frame.to_csv(CSV)
    print(f"wrote {CSV} - {len(frame)} days, {frame.index[0]:%Y-%m-%d} to {frame.index[-1]:%Y-%m-%d}")
    print(frame.tail(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
