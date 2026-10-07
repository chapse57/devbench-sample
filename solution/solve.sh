#!/bin/bash
# 참조 풀이.
# 핵심: (1) runs에 AUTOINCREMENT 순번(seq)을 두고 '기록 순서'의 기준으로 삼는다.
#       (2) run_id = 시작시각 + "-" + seq. 순번은 BEGIN IMMEDIATE(쓰기 잠금) 안에서 발급되므로
#           여러 프로세스가 동시에 collect 해도 겹치지 않는다.
#       (3) 구 스키마 DB는 처음 열 때 잠금 안에서 한 번만 마이그레이션한다(기존 순서 = run_id 순서).
#       (4) 측정값은 OR REPLACE 없이 INSERT — 만에 하나 충돌하면 조용히 덮어쓰지 않고 실패한다.
set -euo pipefail
cd /app/metricsd

cat > db.py <<'PY'
import os
import sqlite3

RUNS_DDL = """
CREATE TABLE {name} (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL UNIQUE,
    started_at TEXT NOT NULL,
    source     TEXT NOT NULL
)
"""

MEASUREMENTS_DDL = """
CREATE TABLE IF NOT EXISTS measurements (
    run_id    TEXT NOT NULL,
    account   TEXT NOT NULL,
    followers INTEGER NOT NULL,
    PRIMARY KEY (run_id, account)
)
"""


def db_path() -> str:
    return os.environ.get("METRICSD_DB", "/app/data/metrics.db")


def _runs_columns(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute("PRAGMA table_info(runs)")]


def _ensure_schema(conn: sqlite3.Connection) -> None:
    if "seq" in _runs_columns(conn):
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        cols = _runs_columns(conn)  # 잠금을 잡은 뒤 다시 확인 — 다른 프로세스가 먼저 끝냈을 수 있다
        if "seq" not in cols:
            conn.execute(MEASUREMENTS_DDL)
            if not cols:
                conn.execute(RUNS_DDL.format(name="runs"))
            else:
                conn.execute(RUNS_DDL.format(name="runs_new"))
                conn.execute(
                    "INSERT INTO runs_new (run_id, started_at, source) "
                    "SELECT run_id, started_at, source FROM runs ORDER BY run_id"
                )
                conn.execute("DROP TABLE runs")
                conn.execute("ALTER TABLE runs_new RENAME TO runs")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 30000")
    _ensure_schema(conn)
    return conn
PY

cat > collect.py <<'PY'
import csv
import uuid
from datetime import datetime

from . import clock, db


def make_run_id(started: datetime, seq: int) -> str:
    return f"{started.strftime('%Y%m%dT%H%M%S')}-{seq:06d}"


def read_input(path: str) -> list[tuple[str, int]]:
    with open(path, newline="", encoding="utf-8") as f:
        return [(row["account"], int(row["followers"])) for row in csv.DictReader(f)]


def collect(input_path: str) -> str:
    started = clock.now()
    rows = read_input(input_path)

    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "INSERT INTO runs (run_id, started_at, source) VALUES (?, ?, ?)",
            (f"pending-{uuid.uuid4().hex}", started.isoformat(), input_path),
        )
        seq = cur.lastrowid
        run_id = make_run_id(started, seq)
        conn.execute("UPDATE runs SET run_id = ? WHERE seq = ?", (run_id, seq))
        conn.executemany(
            "INSERT INTO measurements (run_id, account, followers) VALUES (?, ?, ?)",
            [(run_id, account, followers) for account, followers in rows],
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return run_id
PY

python - <<'PY'
from pathlib import Path
p = Path("report.py")
src = p.read_text(encoding="utf-8")
src = src.replace("GROUP BY r.run_id\n        ORDER BY r.run_id", "GROUP BY r.seq\n        ORDER BY r.seq")
assert "ORDER BY r.seq" in src, "report.py 패치 실패"
p.write_text(src, encoding="utf-8")
PY
