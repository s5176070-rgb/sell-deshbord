# Market Stress Dashboard

A score that says how likely the next twenty sessions are to contain a 5% fall,
and — more importantly — the evidence for whether that score is worth reading.

The evidence is on the dashboard, not in a drawer. Every version of this model
that failed is still in the repo, because knowing what didn't work is most of
what makes the current number believable.

## Run it

```
pip install -r requirements.txt
python breadth.py       # once, then occasionally — builds breadth.csv (~2 min)
python stress.py        # the dashboard, written to a file
python stress.py --serve  # the same page with a working Refresh button
```

`--serve` holds the page open on `127.0.0.1:8765` with two buttons. A file on
disk can't recalculate itself — the browser has no way to run any of this — so
they only appear when something is listening for them.

| Button | What it redoes | How long |
|---|---|---|
| **Refresh** | prices, then rescore | a few seconds |
| **Re-analyse** | breadth counted from all 500 members, options history, then rescore | a minute or two |

Re-analyse runs in a thread and the page polls `/status` for the stage it's on,
because a button that holds one request open for two minutes is a button that
times out. Each stage fails on its own: a breadth download that dies leaves the
cached file in place and the rescore still happens, and the page says so.

`python stress.py --bench` prints the tables and writes nothing. `--full` writes
the evidence page instead of the plain one. Every script has a `--selftest`.

Every run also writes **`score.csv`** — one row per day since 2008:

| column | what it is |
|---|---|
| `score` | 0–100, today against the calmest and worst the model has ever read |
| `chance_pct` | what that means: the % of days like this one that fell 5% in a month |
| `percentile` | the raw factor average, before calibration |
| `regime` | the band label, with hysteresis |
| `walk_forward` | `False` for the pre-2012 rows, where the factors were not picked blind |

`score` is a rank and `chance_pct` is a probability. 100 does not mean the market
will fall; it means nothing in fifteen years looked worse. Quote them together.

## It runs itself

`serve.bat` has a shortcut in the Startup folder, and a scheduled task
(*Market Stress Daily*) fires it once a day around 00:05 Israel time - just
after the New York close - so the server holds the page at
**http://127.0.0.1:8765**. It costs nothing to fire when the server is already
up: `serve.bat` exits at once (the port guard sees something listening), so
this is a once-a-day nudge, not a live-updating loop.

It re-analyses itself **once per trading day, an hour after the New York close**
— 17:00 ET, which is midnight in Israel — breadth recounted, options history
topped up, rescored. The clock is held in exchange time and steps back off a
weekend, so Saturday and Sunday do not rerun Friday's numbers. Public holidays
are not in a calendar: the run happens, finds no new session in the price feed,
and rescores the day it already had. The two buttons do the same work on demand.

One process does all of it on purpose. A second scheduled job would race it for
`breadth.csv` and each would spend the day's 25 API calls believing it had all
of them.

The clock fires on an *unserved slot*, not on a wall-clock match: a machine
asleep at eight catches up when it wakes, and a restart at nine doesn't trigger
a second run. `.last_analysis` holds the stamp.

`serve.bat` restarts the server if it falls over, and stops if it exits 3 — the
code for "something else is already serving this port". That check connects to
the port rather than catching a bind error, because **on Windows a second bind
to the same port succeeds**: `HTTPServer` sets `SO_REUSEADDR` and Windows reads
that as permission to share the port. Four servers were running here before the
probe existed, each doing its own daily re-analysis over the same files.

```
type daily.log                                          REM what it did
curl -X POST http://127.0.0.1:8765/analyze              REM full re-analysis now
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Market Stress Server.lnk"
```

## What each file does

| File | Job |
|---|---|
| `stress.py` | The model: candidates, yearly re-selection, walk-forward, the score |
| `board.py` | The dashboard's look. Nothing here measures anything |
| `breadth.py` | Counts how many S&P 500 members sit above their own 50- and 200-day average |
| `alpha.py` | Gathers put/call history from Alpha Vantage, a few days per run |
| `plan_checks.py` | Measures the claims in the original work plan instead of assuming them |
| `cvs.py` | The first model. It failed. Kept as the record, and for its data helpers |
| `patches.csv` | Closes a feed stopped publishing, with the source of each one |
| `serve.bat` | Starts the server at logon; the server does the daily run itself |

## The one rule

**A factor gets into the score by being tested, not by sounding right.**

Every candidate is re-picked each January using only the years that ended before
it, and scored on the twelve months that follow. Stitch those years together and
the whole track from 2012 on is out-of-sample. That is the number to quote:

| Score | Days | 5% fall within 20 sessions | vs base |
|---|---|---|---|
| all days | 3,646 | 13.3% | — |
| 0–44 | 1,574 | 8.1% | 0.61× |
| 45–69 | 1,515 | 15.4% | 1.15× |
| 70–84 | 445 | 22.5% | 1.69× |
| 85+ | 112 | 22.3% | 1.67× |

Fitting the same model on all history instead reports 2.4× at the top. The gap
between that and 1.67× is what selection invents, and it is why the dashboard
shows both tables side by side.

## What the score does not say

It predicts **drawdown depth, not direction**. Forward 20-day return from the
top band is *positive*. A high reading argues for carrying less risk. It never
argues for calling a top.

The top two bands are currently indistinguishable — 1.69× against 1.67× on 445
and 112 days. The sell flag sits at 85 because that fires on a quarter as many
days for the same accuracy, not because 85 is sharper than 70.

## Things that were tested and rejected

Each of these was a plausible idea someone had written down. None survived a
single one of the fifteen yearly selections:

- `stretch` — distance above the 200-day average. Stretched markets fall *less*.
- `breadth_euphoria` — the claim that S5FI above 70% marks late-stage buying.
  The opposite reading, thin breadth, was picked in all fifteen years.
- `risk_off_20`, `risk_off_accel` — XLY/XLP, including the second derivative.
- `curve_flat`, `rates_up_20` — the yield curve. Its clock is a year; this
  model's is twenty days.

## Known limits

- **Survivorship bias in breadth.** `breadth.py` applies today's membership list
  backwards, so 2008 is measured over the companies that made it to 2026.
  Cross-checked against TradingView's INDEX:S5FI on 2026-08-14: 69.77 vs 69.38.
- **`^VIX3M` stopped updating on yfinance in July 2026**, along with `^VIX9D`
  and `^VIX6M`, while `^VIX` kept printing. The term-structure factor is chosen
  every year, so `patches.csv` carries the missing closes, read off TradingView
  and checked against the 25 days where the two sources overlap — they agree to
  seven decimals. A patch only ever fills a NaN, so the file goes inert by
  itself when the feed recovers. It has to be topped up by hand until then;
  `^VVIX` is in the candidate pool and is current either way.
- **Put/call is not in the score.** The endpoint serves one date per request, so
  the history has to be gathered a few days at a time. It stays out until 300
  rows exist to rank it against.
- **112 days above 85 in fourteen years.** The edge is real and the sample
  behind it is thin.
- **Intraday runs read yesterday.** `^VIX` posts a bar before the ETFs open, so
  a run during market hours sees a last row where most factors are still empty.
  Rather than average the third that reported, the run backs off to the last day
  with at least 75% coverage and says which day it is reading.

## The key

`alpha.py` needs a free Alpha Vantage key in `.env` (see `.env.example`).
Nothing else needs one. `.env` is gitignored — keep it that way.
