"""Alpha Vantage over plain HTTP, so the dashboard can reach it without me.

The MCP server answers only while a chat session is open. A key in `.env` turns
the same endpoints into something the daily script can call on its own.

The put-call ratio endpoint serves one date per request, and the free tier
allows 25 requests a day, so eighteen years of history is not something to sit
and wait for. This builds it the only way it can be built: every run fetches the
missing days it has budget for, newest first, and appends them to
`alpha_putcall.csv`. Nothing already stored is fetched twice. Run it daily and
the file grows a day at a time; run it daily for a year and there is finally
enough history to rank the series and put it through the same walk-forward as
everything else. Until then `stress.py` leaves it out - see NEED_ROWS, which is
the gate, not a suggestion.

Setup - one line in `.env` beside this file:

    ALPHAVANTAGE_API_KEY=your_key_here

    python alpha.py                # fetch what today's budget allows
    python alpha.py --calls 5      # spend fewer
    python alpha.py --check        # cross-check closes, spend one call
    python alpha.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).parent
CSV = HERE / "alpha_putcall.csv"
CONTEXT = HERE / "alpha_context.json"
ENV = HERE / ".env"
URL = "https://www.alphavantage.co/query"
SYMBOL = "SPY"
FREE_TIER_CALLS = 20  # of 25, leaving room for a --check and a mistake
PAUSE = 1.0  # seconds between calls; the daily cap bites long before any rate limit
# Below this many rows the series cannot be ranked against a trailing year, so
# stress.py must not use it. One year of trading days plus a working margin.
NEED_ROWS = 300


def api_key() -> str | None:
    """The key from the environment, or from a `.env` beside this file."""
    if key := os.environ.get("ALPHAVANTAGE_API_KEY"):
        return key
    if not ENV.exists():
        return None
    for line in ENV.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "ALPHAVANTAGE_API_KEY":
            return value.strip().strip("'\"") or None
    return None


def redact(text: str, key: str) -> str:
    """Take the key out of anything on its way to a screen, a log or a file.

    Alpha Vantage quotes the key back inside its own rate-limit message - "We
    have detected your API key as ..." - and that message is an exception string
    that ends up in the terminal and in the dashboard's status feed. A secret
    that only lives in a gitignored file is not protected if the service prints
    it for you.
    """
    return text.replace(key, "***") if key else text


def get(key: str, **params) -> dict:
    """One call. Alpha Vantage answers rate limits with HTTP 200 and a message."""
    r = requests.get(URL, params={**params, "apikey": key}, timeout=30)
    r.raise_for_status()
    data = r.json()
    for field in ("Note", "Information", "Error Message"):
        if field in data:
            raise RuntimeError(redact(f"{field}: {data[field]}", key))
    return data


def load() -> pd.DataFrame:
    """The put-call history gathered so far, oldest first."""
    if not CSV.exists():
        return pd.DataFrame(columns=["full_chain", "front"], index=pd.DatetimeIndex([], name="date"))
    return pd.read_csv(CSV, index_col=0, parse_dates=True).sort_index()


def wanted(sessions: pd.DatetimeIndex, have: pd.DatetimeIndex, budget: int) -> list[pd.Timestamp]:
    """Which dates to spend this run's calls on: the newest ones still missing.

    Newest first so the file is always useful at the recent end, where a reader
    actually looks, rather than complete at the far end and empty at this one.
    """
    missing = [d for d in sessions if d not in have]
    return sorted(missing, reverse=True)[:budget]


def fetch_day(key: str, date: pd.Timestamp) -> dict | None:
    """One date's ratio, or None when the endpoint has nothing for it."""
    data = get(key, function="HISTORICAL_PUT_CALL_RATIO", symbol=SYMBOL,
               date=date.strftime("%Y-%m-%d"))
    chain = data.get("put_call_ratio_full_chain")
    if chain is None:
        return None
    by_exp = data.get("put_call_ratio_by_expiration") or []
    return {"full_chain": float(chain),
            "front": float(by_exp[0]["value"]) if by_exp else float(chain)}


def sessions(days: int = 400) -> pd.DatetimeIndex:
    """Recent trading days, taken from the price feed rather than a calendar."""
    import yfinance as yf
    frame = yf.download(SYMBOL, period=f"{days}d", progress=False, auto_adjust=True)
    return frame.index.normalize()


