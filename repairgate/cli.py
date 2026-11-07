from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeGuard

from .engine import ProposalSource, evaluate, ollama_proposer
from .lab import CASES, run_case, run_lab

logger = logging.getLogger(__name__)


def _is_proposal_list(value: object) -> TypeGuard[list[dict[str, str] | None]]:
    return isinstance(value, list)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify repairs in disposable copies. Originals are never edited."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("demo")
    sample.add_argument("--case", choices=tuple(CASES), default="bill-splitter")
    sample.add_argument("--output", type=Path, default=Path("repair-report.json"))

    lab_parser = sub.add_parser("lab", help="Replay all bundled synthetic regression cases")
    lab_parser.add_argument("--output", type=Path, default=Path("regression-lab-report.json"))

    repair = sub.add_parser("repair")
    repair.add_argument("repo", type=Path)
    repair.add_argument("--holdout", required=True, type=Path)
    repair.add_argument("--task", required=True)
    provider = repair.add_mutually_exclusive_group(required=True)
    provider.add_argument("--proposals", type=Path)
    provider.add_argument("--ollama", metavar="MODEL")
    repair.add_argument("--trust-local-code", action="store_true")
    repair.add_argument("--attempts", type=int, default=3)
    repair.add_argument("--output", type=Path, default=Path("repair-report.json"))
    return parser


def _load_proposals_file(proposals_path: Path) -> list[dict[str, str] | None]:
    try:
        raw_text = proposals_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Unable to read proposals file '%s': %s", proposals_path, exc)
        raise ValueError(f"Unable to read proposals file: {proposals_path}") from exc
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in proposals file '%s': %s", proposals_path, exc)
        raise ValueError(f"Proposals file contains invalid JSON: {proposals_path}") from exc
    if not _is_proposal_list(parsed):
        raise ValueError("Proposals JSON must be a list of replacement mappings.")
    return parsed


def _run_selected_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "demo":
        return dict(run_case(args.case))
    if args.command == "lab":
        return dict(run_lab())

    proposals: ProposalSource
    if args.ollama:
        proposals = ollama_proposer(args.repo.resolve(), args.task, args.ollama)
        provider_label = f"ollama:{args.ollama}"
    else:
        proposals = _load_proposals_file(args.proposals)
        provider_label = "recorded proposals"

    report = evaluate(
        args.repo,
        args.holdout,
        proposals,
        trust_local_code=args.trust_local_code,
        max_attempts=args.attempts,
    )
    report["provider"] = provider_label
    return dict(report)


def _write_report(output_path: Path, report: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = _run_selected_command(args)
    _write_report(args.output, result)
    summary: dict[str, Any] = (
        result["summary"] if args.command == "lab" else {"attempts": len(result["attempts"])}
    )
    print(json.dumps({"status": result["status"], **summary, "report": str(args.output)}))
    if args.command == "lab" and result["status"] != "passed":
        raise SystemExit(1)
    if args.command == "repair" and result["status"] != "accepted":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
