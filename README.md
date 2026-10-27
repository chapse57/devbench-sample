# run-id-same-second-collision — sample task (Harbor format)

> A task that measures whether an AI coding agent, given instructions in Korean, can fix a production bug where **"two runs in the same second silently overwrite each other's data."**
> Author: Jinnu Kim · 2026-10-07 · 한국어: [README.ko.md](README.ko.md)

The agent's instructions (`instruction.md`), code comments and test failure messages are in Korean on purpose: the task was built for a Korean-language coding benchmark. This README explains everything in English.

## At a glance

| Item | Details |
|---|---|
| Category | Data integrity / race conditions / schema migration |
| Difficulty | Medium (see calibration below) |
| Environment | `python:3.12-slim`, standard library + SQLite, single container |
| Grading | 15 pytest tests → `/logs/verifier/reward.txt` (1/0) |
| Verification | Original code scores 0, reference solution scores 1 (passed in all 6 repeated runs), 7 workaround solutions and the original all score 0, checked on the real Docker image |

## Where the task comes from

It is based on a bug I actually fixed in my own project (x-metrics-pipeline, 2026-09). Run IDs were built from a **timestamp in seconds**, so two runs in the same second got the same ID.

The task adds three situations on top of that bug so it is not a one-line fix: retries, concurrent runs from a cron job on a backup server, and the clock going backwards after an NTP correction. All three are **settings made up for the task**.

## Folder layout

```
instruction.md          Instructions given to the agent (in Korean)
task.toml               Metadata, timeouts, resources (Harbor schema 1.3)
environment/Dockerfile  python:3.12-slim + the /app code (tests are not baked into the image)
environment/app/        metricsd with the bug (collect / runs / show / diff CLI)
solution/solve.sh       Reference solution
tests/test.sh           Grading entry point (writes reward.txt)
tests/test_outputs.py   The 15 pytest tests
```

## The three things a solution must satisfy (= the test groups)

1. **Uniqueness.** run_ids must never collide, both for back-to-back runs in the same second and for 12 processes running at once (repeated 5 times). The measurements of different runs must not get mixed either.
2. **Recording order.** "Latest" is decided by the order runs were recorded, not by the clock. Checked with 3 runs at the same timestamp (repeated 4 times) and with the clock moving 4 seconds backwards.
3. **Existing database preserved.** A database in the old schema must keep working with no data loss. It contains **the oldest run, restored later from a backup**, so insertion order differs from run_id order. This includes several processes opening it for the first time at once (a migration race).

On top of that, a constraint test blocks workarounds that fake uniqueness by changing the clock: `started_at` must be the clock value as-is, and the run_id must start with the start time.

## Workaround check (results from actual runs)

I wrote 7 solutions that look right but are wrong, and graded them together with the original. All of them score 0.

| Attempt | Result | Caught by |
|---|---|---|
| Original code as-is | 0 (13 failures) | Almost all tests |
| Sleep 1 second before collect | 0 | No effect with a fake clock → all uniqueness tests |
| Append a random suffix to run_id only | 0 | Recording order, clock going backwards, existing DB |
| Random suffix + sort by start time (rowid on ties) | 0 | Clock going backwards, existing DB |
| "Count runs in the same second and add 1" (no lock) | 0 | Concurrent runs (race), clock going backwards, existing DB |
| On collision, push the timestamp forward 1 second | 0 | Constraint (start-time prefix), concurrent runs |
| Recreate the table when the old schema is found | 0 | Both existing-DB preservation tests |
| Random suffix + sort by implicit rowid | 0 | Both existing-DB preservation tests (backfill makes insertion order ≠ run_id order) |
| **Reference solution** | **1** (15/15 in all 6 repeated runs) | — |

The last rowid solution passed the first version of the tests. So I added a backfill case to actually check a requirement that was already in the instructions ("existing runs stay in run_id order"). The instructions did not change; this closed **a gap where the tests were missing a requirement the instructions already stated**.

## Difficulty calibration — results from real AI models

Each model got only the instructions (tests hidden), solved the task twice, and was graded with the same grader.

| Model | Result | Why it failed |
|---|---|---|
| Claude Haiku 4.5 | **0 / 2** | Run 1: used "count same-second runs + 1", so concurrent runs crashed on a UNIQUE conflict. The migration also copied rows in insertion order instead of run_id order |
| | | Run 2: decided order by the implicit rowid → wrong order for the backfilled existing run |
| Claude Sonnet 5.5 | **2 / 2** | Both runs issued sequence numbers inside a write lock (BEGIN IMMEDIATE) and migrated existing runs in run_id order |

**Reading:** The stronger model passing 2/2 from the instructions alone is the evidence that the instructions are not ambiguous. The weaker model failing at exactly the three points the tests target (race conditions, meaning of order, data preservation) is the evidence that the tests tell those properties apart.

For a strong model, though, this is "easy to medium." Variations that could raise the difficulty:

- **Retry idempotency.** If the first collect crashes after committing, the retry creates another run with the same content. diff then reports "no change", which is the same symptom as the original incident. Sonnet flagged this itself as a "remaining risk" in its first run, so it is a good basis for a next-level task.
- Atomicity when a process is killed mid-transaction (SIGKILL)
- A consistent diff when WAL mode and reader processes are mixed

## Docker results (2026-10-07, Windows + Docker Desktop)

Output from running the commands in "How to run" below as-is. Full logs are in [`docs/run-original.log`](docs/run-original.log) and [`docs/run-oracle.log`](docs/run-oracle.log).

**Original code → reward 0**

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

**With the reference solution → reward 1**

```
...............                                                          [100%]
15 passed in 11.52s
1
```

## How to run

I built the real image and checked it with the commands below on Windows + Docker Desktop (2026-10-07): the original gives 13 failed → reward 0, and with the reference solution 15 passed → reward 1. The 7 workaround solutions and the model calibration were run in an environment that reproduces the container's paths (`/app`, `/tests`, `/logs/verifier`).

```bash
# Run from the task folder
docker build -t kdb-run-id environment

# Original → should print 0
docker run --rm -v "$PWD/tests:/tests" kdb-run-id bash -c "bash /tests/test.sh; cat /logs/verifier/reward.txt"

# With the reference solution → should print 1
docker run --rm -v "$PWD/tests:/tests" -v "$PWD/solution:/solution" kdb-run-id \
  bash -c "bash /solution/solve.sh && bash /tests/test.sh; cat /logs/verifier/reward.txt"
```

In Windows Git Bash, prefix the commands with `MSYS_NO_PATHCONV=1` so the paths are not rewritten, or run them from PowerShell (`${PWD}`).

## Notes

- I built this with heavy use of an AI tool (Claude). The source is the same-second run_id collision that actually happened in my project (x-metrics-pipeline); the task design, implementation, workaround checks and model calibration were done together with Claude. I ran the image build and the grading on Windows + Docker Desktop myself.
- `tests/test.sh` does not use `set -e`. If you branch on `$?` under `set -e`, as in the Harbor docs example, the script exits the moment pytest fails and the reward file is never written.
- Grading looks only at CLI output. The tests touch the database directly only to recreate the "old-schema DB". So a solution passes with different table names or columns as long as it meets the requirements. In fact, Sonnet's second run solved it with a separate `run_order` table and still passed.
