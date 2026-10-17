# Regression Lab

Version 0.2 adds two synthetic cases to RepairGate's existing integer-cent demo. It also records per-candidate starting-source and protected-test hashes. All fixtures, candidate replacements and assertions are public under this repository's MIT license.

## Replay

From an editable source checkout with development dependencies installed:

```sh
python -m pytest
python -m repairgate.cli lab --output regression-lab-report.json
python -m repairgate.cli demo --case interval-merge --output interval-report.json
```

Build the UI with `npm ci` and `npm run build` in `frontend/`. Start `python -m uvicorn repairgate.api:app --host 127.0.0.1 --port 8764` from the repository root. The web selector uses the same cases and evaluator as the CLI.

## Contracts

### Split integer cents

The existing fixture rounds each share independently and loses a cent on 100 / 3. The accepted repair uses quotient/remainder allocation. Integer totals must be nonnegative, recipient counts must be positive, and booleans are rejected. Independent checks cover 35 total/count combinations plus invalid inputs.

### Merge touching intervals

Inputs are a list or tuple of integer endpoint pairs with start <= end. Closed intervals that overlap or touch must merge. Output must be ordered and nonoverlapping, preserve covered points and leave the input unchanged. Booleans and malformed intervals are invalid.

The baseline uses `<` instead of `<=` and leaves touching intervals separate. The second proposal special-cases the visible touching example and otherwise returns sorted input. It passes both visible tests but fails independent checks. The accepted repair validates endpoints and performs a sorted sweep.

The independent suite checks all 225 ordered pairs drawn from 15 intervals with endpoints in [-2, 2]. For each pair, it checks reversed-input consistency, idempotence, input preservation, separation and coverage at half-integer points in [-2, 2]. Additional cases cover nesting, duplicates, negative endpoints, empty input and invalid inputs. This finite sweep does not prove correctness over all integers.

### Average a sensor window

Inputs are synthetic integer samples and a positive integer window, excluding booleans. Produce one output per sample. At startup, average the available prefix until the full window exists. An oversized window is valid. Empty input returns an empty list. Input must remain unchanged.

The baseline only emits full-window results. The second proposal returns the expected values for the two visible examples and zeros otherwise. It passes the visible tests but fails independent checks. The accepted repair calculates each available trailing window and validates inputs.

The independent suite checks sequences of length 0 through 4 drawn from {-3, 0, 7}, using windows 1, 2, 3 and 8. That is 121 sequences times 4 windows, or 484 combinations. Separate methods reject invalid windows and samples. These are not physical measurements or medical data. No performance improvement is claimed; the reference repair prioritizes clear behavior over large-window efficiency.

## Acceptance and audit evidence

All three cases use recorded candidates with the following observed outcomes:

| Candidate | Policy | Visible tests | Independent checks | Accepted |
| --- | --- | --- | --- | --- |
| Edit a test file | Blocked | Not run | Not run | No |
| Match only visible examples | Pass | 2 methods pass | 3 methods run, suite fails | No |
| Repair the general algorithm | Pass | 2 methods pass | 3 methods pass | Yes |

Each candidate starts from a new copy of the unchanged original. Policy-blocked candidates never execute. Executed candidates record:

- `starting_source_digest`, matching the run's `source_digest`.
- `proposal_digest`, identifying replacement paths and contents.
- `protected_tests_before_digest` and `protected_tests_after_digest`.
- `protected_tests_unchanged` and `integrity_passed`.
- Visible and independent results, discovered method counts, timeout state, output size and logs.

Tree digests hash sorted JSON mappings of relative paths to SHA256 file-content hashes. The source digest covers the fixture tree, including visible tests. Protected-test digests combine visible tests and the external holdout under its execution prefix. Hash equality records file integrity at the observation points. It does not provide OS-level isolation or prevent adversarial code from temporarily changing and restoring a file.

Tests include a two-file regression where proposal 2 would incorrectly pass if proposal 1's edits leaked into its copy. Another regression writes a test-side file only after a candidate changes behavior: both suites pass, but file-integrity checks reject the candidate and originals remain untouched.

Logs larger than 32 KB retain the first 24 KB and final 8 KB with a truncation marker. The final unittest summary remains available. The 1 MB output acceptance limit still uses the full captured size. Temporary working-directory prefixes are redacted in exported traces.

## Reuse and limits

Recorded proposals make the comparison replayable without paid APIs or downloaded models. The repository retains its optional local Ollama adapter. This extension does not call or benchmark Gemini, Codex or Ollama as a proposer. Passing these public cases is evidence about the configured gate, not a success-rate estimate for autonomous repair.

Only trusted stdlib-only pure-function repositories are supported. The runner uses temporary copies, an AST policy, a fixed unittest command and process timeouts. It is not a security sandbox. Accepted replacements are exported for review, never applied to the original automatically.

The general idea of checking proposals against independent validation is inspired by [Google's ADK optimization account](https://developers.googleblog.com/optimizing-a-200000-line-python-codebase-overnight-with-gemini-4-argon/). Google describes additional validation rejecting a proposed optimization despite passing open-source checks. RepairGate's cases, source and results are separate synthetic work, developed with Codex assistance.
