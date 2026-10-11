#!/usr/bin/env python3
"""Turn the raw snapshots into tidy CSVs for Tableau.

The core operation is a union-with-dedupe across every Leetify snapshot ever
taken. Each snapshot holds the last 100 matches; consecutive snapshots overlap
heavily, so the union grows monotonically and matches that have aged out of the
API survive in the dataset.

This is not theoretical. Between the first two captures on 2026-08-14, six
matches were played and the API window slid forward eleven days -- 2026-07-02
through 2026-07-12 stopped being reachable. Those matches are in matches.csv
because a snapshot caught them first.

Outputs (data/processed/):
    matches.csv         one row per Leetify match, the union of all snapshots,
                        with FACEIT kills/ADR joined on finish time
    faceit_matches.csv  one row per FACEIT match: kills, deaths, ADR, K/R, ELO
    profile_stats.csv   one row per snapshot: opening duels, flashes, trades...
    daily.csv           one row per day, for the timeline panels
    faceit_elo.csv      FACEIT elo series (history + daily standing)
    summary.json        headline numbers, for sanity-checking the viz

Usage:
    python3 build.py
"""

import csv
import json
import statistics
import sys
from datetime import datetime, timezone

import config

# Mechanical metrics that make up the skill index.
# "lower_is_better" flips the sign so every component points the same way:
# positive z means "played better".
MECHANICS = [
    ("reaction_time_ms", True),
    ("preaim", True),
    ("spray_accuracy", False),
    ("accuracy_head", False),
    ("accuracy_enemy_spotted", False),
]

PREMIER_RANK_TYPE = 11  # data_source=matchmaking + rank_type=11 => Premier ELO


def load_leetify_matches():
    """Union every Leetify snapshot, deduped on match id. Newest wins."""
    snapshots = sorted(config.RAW_LEETIFY.glob("profile-*.json"))
    if not snapshots:
        raise SystemExit("no Leetify snapshots in %s -- run capture.py first"
                         % config.RAW_LEETIFY)

    matches = {}
    first_seen = {}
    for path in snapshots:
        with open(path, encoding="utf-8") as handle:
            profile = json.load(handle)
        for match in profile.get("recent_matches") or []:
            mid = match.get("id")
            if not mid:
                continue
            matches[mid] = match
            first_seen.setdefault(mid, path.name)

    print("read %d snapshots -> %d unique matches" % (len(snapshots), len(matches)))
    return matches, first_seen, snapshots


def to_row(match, first_seen_file, program_start):
    finished = match.get("finished_at") or ""
    day = finished[:10]
    source = match.get("data_source")
    rank = match.get("rank")
    rank_type = match.get("rank_type")

    is_premier = source == "matchmaking" and rank_type == PREMIER_RANK_TYPE
    # Leetify reports rank 0 for FACEIT matches it could not attribute a level to.
    faceit_level = rank if (source == "faceit" and rank) else None

    score = match.get("score") or [None, None]
    days_in = None
    if day:
        days_in = (datetime.strptime(day, "%Y-%m-%d").date()
                   - datetime.strptime(program_start, "%Y-%m-%d").date()).days

    return {
        "match_id": match.get("id"),
        "finished_at": finished,
        "date": day,
        "source": source,
        "is_premier": int(bool(is_premier)),
        # rank 0 = unranked/placement. Writing it as an ELO would draw a cliff to
        # zero on every line chart, so it becomes a gap instead.
        "premier_elo": rank if (is_premier and rank) else None,
        "faceit_level": faceit_level,
        "map_name": match.get("map_name"),
        "outcome": match.get("outcome"),
        "rounds_won": score[0] if len(score) > 0 else None,
        "rounds_lost": score[1] if len(score) > 1 else None,
        "leetify_rating": match.get("leetify_rating"),
        "preaim": match.get("preaim"),
        "reaction_time_ms": match.get("reaction_time_ms"),
        "accuracy_enemy_spotted": match.get("accuracy_enemy_spotted"),
        "accuracy_head": match.get("accuracy_head"),
        "spray_accuracy": match.get("spray_accuracy"),
        "is_program_period": int(bool(day and day >= program_start)),
        "days_from_program_start": days_in,
        "practice_block": practice_block(day),
        "first_seen_snapshot": first_seen_file,
    }


