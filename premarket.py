"""Premarket gap: what the futures are doing now, and what a gap this size
preceded in 36 years of history.

The score in `stress.py` is built on daily closes and knows nothing about the
hours before the bell. This is the separate question - the market is already
down 1% before it opens, does that matter - answered the only honest way, by
counting. Two numbers per bucket, both measured on the S&P itself:

    same day    how often the session closed 2% or more below the day before
    next 20     how often the same 5%-in-20-sessions event `stress.py` scores
                followed, so a gap can be read on the dashboard's own scale

The live reading uses the front S&P future (ES=F) and SPY's premarket prints.
The history uses the index open against the previous close, because there is
no 36-year record of futures quotes at 08:30 - the open gap is the closest
long series to the same thing, and the buckets are wide enough to survive the
difference.

Nothing here feeds the score. It is context, like the CNN sentiment reading.

    python premarket.py             # live gap + the historical table
    python premarket.py --offline   # the table only, from the cached file
    python premarket.py --selftest  # the counting, on a series with known gaps
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from stress import START, event_labels

HERE = Path(__file__).parent
CACHE = HERE / "spx_ohlc.csv"     # open and close, so the table can run offline

# Wide buckets: the open gap is a proxy for the premarket move, not the same
# number, and narrow buckets would promise a precision the proxy cannot carry.
BUCKETS = [(-99, -1.5, "נפילה חדה, ‎-1.5% ומטה"),
           (-1.5, -0.75, "ירידה בולטת, ‎-1.5% עד ‎-0.75%"),
           (-0.75, -0.25, "ירידה קלה, ‎-0.75% עד ‎-0.25%"),
           (-0.25, 0.25, "פתיחה שטוחה, ‎±0.25%"),
           (0.25, 99, "פתיחה בעלייה, מעל ‎+0.25%")]

SAME_DAY_DROP = -0.02             # the "sharp fall today" the table counts

# Alert levels, taken from the table itself and not from taste: a gap under
# -0.75% has closed 2% down roughly eight times as often as an average day,
# and one under -1.5% has done it in three sessions out of four.
ALERT, SEVERE = -0.75, -1.5


def ohlc(offline: bool) -> pd.DataFrame:
    """Daily open and close for the index, cached beside the other CSVs."""
    if offline:
        if not CACHE.exists():
            sys.exit(f"אין קובץ שמור: {CACHE.name}. הריצו בלי --offline פעם אחת.")
        return pd.read_csv(CACHE, index_col=0, parse_dates=True)
    import yfinance as yf
    raw = yf.download("^GSPC", start=START, auto_adjust=False, progress=False)
    if raw.empty:
        sys.exit("הורדת ^GSPC נכשלה.")
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs("^GSPC", axis=1, level=1)
    df = raw[["Open", "Close"]].dropna()
    df.to_csv(CACHE, index_label="date")
    return df


def gaps(df: pd.DataFrame) -> pd.DataFrame:
    """Open against the previous close, plus what that session did after it."""
    prev = df["Close"].shift(1)
    out = pd.DataFrame({"gap": df["Open"] / prev - 1,
                        "same_day": df["Close"] / prev - 1}).dropna()
    return out


def table(offline: bool) -> pd.DataFrame:
    """One row per gap bucket: how many days, and what followed them."""
    prices = ohlc(offline)
    g = gaps(prices)
    y = event_labels(prices["Close"]).reindex(g.index)
    valid = y.notna()
    g = g.loc[valid]
    y = y.loc[valid].astype(bool)
    rows = []
    for lo, hi, label in BUCKETS:
        m = (g["gap"] * 100 >= lo) & (g["gap"] * 100 < hi)
        rows.append({"מה קרה לפני הפתיחה": label, "ימים": int(m.sum()),
                     "ירד 2%+ באותו יום": round(
                         float((g.loc[m, "same_day"] <= SAME_DAY_DROP).mean()) * 100, 1),
                     "נפילה של 5% ב-20 יום": round(float(y[m].mean()) * 100, 1)})
    rows.append({"מה קרה לפני הפתיחה": "כל הימים", "ימים": len(g),
                 "ירד 2%+ באותו יום": round(
                     float((g["same_day"] <= SAME_DAY_DROP).mean()) * 100, 1),
                 "נפילה של 5% ב-20 יום": round(float(y.mean()) * 100, 1)})
    return pd.DataFrame(rows)


def live() -> dict[str, float | pd.Timestamp]:
    """The premarket move right now, from the future and from SPY's prints."""
    import yfinance as yf
    out = {}
    for ticker in ("ES=F", "SPY"):
        bars = yf.download(ticker, period="5d", interval="5m", prepost=True,
                           auto_adjust=False, progress=False)
        if bars.empty:
            raise RuntimeError(f"אין ציטוטים ל-{ticker}.")
        close = bars["Close"].squeeze().dropna()
        close.index = close.index.tz_convert("America/New_York")
        prev = float(yf.Ticker(ticker).fast_info.previous_close)
        out[ticker] = float(close.iloc[-1]) / prev - 1
        out[ticker + "_at"] = close.index[-1]
    return out


def market_session(at: pd.Timestamp) -> str:
    """US equity session at a timezone-aware quote timestamp."""
    ny = at.tz_convert("America/New_York")
    if ny.weekday() >= 5:
        return "סגור"
    minutes = ny.hour * 60 + ny.minute
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return "פרימרקט"
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return "מסחר רגיל"
    if 16 * 60 <= minutes < 20 * 60:
        return "אפטר־מרקט"
    return "סגור"


