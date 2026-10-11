-- Q: What does kills-per-round look like as a trend, not a single average?
--
-- Worked example of a WINDOW FUNCTION. avg(...) OVER (... ROWS BETWEEN 19
-- PRECEDING AND CURRENT ROW) averages each match with the 19 before it -- a
-- rolling 20-match mean. Single matches are noise (K/R swings 0.3 -> 1.5);
-- a rolling mean shows direction. matches_in_window guards the first 19 rows,
-- where the "20-match" average is really built from fewer matches.

SELECT
    finished_at,
    map_name,
    outcome,
    kr,
    elo,
    count(*)  OVER w                 AS matches_in_window,
    round(avg(kr)  OVER w, 3)        AS kr_rolling_20,
    round(avg(adr) OVER w, 1)        AS adr_rolling_20
FROM 'data/processed/faceit_matches.csv'
WHERE date >= DATE '2026-07-01'
WINDOW w AS (ORDER BY finished_at ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
ORDER BY finished_at DESC
LIMIT 25;
