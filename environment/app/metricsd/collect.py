import csv
from datetime import datetime

from . import clock, db


def make_run_id(started: datetime) -> str:
    return started.strftime("%Y%m%dT%H%M%S")


def read_input(path: str) -> list[tuple[str, int]]:
    with open(path, newline="", encoding="utf-8") as f:
        return [(row["account"], int(row["followers"])) for row in csv.DictReader(f)]


def collect(input_path: str) -> str:
    started = clock.now()
    run_id = make_run_id(started)
    rows = read_input(input_path)

    conn = db.connect()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs (run_id, started_at, source) VALUES (?, ?, ?)",
            (run_id, started.isoformat(), input_path),
        )
        conn.executemany(
            "INSERT OR REPLACE INTO measurements (run_id, account, followers) VALUES (?, ?, ?)",
            [(run_id, account, followers) for account, followers in rows],
        )
    conn.close()
    return run_id
