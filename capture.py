#!/usr/bin/env python3
"""Capture an immutable snapshot of Leetify + FACEIT match data.

Why this exists
---------------
Leetify's public API returns only the last 100 matches, as a *rolling* window.
At ~100 matches per six weeks, the pre-program baseline (2026-07-02 onward)
will fall off the end of that window by late September. Once it does, it is
gone -- there is no way to ask the API for it again.

So this script does the least clever thing possible: it fetches the raw
responses and writes them to disk verbatim, timestamped and never overwritten.
Parsing, dedup and analysis all happen later in build.py, against these files.
Each daily snapshot overlaps the previous one by ~99 matches, so the union of
all snapshots grows monotonically and the baseline is preserved forever.

Run daily. Safe to run as often as you like.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone

import requests

import config


def _setup_logging() -> None:
    config.LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[
            logging.FileHandler(config.LOGS / "capture.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def fetch_json(url: str, attempts: int = 4):
    """GET a URL and parse JSON, retrying transient failures with backoff."""
    headers = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, headers=headers, timeout=config.TIMEOUT)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - retry anything transient
            last_error = exc
            if attempt < attempts:
                backoff = 2 ** attempt
                logging.warning(
                    "attempt %d/%d failed for %s (%s); retrying in %ds",
                    attempt, attempts, url, exc, backoff,
                )
                time.sleep(backoff)
    raise RuntimeError("giving up on %s: %s" % (url, last_error))


def fetch_faceit_user():
    """Fetch the FACEIT user record for our Steam64 ID.

    This is the only FACEIT endpoint reachable from a script. The richer
    per-match endpoint (stats/v1/stats/time/...) sits behind Cloudflare and
    returns a challenge page to curl, requests and anything else that is not a
    real browser -- see README "FACEIT access". What this one gives us is
    current `faceit_elo` and `skill_level`, which is enough: sampled daily it
    becomes the FACEIT rank time series for the program period.

    We deliberately keep only the identity and per-game blocks. The raw payload
    also contains a list of the account's friends -- other people's IDs, which
    have nothing to do with this analysis and should not be sitting in a folder
    destined for a public repo.
    """
    url = config.FACEIT_USER_URL.format(steam64=config.STEAM64)
    payload = fetch_json(url).get("payload") or []
    if not payload:
        raise RuntimeError("FACEIT returned no user for steam64 %s" % config.STEAM64)

    user = payload[0]
    guid = user.get("id")
    if guid and guid != config.FACEIT_GUID:
        logging.error(
            "FACEIT GUID drift: resolved %s but config pins %s -- update config.py.",
            guid, config.FACEIT_GUID,
        )

    return {
        "id": guid,
        "nickname": user.get("nickname"),
        "country": user.get("country"),
        "created_at": user.get("created_at"),
        "games": user.get("games") or {},
    }


def load_api_key():
    """Read FACEIT_API_KEY from .env. Returns None if absent -- the rail is optional."""
    if not config.ENV_FILE.exists():
        return None
    for line in config.ENV_FILE.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "FACEIT_API_KEY" and value.strip():
            return value.strip()
    return None


def known_faceit_stat_ids():
    """Match ids already on disk from earlier stats-*.json captures."""
    seen = set()
    for path in config.RAW_FACEIT.glob("stats-*.json"):
        with open(path, encoding="utf-8") as handle:
            for item in json.load(handle):
                seen.add(item.get("Match Id"))
    return seen


def fetch_faceit_match_stats(api_key):
    """New per-match stat lines (kills, deaths, ADR, K/R) from FACEIT Data API v4.

    Unlike Leetify, FACEIT history is permanent and always re-fetchable, so
    there is no need to store overlapping copies: page backwards from the newest
    match and stop at the first page that contains a match we already have. The
    first ever run therefore backfills the whole CS2 history.

    The stats endpoint returns only this player's own line per match -- no other
    players' names or ids beyond opaque team ids.
    """
    headers = {"Authorization": "Bearer %s" % api_key, "Accept": "application/json",
               "User-Agent": config.USER_AGENT}
    url = "%s/players/%s/games/cs2/stats" % (config.FACEIT_DATA_API, config.FACEIT_GUID)
    seen = known_faceit_stat_ids()
    new, before = [], None
    while True:
        # The API rejects offset > 200, so page by time instead: each request
        # asks for matches finished before the oldest one already received.
        params = {"limit": config.FACEIT_PAGE_SIZE}
        if before is not None:
            params["to"] = before - 1
        try:
            response = requests.get(url, headers=headers, timeout=config.TIMEOUT,
                                    params=params)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            if not new:
                raise
            # Keep what we have; the next run resumes from the newest gap.
            logging.warning("FACEIT stats paging stopped early (%s); keeping %d lines",
                            exc, len(new))
            break
        items = [i.get("stats") or {} for i in response.json().get("items") or []]
        fresh = [i for i in items if i.get("Match Id") not in seen]
        new.extend(fresh)
        if len(fresh) < len(items) or len(items) < config.FACEIT_PAGE_SIZE:
            break
        before = min(int(i["Match Finished At"]) for i in items)
    return new


def write_snapshot(directory, prefix: str, payload, stamp: str):
    """Write a raw response verbatim. Never overwrites an existing snapshot."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("%s-%s.json" % (prefix, stamp))
    if path.exists():
        logging.info("snapshot already exists, leaving it alone: %s", path.name)
        return path
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    logging.info("wrote %s (%.1f KB)", path.name, path.stat().st_size / 1024)
    return path


