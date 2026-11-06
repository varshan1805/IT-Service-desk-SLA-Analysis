"""
Loads the CSVs in data/raw/ into PostgreSQL, then builds the clean tables
and the Power BI views.

Before running, create an empty database:
    createdb servicedesk

Then:
    python src/load_to_postgres.py

Connection details come from settings.PG_DEFAULTS, and you can override any
of them with the usual Postgres environment variables (PGHOST, PGPORT,
PGDATABASE, PGUSER, PGPASSWORD).
"""

import os
import sys

import psycopg2

import settings as cfg

SQL_DIR = cfg.ROOT / "sql"

# table name -> csv file. Order matters only for readability here,
# raw tables have no foreign keys.
RAW_TABLES = {
    "raw.employees": "employees.csv",
    "raw.agents": "agents.csv",
    "raw.assignment_groups": "assignment_groups.csv",
    "raw.sla_policy": "sla_policy.csv",
    "raw.tickets": "tickets.csv",
    "raw.ticket_events": "ticket_events.csv",
}


def connect():
    params = {
        "host": os.getenv("PGHOST", cfg.PG_DEFAULTS["host"]),
        "port": os.getenv("PGPORT", cfg.PG_DEFAULTS["port"]),
        "dbname": os.getenv("PGDATABASE", cfg.PG_DEFAULTS["dbname"]),
        "user": os.getenv("PGUSER", cfg.PG_DEFAULTS["user"]),
        "password": os.getenv("PGPASSWORD", cfg.PG_DEFAULTS["password"]),
    }
    try:
        return psycopg2.connect(**params)
    except psycopg2.OperationalError as e:
        sys.exit(f"Couldn't connect to Postgres ({params['host']}:{params['port']}/{params['dbname']}).\n{e}")


def run_sql_file(cur, name):
    print(f"Running {name}")
    cur.execute((SQL_DIR / name).read_text(encoding="utf-8"))
    if cur.description:  # file ended with a SELECT, show it
        cols = [c.name for c in cur.description]
        for row in cur.fetchall():
            print("   ", dict(zip(cols, row)))


def main():
    missing = [f for f in RAW_TABLES.values() if not (cfg.RAW_DIR / f).exists()]
    if missing:
        sys.exit(f"Missing {missing} in data/raw. Run python src/generate_data.py first.")

    conn = connect()
    with conn, conn.cursor() as cur:
        run_sql_file(cur, "01_schema.sql")

        for table, filename in RAW_TABLES.items():
            with open(cfg.RAW_DIR / filename, encoding="utf-8") as f:
                cur.copy_expert(f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')", f)
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  loaded {table:<24} {cur.fetchone()[0]:>8,} rows")

        run_sql_file(cur, "03_clean.sql")
        run_sql_file(cur, "05_powerbi_views.sql")

    conn.close()
    print("All loaded. Try the checks in sql/02_data_quality_checks.sql next.")


if __name__ == "__main__":
    main()
