# Handover — branch `claude/project-artifact-destination-0qd00e`

Written 1 September 2026, at `ba57ada`, for [PR #2](https://github.com/s5176070-rgb/sell-deshbord/pull/2).
Delete this file when the PR merges; it describes one piece of work, not the project.

## What changed

Five commits, oldest first.

| | |
|---|---|
| `7673400` | Ten sessions of `^VIX3M` into `patches.csv`, and a README that finally mentions CBOE |
| `f49a820` | The walk-forward table on the daily page; `spells` and two intervals in `event_rate` |
| `5af858a` | The selftests in CI — the repo had no workflows at all |
| `d82b9e2` | `event_rate` stops scoring the twenty rows whose forward window is cut short |
| `ba57ada` | The headline README table flagged as predating both `event_rate` changes |

## What turned up along the way

Five findings, roughly in order of how much they matter.

**`event_rate` was scoring twenty rows it should not have.** `rank_against_drawdown`
drops the final `EVENT_DAYS` rows at every January cut, and `since2000` drops them
before its own rates. `event_rate` never did. The last row was judged on one
session, the row before it on two, and only rows twenty back got the full window.

The interesting part is the direction, because the first draft of that fix got it
wrong. Copying the reasoning from `rank_against_drawdown` — where the tail reads
calmer, and correctly so for the correlation it guards — produced a comment that
measurement then contradicted:

| | tail scored | tail dropped |
|---|---|---|
| market already sliding when the data ends | 75.0% | 67.5% |
| market calm at the edge | 8.3% | 12.5% |

Both signs occur. So the tail is not a biased estimate of the same quantity that
could be corrected; it is an answer to a shorter-horizon question, and averaging
the two together is the defect. That is why the fix drops rather than adjusts.

**Day counts overstate the sample, and by a lot.** The forward window is twenty
sessions, so two adjacent days share nineteen twentieths of the path they are
judged on. 112 days above 85 are a handful of episodes, not 112 draws. `spells`
counts unbroken runs, and each rate now carries two intervals: `ci_days`, which
makes the table look precise and is wrong, and `ci_spells`, which is defensible
and much wider. On one synthetic series they came out 2.8 against 48.9.

The arithmetic already settles a claim the README makes in words. On day counts
alone, 85+ is 22.3% ±7.7 and 70–84 is 22.5% ±3.9 — the second sits entirely
inside the first, before the spell count widens either.

**The band was being read off the wrong scale.** Bands are cut on the raw
percentile (`MSS`); the dashboard publishes the calibrated 0–100 score. They are
different scales, and 36 on one is not 36 on the other. This was a live mistake
made during this work — an artifact was published marking today's band from the
score — caught by reading `band_of`'s callers and corrected. `simple()` now
carries a docstring saying so, because the mistake is easy and silent.

**`--serious` was never defined in the light palette.** `band_colour` has always
emitted `var(--serious)` for the 70–84 band; `BROADSHEET_CSS` defined only
`--good`, `--warn` and `--crit`. Latent rather than live — nothing on the light
page called it until this branch did — and it would have failed by silently
losing the colour, not by erroring.

**The README described a world the code had left.** Known limits told you to top
`patches.csv` up by hand and never mentioned that `cvs.py` fetches CBOE's own
daily file first. That stale paragraph is what sent this session hand-collecting
ten sessions of `^VIX3M` that the code may well have fetched on its own.

## Where this stopped

**The model has not been scored.** `python stress.py --bench` does not run in the
environment this branch was written in: every one of the twenty tickers returns
`CONNECT tunnel failed, response 403` from the egress proxy, and `stress.build`
correctly refuses with `no price data came back`. The block is an organization
network policy on that environment, recorded by the proxy as `connect_rejected`
against `query1/query2.finance.yahoo.com` and `guce.yahoo.com`. It is not a code
problem and there is no route around it from there.

Everything that does not need market data was run and passes: all five selftests
on 3.11 and 3.12, `compileall` clean, and the new code exercised against
synthetic series built so the counts are known in advance.

**So the headline table in the README is stale, and is marked as such.** Both
`event_rate` changes move it — day counts are each twenty too high in total, the
rates shift by whatever those twenty days did, and the printed table is now wider
than the one in the document.

## Next

1. **Run `python stress.py --bench`** on a machine with market access. It prints
   the tables and writes nothing. This is the first real check of the numbers,
   and it is what settles whether the top band's edge survives its own interval —
   watch the `spells` column above 85, because that is the sample the 1.67×
   actually rests on.
2. **Replace the README table from that output.** A copy, not an edit by hand.
   The section under "The one rule" says so.
3. **Merge the PR** once the table is restated.

Two things deliberately left alone, in case they look like oversights:

- **`cvs.py:105` emits `UserWarning: Boolean Series key will be reindexed`.**
  Traced to the degenerate path where no column returned any data at all — which
  is exactly what a fully blocked download produces. It should not fire on a real
  run. Untouched because it is outside this branch and unverifiable without data.
- **Nothing was added to the score.** Every change here measures the existing
  score more honestly or documents it. `MIN_CORR`, the band edges, the factor
  list and `FLAG` are all untouched, so the reading itself does not move — only
  the confidence attached to it, and the twenty rows that should never have been
  in the table.
