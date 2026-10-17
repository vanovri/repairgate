from pathlib import Path
import threading
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from .lab import CASES, run_case

app = FastAPI(title='RepairGate', docs_url=None, redoc_url=None)
lock = threading.Lock()

@app.get('/api/health')
def health():
    return {'status': 'ok', 'version': '0.2.0'}

@app.get('/api/cases')
def cases():
    return list(CASES.values())

@app.post('/api/demo')
def run_demo(case_id: Literal['bill-splitter', 'interval-merge', 'sample-window'] = 'bill-splitter'):
    if not lock.acquire(blocking=False):
        raise HTTPException(429, 'A verification is already running.')
    try:
        return run_case(case_id)
    finally:
        lock.release()

dist = Path(__file__).resolve().parent.parent / 'frontend/dist'
if dist.is_dir():
    app.mount('/', StaticFiles(directory=dist, html=True), name='ui')
