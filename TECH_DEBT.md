# repairgate: performance and technical debt

Source crosscheck: 2026-11-08 WIB. Locations refer to the current production files. The unified diffs below are proposals only. Production code has not been changed. No elapsed-time improvement is claimed without measurement.

## 1. Skip a second test interpreter after visible verification fails

Location: repairgate/engine.py:534-536.

Every candidate starts both visible and holdout subprocesses. A failed visible suite already prevents acceptance. Skipping the holdout can reduce wasted process startup or timeout latency while preserving the integrity audit and rejected status. The tradeoff is losing holdout diagnostics for visibly broken candidates.

```diff
--- a/repairgate/engine.py
+++ b/repairgate/engine.py
@@ -532,7 +532,14 @@
     diff_text, expected = _apply_candidate_changes(repo, working, candidate, baseline_expected)
     attempt["diff"] = diff_text
     attempt["visible"] = run_tests(working, "tests", timeout)
-    attempt["holdout"] = run_tests(working, "_repairgate_holdout", timeout)
+    if attempt["visible"]["passed"]:
+        attempt["holdout"] = run_tests(working, "_repairgate_holdout", timeout)
+    else:
+        attempt["holdout"] = {
+            "passed": False, "tests": 0, "exit_code": None,
+            "timed_out": False, "output_bytes": 0, "output_truncated": False,
+            "log": "Skipped because visible verification failed.", "duration_ms": 0,
+        }
     _audit_attempt_outcome(attempt, working, protected, expected)
     return attempt
```

Validation: Count run_tests calls for visible failure/success and confirm rejected attempts still run _audit_attempt_outcome. Check report/UI handling of a skipped holdout before adoption.

## 2. Allow independent demo cases to acquire separate verification locks

Location: repairgate/api.py:19, repairgate/api.py:32-40.

The single process-wide lock rejects simultaneous requests even for different bundled cases. Each run uses its own temporary verification workspace. A lock per known case permits bounded parallel work across cases. This intentionally raises peak CPU/process usage and still does not coordinate multiple server processes.

```diff
--- a/repairgate/api.py
+++ b/repairgate/api.py
@@ -16,7 +16,7 @@
 CaseId = Literal["bill-splitter", "interval-merge", "sample-window"]
 
 app = FastAPI(title="RepairGate", docs_url=None, redoc_url=None)
-lock = threading.Lock()
+locks = {case_id: threading.Lock() for case_id in CASES}
 
 
 @app.get("/api/health")
@@ -31,13 +31,14 @@
 
 @app.post("/api/demo")
 def run_demo(case_id: CaseId = "bill-splitter") -> EvaluationReport:
-    if not lock.acquire(blocking=False):
+    case_lock = locks[case_id]
+    if not case_lock.acquire(blocking=False):
         logger.warning("Rejected concurrent /api/demo request for case '%s'", case_id)
         raise HTTPException(429, "A verification is already running.")
     try:
         return run_case(case_id)
     finally:
-        lock.release()
+        case_lock.release()
 
 
 def mount_frontend_if_present(target_app: FastAPI, dist_dir: Path) -> bool:
```

Validation: Test same-case contention, different-case concurrency and release on exceptions. Update callers/tests that import the old lock symbol. Profile resource limits before enabling more parallel verification.

## Crosscheck decisions

The previous snapshot optimization referenced undefined holdout_before and weakened the copied-workspace integrity gate. It has been withdrawn. Keep start != baseline_expected and all protected-source audits intact.
