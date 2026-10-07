#!/bin/bash
# 채점 진입점. 결과는 /logs/verifier/reward.txt (1 = 통과, 0 = 실패)에 쓴다.
# set -e 를 쓰지 않는다: pytest가 실패하는 순간 스크립트가 끝나 reward 파일이 아예 안 써지는 것을 막기 위해.
set -uo pipefail

mkdir -p /logs/verifier
pip install --quiet --no-cache-dir pytest==8.3.4 >/dev/null 2>&1

cd /app
if python -m pytest -q -p no:cacheprovider /tests/test_outputs.py; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
