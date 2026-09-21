"""Self-contained Hebrew website, rendered from model outputs without rescoring."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"


def number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def series(values: pd.Series) -> list[dict]:
    return [{"date": date.strftime("%Y-%m-%d"), "value": number(value)}
            for date, value in values.tail(1260).items()]


def render(export: pd.DataFrame | None = None, res: pd.DataFrame | None = None,
           px: pd.DataFrame | None = None, chosen: list[str] | None = None,
           ev: pd.DataFrame | None = None, *, version: str = "",
           live: bool = False, notice: str | None = None,
           premarket: dict | None = None) -> str:
    data: dict = {"version": version, "live": live, "notice": notice,
                  "premarket": premarket,
                  "reading": None, "factors": [], "evidence": [], "markets": [],
                  "history": {"chance": [], "mss": [], "spx": []}}
    if export is not None and not export.empty and res is not None:
        latest = export.iloc[-1]
        data["reading"] = {"date": export.index[-1].strftime("%Y-%m-%d"),
                           "chance": number(latest["chance_pct"]),
                           "mss": number(latest["percentile"]),
                           "regime": str(latest["regime"]),
                           "change": number(res["MSS_5d"].iloc[-1])}
        data["history"]["chance"] = series(export["chance_pct"])
        data["history"]["mss"] = series(export["percentile"])
        data["factors"] = [{"key": key, "value": number(res[key].iloc[-1])}
                           for key in chosen or []]
    if ev is not None and not ev.empty:
        data["baseline"] = number(ev.loc["all days", "rate"])
        data["evidence"] = [{"band": str(band), "rate": number(row["rate"]),
                             "days": number(row["days"]), "spells": number(row["spells"])}
                            for band, row in ev.iterrows() if band != "all days"]
    if px is not None and not px.empty:
        if "^GSPC" in px:
            data["history"]["spx"] = series(px["^GSPC"])
        for key, title in [("^GSPC", "S&P 500"), ("^VIX", "VIX"),
                           ("^TNX", "אג״ח ארה״ב ל־10 שנים"), ("^RUT", "Russell 2000")]:
            values = px[key].dropna() if key in px else pd.Series(dtype=float)
            data["markets"].append({"key": key, "title": title,
                "value": number(values.iloc[-1]) if len(values) else None,
                "change": number((values.iloc[-1] / values.iloc[-2] - 1) * 100)
                          if len(values) > 1 and values.iloc[-2] != 0 else None,
                "date": values.index[-1].strftime("%Y-%m-%d") if len(values) else None,
                "series": series(values.tail(30))})
    # Escaping '<' prevents a data string from closing the script element.
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    return (WEB.joinpath("index.html").read_text(encoding="utf-8")
            .replace("/* SITE_CSS */", WEB.joinpath("style.css").read_text(encoding="utf-8"))
            .replace("/* PREMARKET_CSS */", WEB.joinpath("premarket.css").read_text(encoding="utf-8"))
            .replace("/* SITE_JS */", WEB.joinpath("app.js").read_text(encoding="utf-8"))
            .replace("/* PREMARKET_JS */", WEB.joinpath("premarket.js").read_text(encoding="utf-8"))
            .replace("__SITE_DATA__", payload))


def cached_page(*, version: str, live: bool = True) -> str:
    """An honest initial screen: local prices, no invented model reading."""
    path = HERE / "spx_ohlc.csv"
    prices = None
    if path.exists():
        try:
            frame = pd.read_csv(path, index_col=0, parse_dates=True)
            prices = frame[["Close"]].rename(columns={"Close": "^GSPC"})
        except (ValueError, KeyError, OSError):
            pass
    return render(px=prices, version=version, live=live,
                  notice="מוצגים מחירים מהקובץ המקומי. חישוב המודל נדרש כדי להציג הערכת סיכון מעודכנת.")
