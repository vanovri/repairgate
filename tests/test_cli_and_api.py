from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path
from urllib.error import URLError

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from repairgate import api, cli, lab
from repairgate.demo import ROOT
from repairgate.engine import ollama_proposer


def test_cli_demo_writes_report_and_prints_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out_file = tmp_path / "demo-out.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["repairgate", "demo", "--case", "bill-splitter", "--output", str(out_file)],
    )
    cli.main()
    stdout = json.loads(capsys.readouterr().out.strip())
    assert stdout == {"status": "accepted", "attempts": 3, "report": str(out_file)}
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved["status"] == "accepted"
    assert saved["case"]["id"] == "bill-splitter"


def test_cli_lab_pass_and_failure_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out_file = tmp_path / "lab-out.json"
    fake_passed = {
        "status": "passed",
        "summary": {"cases": 3, "accepted_repairs": 3, "policy_rejections": 3, "visible_pass_holdout_fail": 3},
        "cases": [],
    }
    monkeypatch.setattr(cli, "run_lab", lambda: fake_passed)
    monkeypatch.setattr(sys, "argv", ["repairgate", "lab", "--output", str(out_file)])
    cli.main()
    stdout = json.loads(capsys.readouterr().out.strip())
    assert stdout["status"] == "passed"
    assert stdout["cases"] == 3

    fake_failed = {**fake_passed, "status": "failed"}
    monkeypatch.setattr(cli, "run_lab", lambda: fake_failed)
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 1


def test_cli_repair_with_proposals_file_and_ollama(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "examples/bill-splitter", repo)
    proposals_path = tmp_path / "proposals.json"
    good_code = (
        "def split_cents(total, people):\n"
        "    if isinstance(total, bool) or not isinstance(total, int) or total < 0:\n"
        '        raise ValueError("total")\n'
        "    if isinstance(people, bool) or not isinstance(people, int) or people <= 0:\n"
        '        raise ValueError("people")\n'
        "    base, remainder = divmod(total, people)\n"
        "    return [base + (1 if i < remainder else 0) for i in range(people)]\n"
    )
    proposals_path.write_text(json.dumps([{"src/money.py": good_code}]), encoding="utf-8")
    out_recorded = tmp_path / "recorded-report.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "repairgate",
            "repair",
            str(repo),
            "--holdout",
            str(ROOT / "examples/holdout"),
            "--task",
            "Split cents conserved",
            "--proposals",
            str(proposals_path),
            "--trust-local-code",
            "--attempts",
            "1",
            "--output",
            str(out_recorded),
        ],
    )
    cli.main()
    recorded_stdout = json.loads(capsys.readouterr().out.strip())
    assert recorded_stdout["status"] == "accepted"
    recorded_report = json.loads(out_recorded.read_text(encoding="utf-8"))
    assert recorded_report["provider"] == "recorded proposals"

    # Now test --ollama branch completely offline via mocked ollama_proposer
    out_ollama = tmp_path / "ollama-report.json"
    monkeypatch.setattr(
        cli,
        "ollama_proposer",
        lambda _repo, _task, _model: (lambda _idx, _fb: {"src/money.py": good_code}),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "repairgate",
            "repair",
            str(repo),
            "--holdout",
            str(ROOT / "examples/holdout"),
            "--task",
            "Split cents conserved",
            "--ollama",
            "local-coder",
            "--trust-local-code",
            "--attempts",
            "1",
            "--output",
            str(out_ollama),
        ],
    )
    cli.main()
    ollama_stdout = json.loads(capsys.readouterr().out.strip())
    assert ollama_stdout["status"] == "accepted"
    ollama_report = json.loads(out_ollama.read_text(encoding="utf-8"))
    assert ollama_report["provider"] == "ollama:local-coder"


def test_lab_unknown_case_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown bundled regression case"):
        lab.run_case("nonexistent-case")


