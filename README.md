# run-id-same-second-collision — 샘플 과제 (Harbor 형식)

> 한국어 지시를 받은 AI 코딩 에이전트가 **"같은 초에 두 번 실행되면 데이터가 조용히 덮어써지는"** 운영 장애를 고칠 수 있는지 측정하는 과제입니다.
> 작성: 진우 (에테르) · 2026-10-07

## 한눈에 보기

| 항목 | 내용 |
|---|---|
| 범주 | 데이터 정합성 / 경쟁 상태 / 스키마 마이그레이션 |
| 난이도 | 중간 (보정 결과 아래 참고) |
| 환경 | `python:3.12-slim`, 표준 라이브러리 + SQLite, 단일 컨테이너 |
| 채점 | pytest 15개 → `/logs/verifier/reward.txt` (1/0) |
| 검증 | 원본 0점, 참조 풀이 1점(6회 반복 모두 통과), 우회 시도 8종 모두 0점, Docker 이미지 실측 확인 |

## 이 과제가 어디서 왔나

제 개인 프로젝트(x-metrics-pipeline, 2026-09)에서 실제로 고친 버그가 바탕입니다. 실행 ID를 **초 단위 시각**으로 만들었기 때문에, 같은 초에 실행이 두 번 생기면 ID가 겹쳤습니다.

과제에서는 이 버그에 세 가지 상황을 덧붙여 "한 줄 고치면 끝나는 문제"가 아니게 만들었습니다. 재시도, 백업 서버 cron에 의한 동시 실행, NTP 시계 역행이며, 모두 **과제용 설정**입니다.

## 폴더 구조

```
instruction.md          에이전트에게 주는 한국어 지시문
task.toml               메타데이터·타임아웃·자원 (Harbor schema 1.3)
environment/Dockerfile  python:3.12-slim + /app 코드 (테스트는 이미지에 넣지 않음)
environment/app/        버그가 있는 metricsd (collect / runs / show / diff CLI)
solution/solve.sh       참조 풀이
tests/test.sh           채점 진입점 (reward.txt 작성)
tests/test_outputs.py   pytest 채점기 15개
```

## 풀이가 만족해야 하는 세 가지 (= 테스트 묶음)

1. **고유성.** 같은 초 연속 실행과 12개 프로세스 동시 실행(5회 반복)에서 run_id가 겹치지 않아야 합니다. 각 실행의 측정값이 섞이지도 않아야 합니다.
2. **기록 순서.** "최신"은 시각이 아니라 기록된 순서로 정합니다. 같은 시각으로 3회 실행(4회 반복)한 경우와, 시계가 4초 뒤로 간 경우를 확인합니다.
3. **기존 DB 보존.** 구 스키마 DB를 데이터 손실 없이 이어 써야 합니다. 이 DB에는 **백업에서 나중에 복원된 가장 오래된 실행**이 들어 있어서, 삽입 순서와 run_id 순서가 다릅니다. 여러 프로세스가 동시에 처음 여는 경우(마이그레이션 경합)도 포함합니다.

추가로, 시계를 조작해서 고유성을 만드는 꼼수를 막는 제약 테스트가 있습니다. `started_at`은 시계 값 그대로여야 하고, run_id는 시작 시각으로 시작해야 합니다.

## 우회 차단 검증 (실제로 돌린 결과)

정답처럼 보이지만 틀린 풀이 8가지를 직접 만들어 채점했습니다. 전부 0점입니다.

| 우회 시도 | 결과 | 잡아낸 테스트 |
|---|---|---|
| 원본 그대로 | 0점 (13개 실패) | 거의 전부 |
| collect 전에 1초 쉬기 | 0점 | 가짜 시계라 효과 없음 → 고유성 전부 |
| run_id에 랜덤 꼬리표만 붙이기 | 0점 | 기록 순서, 시계 역행, 기존 DB |
| 랜덤 꼬리표 + 시작 시각(동률이면 rowid)으로 정렬 | 0점 | 시계 역행, 기존 DB |
| "같은 초 실행 수 세서 +1" (잠금 없음) | 0점 | 동시 실행(경쟁 상태), 시계 역행, 기존 DB |
| 겹치면 시각을 1초씩 밀기 | 0점 | 제약(시작 시각 접두어), 동시 실행 |
| 구 스키마를 만나면 테이블을 새로 만들기 | 0점 | 기존 DB 보존 2개 |
| 랜덤 꼬리표 + 암묵적 rowid로 정렬 | 0점 | 기존 DB 보존 2개 (backfill로 삽입 순서 ≠ run_id 순서) |
| **참조 풀이** | **1점** (6회 반복 모두 15/15) | — |

마지막 rowid 풀이는 처음 테스트에서는 통과했습니다. 그래서 지시문에 이미 있는 요구("기존 실행끼리는 run_id 순서")를 실제로 검사하도록 backfill 케이스를 추가했습니다. 지시문을 바꾼 게 아니라, **지시문에 적힌 요구를 테스트가 빠뜨리고 있던 구멍**을 메운 것입니다.

## 난이도 보정 — AI 모델에게 실제로 풀게 한 결과

지시문만 주고(테스트 비공개) 모델별로 2회씩 풀게 한 뒤 같은 채점기로 채점했습니다.

