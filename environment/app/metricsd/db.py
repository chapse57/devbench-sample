import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    source     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS measurements (
    run_id    TEXT NOT NULL,
    account   TEXT NOT NULL,
    followers INTEGER NOT NULL,
    PRIMARY KEY (run_id, account)
);
"""


def db_path() -> str:
    return os.environ.get("METRICSD_DB", "/app/data/metrics.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.executescript(SCHEMA)
    return conn
