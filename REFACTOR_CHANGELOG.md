# Refactor & QA Verification Changelog (`repairgate`)

## 1. Branch & Git Safety Summary

| Property | Value |
| --- | --- |
| Original Branch | `main` (`a895d54b748cf51a2237c5091b05c53b1e7a6f33`) |
| Pre-Refactor Backup Stash | `stash@{0}: On main: pre-refactor-backup-snapshot` (preserves pre-existing untracked notes/artifacts untouched) |
| Refactoring Branch | `codex/auto-refactor-and-tests` |
| Backward Compatibility | 100% preserved across `repairgate` CLI entry points, FastAPI routes, public functions, and all 28 original tests |

---

## 2. Modified & Added Files

| File | Status | Summary of Changes |
| --- | --- | --- |
| `repairgate/__init__.py` | Modified | Added `from __future__ import annotations`, explicit `__version__ = "0.2.0"`, and `__all__`. |
| `repairgate/engine.py` | Modified | Added strict `TypedDict` contracts (`TestRunResult`, `BaselineResult`, `AttemptReport`, `EvaluationReport`), `TypeGuard` validators, pre-hash repository file/byte cap checks, streaming `hashlib.file_digest` SHA-256 hashing, directory-pruned tree scanning, pre-compiled regex/frozenset constants, POSIX `killpg` / Windows `taskkill` race-safe process cleanup, structured Ollama payload parsing, and decomposed >50-line functions into <=45-line single-responsibility helpers. |
| `repairgate/cli.py` | Modified | Decomposed `main()` into `build_parser()`, `_load_proposals_file()`, `_run_selected_command()`, and `_write_report()`; added optional `argv` parameter, explicit UTF-8 file decoding, parent-dir creation on output reports, full type annotations, and structured `ValueError`/`OSError` diagnostics. |
| `repairgate/api.py` | Modified | Added full return type annotations, structured `logging.getLogger(__name__)` warning on lock contention, and extracted `mount_frontend_if_present()` helper for testable static bundle mounting. |
| `repairgate/demo.py` | Modified | Added `from __future__ import annotations` and `EvaluationReport` return type contract. |
| `repairgate/lab.py` | Modified | Added `CaseMetadata`, `LabSummary`, and `LabReport` `TypedDict` contracts plus explicit `encoding="utf-8"` on all fixture source reads. |
| `tests/test_engine.py` | Modified | Cleaned unused imports and normalized import ordering for Ruff compliance while preserving all 19 original tests unchanged. |
| `tests/test_provider.py` | Modified | Cleaned unused `pytest` import and normalized import ordering while preserving both original provider tests unchanged. |
| `tests/test_snapshot_and_policy.py` | Added | Unit tests for `digest()`, `tree_digest()`, streaming `snapshot()` (empty, binary, >256 KB multi-chunk files, ignored `.git`/`.venv`/`__pycache__`, symlink rejection), `validate_changes()`, and `validate_source()` AST policy rules. |
| `tests/test_evaluate_lifecycle.py` | Added | Comprehensive unit tests for `evaluate()` and `run_tests()`: passing baseline short-circuit, callable/sequence proposers, layout & holdout path validation, pre-hash 5 MB / 500-file cap checks, baseline mutation rejection, mid-run tampering detection, boolean/float/NaN/Inf/string execution limit rejection, mocked Windows & POSIX subprocess timeouts, `ProcessLookupError` race resilience, and >1 MB output rejection. |
| `tests/test_cli_and_api.py` | Added | Offline unit tests for `cli.main()` (`demo`, `lab` exit codes `0`/`1`, `repair` with `--proposals` and mocked `--ollama`, malformed proposal files), `lab.run_case()` error handling, `api` 429 lock contention/release, `mount_frontend_if_present()`, and `ollama_proposer()` error/size bounds. |
| `.gitignore` | Modified | Added `.coverage` so local coverage runs keep the git working tree clean. |

---

## 3. Architectural Improvements & Concrete Bugs Fixed

### Pillar 1: Type Safety & Contracts
- Added `from __future__ import annotations` and complete static type annotations (`TypedDict`, `NotRequired`, `TypeGuard`, `Callable`, `Mapping`, `Sequence`, `Literal`, `Final`) across every module in `repairgate/`.
- **Bug Fixed — Boolean & Non-Integer Execution Limits:** Previously, `if not 1 <= max_attempts <= 5 or not 1 <= timeout <= 60:` accepted `True` (since `isinstance(True, int)` and `True == 1` in Python), allowed fractional floats like `max_attempts=2.5` to execute baseline subprocesses before crashing at `range(max_attempts)` with `TypeError`, and raised raw `TypeError` on strings/`None`. `_is_strict_int_in_range()` now rejects `bool`, `float` (`NaN`/`Inf`/fractional), `str`, `None`, and out-of-range integers upfront with `ValueError` before any verification starts—in both `evaluate()` and direct `run_tests()` calls.
- **Bug Fixed — Non-Boolean `trust_local_code` Truthiness:** Tightened `if not trust_local_code:` to `if trust_local_code is not True:` so truthy non-booleans (`1`, `"true"`) cannot accidentally bypass the explicit trust gate.
- **Bug Fixed — Windows Locale Encoding:** Added explicit `encoding="utf-8"` to `cli.py` proposal loading and `lab.py` starting source reads, preventing `cp1252` decoding corruption on Windows.