def describe_leetify(profile) -> None:
    """Log what we just captured, so the cron log is worth reading."""
    matches = profile.get("recent_matches") or []
    if not matches:
        logging.warning("Leetify returned zero matches -- check the profile is public")
        return

    ranks = profile.get("ranks") or {}
    oldest = matches[-1].get("finished_at", "?")[:10]
    newest = matches[0].get("finished_at", "?")[:10]
    logging.info(
        "Leetify: %d matches spanning %s..%s | premier=%s faceit_lvl=%s total=%s",
        len(matches), oldest, newest,
        ranks.get("premier"), ranks.get("faceit"), profile.get("total_matches"),
    )
    if len(matches) >= config.LEETIFY_WINDOW:
        logging.info(
            "window is full (%d) -- matches older than %s are no longer "
            "reachable from the API and now live only in these snapshots",
            len(matches), oldest,
        )


def main() -> int:
    _setup_logging()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    logging.info("=== capture run %s ===", stamp)

    failures = []

    # --- Leetify: the time-critical one -------------------------------------
    try:
        profile = fetch_json(config.LEETIFY_PROFILE_URL.format(steam64=config.STEAM64))
        write_snapshot(config.RAW_LEETIFY, "profile", profile, stamp)
        describe_leetify(profile)
    except Exception as exc:  # noqa: BLE001
        logging.error("Leetify capture FAILED: %s", exc)
        failures.append("leetify")

    # --- FACEIT: today's standing. Sampled daily, this becomes the series. ---
    try:
        user = fetch_faceit_user()
        write_snapshot(config.RAW_FACEIT, "user", user, stamp)
        cs2 = user.get("games", {}).get("cs2") or {}
        logging.info(
            "FACEIT: elo=%s level=%s region=%s",
            cs2.get("faceit_elo"), cs2.get("skill_level"), cs2.get("region"),
        )
    except Exception as exc:  # noqa: BLE001
        logging.error("FACEIT capture FAILED: %s", exc)
        failures.append("faceit")

    # --- FACEIT per-match stats: kills, deaths, ADR (needs a Data API key) ----
    api_key = load_api_key()
    if not api_key:
        logging.info("no FACEIT_API_KEY in .env -- skipping per-match kill stats")
    else:
        try:
            new_stats = fetch_faceit_match_stats(api_key)
            if new_stats:
                write_snapshot(config.RAW_FACEIT, "stats", new_stats, stamp)
            logging.info("FACEIT stats: %d new match lines", len(new_stats))
        except Exception as exc:  # noqa: BLE001
            logging.error("FACEIT stats capture FAILED: %s", exc)
            failures.append("faceit_stats")

    if failures:
        logging.error("capture finished with failures: %s", ", ".join(failures))
        return 1

    logging.info("capture OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
