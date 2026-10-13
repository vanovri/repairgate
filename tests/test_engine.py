import json
from pathlib import Path
import shutil
import pytest
from fastapi.testclient import TestClient
from repairgate.demo import ROOT, demo
from repairgate.engine import evaluate, snapshot, validate_changes, validate_source
from repairgate.api import app

def test_repair_gate_rejects_cheating_and_overfit():
    report = demo()
    assert report['status'] == 'accepted'
    assert report['original_unchanged']
    assert len(report['attempts']) == 3
    assert 'protected' in report['attempts'][0]['reason']
    assert not report['attempts'][1]['holdout']['passed']
    assert report['attempts'][1]['visible']['passed']
    assert report['attempts'][2]['integrity_passed']
    assert report['attempts'][2]['visible']['passed']
    assert report['attempts'][2]['holdout']['passed']

@pytest.mark.parametrize('name', ['../escape.py','src/../tests/x.py','src\\x.py','C:/src/x.py','/src/x.py','src/new.py','pyproject.toml','src//money.py'])
def test_unsafe_paths(name):
    with pytest.raises(ValueError):
        validate_changes({name:'pass'}, ROOT / 'examples/bill-splitter')

def test_requires_trust():
    with pytest.raises(ValueError, match='trust'):
        evaluate(ROOT / 'examples/bill-splitter', ROOT / 'examples/holdout', [])

def test_attempt_cap():
    report = evaluate(ROOT / 'examples/bill-splitter', ROOT / 'examples/holdout', [{'tests/x.py':'pass'}] * 5,
                      trust_local_code=True, max_attempts=2)
    assert len(report['attempts']) == 2
    assert report['accepted_changes'] is None

def test_timeout_does_not_accept(tmp_path):
    repo = tmp_path / 'repo'
    shutil.copytree(ROOT / 'examples/bill-splitter', repo)
    report = evaluate(repo, ROOT / 'examples/holdout', [{'src/money.py':'def split_cents(total, people):\n    while True: pass\n'}],
                      trust_local_code=True, timeout=1, max_attempts=1)
    assert report['status'] == 'rejected'
    assert report['attempts'][0]['visible']['timed_out']
    assert report['original_unchanged']

def test_api_exposes_fixed_demo_only():
    client = TestClient(app)
    assert client.get('/api/health').status_code == 200
    assert client.post('/api/repair', json={'repo':'C:/'}).status_code in (404, 405)
    assert client.post('/api/demo').json()['status'] == 'accepted'

def test_zero_tests_rejected(tmp_path):
    repo = tmp_path / 'repo'
    shutil.copytree(ROOT / 'examples/bill-splitter', repo)
    (repo / 'tests/test_money.py').write_text('')
    report = evaluate(repo, ROOT / 'examples/holdout', [{'src/money.py':'def split_cents(total, people):\n    return [0] * people\n'}], trust_local_code=True)
    assert report['baseline']['visible']['tests'] == 0
    assert report['status'] == 'rejected'

@pytest.mark.parametrize('code', [
    'import unittest\nunittest.TestCase.assertEqual = lambda *args: None',
    'def f():\n    return __import__("os")',
    'def f():\n    return open("tests/x.py", "w")',
    'def f(x):\n    return x.__class__',
    '@print("cheat")\ndef f():\n    return 1',
])
def test_obvious_test_tampering_rejected(code):
    with pytest.raises(ValueError):
        validate_source(code)
