-- YOUR TURN.
-- Q: Do Leetify's mechanics (reaction time, preaim, spray, headshot accuracy)
--    show up in kills? Better aim on paper should mean more kills in the game.
--
-- Table: data/processed/matches.csv  (one row per Leetify match; the FACEIT
-- matches have kills / adr / kr joined in -- filter WHERE kills IS NOT NULL)
-- Use corr(x, y) for each mechanic against kr. Report n alongside.
-- Remember: correlation over ~100 matches, from one player, is a hint about
-- where to look -- not proof of cause.