### Pillar 2: Modularity & Clean Architecture
- Eliminated all >50-line functions (maximum function span across the entire `repairgate` package is now **45 lines**):
  - `repairgate/engine.py`: Decomposed the 99-line `evaluate()` and `run_tests()` into focused helpers: `_validate_eval_inputs()`, `_prepare_initial_snapshots()`, `_build_initial_report()`, `_run_baseline_verification()`, `_run_proposal_attempts()`, `_verify_candidate_attempt()`, `_apply_candidate_changes()`, `_audit_attempt_outcome()`, `_execute_unittest_process()`, `_terminate_process_tree()`, and `_read_bounded_log()`.
  - `repairgate/cli.py`: Decomposed `main()` into `build_parser()`, `_load_proposals_file()`, `_run_selected_command()`, and `_write_report()`.
  - `repairgate/api.py`: Extracted `mount_frontend_if_present()` for clean, isolated testing of frontend asset mounting.

### Pillar 3: Performance & Concurrency
- **Bug Fixed — Unbounded Memory Read Before 5 MB Cap Check:** Previously, `evaluate()` called `snapshot(repo)` (allocating every file completely via `path.read_bytes()`) and parsed `src/*.py` ASTs *before* checking the 500-file / 5 MB repository cap. `_collect_repo_entries()` now enforces file count and `stat().st_size` cumulative byte limits *before* opening any file, and `_snapshot_bounded()` streams SHA-256 digests in bounded chunks via `with file_path.open("rb") as handle: hashlib.file_digest(handle, "sha256").hexdigest()`.
- **Directory Pruning in `snapshot()`:** Prunes `.git`, `.venv`, and `__pycache__` directories during traversal (`IGNORED_PARTS` `frozenset`) instead of walking and sorting thousands of ignored files via `root.rglob("*")`.
- **Pre-Compiled Constants:** Hoisted `_RAN_TESTS_RE = re.compile(r"Ran (\d+) tests?")`, `IGNORED_PARTS`, `ALLOWED_ENV_KEYS`, `ALLOWED_CALLS`, and `FORBIDDEN_AST_NODES` to module-level `Final` constants, eliminating repeated per-call regex compilation and set/list reconstruction.
- **Deterministic Process & File Handle Cleanup:** Wrapped subprocess execution in `try ... finally` ensuring lingering child processes are terminated and reaped (`proc.wait()`) before temporary output handles close.

### Pillar 4: Error Resilience
- **Bug Fixed — Cross-Platform POSIX Signal & `killpg` Race Condition:** Replaced inner `signal.SIGKILL` / unguarded `os.killpg` with safe `getattr` lookup and `try ... except OSError` handling so POSIX process-group cleanup never crashes with `ProcessLookupError` if a timed-out child exits concurrently (and passes static Mypy analysis on Windows).
- **Bug Fixed — Unhandled `KeyError`/`TypeError` on Malformed Ollama Responses:** Replaced `json.loads(json.loads(raw)['response'])['files']` with `_parse_ollama_files()`, raising descriptive `ValueError` exceptions on malformed JSON or missing `'response'`/`'files'` fields, and pre-checking file sizes in `_load_prompt_sources()`.
- Added structured `logging.getLogger(__name__)` diagnostics across `engine.py`, `cli.py`, and `api.py` for timeouts, policy rejections, lock contention, and I/O or endpoint failures.

---

## 4. Before vs. After Test Suite & Coverage Metrics

### Summary Metrics

| Metric | Before Refactor | After Refactor | Delta |
| --- | --- | --- | --- |
| Total Automated Tests | 28 | **108** | **+80 (+285.7%)** |
| Pass Rate | 28 / 28 (100%) | **108 / 108 (100%)** | 100% deterministic offline |
| Statement Coverage (`--cov=repairgate`) | 77% (215 / 280 stmts) | **99% (551 / 557 stmts)** | **+22%** |
| Branch Coverage (`--cov=repairgate --cov-branch`) | 75% | **98%** | **+23%** |
| Ruff Lint Errors (`ruff check repairgate tests`) | 13 errors (exit code `1`) | **0 errors (exit code `0`)** | **-13 errors** |
| Mypy Type Errors (`mypy repairgate --ignore-missing-imports`) | 18 errors (exit code `1`) | **0 errors (exit code `0`)** | **-18 errors** |

### Per-Module Statement Coverage Breakdown

| Module | Before Stmts | Before Miss | Before Cover | After Stmts | After Miss | After Cover |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `repairgate/__init__.py` | 0 | 0 | 100% | 3 | 0 | **100%** |
| `repairgate/api.py` | 24 | 1 | 96% | 34 | 0 | **100%** |
| `repairgate/cli.py` | 38 | 38 | 0% | 74 | 1 | **99%** |
| `repairgate/demo.py` | 6 | 0 | 100% | 7 | 0 | **100%** |
| `repairgate/engine.py` | 193 | 25 | 87% | 392 | 5 | **99%** |
| `repairgate/lab.py` | 19 | 1 | 95% | 47 | 0 | **100%** |
| **TOTAL** | **280** | **65** | **77%** | **557** | **6** | **99%** |

### Verification Commands & Exit Codes

```powershell
# 1. Full Test Suite + Statement Coverage -> Exit Code: 0 (108 passed, 99% coverage)
.\.venv\Scripts\python.exe -m pytest --cov=repairgate --cov-report=term-missing

# 2. Ruff Linter -> Exit Code: 0 (All checks passed!)
C:\Users\ardhy\.gemini\antigravity\brain\7b19fb5e-cc47-425f-9713-ee64d56c8136\scratch\qa-tools\qa-venv\Scripts\ruff.exe check repairgate tests

# 3. Mypy Static Type Checker -> Exit Code: 0 (Success: no issues found in 6 source files)
C:\Users\ardhy\.gemini\antigravity\brain\7b19fb5e-cc47-425f-9713-ee64d56c8136\scratch\qa-tools\qa-venv\Scripts\mypy.exe repairgate --ignore-missing-imports
```
