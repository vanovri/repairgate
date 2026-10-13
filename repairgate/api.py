from pathlib import Path
import threading
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from .demo import demo

app = FastAPI(title='RepairGate', docs_url=None, redoc_url=None)
lock = threading.Lock()

@app.get('/api/health')
def health():
    return {'status': 'ok', 'version': '0.1.0'}

@app.post('/api/demo')
def run_demo():
    if not lock.acquire(blocking=False):
        raise HTTPException(429, 'A verification is already running.')
    try:
        return demo()
    finally:
        lock.release()

dist = Path(__file__).resolve().parent.parent / 'frontend/dist'
if dist.is_dir():
    app.mount('/', StaticFiles(directory=dist, html=True), name='ui')