def practice_block(day):
    """Which two-week practice block a date falls in, or None outside them."""
    if not day:
        return None
    if day < config.PRACTICE_START:
        return "pre_practice"
    for first, last, focus in config.PRACTICE_BLOCKS:
        if first <= day <= last:
            return focus
    return "post_practice"


def add_mechanics_index(rows):
    """Z-score each mechanical metric against the PRE-program baseline.

    Baselining on the pre-program window (rather than on all data) is the whole
    point: it means a program-period value of +0.5 reads as "half a baseline
    standard deviation better than how I played before I started training",
    which is a statement someone can actually check.

    Returns the baseline stats so they can be written into summary.json --
    an index whose constants are invisible is not an argument, it is a mood.
    """
    baseline = [r for r in rows if not r["is_program_period"]]
    stats = {}
    for field, lower_is_better in MECHANICS:
        values = [r[field] for r in baseline if r.get(field) is not None]
        if len(values) < 2:
            print("  ! %s: only %d baseline values, skipping" % (field, len(values)))
            continue
        stats[field] = {
            "mean": statistics.mean(values),
            "stdev": statistics.pstdev(values),
            "n": len(values),
            "lower_is_better": lower_is_better,
        }

    for row in rows:
        parts = []
        for field, lower_is_better in MECHANICS:
            spec = stats.get(field)
            value = row.get(field)
            if not spec or value is None or spec["stdev"] == 0:
                row["z_" + field] = None
                continue
            z = (value - spec["mean"]) / spec["stdev"]
            if lower_is_better:
                z = -z
            row["z_" + field] = round(z, 4)
            parts.append(z)
        row["mechanics_index"] = round(sum(parts) / len(parts), 4) if parts else None

    return stats