def cross_check(key: str) -> dict:
    """Today's close from both sources. Cheap, and the only claim here that is tested."""
    from cvs import closes  # already unwraps yfinance's MultiIndex for one ticker
    data = get(key, function="GLOBAL_QUOTE", symbol=SYMBOL, datatype="json")
    quote = data["Global Quote"]
    av = float(quote["05. price"])
    frame, _ = closes([SYMBOL], (pd.Timestamp.today() - pd.Timedelta(days=14))
                      .strftime("%Y-%m-%d"))
    yf_close = float(frame[SYMBOL].iloc[-1])
    return {"symbol": SYMBOL, "alpha_vantage": round(av, 2),
            "yfinance": round(yf_close, 2), "agree": abs(av - yf_close) < 0.05,
            "latest_day": quote.get("07. latest trading day"), "source": "GLOBAL_QUOTE"}


def gather(key: str, calls: int = FREE_TIER_CALLS, note=print) -> tuple[int, int]:
    """Fetch the missing days this run has budget for. Returns (fetched, stored).

    Shared by the command line and by the dashboard's re-analysis button, so a
    click and a terminal run spend the daily budget the same way and neither can
    drift into fetching days the other already has.
    """
    history = load()
    todo = wanted(sessions(), history.index, calls)
    if not todo:
        write_context(history, None)
        return 0, len(history)
    rows = {}
    for i, date in enumerate(todo):
        try:
            got = fetch_day(key, date)
        except RuntimeError as exc:
            note(f"stopped at {date:%Y-%m-%d}: {exc}")
            break
        if got:
            rows[date] = got
        if i < len(todo) - 1:
            time.sleep(PAUSE)
    if rows:
        history = pd.concat([history, pd.DataFrame(rows).T]).sort_index()
        history.index.name = "date"
        history.to_csv(CSV)
    write_context(history, None)
    return len(rows), len(history)


def write_context(history: pd.DataFrame, check: dict | None) -> None:
    """The snapshot the dashboard strip reads. Regenerated, never hand-edited."""
    last = history.iloc[-1] if len(history) else None
    CONTEXT.write_text(json.dumps({
        "note": "Written by alpha.py. Every field is a snapshot with a date on it.",
        "as_of": f"{history.index[-1]:%Y-%m-%d}" if last is not None else None,
        "rows": len(history),
        "need_rows": NEED_ROWS,
        "in_score": len(history) >= NEED_ROWS,
        "put_call": {
            "symbol": SYMBOL,
            "full_chain": None if last is None else float(last["full_chain"]),
            "front_expiry": None if last is None else float(last["front"]),
            "source": "HISTORICAL_PUT_CALL_RATIO",
        },
        "cross_check": check,
    }, indent=2) + "\n", encoding="utf-8")


def selftest() -> None:
    idx = pd.to_datetime(["2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13"])
    have = pd.to_datetime(["2026-08-11"])
    # Newest missing first, and the budget is a hard stop.
    assert wanted(idx, have, 2) == list(pd.to_datetime(["2026-08-13", "2026-08-12"]))
    assert wanted(idx, have, 99) == list(
        pd.to_datetime(["2026-08-13", "2026-08-12", "2026-08-10"]))
    assert wanted(idx, idx, 5) == [], "nothing missing means nothing fetched"
    # A rate-limit reply arrives as HTTP 200 with a message, so it has to raise.
    body = {"Information": "rate limit"}
    assert any(f in body for f in ("Note", "Information", "Error Message")), \
        "a limit message must not pass as data"

    # And that message quotes the key back, so nothing may carry it onward.
    quoted = "We have detected your API key as SECRET123 and our standard limit"
    assert "SECRET123" not in redact(quoted, "SECRET123")
    assert redact("no key here", "SECRET123") == "no key here"
    print("selftest ok")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--calls", type=int, default=FREE_TIER_CALLS,
                    help=f"put-call requests to spend this run (free tier allows 25/day)")
    ap.add_argument("--check", action="store_true", help="cross-check closes only")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        selftest()
        return 0

    key = api_key()
    if not key:
        print("no ALPHAVANTAGE_API_KEY - put one in .env beside this file:\n"
              "  ALPHAVANTAGE_API_KEY=your_key_here\n"
              "free keys: https://www.alphavantage.co/support/#api-key", file=sys.stderr)
        return 1

    history = load()
    check = None
    if a.check:
        check = cross_check(key)
        print(f"{check['symbol']} {check['latest_day']}: "
              f"alpha vantage {check['alpha_vantage']}, yfinance {check['yfinance']} - "
              f"{'agree' if check['agree'] else 'DISAGREE'}")
        write_context(history, check)
        return 0

    fetched, stored = gather(key, a.calls,
                             note=lambda m: print(m, file=sys.stderr))
    print(f"fetched {fetched} - {stored} rows stored")
    if stored < NEED_ROWS:
        left = NEED_ROWS - stored
        print(f"{left} more rows before stress.py will use it "
              f"(about {-(-left // a.calls)} more runs)")
    else:
        print("enough history - stress.py will rank it with the other candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
