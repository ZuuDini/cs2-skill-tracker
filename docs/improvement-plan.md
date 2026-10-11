# Improvement plan: FACEIT Level 6 → Level 8

Written 2026-10-11 from the data in this repo (see `analysis.ipynb`). Runs 12 weeks from
2026-10-12 at about **3 hours a week** of practice outside normal matches. The block dates live
in `config.py → PRACTICE_BLOCKS`, so every match is tagged with the block it was played in.

## Where things stand

| | Now | Target |
|---|---|---|
| FACEIT ELO | 1,243 (Level 6) | 1,531 (Level 8 floor, +288) |
| Win rate since 2026-08-13 | 51.8% (n=112) | 55%+ |
| Kills per round, last 20 | 0.62 | 0.75 by week 6, 0.85 by week 12 |
| Kills per game | 15.5 since the program | ~16, then ~18 |

**Win rate is the lever, not volume.** Measured since the program started, a win is worth +27.3
ELO and a loss −25.0. To gain the +288:

| Win rate | ELO per game | Games to Level 8 |
|---|---|---|
| 51.8% (now) | +2.1 | ~138 |
| 55% | +3.8 | ~76 |
| 58% | +5.3 | ~54 |

**About the 20–25 kills goal.** At ~22 rounds a game, that's 0.95–1.15 kills per round, a 45–75%
jump from now. Level 8 doesn't require it. Wins average 16.5 kills and losses 14.4, so the gap
that decides games is about two kills and twelve damage per round. The staged targets above aim
at that gap. Damage per round (ADR) is tracked alongside kills so the number can't be gamed by
baiting teammates.

## What to fix, in order

From Leetify's aggregate stats, August window (Jul 2–Aug 14) vs. October window (Aug 24–Oct 10):

1. **Opening duels.** CT first-duel win rate fell 47% → 40%, and T sits at 39%. You lose about 6
   of every 10 first fights.
2. **Flashing teammates.** 0.62 teammates blinded per flash, now equal to enemies blinded. It was
   0.49. Utility rating fell 70 → 61.
3. **Converting aim into hits.** Reaction time (694 → 641 ms) and preaim (11.3° → 10.1°) really
   improved (per-match, non-overlapping 95% intervals), but accuracy with an enemy spotted fell
   36% → 33% and spray accuracy 37% → 34%.
   Counter-strafe ratio slipped 88% → 85%.
4. **Trading.** You trade a teammate's death 44% of the time (was 49%).
5. **Maps, since 2026-08-13.** Dust2 is 5–11 (31%) and Anubis 6–11 (35%), against Ancient 11–4
   (73%) and Mirage 18–13 (58%). Under 20 games per map, so treat these as directional.

**Protect these:** reaction time, preaim, T-side opening aggression (35% → 63%), and positioning
rating (55 → 59).

## Weekly shape (~3 hours)

- **4 × 20-min warm-up before you queue (80 min):** 5 min counter-strafe taps on Aim Botz,
  5 min spray transfers, 10 min prefire or crosshair placement on tonight's map.
- **1 × 45-min demo review:** watch only your **first death of each round** and **every flash you
  throw**. Tag each death won/lost, the cause, and whether it was tradeable. Then log it:
  `python3 log_training.py -m 45 -d demo_review -f opening_duels -n "6/10 first deaths untradeable"`
- **1 × 45-min study block** on the fortnight's focus (below).
- **Log every session, including rest days** (`--rest`). The first program was never logged, which
  is why the data can't say what caused the climb.

## The 12 weeks

| Weeks | Dates | Focus | Leetify measure that has to move | Videos |
|---|---|---|---|---|
| 1–2 | Oct 12–25 | Opening duels and peeking | CT/T first-duel win % → 45%+ | [Biley – The GREATEST CS2 Peeking Guide](https://www.youtube.com/watch?v=S_3cHXNOt8I) · [louiecs2 – This Will Change the Way You Peek](https://www.youtube.com/watch?v=6wPne7EmMEE) · [Tigerr – You're Peeking Wrong in CS2](https://www.youtube.com/watch?v=_XgTWfNkyfs) |
| 3–4 | Oct 26–Nov 8 | Crosshair placement, counter-strafe, spray | counter-strafe → 90%, spray → 37%+, accuracy spotted → 36%+ | [Biley – Crosshair Placement Guide (10 min)](https://www.youtube.com/watch?v=7zybiFlBGbg) · [sebcs – Ultimate Guide to Counter Strafing](https://www.youtube.com/watch?v=Li4J09ei8ro) · [kneel – Ultimate CS2 Spray Control Guide](https://www.youtube.com/watch?v=vl6J1cQcErU) |
| 5–6 | Nov 9–22 | Flashes and utility | teammates flashed per flash → under 0.30, utility rating → 67+ | [WilsonCS2 – Ultimate Flashbang Guide (Zero Lineups)](https://www.youtube.com/watch?v=i59BlyMzBHE) · [Wan0play – Use counter-flashes wisely](https://www.youtube.com/watch?v=o8hgmYlfUL8) |
| 7–8 | Nov 23–Dec 6 | Positioning and trading | trade-kill success → 50%+ | [Biley – The GREATEST CS2 Positioning Guide](https://www.youtube.com/watch?v=RrGFGUIzCt0) · [louiecs2 – In-Depth Guide to Positioning](https://www.youtube.com/watch?v=Fp3k9WRJupY) |
| 9–10 | Dec 7–20 | Dust2 and Anubis | map win % (small samples, directional) | [21kiyotaka – Dust 2 Like a FACEIT Level 10](https://www.youtube.com/watch?v=c6saobQe3cc) · [Tigerr – Dust 2 Utility Every Player Needs](https://www.youtube.com/watch?v=ghZjWmo_44k) · [sebcs – Play Anubis Like the Pros](https://www.youtube.com/watch?v=AjvPl3qamwE) · [NartOutHere – Anubis Nades Guide](https://www.youtube.com/watch?v=SWlsYC_bAlo) |
| 11–12 | Dec 21–Jan 3 | Demo review as a habit, then re-test everything | all of the above | [Biley – How to Demo Review Like a Pro](https://www.youtube.com/watch?v=UxTlDS5aKzw) · [NartOutHere – How to Watch Demos in CS2](https://www.youtube.com/watch?v=3c3zLINiApE) |

All video links were checked to exist on 2026-10-11.

## How progress is judged

- **Every two weeks, re-measure from the pipeline, not by feel:** `python3 build.py`, then
  `sql/07_practice_scorecard.sql`.
- **A block is done when its measure moves, not when the videos are watched.** If it didn't move,
  repeat the block before moving on.
- Leetify's profile stats are 100-match rolling averages. A two-week block of ~15 matches only
  replaces part of the window, so expect the needle to move slowly. Per-match FACEIT kills and ADR
  respond faster.