def load_faceit_history():
    path = config.RAW_FACEIT / "faceit_cs2_history.csv"
    if not path.exists():
        print("no FACEIT history CSV (run backfill_faceit.py); continuing without it")
        return []
    with open(path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    out = []
    for row in rows:
        if not row.get("elo"):
            continue  # non-ELO match; never impute silently
        out.append({
            "date": row["finished_at"][:10],
            "finished_at": row["finished_at"],
            "elo": int(row["elo"]),
            "elo_delta": int(row["elo_delta"]) if row.get("elo_delta") else None,
            "map_name": row.get("map_name"),
            "kd": row.get("kd"),
            "hs_pct": row.get("hs_pct"),
            "source": "match_history",
        })
    print("FACEIT history: %d of %d matches carry an elo" % (len(out), len(rows)))
    return out


def load_faceit_snapshots():
    """Daily standing from capture.py -- covers the program period going forward."""
    out = []
    for path in sorted(config.RAW_FACEIT.glob("user-*.json")):
        with open(path, encoding="utf-8") as handle:
            user = json.load(handle)
        cs2 = (user.get("games") or {}).get("cs2") or {}
        if not cs2.get("faceit_elo"):
            continue
        stamp = path.stem.split("-", 1)[1]
        captured = datetime.strptime(stamp, "%Y-%m-%dT%H%M%SZ").replace(
            tzinfo=timezone.utc)
        out.append({
            "date": captured.date().isoformat(),
            "finished_at": captured.isoformat(),
            "elo": int(cs2["faceit_elo"]),
            "elo_delta": None,
            "map_name": None,
            "kd": None,
            "hs_pct": None,
            "source": "daily_snapshot",
        })
    return out


def load_faceit_matches():
    """One row per FACEIT match: kills, deaths, ADR, K/R from Data API v4.

    stats-*.json files hold only lines that were new when captured, so a union
    deduped on match id is the full history. Per-match ELO is not in v4; it is
    joined in from the browser backfill (faceit_cs2_history.csv) where it exists.
    """
    lines = {}
    for path in sorted(config.RAW_FACEIT.glob("stats-*.json")):
        with open(path, encoding="utf-8") as handle:
            for item in json.load(handle):
                lines[item["Match Id"]] = item
    if not lines:
        print("no FACEIT stats-*.json (needs FACEIT_API_KEY); skipping kills")
        return []

    elo = {}
    history = config.RAW_FACEIT / "faceit_cs2_history.csv"
    if history.exists():
        with open(history, encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                elo[row["match_id"]] = row

    def num(value, kind=float):
        return kind(value) if value not in (None, "") else None

    out = []
    for mid, s in lines.items():
        finished = datetime.fromtimestamp(int(s["Match Finished At"]) / 1000,
                                          tz=timezone.utc)
        day = finished.date().isoformat()
        rounds = num(s.get("Rounds"), int)
        old = elo.get(mid, {})
        out.append({
            "faceit_match_id": mid,
            "finished_at": finished.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "date": day,
            "map_name": s.get("Map"),
            "outcome": "win" if s.get("Result") == "1" else "loss",
            "score": s.get("Score"),
            "rounds": rounds,
            "kills": num(s.get("Kills"), int),
            "deaths": num(s.get("Deaths"), int),
            "assists": num(s.get("Assists"), int),
            "headshots": num(s.get("Headshots"), int),
            "hs_pct": num(s.get("Headshots %")),
            "kd": num(s.get("K/D Ratio")),
            "kr": num(s.get("K/R Ratio")),
            "adr": num(s.get("ADR")),
            "mvps": num(s.get("MVPs"), int),
            "multi_kills": sum(num(s.get(k), int) or 0 for k in
                               ("Double Kills", "Triple Kills", "Quadro Kills",
                                "Penta Kills")),
            "kills_20_plus": int((num(s.get("Kills"), int) or 0) >= 20),
            "elo": num(old.get("elo"), int),
            "elo_delta": num(old.get("elo_delta"), int),
            "is_program_period": int(day >= config.PROGRAM_START),
            "practice_block": practice_block(day),
        })
    out.sort(key=lambda r: r["finished_at"])
    print("FACEIT stats: %d matches, %s..%s"
          % (len(out), out[0]["date"], out[-1]["date"]))
    return out


def join_faceit_kills(rows, faceit_rows, tolerance_s=600):
    """Attach FACEIT kills/ADR to Leetify's FACEIT matches by finish time.

    The two sources use different match ids, so the join key is time: nearest
    FACEIT match within +-10 minutes. Two matches never finish that close
    together, so a hit is unambiguous. Misses are counted, not hidden.
    """
    def ts(value):
        return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").timestamp()

    faceit_ts = [(ts(f["finished_at"]), f) for f in faceit_rows]
    matched = unmatched = 0
    for row in rows:
        for field in ("faceit_match_id", "kills", "deaths", "adr", "kr"):
            row[field] = None
        if row["source"] != "faceit" or not faceit_ts:
            continue
        t = ts(row["finished_at"])
        gap, best = min(((abs(t - ft), f) for ft, f in faceit_ts), key=lambda p: p[0])
        if gap > tolerance_s:
            unmatched += 1
            continue
        matched += 1
        row.update({"faceit_match_id": best["faceit_match_id"],
                    "kills": best["kills"], "deaths": best["deaths"],
                    "adr": best["adr"], "kr": best["kr"]})
    print("Leetify<->FACEIT join: %d matched, %d unmatched (+-%ds)"
          % (matched, unmatched, tolerance_s))
    return matched, unmatched


# Aggregate Leetify stats worth tracking over time. Each snapshot reports them
# over its own 100-match window, so the series is a rolling average, not a
# per-match measurement -- consecutive points share ~99% of their matches.
PROFILE_STATS = [
    "ct_opening_duel_success_percentage", "t_opening_duel_success_percentage",
    "ct_opening_aggression_success_rate", "t_opening_aggression_success_rate",
    "trade_kills_success_percentage", "traded_deaths_success_percentage",
    "trade_kill_opportunities_per_round",
    "flashbang_hit_foe_per_flashbang", "flashbang_hit_friend_per_flashbang",
    "flashbang_leading_to_kill", "flashbang_thrown", "utility_on_death_avg",
    "he_foes_damage_avg", "he_friends_damage_avg",
    "counter_strafing_good_shots_ratio", "spray_accuracy", "accuracy_head",
    "accuracy_enemy_spotted", "preaim", "reaction_time_ms",
]
PROFILE_RATINGS = ["aim", "positioning", "utility", "clutch", "opening",
                   "ct_leetify", "t_leetify"]


def load_profile_stats(snapshots):
    """One row per Leetify snapshot: ranks, ratings and window-level stats."""
    faceit_elo = {}
    for path in config.RAW_FACEIT.glob("user-*.json"):
        with open(path, encoding="utf-8") as handle:
            cs2 = (json.load(handle).get("games") or {}).get("cs2") or {}
        faceit_elo[path.stem.split("-", 1)[1]] = cs2.get("faceit_elo")

    out = []
    for path in snapshots:
        with open(path, encoding="utf-8") as handle:
            profile = json.load(handle)
        stamp = path.stem.split("-", 1)[1]
        matches = profile.get("recent_matches") or []
        ranks = profile.get("ranks") or {}
        rating = profile.get("rating") or {}
        stats = profile.get("stats") or {}
        row = {
            "captured_at": datetime.strptime(stamp, "%Y-%m-%dT%H%M%SZ")
            .replace(tzinfo=timezone.utc).isoformat(),
            "snapshot": path.name,
            "window_start": matches[-1]["finished_at"][:10] if matches else None,
            "window_end": matches[0]["finished_at"][:10] if matches else None,
            "window_matches": len(matches),
            "total_matches": profile.get("total_matches"),
            "winrate": profile.get("winrate"),
            "premier": ranks.get("premier"),
            "faceit_level": ranks.get("faceit"),
            "faceit_elo": faceit_elo.get(stamp),
            "leetify_rank": ranks.get("leetify"),
        }
        row.update({"rating_" + k: rating.get(k) for k in PROFILE_RATINGS})
        row.update({k: stats.get(k) for k in PROFILE_STATS})
        out.append(row)
    return out


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print("wrote %s (%d rows)" % (path.name, len(rows)))


def build_daily(rows):
    """One row per day: rank standing plus mean mechanics."""
    days = {}
    for row in rows:
        if not row["date"]:
            continue
        day = days.setdefault(row["date"], {"date": row["date"], "matches": 0,
                                            "premier": [], "mech": [], "wins": 0})
        day["matches"] += 1
        if row["outcome"] == "win":
            day["wins"] += 1
        if row["premier_elo"]:
            day["premier"].append(row["premier_elo"])
        if row["mechanics_index"] is not None:
            day["mech"].append(row["mechanics_index"])

    out = []
    for day in sorted(days.values(), key=lambda d: d["date"]):
        out.append({
            "date": day["date"],
            "matches": day["matches"],
            "wins": day["wins"],
            # Closing ELO is the day's standing; mean would blur real movement.
            "premier_elo_close": day["premier"][-1] if day["premier"] else None,
            "premier_elo_min": min(day["premier"]) if day["premier"] else None,
            "premier_elo_max": max(day["premier"]) if day["premier"] else None,
            "mechanics_index_mean": (round(statistics.mean(day["mech"]), 4)
                                     if day["mech"] else None),
            "is_program_period": int(day["date"] >= config.PROGRAM_START),
        })
    return out


def main() -> int:
    config.PROCESSED.mkdir(parents=True, exist_ok=True)

    matches, first_seen, snapshots = load_leetify_matches()
    rows = [to_row(m, first_seen[mid], config.PROGRAM_START)
            for mid, m in matches.items()]
    rows.sort(key=lambda r: r["finished_at"])

    print("computing mechanics index against the pre-program baseline...")
    baseline_stats = add_mechanics_index(rows)

    faceit_matches = load_faceit_matches()
    join_matched, join_unmatched = join_faceit_kills(rows, faceit_matches)
    if faceit_matches:
        write_csv(config.PROCESSED / "faceit_matches.csv", faceit_matches,
                  list(faceit_matches[0].keys()))

    profile_stats = load_profile_stats(snapshots)
    write_csv(config.PROCESSED / "profile_stats.csv", profile_stats,
              list(profile_stats[0].keys()))

    fields = list(rows[0].keys())
    write_csv(config.PROCESSED / "matches.csv", rows, fields)

    daily = build_daily(rows)
    write_csv(config.PROCESSED / "daily.csv", daily, list(daily[0].keys()))

    faceit = load_faceit_history() + load_faceit_snapshots()
    faceit.sort(key=lambda r: r["finished_at"])
    if faceit:
        write_csv(config.PROCESSED / "faceit_elo.csv", faceit, list(faceit[0].keys()))

    # --- summary, so the dashboard's headline numbers can be checked ---------
    premier = [r for r in rows if r["premier_elo"]]
    program = [r for r in rows if r["is_program_period"]]
    base = [r for r in rows if not r["is_program_period"]]

    def mean_of(subset, field):
        vals = [r[field] for r in subset if r.get(field) is not None]
        return round(statistics.mean(vals), 3) if vals else None

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "program_start": config.PROGRAM_START,
        "snapshots_read": len(snapshots),
        "matches_total": len(rows),
        "date_range": [rows[0]["date"], rows[-1]["date"]],
        "api_window_now": [
            json.load(open(snapshots[-1], encoding="utf-8"))["recent_matches"][-1]
            ["finished_at"][:10],
            rows[-1]["date"],
        ],
        "matches_recovered_beyond_api_window": sum(
            1 for r in rows
            if r["date"] < json.load(open(snapshots[-1], encoding="utf-8"))
            ["recent_matches"][-1]["finished_at"][:10]
        ),
        "baseline": {
            "n": len(base),
            "premier_first": premier[0]["premier_elo"] if premier else None,
            **{f: mean_of(base, f) for f, _ in MECHANICS},
        },
        "program": {
            "n": len(program),
            "premier_last": premier[-1]["premier_elo"] if premier else None,
            **{f: mean_of(program, f) for f, _ in MECHANICS},
        },
        "mechanics_index_baseline_stats": {
            k: {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                for kk, vv in v.items()}
            for k, v in baseline_stats.items()
        },
        "faceit": {
            "matches": len(faceit_matches),
            "date_range": ([faceit_matches[0]["date"], faceit_matches[-1]["date"]]
                           if faceit_matches else None),
            "leetify_join_matched": join_matched,
            "leetify_join_unmatched": join_unmatched,
            "last_50": {
                "kills": mean_of(faceit_matches[-50:], "kills"),
                "deaths": mean_of(faceit_matches[-50:], "deaths"),
                "kr": mean_of(faceit_matches[-50:], "kr"),
                "adr": mean_of(faceit_matches[-50:], "adr"),
                "rounds": mean_of(faceit_matches[-50:], "rounds"),
                "kills_20_plus_share": mean_of(faceit_matches[-50:], "kills_20_plus"),
            },
        },
        "profile_now": {k: profile_stats[-1][k] for k in
                        ("captured_at", "premier", "faceit_level", "faceit_elo",
                         "total_matches")},
    }
    with open(config.PROCESSED / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    print("\n--- summary ---")
    print("matches: %d over %s..%s (from %d snapshots)"
          % (len(rows), rows[0]["date"], rows[-1]["date"], len(snapshots)))
    print("API can currently see back to %s; %d matches survive only in snapshots"
          % (summary["api_window_now"][0],
             summary["matches_recovered_beyond_api_window"]))
    print("baseline n=%d, program n=%d" % (len(base), len(program)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
