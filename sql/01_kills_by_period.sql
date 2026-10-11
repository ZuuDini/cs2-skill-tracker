-- Q: Did kill output change after the training program started (2026-08-13)?
--
-- Worked example. Note what it does besides averaging:
--   * reports n, because a mean without a sample size is not a finding
--   * adds a 95% confidence interval (mean +- 1.96 * sd / sqrt(n)), so two
--     periods only "differ" if their intervals mostly don't overlap
--   * filters to 2025+ so a 2024 season with a different queue mix does not
--     quietly sit inside the "before" number

SELECT
    CASE WHEN date < DATE '2026-08-13' THEN '1 before program'
         ELSE '2 since program' END                      AS period,
    count(*)                                             AS n,
    round(avg(kills), 1)                                 AS kills,
    round(avg(kr), 3)                                    AS kills_per_round,
    round(avg(kr) - 1.96 * stddev_samp(kr) / sqrt(count(*)), 3) AS kr_ci_low,
    round(avg(kr) + 1.96 * stddev_samp(kr) / sqrt(count(*)), 3) AS kr_ci_high,
    round(avg(adr), 1)                                   AS adr,
    round(100 * avg(kills_20_plus), 0)                   AS pct_games_20_kills,
    round(100 * avg(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END), 1) AS win_pct
FROM 'data/processed/faceit_matches.csv'
WHERE date >= DATE '2025-01-01'
GROUP BY period
ORDER BY period;
