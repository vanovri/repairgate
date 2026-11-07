from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from repairgate.demo import ROOT
from repairgate.engine import (
    digest,
    snapshot,
    tree_digest,
    validate_changes,
    validate_source,
)


def test_digest_and_tree_digest_determinism() -> None:
    empty_sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert digest(b"") == empty_sha256
    assert tree_digest({"a": "1", "b": "2"}) == tree_digest({"b": "2", "a": "1"})
    assert tree_digest({"a": "1"}) != tree_digest({"a": "2"})
    assert tree_digest({}) == digest(b"{}")


def test_snapshot_hashes_empty_binary_and_multichunk_files(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.txt"
    binary_file = tmp_path / "nested" / "binary.bin"
    large_file = tmp_path / "nested" / "deep" / "multichunk.bin"
    binary_file.parent.mkdir(parents=True)
    large_file.parent.mkdir(parents=True)

    empty_payload = b""
    binary_payload = bytes(range(256)) * 4
    large_payload = (b"repairgate-stream-chunk-" * 15_000) + b"\x00\xff\xfe"

    empty_file.write_bytes(empty_payload)
    binary_file.write_bytes(binary_payload)
    large_file.write_bytes(large_payload)

    snap = snapshot(tmp_path)
    assert snap == {
        "empty.txt": hashlib.sha256(empty_payload).hexdigest(),
        "nested/binary.bin": hashlib.sha256(binary_payload).hexdigest(),
        "nested/deep/multichunk.bin": hashlib.sha256(large_payload).hexdigest(),
    }


def test_snapshot_ignores_cache_git_and_venv_directories(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    for ignored in ("__pycache__", ".git", ".venv"):
        ignored_dir = tmp_path / ignored / "sub"
        ignored_dir.mkdir(parents=True)
        (ignored_dir / "ignored.py").write_text("x = 1\n", encoding="utf-8")
    nested_cache = tmp_path / "src" / "__pycache__"
    nested_cache.mkdir()
    (nested_cache / "mod.cpython-314.pyc").write_bytes(b"\x00\x01\x02")

    snap = snapshot(tmp_path)
    assert list(snap) == ["src/mod.py"]


def test_snapshot_rejects_symlinks_via_monkeypatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "real.txt"
    target.write_text("hello", encoding="utf-8")
    fake_link = tmp_path / "fake_link.txt"
    fake_link.write_text("link", encoding="utf-8")

    orig_path_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda self: self.name == "fake_link.txt" or orig_path_is_symlink(self),
    )

    with pytest.raises(ValueError, match="Symlinks are not supported"):
        snapshot(tmp_path)


@pytest.mark.parametrize(
    "invalid_changes",
    [
        None,
        [],
        "src/money.py",
        {},
        {f"src/f{i}.py": "def f():\n    return 1\n" for i in range(11)},
    ],
)
def test_validate_changes_rejects_invalid_container_or_count(invalid_changes: object) -> None:
    with pytest.raises(ValueError, match="1 to 10 replacement files"):
        validate_changes(invalid_changes, ROOT / "examples/bill-splitter")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_mapping",
    [
        {123: "def f():\n    return 1\n"},
        {"src/money.py": None},
        {"src/money.py": 999},
    ],
)
def test_validate_changes_rejects_non_string_entries(bad_mapping: object) -> None:
    with pytest.raises(ValueError, match="strings"):
        validate_changes(bad_mapping, ROOT / "examples/bill-splitter")  # type: ignore[arg-type]


def test_validate_changes_rejects_oversized_cache_and_symlink_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "examples/bill-splitter", repo)

    # Multi-byte UTF-8 exceeding 100,000 bytes even with <100,000 characters
    oversized_doc = '"""' + ("\u2603" * 34_000) + '"""\ndef split_cents(total, people):\n    return []\n'
    with pytest.raises(ValueError, match="100 KB"):
        validate_changes({"src/money.py": oversized_doc}, repo)

    # Existing file under src/__pycache__/ must still be rejected
    cache_dir = repo / "src" / "__pycache__"
    cache_dir.mkdir(exist_ok=True)
    (cache_dir / "cached.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Cache paths cannot change"):
        validate_changes({"src/__pycache__/cached.py": "def f():\n    return 2\n"}, repo)

    # Symlink target file must be rejected
    orig_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda self: self.name == "money.py" or orig_is_symlink(self),
    )
    with pytest.raises(ValueError, match="existing regular source file"):
        validate_changes({"src/money.py": "def split_cents(total, people):\n    return []\n"}, repo)


@pytest.mark.parametrize(
    ("source", "expected_match"),
    [
        ("def broken(:\n    pass\n", "invalid Python syntax"),
        ("from math import ceil\ndef f(x):\n    return x\n", "Pure-function policy blocks imports"),
        ("class Helper:\n    pass\n", "Pure-function policy blocks imports"),
        ("def f():\n    global x\n    return 1\n", "Pure-function policy blocks imports"),
        ("async def f():\n    return 1\n", "Pure-function policy blocks imports"),
        ("def f(x):\n    del x\n    return 1\n", "Pure-function policy blocks imports"),
        ("def f():\n    return __name__\n", "introspection names"),
        ("def f():\n    return eval('1')\n", "allowlist"),
        ("def f():\n    return (f if True else f)()\n", "allowlist"),
        ("CONST = 42\ndef f():\n    return 1\n", "function definitions and docstrings only"),
        ("def f(x=len(())):\n    return x\n", "Decorators and evaluated defaults"),
        ("def f(*, x=len(())):\n    return x\n", "Decorators and evaluated defaults"),
    ],
)
def test_validate_source_rejects_policy_violations(source: str, expected_match: str) -> None:
    with pytest.raises(ValueError, match=expected_match):
        validate_source(source)


def test_validate_source_accepts_docstrings_constants_and_sibling_calls() -> None:
    valid_code = (
        '"""Pure helper module."""\n'
        "def helper(x=0, *, step=1):\n"
        "    return x + step\n\n"
        "def compute(n):\n"
        "    return sum(helper(i, step=2) for i in range(n))\n"
    )
    validate_source(valid_code)