| 모델 | 결과 | 실패 원인 |
|---|---|---|
| Claude Haiku 4.5 | **0 / 2** | 1회차: "같은 초 개수 +1" 방식이라 동시 실행에서 UNIQUE 충돌로 crash. 마이그레이션도 run_id 순서가 아닌 삽입 순서로 복사 |
| | | 2회차: 암묵적 rowid로 순서를 판단 → backfill된 기존 실행 순서가 틀림 |
| Claude Sonnet 5.5 | **2 / 2** | 둘 다 쓰기 잠금(BEGIN IMMEDIATE) 안에서 순번을 발급하고, 기존 실행을 run_id 순으로 마이그레이션 |

**해석:** 지시문이 모호하지 않다는 근거는 상위 모델이 지시문만 보고 2/2 통과했다는 점입니다. 테스트가 성질(경쟁 상태, 순서 의미, 데이터 보존)을 구분해 낸다는 근거는 하위 모델이 정확히 그 세 지점에서 떨어졌다는 점입니다.

다만 상위 모델 기준으로는 "쉬움~중간"입니다. 난이도를 올리려면 아래 변형을 검토할 수 있습니다.

- **재시도 멱등성.** 첫 collect가 커밋 후 비정상 종료하면 재시도가 같은 내용의 실행을 하나 더 만듭니다. 그러면 diff가 "변화 없음"을 내는데, 이건 원래 장애와 같은 증상입니다. Sonnet 1회차가 스스로 "남은 위험"으로 지적한 지점이라, 다음 단계 과제 소재로 적합합니다.
- 프로세스가 트랜잭션 중간에 죽는 경우(SIGKILL)의 원자성 검사
- WAL 모드와 읽기 프로세스가 섞인 경우의 일관된 diff

## Docker 실측 결과 (2026-10-07, Windows + Docker Desktop)

아래 실행 방법의 명령을 그대로 돌린 출력입니다. 전체 로그는 [`docs/run-original.log`](docs/run-original.log), [`docs/run-oracle.log`](docs/run-oracle.log)에 있습니다.

**원본 코드 → reward 0**

```
FAILED ..test_same_second_runs_get_distinct_ids_and_keep_their_own_data
FAILED ..test_concurrent_processes_never_collide_or_mix[0]
FAILED ..test_concurrent_processes_never_collide_or_mix[1]
FAILED ..test_concurrent_processes_never_collide_or_mix[2]
FAILED ..test_concurrent_processes_never_collide_or_mix[3]
FAILED ..test_concurrent_processes_never_collide_or_mix[4]
FAILED ..test_diff_uses_recording_order_when_clock_is_identical[0]
FAILED ..test_diff_uses_recording_order_when_clock_is_identical[1]
FAILED ..test_diff_uses_recording_order_when_clock_is_identical[2]
FAILED ..test_diff_uses_recording_order_when_clock_is_identical[3]
FAILED ..test_clock_going_backwards_does_not_change_what_latest_means
FAILED ..test_legacy_db_is_preserved_and_new_runs_come_after_it
FAILED ..test_legacy_db_survives_concurrent_first_open
13 failed, 2 passed in 5.06s
0
```

**참조 풀이 적용 → reward 1**

```
...............                                                          [100%]
15 passed in 11.52s
1
```

## 실행 방법

Windows + Docker Desktop에서 아래 명령으로 실제 이미지를 빌드해 확인했습니다 (2026-10-07). 원본은 13 failed → reward 0, 참조 풀이 적용 후 15 passed → reward 1. 우회 8종과 모델 보정은 컨테이너와 같은 경로(`/app`, `/tests`, `/logs/verifier`)를 재현한 환경에서 돌렸습니다.

```bash
# 과제 폴더에서 실행
docker build -t kdb-run-id environment

# 원본 → 0이 나와야 함
docker run --rm -v "$PWD/tests:/tests" kdb-run-id bash -c "bash /tests/test.sh; cat /logs/verifier/reward.txt"

# 참조 풀이 적용 → 1이 나와야 함
docker run --rm -v "$PWD/tests:/tests" -v "$PWD/solution:/solution" kdb-run-id \
  bash -c "bash /solution/solve.sh && bash /tests/test.sh; cat /logs/verifier/reward.txt"
```

Windows Git Bash에서는 경로가 바뀌지 않도록 명령 앞에 `MSYS_NO_PATHCONV=1` 을 붙이거나 PowerShell(`${PWD}`)에서 실행하세요.

## 작성 메모

- AI 도구(Claude)를 활용해 만들었습니다. 버그 소재 선정과 Docker 실측은 직접 했고, 구현·우회 검증·모델 보정은 Claude와 함께 진행했습니다.

- `tests/test.sh`는 `set -e`를 쓰지 않습니다. Harbor 문서 예시처럼 `set -e` 상태에서 `$?`로 분기하면, pytest가 실패하는 순간 스크립트가 끝나 reward 파일이 아예 쓰이지 않습니다.
- 채점은 CLI 출력만 봅니다. DB에 직접 손대는 건 "구 스키마 DB"를 재현할 때뿐입니다. 그래서 테이블 이름이나 컬럼 구조가 달라도 요구사항을 지키면 통과합니다. 실제로 Sonnet 2회차는 별도 `run_order` 테이블로 풀었는데도 통과했습니다.
