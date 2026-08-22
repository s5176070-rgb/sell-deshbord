"""Today's reading against every day since 2000. Descriptive, not walk-forward.

The full model cannot reach 2000 - RSP starts 2003, TLT and LQD 2002, HYG,
VVIX and VIX3M 2006-07 - so this uses the eleven confirmed factors whose
inputs exist the whole way back: the VIX family, the trend family, and the
defensive-rotation family. Everything here is ranked in-sample over the whole
26 years and read off directly. That is the honest label: it answers "how do
days that looked like today usually end?", not "what would the model have
said at the time?" - the walk-forward in stress.py answers that.

    python since2000.py
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from cvs import pct_rank
from stress import fwd_drawdown, EVENT_DEPTH

START = "1999-01-01"          # a year early so the 200-day windows are warm by 2000
TICKERS = ["^GSPC", "^VIX", "SPY", "XLP", "XLU", "XLY"]
NEAR = 5.0                    # a day "looks like today" within this many points

ERAS = [("2000-2002 dot-com", "2000-01-01", "2003-01-01"),
        ("2003-2007 recovery", "2003-01-01", "2008-01-01"),
        ("2008-2009 GFC", "2008-01-01", "2010-01-01"),
        ("2010-2019 bull", "2010-01-01", "2020-01-01"),
        ("2020-2021 covid", "2020-01-01", "2022-01-01"),
        ("2022-2026", "2022-01-01", "2027-01-01")]


def factors(px: pd.DataFrame) -> pd.DataFrame:
    spx, vix = px["^GSPC"], px["^VIX"]
    xlp_spx = px["XLP"] / spx
    c = {
        "vix_5d": vix.diff(5),
        "vix_20d": vix.diff(20),
        "vix_level": vix,
        "vol_of_vol": vix.rolling(20).std(),
        "realized_vol": spx.pct_change().rolling(20).std(),
        "off_high": -(spx / spx.rolling(60).max() - 1),
        "below_50": -(spx / spx.rolling(50).mean() - 1),
        "below_150": -(spx / spx.rolling(150).mean() - 1),
        "below_200": -(spx / spx.rolling(200).mean() - 1),
        "defensive": ((px["XLP"] + px["XLU"]) / px["SPY"]).pct_change(20),
        "xlp_slope": xlp_spx.ewm(span=20).mean().diff(10),
    }
    return pd.DataFrame(c)


def analogs() -> dict:
    """Today against every similar-looking day since 2000, as plain numbers.

    Called by the dashboard build as well as the command line, so the daily
    page always carries the long-history comparison. One extra download of six
    tickers; a failure here is the caller's to swallow - the dashboard must
    not die because 1999 was unreachable this morning.
    """
    raw = yf.download(TICKERS, start=START, auto_adjust=True, progress=False)["Close"]
    px = raw.dropna(how="any")
    ranked = factors(px).apply(pct_rank, lookback=252).dropna()
    comp = ranked.mean(axis=1).loc["2000-01-01":]
    hit = fwd_drawdown(px["^GSPC"].reindex(comp.index)) <= EVENT_DEPTH
    # The last 20 sessions have no complete forward window - leave them out of rates.
    scored, h = comp.iloc[:-20], hit.iloc[:-20]
    today = comp.iloc[-1]
    near = (scored - today).abs() <= NEAR
    return {
        "asof": comp.index[-1],
        "composite": float(today),
        "days": int(near.sum()),
        "spells": int((near & ~near.shift(fill_value=False)).sum()),
        "near_rate": float(h[near].mean()),
        "base": float(h.mean()),
        "lift": float(h[near].mean() / h.mean()) if h.mean() else 1.0,
    }


def main() -> int:
    raw = yf.download(TICKERS, start=START, auto_adjust=True, progress=False)["Close"]
    px = raw.dropna(how="any")
    ranked = factors(px).apply(pct_rank, lookback=252).dropna()
    comp = ranked.mean(axis=1).loc["2000-01-01":]
    hit = fwd_drawdown(px["^GSPC"].reindex(comp.index)) <= EVENT_DEPTH
    # The last 20 sessions have no complete forward window - leave them out of rates.
    scored, h = comp.iloc[:-20], hit.iloc[:-20]

    today = comp.iloc[-1]
    print(f"composite today ({comp.index[-1]:%d %b %Y}): {today:.1f} "
          f"(eleven factors, ranked over 2000-2026)")
    print(f"days since 2000: {len(scored)}   "
          f"base rate of a 5% fall in 20 sessions: {h.mean():.1%}\n")

    near = (scored - today).abs() <= NEAR
    runs = (near & ~near.shift(fill_value=False)).sum()
    print(f"days that looked like today ({today - NEAR:.0f}-{today + NEAR:.0f}): "
          f"{near.sum()} across ~{runs} separate spells")
    print(f"how they ended: {h[near].mean():.1%} fell 5%+  "
          f"({h[near].mean() / h.mean():.2f}x the everyday chance)\n")

    print("the same reading, era by era")
    rows = []
    for name, a, b in ERAS:
        m = near & (scored.index >= a) & (scored.index < b)
        all_m = (scored.index >= a) & (scored.index < b)
        rows.append({"era": name, "days_like_today": int(m.sum()),
                     "fell": f"{h[m].mean():.0%}" if m.any() else "-",
                     "era_base": f"{h[all_m].mean():.0%}"})
    print(pd.DataFrame(rows).set_index("era").to_string())

    print("\nwhere today's raw readings sit in 26 years (100 = the worst day)")
    raw_f = factors(px).loc["2000-01-01":]
    pct = raw_f.rank(pct=True).iloc[-1] * 100
    for k, v in pct.sort_values(ascending=False).items():
        print(f"  {k:14} {v:5.1f}   (now {raw_f[k].iloc[-1]:.4g})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
