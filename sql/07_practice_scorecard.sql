-- YOUR TURN (from 2026-10-26, once the first practice block has data).
-- Q: Did each practice block move the stat it targeted?
--
-- Tables: data/processed/profile_stats.csv  (one row per daily snapshot)
--         data/processed/matches.csv        (practice_block column)
-- For the opening-duels block, compare ct_opening_duel_success_percentage and
-- t_opening_duel_success_percentage on the snapshot before the block started
-- vs the last snapshot inside it. Profile stats are 100-match rolling averages,
-- so a two-week block only replaces part of the window -- say so in the result.

