# Architecture: repairgate

Reviewed on 2026-11-08 against the local working tree (`.`). `graphify-out/graph.json` provides the local AST symbol graph.

## 1. System Context & Data Flow

Holdout-verified pure-function Python repair evaluator (CLI + FastAPI + React lab) that enforces narrow AST/path policies, executes visible and external holdout `unittest` suites in isolated child processes,withholds holdout logs from proposers to prevent overfitting, and verifies cryptographic tree integrity.

```mermaid
graph TD
Dev["Developer / Reviewer"] --> CLI["repairgate.cli"]
    Dev --> UI["React Lab UI (frontend/src/main.jsx)"]
    UI --> API["Fixed-Case FastAPI Routes (repairgate/api.py)"]
    API --> Lab["Bundled Regression Lab (repairgate/lab.py)"]
    CLI --> Eval["engine.evaluate()"]
    Lab --> Eval
    Eval --> Policy["Path & Pure-Function AST Policy (validate_changes / validate_source)"]
    Policy --> Subproc["Isolated unittest -I -B Subprocesses (Visible + Holdout)"]
    Subproc --> Audit["SHA-256 Protected-Tests & Full-Tree Integrity Gate"]
    Ollama["Optional Localhost Ollama Proposer"] -. visible feedback only .-> Eval
```

## 2. Execution & Pipeline Sequence

```mermaid
sequenceDiagram
participant E as engine.evaluate
    participant P as ProposalSource
    participant WS as Temp Copy
    participant U as unittest Subprocess
    E->>WS: Snapshot repo & external holdout + run baseline suites
    loop Up to max_attempts (1..5)
      E->>P: Request candidate with visible test feedback only
      P-->>E: Replacement dict {"src/..py": "..."}
      E->>E: validate_changes() + AST pure-function allowlist
      E->>WS: Copy repo + holdout into attempt-N workspace & apply diff
      E->>U: Run visible tests ("tests") & holdout tests ("_repairgate_holdout")
      E->>WS: Re-hash workspace & verify protected tests byte-for-byte unchanged
      alt Visible + holdout + integrity all pass
        E-->>E: Mark status="accepted" and stop loop
      else Overfit or failure
        E-->>E: Append attempt report & pass visible log only to next attempt
      end
    end
```

## 3. Module Breakdown

| Path | Responsibility |
| :--- | :--- |
| `repairgate/engine.py` | Bounded tree snapshotting (`file_digest`), pure-function AST allowlist, path containment guards, isolated `unittest` runner with process-tree kill & log truncation, holdout-shielded attempt loop, and optional localhost Ollama proposer. |
| `repairgate/demo.py` | Recorded `bill-splitter` proposals demonstrating test-tampering rejection, holdout overfitting rejection, and general repair acceptance. |
| `repairgate/lab.py` | Three-case regression lab (`bill-splitter`, `interval-merge`, `sample-window`) and summary runner. |
| `repairgate/api.py` | Localhost FastAPI endpoints (`/api/health`, `/api/cases`, `/api/demo`) guarded by a non-blocking process lock. |
| `repairgate/cli.py` | CLI commands (`demo`, `lab`, `evaluate`) exiting non-zero on rejected proposals. |
| `tests/` | 6 pytest suites (`test_engine.py`, `test_snapshot_and_policy.py`, `test_evaluate_lifecycle.py`, `test_lab.py`, `test_cli_and_api.py`, `test_provider.py`). |

## 4. State Management & Failure Handling

Candidate files are written exclusively inside `TemporaryDirectory(prefix='repairgate-')` per-attempt subdirectories; original `repo` and `holdout` trees are re-hashed at completion (`original_unchanged`). Proposers receive `attempt['visible']['log']` and high-level rejection reasons only—never holdout assertions or stack traces.

## 5. Verification Commands

```powershell
Set-Location 'python' -m pytest -q
```

## 6. Integration Boundaries

AST allowlist and temporary workspace copies enforce pure-function benchmark rules on trusted local code; they are not an OS container sandbox for untrusted code.

## Source crosscheck, 2026-11-08

The API currently uses one process-local lock for all demo cases. Candidate verification still checks the freshly copied tree against the expected baseline before applying changes. No integrity shortcut is implemented by this documentation review.
