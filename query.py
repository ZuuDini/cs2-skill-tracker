#!/usr/bin/env python3
"""Run a SQL file from sql/ against the processed CSVs with DuckDB.

    .venv/bin/python query.py sql/01_kills_by_period.sql

Queries read the CSVs directly (FROM 'data/processed/faceit_matches.csv'),
so there is no database to build or keep in sync -- rerun build.py and every
query sees the new data.
"""

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    sql = Path(sys.argv[1]).read_text(encoding="utf-8")
    con = duckdb.connect()
    con.execute("SET file_search_path = '%s'" % ROOT)
    print(con.sql(sql))
    return 0


if __name__ == "__main__":
    sys.exit(main())
