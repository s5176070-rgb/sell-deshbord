"""Audition for new long-history candidates, before any of them touch the score.

Same judge as the live bench: rank each candidate over a trailing year, ask
every January how it correlated with the drawdown that followed on prior data
only, and count the years it cleared the bar. Nothing here changes the model -
the winners get wired into stress.py by hand, the losers get a line in memory
so they are not proposed twice.

    python bench_new.py
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from cvs import pct_rank
from stress import rank_against_drawdown, MIN_CORR, MIN_TRAIN, FIRST_LIVE_YEAR

TICKERS = ["^GSPC", "^RUT", "^IXIC", "^SOX", "^DJT", "^DJI", "^SKEW", "GLD", "UUP", "CL=F"]
START = "2004-01-01"


def factors(px: pd.DataFrame) -> pd.DataFrame:
    spx = px["^GSPC"]
    rut, sox, djt, dji, ixic = px["^RUT"], px["^SOX"], px["^DJT"], px["^DJI"], px["^IXIC"]
    over = lambda s, n: s / s.rolling(n).mean()
    return pd.DataFrame({
        # Small caps break first: their own trend, and how far they lag the index.
        "rut_off_high": -(rut / rut.rolling(60).max() - 1),
        "rut_below_200": -over(rut, 200) + 1,
        "rut_lag": over(spx, 200) - over(rut, 200),
        # Semiconductors as the cycle's loudest early warning.
        "sox_off_high": -(sox / sox.rolling(60).max() - 1),
        "sox_fade_60": -(sox / spx).pct_change(60),
        # Dow theory: transports refusing to confirm the industrials.
        "djt_div": over(dji, 200) - over(djt, 200),
        # Tech appetite fading while the index holds.
        "ixic_fade_60": -(ixic / spx).pct_change(60),
        # Flights to safety, the same construction as bonds_bid, which passed.
        "gold_bid": (px["GLD"] / spx).pct_change(20),
        "dollar_bid": px["UUP"].pct_change(20),
        # Tail-risk pricing and the oil-demand read. Bench only: SKEW has 67
        # holes inside its span and futures trade a different calendar, so
        # neither can be wired into the live frame as-is.
        "skew_level": px["^SKEW"],
        "oil_crash_60": -px["CL=F"].pct_change(60),
    })


def main() -> int:
    px = yf.download(TICKERS, start=START, auto_adjust=True, progress=False)["Close"]
    px = px.dropna(how="all")
    spx = px["^GSPC"]
    ranked = factors(px).apply(pct_rank, lookback=252).dropna(how="all")

    years = {}
    for year in range(FIRST_LIVE_YEAR, ranked.index[-1].year + 1):
        past = ranked[ranked.index < f"{year}-01-01"].dropna(how="any")
        if len(past) < MIN_TRAIN:
            continue
        corr = rank_against_drawdown(past, spx)
        years[year] = corr[corr <= MIN_CORR].index.tolist()

    latest = rank_against_drawdown(
        ranked[ranked.index < "2026-01-01"].dropna(how="any"), spx)
    table = pd.DataFrame({
        "years_picked": {f: sum(f in v for v in years.values()) for f in ranked.columns},
        "of": len(years),
        "corr_2026": latest.round(4),
    }).sort_values("years_picked", ascending=False)
    print(f"bar: corr <= {MIN_CORR}, judged each January on prior years only\n")
    print(table.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
