# Market Stress Dashboard — working notes for Claude

One question: how likely are the next 20 sessions to contain a 5% close-to-close
fall in the S&P 500. Every number on the page is either that estimate or the
evidence for whether the estimate is worth reading.

## Commands

```
python check.py                  # today's reading, refreshes prices
python check.py --offline        # the saved reading, no network
python check.py --json           # same numbers, machine-readable
python stress.py                 # full rebuild: score.csv + dashboard page
python stress.py --serve --no-open          # the page on 127.0.0.1:8765, daily schedule
python stress.py --serve --preview --no-open # same page from saved prices, no schedule
python premarket.py              # the open gap now, and what gaps that size preceded
python eval.py                   # Brier, AUC, reliability on the published history
```

Data builders, run occasionally, each writes its own CSV:
`breadth.py` (~2 min), `valuation.py`, `debt.py`, `pcr.py`, `fear.py`, `alpha.py`.

Tests — every script carries its own, there is no pytest:

```
python stress.py --selftest
python premarket.py --selftest
python eval.py --selftest
python test_check.py
python -m unittest test_stress_logic
python -m unittest test_website
```

CI (`.github/workflows/selftests.yml`) runs all of them on 3.11 and 3.12.

## Layout

| File | Role |
| --- | --- |
| `stress.py` | The model. Candidate factors, January re-selection, walk-forward score, calibration, `score.csv`, `score_meta.json`, `--serve` |
| `cvs.py` | Shared primitives: `closes`, `pct_rank`, `regimes`, `stale`, `patch`, `BANDS` |
| `eval.py` | Does the number mean anything: `hits`, `brier`, `auc`, `reliability` |
| `check.py` | Reads `score.csv` and prints the Hebrew reading. Never recomputes |
| `website.py` + `web/` | The Hebrew page, rendered from model output without rescoring |
| `board.py` | The older evidence page (`--full`) |
| `premarket.py` | The open gap, as context. Separate from the score on purpose |
| `since2000.py`, `bench_new.py`, `plan_checks.py` | Descriptive comparison, candidate auditions, claims the plan makes |

## Rules that are not style preferences

**Nothing is scored on data it was chosen with.** Factors are re-picked every
January from the years that ended before that January. The ranking window looks
backwards only, and the last `EVENT_DAYS` rows of each training slice are
dropped because their forward window crosses the boundary. A change that lets
today's value see tomorrow's price is a bug, not an optimisation.

**Context stays out of the score.** The CNN Fear & Greed reading (`fear.py`) and
the premarket gap (`premarket.py`) are shown beside the number and never inside
it. Moving either into the score needs a methodological case first, not a
plausible story.

**`chance_pct` is a probability, not an instruction.** It is the only column that
is one; `percentile` is the raw MSS, an average of factor percentiles. Never
write copy that reads the probability as advice to buy or sell.

**Numeric definitions live in one place.** The threshold, horizon and depth are
defined in `cvs.py` and `stress.py` and written into `score_meta.json` on every
run. `MODEL.md` explains them; it does not define them. If a doc contradicts the
code, the code is right and the doc is the bug.

**Bump `MODEL_VERSION` on any change that moves a published number** — a new
factor, a new band, a different calibration. It rides along in
`score_meta.json` so a reading can be told apart from one this model would not
have produced. After a bump, the performance figures in `README.md`, `MODEL.md`
and `CALIBRATION.md` belong to the previous version until they are regenerated;
say so in those files rather than leaving them to be read as current.

**Fail loudly.** A stale feed, missing coverage, or a calibration window with too
little history is an error or an explicit hold-back, never a quietly reused
number from yesterday.

## Conventions

- Code, comments, docstrings and commit messages: English prose.
- Everything a user reads — the dashboard, `check.py` output, the `.md` docs
  other than this file: Hebrew.
- Charts are hand-written SVG. No plotting library; see the bottom of
  `requirements.txt` for what is deliberately absent and why.
- Both the generated files (`score.csv`, `score_meta.json`, `dashboard*.html`,
  `daily.log`) and the gathered feeds (`breadth.csv`, `valuation.csv`,
  `debt.csv`, `fear.csv`, `spx.csv`, the put/call files) are gitignored — they
  are rebuilt by running the scripts. The only data files in git are
  `patches.csv`, the hand-entered fills, and `spx_ohlc.csv`.
- Secrets live in `.env` (`.env.example` lists the keys). `alpha.py` parses it.