def test_api_returns_429_when_busy_and_releases_lock_after_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(api.app) as client:
        assert api.lock.acquire(blocking=False)
        try:
            busy = client.post("/api/demo")
            assert busy.status_code == 429
            assert "already running" in busy.json()["detail"]
        finally:
            api.lock.release()

        def boom(_case_id: str) -> dict[str, object]:
            raise RuntimeError("injected failure")

        monkeypatch.setattr(api, "run_case", boom)
        with pytest.raises(RuntimeError, match="injected failure"):
            client.post("/api/demo")

        # Lock must have been released by finally block
        assert api.lock.acquire(blocking=False)
        api.lock.release()


def test_ollama_proposer_edge_cases_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. Source > 100_000 chars rejected before network access
    big_repo = tmp_path / "big"
    (big_repo / "src").mkdir(parents=True)
    (big_repo / "src" / "huge.py").write_text("x" * 100_001, encoding="utf-8")
    with pytest.raises(ValueError, match="Source is too large"):
        ollama_proposer(big_repo, "Fix", "demo")

    # 2. Response > 200_000 bytes rejected
    monkeypatch.setattr(
        "repairgate.engine.urlopen",
        lambda *_a, **_kw: io.BytesIO(b"x" * 200_001),
    )
    proposer = ollama_proposer(ROOT / "examples/bill-splitter", "Fix", "demo")
    with pytest.raises(ValueError, match="Model response too large"):
        proposer(0, "failed")

    # 3. Malformed model JSON payload rejected with ValueError
    monkeypatch.setattr(
        "repairgate.engine.urlopen",
        lambda *_a, **_kw: io.BytesIO(json.dumps({"response": "not-json"}).encode()),
    )
    with pytest.raises(ValueError):
        proposer(0, "failed")

    monkeypatch.setattr(
        "repairgate.engine.urlopen",
        lambda *_a, **_kw: io.BytesIO(json.dumps({"missing_response": "{}"}).encode()),
    )
    with pytest.raises(ValueError, match="Invalid Ollama response"):
        proposer(0, "failed")

    monkeypatch.setattr(
        "repairgate.engine.urlopen",
        lambda *_a, **_kw: io.BytesIO(
            json.dumps({"response": json.dumps({"not_files": {}})}).encode()
        ),
    )
    with pytest.raises(ValueError, match="missing 'files' mapping"):
        proposer(0, "failed")

    # 4. Network error (URLError) surfaces cleanly
    def fail_network(*_a: object, **_kw: object) -> io.BytesIO:
        raise URLError("connection refused")

    monkeypatch.setattr("repairgate.engine.urlopen", fail_network)
    with pytest.raises(URLError, match="connection refused"):
        proposer(0, "failed")


def test_cli_invalid_proposals_files_raise_value_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(ValueError, match="Unable to read proposals file"):
        cli._load_proposals_file(missing)

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        cli._load_proposals_file(bad_json)

    not_a_list = tmp_path / "dict.json"
    not_a_list.write_text('{"src/money.py": "pass"}', encoding="utf-8")
    with pytest.raises(ValueError, match="must be a list"):
        cli._load_proposals_file(not_a_list)


def test_api_mount_frontend_if_present(tmp_path: Path) -> None:
    sub_app = FastAPI()
    assert api.mount_frontend_if_present(sub_app, tmp_path / "missing_dist") is False

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>UI</body></html>", encoding="utf-8")
    assert api.mount_frontend_if_present(sub_app, dist_dir) is True
    with TestClient(sub_app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "UI" in resp.text



def test_cli_repair_exits_nonzero_when_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "examples/bill-splitter", repo)
    bad_proposals = tmp_path / "bad_proposals.json"
    bad_proposals.write_text(json.dumps([{"src/money.py": "def split_cents(total, people):\n    return []\n"}]), encoding="utf-8")
    out_file = tmp_path / "rejected-report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "repairgate",
            "repair",
            str(repo),
            "--holdout",
            str(ROOT / "examples/holdout"),
            "--task",
            "Split cents conserved",
            "--proposals",
            str(bad_proposals),
            "--trust-local-code",
            "--attempts",
            "1",
            "--output",
            str(out_file),
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 1
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved["status"] == "rejected"
