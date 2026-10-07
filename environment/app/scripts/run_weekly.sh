#!/bin/bash
# 매주 월요일 cron이 호출하는 수집 스크립트.
# 업스트림이 가끔 응답 직후 연결을 끊어서 collect가 실패한 것처럼 보이면 1번 즉시 재시도한다.
# (같은 시간대에 백업 서버의 cron도 같은 스크립트를 돌린다.)
set -u
INPUT="${1:-/app/data/samples/week.csv}"

for attempt in 1 2; do
  if python -m metricsd collect --input "$INPUT"; then
    break
  fi
  echo "collect 실패 (시도 $attempt) — 즉시 재시도" >&2
done

python -m metricsd diff
