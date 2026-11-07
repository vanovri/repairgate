from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from repairgate import engine
from repairgate.demo import ROOT
from repairgate.engine import evaluate, run_tests


def _make_minimal_fixture(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    holdout = tmp_path / "holdout"
    for folder in (repo / "src", repo / "tests", holdout):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "calc.py").write_text("def double(x):\n    return x\n", encoding="utf-8")
    (repo / "tests" / "test_calc.py").write_text(
        "import unittest\nfrom src.calc import double\n"
        "class VisibleTests(unittest.TestCase):\n"
        "    def test_two(self):\n        self.assertEqual(double(2), 4)\n",
        encoding="utf-8",
    )
    (holdout / "test_holdout.py").write_text(
        "import unittest\nfrom src.calc import double\n"
        "class HoldoutTests(unittest.TestCase):\n"
        "    def test_many(self):\n"
        "        for n in (-3, 0, 2, 7):\n"
        "            self.assertEqual(double(n), n * 2)\n",
        encoding="utf-8",
    )
    return repo, holdout


def test_already_correct_fixture_short_circuits_without_calling_proposer(tmp_path: Path) -> None:
    repo, holdout = _make_minimal_fixture(tmp_path)
    (repo / "src" / "calc.py").write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    def forbidden_proposer(_index: int, _feedback: str) -> dict[str, str]:
        raise AssertionError("Proposer should not be invoked when baseline passes")

    report = evaluate(repo, holdout, forbidden_proposer, trust_local_code=True)
    assert report["status"] == "no_repair_needed"
    assert report["attempts"] == []
    assert report["original_unchanged"] is True


def test_evaluate_callable_proposer_stops_on_none_and_handles_visible_failure(tmp_path: Path) -> None:
    repo, holdout = _make_minimal_fixture(tmp_path)
    responses: list[dict[str, str] | None] = [
        {"src/calc.py": "def double(x):\n    return x + 1\n"},
        None,
    ]

    report = evaluate(
        repo,
        holdout,
        lambda idx, _fb: responses[idx],
        trust_local_code=True,
        max_attempts=4,
    )
    assert report["status"] == "rejected"
    assert len(report["attempts"]) == 1
    assert report["attempts"][0]["reason"] == "Visible tests failed or no tests ran."
    assert report["original_unchanged"] is True


def test_evaluate_rejects_invalid_repo_and_holdout_layouts(tmp_path: Path) -> None:
    repo, holdout = _make_minimal_fixture(tmp_path)

    missing_src = tmp_path / "missing_src"
    (missing_src / "tests").mkdir(parents=True)
    (missing_src / "tests" / "__init__.py").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected src/ and tests/__init__.py"):
        evaluate(missing_src, holdout, [], trust_local_code=True)

    # Holdout equal to repo
    with pytest.raises(ValueError, match="Holdout tests must be an external directory"):
        evaluate(repo, repo, [], trust_local_code=True)

    # Holdout nested inside repo
    nested_holdout = repo / "nested_holdout"
    nested_holdout.mkdir()
    (nested_holdout / "__init__.py").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="Holdout tests must be an external directory"):
        evaluate(repo, nested_holdout, [], trust_local_code=True)

    # Holdout missing __init__.py
    bad_holdout = tmp_path / "bad_holdout"
    bad_holdout.mkdir()
    with pytest.raises(ValueError, match="Holdout tests must be an external directory"):
        evaluate(repo, bad_holdout, [], trust_local_code=True)


def test_evaluate_rejects_reserved_holdout_dir_in_repo(tmp_path: Path) -> None:
    repo, holdout = _make_minimal_fixture(tmp_path)
    reserved = repo / "_repairgate_holdout"
    reserved.mkdir()
    (reserved / "marker.txt").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="Reserved holdout directory already exists"):
        evaluate(repo, holdout, [], trust_local_code=True)


