from . import db


def list_runs() -> list[dict]:
    conn = db.connect()
    rows = conn.execute(
        """
        SELECT r.run_id, r.started_at, r.source, COUNT(m.account)
        FROM runs r LEFT JOIN measurements m ON m.run_id = r.run_id
        GROUP BY r.run_id
        ORDER BY r.run_id
        """
    ).fetchall()
    conn.close()
    return [
        {"run_id": run_id, "started_at": started_at, "source": source, "count": count}
        for run_id, started_at, source, count in rows
    ]


def show(run_id: str) -> dict[str, int]:
    conn = db.connect()
    rows = conn.execute(
        "SELECT account, followers FROM measurements WHERE run_id = ? ORDER BY account",
        (run_id,),
    ).fetchall()
    conn.close()
    return dict(rows)


def diff() -> dict:
    """가장 최근 실행(head)과 그 직전 실행(base)을 비교한다."""
    runs = list_runs()
    if len(runs) < 2:
        return {"base": None, "head": runs[-1]["run_id"] if runs else None, "changes": []}
    base_id, head_id = runs[-2]["run_id"], runs[-1]["run_id"]
    base, head = show(base_id), show(head_id)
    changes = []
    for account in sorted(set(base) | set(head)):
        before, after = base.get(account), head.get(account)
        if before != after:
            changes.append({"account": account, "before": before, "after": after})
    return {"base": base_id, "head": head_id, "changes": changes}
