#!/usr/bin/env python3
"""Append a day's training to the log.

The mechanical data collects itself. This file does not -- and without it
there is no independent variable, just a rank chart with a vertical line on it.
Thirty seconds a day is the whole cost of the analysis being about something.

    python3 log_training.py -m 45 -d aim_botz,deathmatch -f "crosshair placement"
    python3 log_training.py -m 30 -d prefire --date 2026-08-13 -n "nuke angles"
    python3 log_training.py --rest                 # a zero-minute day still counts
    python3 log_training.py --show                 # print the log

Rest days matter as much as training days: a gap in the log is ambiguous
(did he not train, or not record it?), whereas a logged zero is data.
"""

import argparse
import csv
import sys
from datetime import date

import config

PATH = config.PROCESSED / "training_log.csv"
FIELDS = ["date", "minutes", "drills", "focus", "notes"]


def read_log():
    if not PATH.exists():
        return []
    with open(PATH, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_log(rows):
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: r["date"])
    with open(PATH, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-m", "--minutes", type=int, help="minutes trained")
    parser.add_argument("-d", "--drills", default="",
                        help="comma-separated, e.g. aim_botz,deathmatch,prefire")
    parser.add_argument("-f", "--focus", default="", help="what you were working on")
    parser.add_argument("-n", "--notes", default="", help="anything worth remembering")
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="YYYY-MM-DD (default: today)")
    parser.add_argument("--rest", action="store_true", help="log a zero-minute day")
    parser.add_argument("--show", action="store_true", help="print the log and exit")
    args = parser.parse_args()

    rows = read_log()

    if args.show:
        if not rows:
            print("training log is empty -- nothing recorded yet")
            return 0
        total = sum(int(r["minutes"] or 0) for r in rows)
        trained = sum(1 for r in rows if int(r["minutes"] or 0) > 0)
        print("%-12s %7s  %s" % ("DATE", "MINUTES", "DRILLS / FOCUS"))
        for row in rows:
            print("%-12s %7s  %s%s" % (
                row["date"], row["minutes"], row["drills"],
                " | " + row["focus"] if row["focus"] else ""))
        print("\n%d days logged, %d with training, %d minutes total (%.1f h)"
              % (len(rows), trained, total, total / 60))
        return 0

    if args.rest:
        args.minutes = 0
    if args.minutes is None:
        parser.error("give --minutes, or --rest for a day off (--show to read the log)")

    entry = {
        "date": args.date,
        "minutes": args.minutes,
        "drills": args.drills,
        "focus": args.focus,
        "notes": args.notes,
    }

    existing = next((r for r in rows if r["date"] == args.date), None)
    if existing:
        rows[rows.index(existing)] = entry
        print("updated %s" % args.date)
    else:
        rows.append(entry)
        print("logged %s" % args.date)

    write_log(rows)

    if args.date < config.PROGRAM_START:
        print("note: %s is before the program start (%s), so this entry counts "
              "as baseline, not training" % (args.date, config.PROGRAM_START))
    return 0


if __name__ == "__main__":
    sys.exit(main())
