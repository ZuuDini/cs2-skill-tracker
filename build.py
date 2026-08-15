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
    matches.csv      one row per match, the union of all snapshots
    daily.csv        one row per day, for the timeline panels
    faceit_elo.csv   FACEIT elo series (history + daily standing)
    summary.json     headline numbers, for sanity-checking the viz

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
        "premier_elo": rank if is_premier else None,
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
        "first_seen_snapshot": first_seen_file,
    }


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
