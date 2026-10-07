"""run-id-same-second-collision 채점 테스트.

모든 검사는 CLI(`python -m metricsd ...`)를 통해서만 한다. 단, '운영 중인 구 스키마 DB'를
재현할 때만 원래 스키마로 SQLite 파일을 직접 만든다.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

APP_DIR = Path(os.environ.get("APP_DIR", "/app"))
SAME_SECOND = "2026-09-21T09:00:00+00:00"
RUN_ID_PREFIX = "20260921T090000"


def cli(*args, db, fake_now=None, check=True):
    env = dict(os.environ)
    env["METRICSD_DB"] = str(db)
    env.pop("METRICSD_FAKE_NOW", None)
    if fake_now:
        env["METRICSD_FAKE_NOW"] = fake_now
    proc = subprocess.run(
        [sys.executable, "-m", "metricsd", *args],
        cwd=APP_DIR, env=env, capture_output=True, text=True, timeout=60,
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"metricsd {' '.join(args)} 실패 (exit {proc.returncode}): {proc.stderr}")
    return proc


def write_csv(path: Path, rows: dict[str, int]) -> Path:
    lines = ["account,followers"] + [f"{a},{f}" for a, f in rows.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def collect(db, csv_path, fake_now=SAME_SECOND) -> str:
    out = cli("collect", "--input", str(csv_path), db=db, fake_now=fake_now).stdout.strip()
    lines = [l for l in out.splitlines() if l.strip()]
    assert len(lines) == 1, f"collect는 run_id 한 줄만 출력해야 합니다: {out!r}"
    return lines[0].strip()


def runs(db):
    return json.loads(cli("runs", db=db).stdout)


def show(db, run_id):
    return json.loads(cli("show", run_id, db=db).stdout)


def diff(db):
    return json.loads(cli("diff", db=db).stdout)


LEGACY_ORDER = ["20260907T090000", "20260914T090000", "20260921T090005"]


def make_legacy_db(path: Path):
    """현재(수정 전) 스키마로 만들어진 운영 DB. 실행 3개, 측정값 6개.

    9/7 실행은 백업에서 나중에 복원(backfill)되어 '가장 마지막에 INSERT'되었다.
    지시문대로 기존 실행끼리의 순서는 run_id 순서여야 하므로, 암묵적 rowid(삽입 순서)에
    기대는 풀이는 여기서 걸린다.
    """
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, source TEXT NOT NULL);
        CREATE TABLE measurements (run_id TEXT NOT NULL, account TEXT NOT NULL,
                                   followers INTEGER NOT NULL, PRIMARY KEY (run_id, account));
        """
    )
    conn.executemany(
        "INSERT INTO runs VALUES (?, ?, ?)",
        [
            ("20260914T090000", "2026-09-14T09:00:00+00:00", "legacy-a.csv"),
            ("20260921T090005", "2026-09-21T09:00:05+00:00", "legacy-b.csv"),
        ],
    )
    conn.executemany(
        "INSERT INTO measurements VALUES (?, ?, ?)",
        [
            ("20260914T090000", "alpha_cafe", 1500),
            ("20260914T090000", "beta_studio", 870),
            ("20260921T090005", "alpha_cafe", 1520),
            ("20260921T090005", "beta_studio", 880),
            ("20260921T090005", "gamma_lab", 12040),
        ],
    )
    # backfill: 가장 오래된 실행이 가장 나중에 들어온다
    conn.execute("INSERT INTO runs VALUES (?, ?, ?)",
                 ("20260907T090000", "2026-09-07T09:00:00+00:00", "restored-from-backup.csv"))
    conn.execute("INSERT INTO measurements VALUES (?, ?, ?)", ("20260907T090000", "alpha_cafe", 1490))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- 1. 고유성


def test_same_second_runs_get_distinct_ids_and_keep_their_own_data(tmp_path):
    db = tmp_path / "m.db"
    a = write_csv(tmp_path / "a.csv", {"alpha_cafe": 100, "beta_studio": 200})
    b = write_csv(tmp_path / "b.csv", {"alpha_cafe": 111, "gamma_lab": 300})

    id_a = collect(db, a)
    id_b = collect(db, b)

    assert id_a != id_b, "같은 초에 시작한 두 실행이 같은 run_id를 받았습니다"
    assert show(db, id_a) == {"alpha_cafe": 100, "beta_studio": 200}, "첫 실행의 측정값이 덮어써지거나 섞였습니다"
    assert show(db, id_b) == {"alpha_cafe": 111, "gamma_lab": 300}
    assert len(runs(db)) == 2


def test_run_id_starts_with_start_time_and_started_at_is_untouched(tmp_path):
    db = tmp_path / "m.db"
    a = write_csv(tmp_path / "a.csv", {"alpha_cafe": 1})
    ids = [collect(db, a) for _ in range(3)]
    for rid in ids:
        assert rid.startswith(RUN_ID_PREFIX), f"run_id는 시작 시각 {RUN_ID_PREFIX}로 시작해야 합니다: {rid}"
    for r in runs(db):
        assert r["started_at"] == SAME_SECOND, f"started_at은 시계 값 그대로여야 합니다: {r['started_at']}"


