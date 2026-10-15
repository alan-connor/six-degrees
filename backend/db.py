"""Shared database connection helper.

Every script imports get_connection() from here so there's one place that
knows how to reach Postgres. Values default to the local Docker setup but
can be overridden with environment variables (handy for deployment).
"""
import os
import psycopg2


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", "six"),
        dbname=os.environ.get("PGDATABASE", "sixdegrees"),
    )
