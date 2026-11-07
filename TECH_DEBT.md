# Technical Debt & Performance Ledger: repairgate

Reviewed on 2026-11-07 against the current working tree on disk. All line numbers are 1-based and verified directly against the current production files. Every diff below is a non-destructive engineering proposal, not an applied production edit.

## TD-01 — Skip spawning holdout `unittest` subprocess when visible tests already failed

- **Location**: `repairgate/engine.py:534-535`
- **Analysis**: `_verify_candidate_attempt` unconditionally spawns a second Python interpreter subprocess for `_repairgate_holdout` even when `attempt['visible']['passed']` is `False`, doubling subprocess startup and discovery latency (or timeout wait) on visibly broken candidates.

```diff
--- a/repairgate/engine.py
+++ b/repairgate/engine.py
@@ -532,7 +532,19 @@
     diff_text, expected = _apply_candidate_changes(repo, working, candidate, baseline_expected)
     attempt["diff"] = diff_text
     attempt["visible"] = run_tests(working, "tests", timeout)
-    attempt["holdout"] = run_tests(working, "_repairgate_holdout", timeout)
+    if attempt["visible"]["passed"]:
+        attempt["holdout"] = run_tests(working, "_repairgate_holdout", timeout)
+    else:
+        attempt["holdout"] = {
+            "passed": False,
+            "tests": 0,
+            "exit_code": None,
+            "timed_out": False,
+            "output_bytes": 0,
+            "output_truncated": False,
+            "log": "Skipped holdout suite because visible tests failed.",
+            "duration_ms": 0,
+        }
     _audit_attempt_outcome(attempt, working, protected, expected)
     return attempt
```

- **Validation**: Verify UI/test consumers tolerate `exit_code=None, tests=0` on skipped holdout runs and run `.\.venv\Scripts\python.exe -m pytest -q`.

## TD-02 — Copy pre-verified baseline directory instead of re-copying two trees and re-hashing `start` per attempt

- **Location**: `repairgate/engine.py:523-527`
- **Analysis**: `_verify_candidate_attempt` walks and SHA-256 hashes the newly copied `working` directory (`start = snapshot(working)`) and filters `starting_source` on every attempt, then hashes `working` again in `_audit_attempt_outcome`. Cloning from the already-verified clean baseline copy (or checking source hashes only when needed) avoids redundant full-tree I/O.

```diff
--- a/repairgate/engine.py
+++ b/repairgate/engine.py
@@ -521,10 +521,9 @@
 
     attempt["policy_passed"] = True
     _copy_verification_workspace(repo, holdout, working)
-    start = snapshot(working)
-    starting_source = {k: v for k, v in start.items() if not k.startswith("_repairgate_holdout/")}
-    if starting_source != before or start != baseline_expected:
+    if snapshot(repo) != before or snapshot(holdout) != holdout_before:
         raise ValueError("Source or tests changed before candidate verification.")
+    starting_source = before
 
     attempt["starting_source_digest"] = tree_digest(starting_source)
     attempt["protected_tests_before_digest"] = tree_digest(protected)
```

- **Validation**: Pass `holdout_before` into `_verify_candidate_attempt` (or clone a clean read-only staging snapshot) and run `.\.venv\Scripts\python.exe -m pytest -q`.

## TD-03 — Use per-case locks instead of a single global `threading.Lock` in `/api/demo`

- **Location**: `repairgate/api.py:19`
- **Analysis**: A single process-wide `lock` rejects concurrent `/api/demo` requests for distinct bundled cases (`bill-splitter` vs `interval-merge`) with HTTP 429 even though `evaluate()` runs each case inside its own `TemporaryDirectory`.

```diff
--- a/repairgate/api.py
+++ b/repairgate/api.py
@@ -16,7 +16,7 @@
 CaseId = Literal["bill-splitter", "interval-merge", "sample-window"]
 
 app = FastAPI(title="RepairGate", docs_url=None, redoc_url=None)
-lock = threading.Lock()
+locks: dict[str, threading.Lock] = {case_id: threading.Lock() for case_id in CASES}
 
 
 @app.get("/api/health")
```

- **Validation**: Acquire `locks[case_id]` in `run_demo` while retaining global `lock` alias or updating `test_cli_and_api.py` lock-contention tests.
