# CS2 Skill vs. Rank

Measuring a deliberate Counter-Strike 2 training program that began **2026-08-13**:
does trained mechanical skill actually move rank, and with how much lag?

Built as the application visualization for [The Data School NY](https://www.thedataschool.com/apply/).

## The question

Six weeks of data *before* the program started already show the two signals disagreeing:

| Metric | First 50 matches | Last 50 matches | |
|---|---|---|---|
| Premier ELO | 13,438 | 12,851 | ↓ 590 |
| FACEIT ELO | ~1,000 | 972 | flat |
| Reaction time | 713 ms | 669 ms | ↓ 6% (better) |
| Spray accuracy | 37.0% | 38.6% | ↑ |
| Headshot accuracy | 17.9% | 18.5% | ↑ |
| Preaim | 11.45° | 11.27° | ↓ (better) |

Mechanics drifted up. Rank drifted down. Rank is noisy, lagging and team-dependent;
mechanics are measured per match against the player alone. The program is the test:
if mechanics improve deliberately, does rank eventually follow?

## Why the snapshots exist

Leetify's public API returns the last **100 matches** as a *rolling* window. This is not
an abstract risk — it was observed happening on day one:

| Capture (2026-08-14) | API window | Premier | Career matches |
|---|---|---|---|
| 18:26 UTC | 2026-07-02 → 08-14 | 12,851 | 672 |
| 02:50 UTC | **2026-07-13** → 08-15 | 13,131 | 678 |

Six matches were played and the window slid forward eleven days. 2026-07-02 through
07-12 became permanently unreachable from the API in under nine hours.

So `capture.py` writes the raw response to disk, timestamped and never overwritten, and
`build.py` unions every snapshot deduped on match id. Consecutive snapshots overlap by
~99 matches, so the dataset grows monotonically and aged-out matches survive. As of the
third capture, **7 matches exist only because a snapshot caught them.**

## Layout

```
capture.py            daily: snapshot Leetify + FACEIT standing   (cron, 4am)
build.py              snapshots -> tidy CSVs for Tableau
log_training.py       append a day's training                     (manual, 30s)
backfill_faceit.py    one-shot FACEIT per-match ELO history

data/raw/leetify/     profile-<ts>.json    immutable, never edited
data/raw/faceit/      user-<ts>.json       daily elo + skill level
                      faceit_cs2_history.csv   199 matches, 2024-07 -> now
data/processed/       matches.csv          the union — one row per match
                      daily.csv            one row per day
                      faceit_elo.csv       FACEIT elo series
                      training_log.csv     manual: the independent variable
                      summary.json         headline numbers, for checking the viz
```

## Running it

```bash
python3 capture.py          # idempotent; cron runs this daily at 4am
python3 build.py            # regenerate the processed CSVs
python3 log_training.py -m 45 -d aim_botz,deathmatch -f "crosshair placement"
python3 log_training.py --show
```

The cron entry (verify with `crontab -l`, alongside the unrelated SDR job):

```
0 4 * * * cd "/Users/zuberidaley/Documents/cs2-skill-tracker" && /usr/bin/python3 capture.py >> logs/cron.log 2>&1
```

## Data sources

**Leetify** `api-public.cs-prod.leetify.com/v3/profile?steam64_id=…` — no auth. Ranks,
aggregate ratings, and the last 100 matches with per-match `preaim`, `reaction_time_ms`,
`accuracy_head`, `spray_accuracy`, `accuracy_enemy_spotted`, `leetify_rating`.

- Premier ELO = `data_source == "matchmaking"` **and** `rank_type == 11`; `rank` is the ELO.
- FACEIT level = `data_source == "faceit"`; `rank` is the level (0 means unknown — dropped).

**FACEIT** `api.faceit.com/users/v1/users?game=cs2&game_id=…` — no auth, gives current
`faceit_elo` and `skill_level`. Sampled daily, this becomes the FACEIT series.

### FACEIT access

Per-match FACEIT ELO lives only at
`api.faceit.com/stats/v1/stats/time/users/{guid}/games/cs2?page=N&size=100`, which is
behind Cloudflare. curl, `requests` and every other non-browser client get a 403
challenge page regardless of headers — it is a TLS-fingerprint check, not something a
User-Agent can talk past. A real browser passes. `backfill_faceit.py` therefore runs a
localhost receiver and prints a snippet to paste into Chrome devtools on the
api.faceit.com origin. It is a backfill, not a daily job: FACEIT history is immutable and
always re-fetchable, unlike Leetify's rolling window.

## Method notes

**Mechanics index** — z-score of five metrics (reaction time and preaim inverted so
higher is always better), averaged. Standardized against the **pre-program** mean and
standard deviation, so a program-period value of `+0.5` means "half a baseline standard
deviation better than how I played before training." The constants live in
`summary.json → mechanics_index_baseline_stats`.

**FACEIT ELO gaps** — 20 of 199 historical matches carry no `elo` (non-ELO queues).
They are dropped, never interpolated. Imputing a rank series would manufacture exactly
the trend the analysis is trying to test.

**Confounders, stated rather than hidden** — Per Scholas runs 9–4 in person Mon–Fri from
2026-08-03, which changed play volume and time of day mid-window. `finished_at` carries
time of day; treat it as a covariate, not noise.

**Sample size** — the baseline is ~100 matches; the program period starts at zero and
grows. Any program-period claim before roughly mid-September is describing noise.
Report `n`.
