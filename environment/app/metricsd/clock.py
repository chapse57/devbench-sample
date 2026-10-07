import os
from datetime import datetime, timezone


def now() -> datetime:
    """현재 시각(초 단위). 테스트·재현용으로 METRICSD_FAKE_NOW(ISO 8601)를 주면 그 값을 쓴다."""
    fake = os.environ.get("METRICSD_FAKE_NOW")
    if fake:
        return datetime.fromisoformat(fake)
    return datetime.now(timezone.utc).replace(microsecond=0)
