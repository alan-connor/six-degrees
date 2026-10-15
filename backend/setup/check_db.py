"""Checkpoint: confirm Python can reach the Postgres database.

Run:  python setup/check_db.py
Expects the Docker Postgres from the roadmap to be running.
"""
import psycopg2

# Connection info from the Docker container (see roadmap).
# host/port come from the -p 5432:5432 mapping; user/password/db from the -e env vars.
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="six",
    dbname="sixdegrees",
)

# A cursor is how you send SQL and read results back.
with conn.cursor() as cur:
    cur.execute("SELECT version();")   # ask Postgres its version
    version = cur.fetchone()[0]        # fetchone() -> a 1-tuple; [0] is the string
    print("Connected! Postgres says:")
    print(version)

conn.close()
