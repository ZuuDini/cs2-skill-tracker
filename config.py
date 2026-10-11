"""Shared configuration for the CS2 skill-vs-rank tracker."""

from pathlib import Path

# --- Identity -----------------------------------------------------------------
# Both of these are already public (public Leetify and FACEIT profiles).
STEAM64 = "76561198268022887"
FACEIT_NICKNAME = "Zuu-"

# Resolved once from api.faceit.com/users/v1/users?game=cs2&game_id=<STEAM64>.
# capture.py re-resolves and warns if this ever drifts.
FACEIT_GUID = "7ab09f5e-d118-44ef-8871-ad9ff1b3f224"

# --- The intervention ---------------------------------------------------------
# The deliberate training program began on this date. Everything before it is
# baseline; everything on or after it is the program period.
PROGRAM_START = "2026-08-13"

# The first program was never logged (training_log.csv stayed empty), so it can
# only be read as "before vs after a date". The second one is structured: two-week
# blocks, each aimed at one weakness the data surfaced, with a Leetify measure
# that has to move. See docs/improvement-plan.md.
PRACTICE_START = "2026-10-12"
PRACTICE_BLOCKS = [
    # (first day, last day, focus)
    ("2026-10-12", "2026-10-25", "opening_duels"),
    ("2026-10-26", "2026-11-08", "aim_mechanics"),
    ("2026-11-09", "2026-11-22", "flashes_utility"),
    ("2026-11-23", "2026-12-06", "positioning_trading"),
    ("2026-12-07", "2026-12-20", "weak_maps"),
    ("2026-12-21", "2027-01-03", "demo_review_retest"),
]

# --- Endpoints ----------------------------------------------------------------
LEETIFY_PROFILE_URL = (
    "https://api-public.cs-prod.leetify.com/v3/profile?steam64_id={steam64}"
)
FACEIT_USER_URL = (
    "https://api.faceit.com/users/v1/users?game=cs2&game_id={steam64}"
)
FACEIT_STATS_URL = (
    "https://api.faceit.com/stats/v1/stats/time/users/{guid}/games/cs2"
    "?page={page}&size={size}"
)

# The Leetify public endpoint returns at most this many matches, as a *rolling*
# window. This constant is the entire reason the raw snapshots exist.
LEETIFY_WINDOW = 100
FACEIT_PAGE_SIZE = 100

# --- Paths --------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
RAW_LEETIFY = ROOT / "data" / "raw" / "leetify"
RAW_FACEIT = ROOT / "data" / "raw" / "faceit"
PROCESSED = ROOT / "data" / "processed"
LOGS = ROOT / "logs"

# FACEIT Data API v4 -- official, key-authed, not behind Cloudflare. This is
# what makes per-match kills a daily job instead of a browser backfill.
# The key lives in .env (gitignored), never in this file.
FACEIT_DATA_API = "https://open.faceit.com/data/v4"
ENV_FILE = ROOT / ".env"

USER_AGENT = "cs2-skill-tracker/1.0 (personal skill-progression research)"
TIMEOUT = 30
