"""A slower question beside the score: a 20% fall within a year, given the P/E.

MSS asks about the next 20 sessions, and at that horizon a stretched market
barely moves the odds (measured 2026-11-01 from 1927: a 5% fall followed 21% of
days with the trailing P/E above 90% of its history, 17% of the rest). Over a
year it does: a 20% fall followed 28% of those days against 13% of the rest,
and the gap held from 1950 (20% vs 8%) and from 1980 (20% vs 6%). Shiller's
CAPE was tried in its place and separated less (21% vs 16% from 1927).

This is context, shown beside the score and never inside it, like the
premarket gap. It does not say when: from 1991 to 1999 the P/E sat in its top
band for years and no such fall came.

    python yearly.py            # recompute yearly.json (S&P 500 closes since 1927)
    python yearly.py --check    # print yearly.json, download nothing
    python yearly.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

import valuation

JSON = Path(__file__).with_name("yearly.json")
HORIZON = 252          # sessions ahead, about one year
DEPTH = -0.20          # deepest close at or below this, against today's close
PE_FROM = "1900-01-01"
PRICES_FROM = "1927-01-01"  # ^GSPC's first daily close on Yahoo
WARMUP_MONTHS = 240    # a month is ranked only against twenty years before it
BANDS = [0, 50, 80, 90, 101]
LABELS = ["<50", "50-80", "80-90", "90+"]


def percentile(pe: pd.Series) -> pd.Series:
    """Each month's P/E against every earlier month only - no later month moves it."""
    pe = pe[pe.index >= PE_FROM].dropna()
    return pe.expanding(WARMUP_MONTHS).apply(lambda s: (s[:-1] < s[-1]).mean() * 100, raw=True)


def worst_ahead(px: pd.Series, horizon: int = HORIZON) -> pd.Series:
    """Deepest close over the next `horizon` sessions, not counting today, as a return."""
    return px.rolling(horizon).min().shift(-horizon) / px - 1


def compute(pe: pd.Series, px: pd.Series, horizon: int = HORIZON) -> dict:
    pct_m = percentile(pe).dropna()
    if pct_m.empty:
        raise RuntimeError(f"P/E history shorter than {WARMUP_MONTHS} months")
    pct = pct_m.reindex(px.index, method="ffill")
    band = pd.cut(pct, BANDS, labels=LABELS, right=False)
    worst = worst_ahead(px, horizon)
    d = pd.DataFrame({"band": band, "event": (worst <= DEPTH).where(worst.notna())})
    d = d.dropna()  # rank warm-up at the front, open windows at the back
    if d.empty:
        raise RuntimeError("no day has both a P/E rank and a finished window")
    now = float(pct_m.iloc[-1])
    now_band = LABELS[next(i for i in range(len(LABELS)) if BANDS[i] <= now < BANDS[i + 1])]
    rates = d.groupby("band", observed=False)["event"].agg(["mean", "size"])
    recent = band.loc["1990":]
    return {
        "as_of": f"{pct_m.index[-1]:%Y-%m-%d}",
        "prices_to": f"{px.index[-1]:%Y-%m-%d}",
        "history_from": f"{d.index[0]:%Y-%m-%d}",
        "horizon": horizon,
        "depth_pct": DEPTH * 100,
        "pe": float(pe.dropna().iloc[-1]),
        "percentile": round(now, 1),
        "band": now_band,
        "chance": round(float(rates.loc[now_band, "mean"]) * 100, 1),
        "days": int(rates.loc[now_band, "size"]),
        "baseline": round(float(d["event"].mean()) * 100, 1),
        "since_1990_share": round(float((recent == now_band).mean()) * 100, 1),
        "bands": [{"band": b, "chance": round(float(r["mean"]) * 100, 1), "days": int(r["size"])}
                  for b, r in rates.iterrows()],
    }


def snapshot() -> dict:
    """Recompute from multpl and Yahoo, write yearly.json, return it.

    The P/E is fetched fresh rather than read from valuation.csv: nothing in the
    daily run rebuilds that file, and on 2026-11-01 it was two months behind.
    It is not written back - the score's own feed changes only when
    `python valuation.py` is run.
    """
    import yfinance as yf
    val = valuation.fetch()
    px = yf.download("^GSPC", start=PRICES_FROM, auto_adjust=True, progress=False)["Close"]
    px = px.squeeze().dropna()
    if len(px) < HORIZON * 20:
        raise RuntimeError(f"only {len(px)} S&P 500 closes since {PRICES_FROM}")
    out = compute(val["pe"], px)
    JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def load() -> dict | None:
    return json.loads(JSON.read_text(encoding="utf-8")) if JSON.exists() else None


def selftest() -> None:
    px = pd.Series([100, 100, 79, 100, 100, 100], dtype=float)
    w = worst_ahead(px, 2)
    assert abs(w[0] + 0.21) < 1e-9 and abs(w[1] + 0.21) < 1e-9, w.tolist()
    assert w[2] > 0, "today's own close is not in its window"
    assert w[3] == 0 and w[4:].isna().all(), "an unfinished window has no answer"

    months = pd.date_range(PE_FROM, periods=WARMUP_MONTHS + 60, freq="MS")
    pe = pd.Series(range(len(months)), index=months, dtype=float)
    before = percentile(pe)
    later = pe.copy()
    later.iloc[-1] = -1.0
    assert percentile(later).iloc[:-1].equals(before.iloc[:-1]), "a later month moved an earlier rank"
    assert before.iloc[-1] == 100.0

    days = pd.bdate_range(months[WARMUP_MONTHS], periods=600)
    prices = pd.Series(100.0, index=days)
    prices.iloc[300:] = 70.0  # a 30% fall inside the first days' window
    r = compute(pe, prices, horizon=50)
    assert r["band"] == "90+" and r["percentile"] == 100.0, r
    assert 0 < r["chance"] < 100 and r["days"] == 550, r
    print("yearly selftest ok")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="print yearly.json, download nothing")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    out = load() if a.check else snapshot()
    if out is None:
        print("no yearly.json - run `python yearly.py`", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
