import io
import json
import pytest
from repairgate.demo import ROOT
from repairgate.engine import ollama_proposer, evaluate

def test_ollama_receives_visible_feedback_only(monkeypatch):
    calls=[]
    def response(request, timeout):
        calls.append(json.loads(request.data))
        assert request.full_url == 'http://127.0.0.1:11434/api/generate'
        return io.BytesIO(json.dumps({'response':json.dumps({'files':{'src/money.py':'def split_cents(total, people):\n    return [0] * people\n'}})}).encode())
    monkeypatch.setattr('repairgate.engine.urlopen',response)
    provider=ollama_proposer(ROOT/'examples/bill-splitter','Fix splitting','demo-model')
    report=evaluate(ROOT/'examples/bill-splitter',ROOT/'examples/holdout',provider,trust_local_code=True,max_attempts=1)
    assert report['status']=='rejected'
    assert len(calls)==1
    assert 'test_conservation_and_fairness' not in calls[0]['prompt']
    assert '35' not in calls[0]['prompt']

def test_ollama_response_cannot_write_tests(monkeypatch):
    monkeypatch.setattr('repairgate.engine.urlopen',lambda *a,**kw:io.BytesIO(json.dumps({'response':json.dumps({'files':{'tests/test_money.py':''}})}).encode()))
    provider=ollama_proposer(ROOT/'examples/bill-splitter','Repair','demo')
    report=evaluate(ROOT/'examples/bill-splitter',ROOT/'examples/holdout',provider,trust_local_code=True,max_attempts=1)
    assert 'protected' in report['attempts'][0]['reason']