@pytest.mark.parametrize("round_no", range(5))
def test_concurrent_processes_never_collide_or_mix(tmp_path, round_no):
    db = tmp_path / "m.db"
    collect(db, write_csv(tmp_path / "seed.csv", {"seed": 0}))  # DB·스키마를 먼저 준비

    n = 12
    csvs = [
        write_csv(tmp_path / f"p{i}.csv", {f"acct_{i}_{k}": i * 100 + k for k in range(5)})
        for i in range(n)
    ]
    env = dict(os.environ, METRICSD_DB=str(db), METRICSD_FAKE_NOW=SAME_SECOND)
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "metricsd", "collect", "--input", str(c)],
            cwd=APP_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for c in csvs
    ]
    results = []
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, f"동시 collect 중 하나가 실패했습니다: {err}"
        results.append(out.strip())

    assert len(set(results)) == n, f"동시 실행에서 run_id가 겹쳤습니다: {results}"
    for i, rid in enumerate(results):
        expected = {f"acct_{i}_{k}": i * 100 + k for k in range(5)}
        assert show(db, rid) == expected, f"프로세스 {i}의 측정값이 다른 실행과 섞였습니다"
    assert len(runs(db)) == n + 1


# ---------------------------------------------------------------- 2. 기록 순서


@pytest.mark.parametrize("round_no", range(4))
def test_diff_uses_recording_order_when_clock_is_identical(tmp_path, round_no):
    db = tmp_path / "m.db"
    ids = []
    for i in range(3):
        ids.append(collect(db, write_csv(tmp_path / f"r{i}.csv", {"alpha_cafe": 1000 + i})))

    assert [r["run_id"] for r in runs(db)] == ids, "runs 출력이 기록 순서가 아닙니다"
    d = diff(db)
    assert (d["base"], d["head"]) == (ids[1], ids[2]), "diff가 마지막 두 실행을 비교하지 않았습니다"
    assert d["changes"] == [{"account": "alpha_cafe", "before": 1001, "after": 1002}]


def test_clock_going_backwards_does_not_change_what_latest_means(tmp_path):
    db = tmp_path / "m.db"
    first = collect(db, write_csv(tmp_path / "a.csv", {"alpha_cafe": 10}), fake_now="2026-09-21T09:00:05+00:00")
    later = collect(db, write_csv(tmp_path / "b.csv", {"alpha_cafe": 20}), fake_now="2026-09-21T09:00:01+00:00")

    assert [r["run_id"] for r in runs(db)] == [first, later]
    d = diff(db)
    assert (d["base"], d["head"]) == (first, later), "시계가 뒤로 간 뒤 기록된 실행이 최신으로 잡혀야 합니다"
    assert later.startswith("20260921T090001")


# ---------------------------------------------------------------- 3. 기존 데이터


def test_legacy_db_is_preserved_and_new_runs_come_after_it(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)

    # 시계가 기존 마지막 실행(09:00:05)보다 '앞선' 시각이어도 새 실행은 뒤에 와야 한다
    new_id = collect(db, write_csv(tmp_path / "n.csv", {"alpha_cafe": 1600, "beta_studio": 880}))

    after = runs(db)
    assert [r["run_id"] for r in after] == LEGACY_ORDER + [new_id], "기존 실행 순서(run_id 순) 또는 새 실행 위치가 틀렸습니다"
    assert [r["count"] for r in after[:3]] == [1, 2, 3], "기존 실행의 측정값이 바뀌었습니다"
    assert after[1]["started_at"] == "2026-09-14T09:00:00+00:00"
    assert after[2]["source"] == "legacy-b.csv"
    assert show(db, "20260907T090000") == {"alpha_cafe": 1490}
    assert show(db, "20260921T090005") == {"alpha_cafe": 1520, "beta_studio": 880, "gamma_lab": 12040}

    d = diff(db)
    assert (d["base"], d["head"]) == ("20260921T090005", new_id)
    assert d["changes"] == [
        {"account": "alpha_cafe", "before": 1520, "after": 1600},
        {"account": "gamma_lab", "before": 12040, "after": None},
    ]


def test_legacy_db_survives_concurrent_first_open(tmp_path):
    """구 스키마 DB를 여러 프로세스가 동시에 처음 열어도(마이그레이션 경합) 데이터가 보존된다."""
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    env = dict(os.environ, METRICSD_DB=str(db), METRICSD_FAKE_NOW=SAME_SECOND)
    csvs = [write_csv(tmp_path / f"c{i}.csv", {f"x{i}": i}) for i in range(8)]
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "metricsd", "collect", "--input", str(c)],
            cwd=APP_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for c in csvs
    ]
    ids = []
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, f"동시 첫 접근에서 collect가 실패했습니다: {err}"
        ids.append(out.strip())

    listed = [r["run_id"] for r in runs(db)]
    assert listed[:3] == LEGACY_ORDER, "기존 실행이 사라졌거나 순서가 바뀌었습니다"
    assert sorted(listed[3:]) == sorted(ids) and len(listed) == 11
    assert show(db, "20260914T090000") == {"alpha_cafe": 1500, "beta_studio": 870}


# ---------------------------------------------------------------- 인터페이스


def test_cli_contract_is_kept(tmp_path):
    db = tmp_path / "m.db"
    rid = collect(db, write_csv(tmp_path / "a.csv", {"alpha_cafe": 5}))
    assert re.fullmatch(r"\S+", rid), "run_id에 공백이 들어가면 안 됩니다"
    r = runs(db)[0]
    assert set(r) >= {"run_id", "started_at", "source", "count"}
    d = diff(db)
    assert set(d) == {"base", "head", "changes"} and d["base"] is None and d["head"] == rid