def test_evaluate_rejects_repo_exceeding_5mb_without_reading_oversized_blob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, holdout = _make_minimal_fixture(tmp_path)
    huge_blob = repo / "oversized.bin"
    with huge_blob.open("wb") as handle:
        handle.seek(5_000_001 - 1)
        handle.write(b"\x01")

    orig_open = Path.open

    def guarded_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.name == "oversized.bin":
            raise AssertionError("Oversized repository should be rejected before reading 5MB+ file bytes")
        return orig_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    with pytest.raises(ValueError, match="Repository exceeds 500 files or 5 MB"):
        evaluate(repo, holdout, [], trust_local_code=True)


def test_evaluate_rejects_repo_exceeding_500_files(tmp_path: Path) -> None:
    repo, holdout = _make_minimal_fixture(tmp_path)
    extra_dir = repo / "extra"
    extra_dir.mkdir()
    for idx in range(501):
        (extra_dir / f"f_{idx}.txt").write_bytes(b"x")

    with pytest.raises(ValueError, match="Repository exceeds 500 files or 5 MB"):
        evaluate(repo, holdout, [], trust_local_code=True)


def test_evaluate_rejects_baseline_tests_that_modify_files(tmp_path: Path) -> None:
    repo, holdout = _make_minimal_fixture(tmp_path)
    (repo / "tests" / "test_calc.py").write_text(
        "import unittest\nfrom pathlib import Path\n"
        "class DirtyBaseline(unittest.TestCase):\n"
        "    def test_dirty(self):\n"
        "        Path('dirty.txt').write_text('mutated')\n"
        "        self.assertTrue(True)\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Baseline tests changed files"):
        evaluate(repo, holdout, [], trust_local_code=True)


@pytest.mark.parametrize(
    "bad_attempts",
    [True, False, 0, 6, -1, 1.5, 3.0, float("nan"), float("inf"), "3", None],
)
def test_evaluate_rejects_invalid_max_attempts_types_and_bounds(bad_attempts: Any) -> None:
    with pytest.raises(ValueError, match="Attempt limit must be 1-5 and timeout 1-60 seconds"):
        evaluate(
            ROOT / "examples/bill-splitter",
            ROOT / "examples/holdout",
            [],
            trust_local_code=True,
            max_attempts=bad_attempts,
        )


@pytest.mark.parametrize(
    "bad_timeout",
    [True, False, 0, 61, -5, 2.5, 10.0, float("nan"), float("inf"), "10", None],
)
def test_evaluate_rejects_invalid_timeout_types_and_bounds(bad_timeout: Any) -> None:
    with pytest.raises(ValueError, match="Attempt limit must be 1-5 and timeout 1-60 seconds"):
        evaluate(
            ROOT / "examples/bill-splitter",
            ROOT / "examples/holdout",
            [],
            trust_local_code=True,
            timeout=bad_timeout,
        )


@pytest.mark.parametrize("bad_trust", [False, None, 0, 1, "true"])
def test_evaluate_rejects_non_true_trust_flag(bad_trust: Any) -> None:
    with pytest.raises(ValueError, match="trust"):
        evaluate(
            ROOT / "examples/bill-splitter",
            ROOT / "examples/holdout",
            [],
            trust_local_code=bad_trust,
        )


def test_evaluate_detects_mid_run_tampering_on_original_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    holdout = tmp_path / "holdout"
    shutil.copytree(ROOT / "examples/bill-splitter", repo)
    shutil.copytree(ROOT / "examples/holdout", holdout)

    def mutating_proposer(_idx: int, _feedback: str) -> dict[str, str] | None:
        (holdout / "tampered.txt").write_text("oops", encoding="utf-8")
        return None

    with pytest.raises(ValueError, match="Original repository or holdout changed during the run"):
        evaluate(repo, holdout, mutating_proposer, trust_local_code=True)