def snapshot() -> dict:
    """JSON-ready live context for the dashboard; never changes the MSS score."""
    quotes = live()
    es_at = pd.Timestamp(quotes["ES=F_at"])
    spy_at = pd.Timestamp(quotes["SPY_at"])
    newest = max(es_at, spy_at)
    age = max(0, int((pd.Timestamp.now(tz="UTC") - newest.tz_convert("UTC")).total_seconds() // 60))
    es_pct = float(quotes["ES=F"]) * 100
    label, _ = bucket_of(es_pct)
    history = table(offline=True)
    match = history[history["מה קרה לפני הפתיחה"] == label]
    historical = None
    if not match.empty:
        row = match.iloc[0]
        historical = {
            "label": label,
            "days": int(row["ימים"]),
            "same_day_drop_pct": float(row["ירד 2%+ באותו יום"]),
            "drawdown_20d_pct": float(row["נפילה של 5% ב-20 יום"]),
        }
    return {
        "session": market_session(newest),
        "status": status(es_pct),
        "is_stale": age > 30,
        "age_minutes": age,
        "es": {"change_pct": es_pct, "at": es_at.tz_convert("Asia/Jerusalem").isoformat()},
        "spy": {"change_pct": float(quotes["SPY"]) * 100,
                "at": spy_at.tz_convert("Asia/Jerusalem").isoformat()},
        "historical": historical,
        "source": "Yahoo Finance דרך yfinance",
        "score_input": False,
    }


def bucket_of(gap_pct: float) -> tuple[str, pd.Series | None]:
    """The historical row a live gap of this size belongs to."""
    for lo, hi, label in BUCKETS:
        if lo <= gap_pct < hi:
            return label, None
    return "מחוץ לטווח", None


def status(gap_pct: float) -> str:
    """The one line a scheduled run is there to print."""
    if gap_pct <= SEVERE:
        return f"התראה חריגה: פער פתיחה {gap_pct:+.2f}%, מתחת ל-{SEVERE}%"
    if gap_pct <= ALERT:
        return f"התראה: פער פתיחה {gap_pct:+.2f}%, מתחת ל-{ALERT}%"
    return f"רגיל: פער פתיחה {gap_pct:+.2f}%, מעל סף ההתראה ({ALERT}%)"


def report(offline: bool) -> None:
    t = table(offline)
    if not offline:
        now = live()
        es = now["ES=F"] * 100
        stamp = now["ES=F_at"].tz_convert("Asia/Jerusalem").strftime("%d.%m %H:%M")
        print("— פרימרקט —")
        print(status(es))
        print(f"חוזי S&P: {es:+.2f}%   SPY: {now['SPY'] * 100:+.2f}%"
              f"   ({stamp} שעון ישראל)")
        label, _ = bucket_of(es)
        row = t[t["מה קרה לפני הפתיחה"] == label]
        if not row.empty:
            r = row.iloc[0]
            print(f"היסטורית, פתיחות מהסוג הזה ({label}, {r['ימים']} ימים):")
            print(f"  ירדו 2% ומעלה באותו יום: {r['ירד 2%+ באותו יום']}%")
            print(f"  לוו בנפילה של 5% ב-20 מפגשים: {r['נפילה של 5% ב-20 יום']}%")
        print()
    print(t.to_string(index=False))
    print("\n— תמונת הקשר בלבד. הפרימרקט לא נכנס לציון ואינו הוראת פעולה —")


def selftest() -> None:
    """Count on a series whose gaps are known by construction."""
    idx = pd.bdate_range("2020-01-01", periods=6)
    # closes 100, opens chosen so gap 1 is -2%, gap 2 is +1%, rest flat
    df = pd.DataFrame({"Open": [100, 98, 101, 100, 100, 100],
                       "Close": [100.0] * 6}, index=idx)
    g = gaps(df)
    assert len(g) == 5, g
    assert round(g["gap"].iloc[0] * 100, 2) == -2.0, g["gap"].iloc[0]
    assert round(g["gap"].iloc[1] * 100, 2) == 1.0, g["gap"].iloc[1]
    assert (g["same_day"] == 0).all(), g["same_day"]
    assert bucket_of(-2.0)[0] == BUCKETS[0][2]
    assert bucket_of(0.0)[0] == BUCKETS[3][2]
    assert status(-2.0).startswith("התראה חריגה"), status(-2.0)
    assert status(-1.0).startswith("התראה:"), status(-1.0)
    assert status(-0.3).startswith("רגיל"), status(-0.3)
    monday = pd.Timestamp("2026-09-14 08:00", tz="America/New_York")
    assert market_session(monday) == "פרימרקט"
    assert market_session(monday.replace(hour=10)) == "מסחר רגיל"
    assert market_session(monday.replace(hour=17)) == "אפטר־מרקט"
    assert market_session(pd.Timestamp("2026-09-13 10:00", tz="America/New_York")) == "סגור"
    print("selftest ok")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline", action="store_true", help="בלי הורדות")
    p.add_argument("--selftest", action="store_true", help="בדיקות, בלי רשת")
    a = p.parse_args()
    if a.selftest:
        selftest()
        return 0
    report(a.offline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
