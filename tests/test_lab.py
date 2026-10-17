"""Real subprocess replay, including failures that visible examples miss."""
import pytest
from fastapi.testclient import TestClient

from repairgate.api import app
from repairgate.engine import evaluate
from repairgate.lab import CASES, run_lab


@pytest.fixture(scope='module')
def lab_report():
    return run_lab()


@pytest.mark.parametrize('case_id', tuple(CASES))
def test_each_case_rejects_overfit_and_preserves_evidence(lab_report, case_id):
    report = next(item for item in lab_report['cases'] if item['case']['id'] == case_id)
    blocked, overfit, repaired = report['attempts']
    assert not report['baseline']['visible']['passed']
    assert not blocked['policy_passed']
    assert 'visible' not in blocked
    assert overfit['visible']['passed'] and not overfit['holdout']['passed']
    assert overfit['visible']['tests'] == 2 and overfit['holdout']['tests'] == 3
    assert '<verification-copy>' in overfit['holdout']['log']
    if case_id != 'bill-splitter':
        assert overfit['holdout']['output_truncated']
        assert '[output truncated;' in overfit['holdout']['log']
    assert repaired['status'] == 'accepted'
    assert repaired['visible']['passed'] and repaired['holdout']['passed']
    assert overfit['proposal_digest'] != repaired['proposal_digest']
    for attempt in (overfit, repaired):
        assert attempt['starting_source_digest'] == report['source_digest']
        assert attempt['protected_tests_before_digest'] == report['protected_tests_digest']
        assert attempt['protected_tests_after_digest'] == report['protected_tests_digest']
        assert attempt['protected_tests_unchanged'] and attempt['integrity_passed']
    assert report['original_unchanged']


def test_lab_summary(lab_report):
    assert lab_report['status'] == 'passed'
    assert lab_report['summary'] == {
        'cases': 3, 'accepted_repairs': 3,
        'policy_rejections': 3, 'visible_pass_holdout_fail': 3,
    }


def write_fixture(tmp_path, visible, holdout):
    repo, checks = tmp_path / 'repo', tmp_path / 'holdout'
    for directory in (repo / 'src', repo / 'tests', checks):
        directory.mkdir(parents=True)
        (directory / '__init__.py').write_text('')
    (repo / 'tests/test_values.py').write_text(visible)
    (checks / 'test_values.py').write_text(holdout)
    return repo, checks


def test_candidates_do_not_accumulate_previous_changes(tmp_path):
    repo, checks = write_fixture(tmp_path,
        'import unittest\nfrom src.a import a\nclass Visible(unittest.TestCase):\n    def test_a(self): self.assertEqual(a(), 1)\n',
        'import unittest\nfrom src.a import a\nfrom src.b import b\nclass Holdout(unittest.TestCase):\n    def test_both(self): self.assertEqual((a(), b()), (1, 2))\n')
    (repo / 'src/a.py').write_text('def a():\n    return 0\n')
    (repo / 'src/b.py').write_text('def b():\n    return 0\n')
    fix_a, fix_b = 'def a():\n    return 1\n', 'def b():\n    return 2\n'
    report = evaluate(repo, checks, [
        {'src/a.py': fix_a}, {'src/b.py': fix_b}, {'src/a.py': fix_a, 'src/b.py': fix_b},
    ], trust_local_code=True)
    first, second, third = report['attempts']
    assert first['visible']['passed'] and not first['holdout']['passed']
    # If proposal 1 leaked into proposal 2, both suites would pass here.
    assert not second['visible']['passed'] and not second['holdout']['passed']
    assert third['status'] == 'accepted'
    assert {item['starting_source_digest'] for item in report['attempts']} == {report['source_digest']}
    assert report['original_unchanged']


def test_test_file_write_rejects_an_otherwise_passing_candidate(tmp_path):
    repo, checks = write_fixture(tmp_path,
        'import unittest\nfrom pathlib import Path\nfrom src.value import value\nclass Visible(unittest.TestCase):\n'
        '    def test_value(self):\n        if value() == 1: Path("tests/changed.txt").write_text("changed")\n'
        '        self.assertIn(value(), (0, 1))\n',
        'import unittest\nfrom src.value import value\nclass Holdout(unittest.TestCase):\n    def test_fixed(self): self.assertEqual(value(), 1)\n')
    (repo / 'src/value.py').write_text('def value():\n    return 0\n')
    report = evaluate(repo, checks, [{'src/value.py': 'def value():\n    return 1\n'}], trust_local_code=True)
    attempt = report['attempts'][0]
    assert attempt['visible']['passed'] and attempt['holdout']['passed']
    assert not attempt['protected_tests_unchanged'] and not attempt['integrity_passed']
    assert attempt['protected_tests_before_digest'] != attempt['protected_tests_after_digest']
    assert report['status'] == 'rejected' and report['original_unchanged']
    assert not (repo / 'tests/changed.txt').exists()


def test_api_case_catalog_and_invalid_selection():
    client = TestClient(app)
    catalog = client.get('/api/cases').json()
    assert [item['id'] for item in catalog] == list(CASES)
    assert client.get('/api/health').json()['version'] == '0.2.0'
    assert client.post('/api/demo?case_id=../../arbitrary').status_code == 422
    response = client.post('/api/demo?case_id=sample-window')
    assert response.status_code == 200
    assert response.json()['case']['id'] == 'sample-window'
    assert response.json()['status'] == 'accepted'