def test_evaluate_detects_tampering_before_candidate_verification(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    holdout = tmp_path / "holdout"
    shutil.copytree(ROOT / "examples/bill-splitter", repo)
    shutil.copytree(ROOT / "examples/holdout", holdout)

    def mutating_proposer(_idx: int, _feedback: str) -> dict[str, str]:
        (repo / "README_EXTRA.txt").write_text("tamper", encoding="utf-8")
        return {"src/money.py": "def split_cents(total, people):\n    return [0] * people\n"}

    with pytest.raises(ValueError, match="Source or tests changed before candidate verification"):
        evaluate(repo, holdout, mutating_proposer, trust_local_code=True, max_attempts=1)


def test_run_tests_mocked_timeout_windows_and_posix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    killed_cmds: list[list[str]] = []
    killed_pgids: list[tuple[int, int]] = []

    class FakePopen:
        def __init__(self, _cmd: list[str], *, stdout: Any, **_kwargs: Any) -> None:
            self.pid = 4242
            self.returncode: int | None = None
            self._timed_out_once = False
            stdout.write(b"test_hang ... ")
            stdout.flush()

        def wait(self, timeout: int | None = None) -> int:
            if timeout is not None and not self._timed_out_once:
                self._timed_out_once = True
                raise subprocess.TimeoutExpired(cmd="unittest", timeout=timeout)
            self.returncode = -9
            return -9

        def poll(self) -> int | None:
            return self.returncode

    monkeypatch.setattr(engine.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(
        engine.subprocess,
        "run",
        lambda cmd, **_kw: killed_cmds.append(list(cmd)),
    )

    monkeypatch.setattr(engine.os, "name", "nt")
    win_res = run_tests(tmp_path, "tests", timeout=2)
    assert win_res["timed_out"] is True
    assert win_res["passed"] is False
    assert killed_cmds == [["taskkill", "/PID", "4242", "/T", "/F"]]

    monkeypatch.setattr(engine.os, "name", "posix")
    monkeypatch.setattr(
        engine.os,
        "killpg",
        lambda pid, sig: killed_pgids.append((pid, int(sig))),
        raising=False,
    )
    posix_res = run_tests(tmp_path, "tests", timeout=2)
    assert posix_res["timed_out"] is True
    assert posix_res["passed"] is False
    assert len(killed_pgids) == 1
    assert killed_pgids[0][0] == 4242


def test_run_tests_posix_killpg_process_lookup_error_resilience(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakePopen:
        def __init__(self, _cmd: list[str], *, stdout: Any, **_kwargs: Any) -> None:
            self.pid = 9999
            self.returncode: int | None = None
            self._first = True
            stdout.write(b"Ran 1 test in 1.0s\nOK\n")
            stdout.flush()

        def wait(self, timeout: int | None = None) -> int:
            if timeout is not None and self._first:
                self._first = False
                raise subprocess.TimeoutExpired(cmd="unittest", timeout=timeout)
            self.returncode = 0
            return 0

        def poll(self) -> int | None:
            return self.returncode

    def raise_lookup(_pid: int, _sig: int) -> None:
        raise ProcessLookupError("No such process")

    monkeypatch.setattr(engine.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(engine.os, "name", "posix")
    monkeypatch.setattr(engine.os, "killpg", raise_lookup, raising=False)

    res = run_tests(tmp_path, "tests", timeout=1)
    assert res["timed_out"] is True
    assert res["passed"] is False


def test_run_tests_rejects_excessive_output_above_one_megabyte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class LoudPopen:
        def __init__(self, _cmd: list[str], *, stdout: Any, **_kwargs: Any) -> None:
            self.pid = 1111
            self.returncode = 0
            stdout.write(b"A" * 1_000_050 + b"\nRan 2 tests in 0.01s\nOK\n")
            stdout.flush()

        def wait(self, timeout: int | None = None) -> int:
            return 0

        def poll(self) -> int | None:
            return 0

    monkeypatch.setattr(engine.subprocess, "Popen", LoudPopen)
    res = run_tests(tmp_path, "tests", timeout=5)
    assert res["exit_code"] == 0
    assert res["tests"] == 2
    assert res["output_truncated"] is True
    assert res["output_bytes"] > 1_000_000
    assert res["passed"] is False
    assert os.fspath(tmp_path) not in res["log"]


@pytest.mark.parametrize("bad_timeout", [True, False, 0, 61, 1.5, "5"])
def test_run_tests_rejects_invalid_timeout_directly(tmp_path: Path, bad_timeout: Any) -> None:
    with pytest.raises(ValueError, match="Attempt limit must be 1-5 and timeout 1-60 seconds"):
        run_tests(tmp_path, "tests", timeout=bad_timeout)

