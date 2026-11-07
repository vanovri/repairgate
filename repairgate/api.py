from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .engine import EvaluationReport
from .lab import CASES, CaseMetadata, run_case

logger = logging.getLogger(__name__)

CaseId = Literal["bill-splitter", "interval-merge", "sample-window"]

app = FastAPI(title="RepairGate", docs_url=None, redoc_url=None)
lock = threading.Lock()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.2.0"}


@app.get("/api/cases")
def cases() -> list[CaseMetadata]:
    return list(CASES.values())


@app.post("/api/demo")
def run_demo(case_id: CaseId = "bill-splitter") -> EvaluationReport:
    if not lock.acquire(blocking=False):
        logger.warning("Rejected concurrent /api/demo request for case '%s'", case_id)
        raise HTTPException(429, "A verification is already running.")
    try:
        return run_case(case_id)
    finally:
        lock.release()


def mount_frontend_if_present(target_app: FastAPI, dist_dir: Path) -> bool:
    if dist_dir.is_dir():
        target_app.mount("/", StaticFiles(directory=dist_dir, html=True), name="ui")
        return True
    return False


dist = Path(__file__).resolve().parent.parent / "frontend/dist"
mount_frontend_if_present(app, dist)
