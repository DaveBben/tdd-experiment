"""Known-answer tests for runner.py, the in-container test runner, using the harness image's pytest."""
import json
import os
import sys

import pytest as _pytest

from harness import runner

SUITE = '''
import pytest
from mod import double

@pytest.mark.parametrize("s", ["hello world", "a b c"])
def test_space(s):
    assert double(2) == 4 and s

def test_kills():
    assert double(3) == 6

def test_fails():
    assert False

@pytest.mark.xfail
def test_xf():
    assert False

@pytest.mark.skip
def test_sk():
    pass

@pytest.fixture
def bad_teardown():
    yield
    raise RuntimeError("teardown")

def test_teardown(bad_teardown):
    pass
'''


@_pytest.fixture
def repo(tmp_path):
    (tmp_path / "mod.py").write_text("def double(x):\n    return x * 2\n")
    (tmp_path / "test_tdd_a.py").write_text(SUITE)
    (tmp_path / "test_tdd_broken.py").write_text("import not_a_module\n\ndef test_x():\n    pass\n")
    return tmp_path


CMD = f"{sys.executable} -m pytest -q"


def test_outcomes_survive_spaces_and_collection_errors(repo):
    res = runner.outcomes(CMD, ["test_tdd_a.py", "test_tdd_broken.py"], 2, cwd=str(repo))
    o = res["runs"][0]
    assert o["test_tdd_a.py::test_space[hello world]"] == "PASSED"
    assert o["test_tdd_a.py::test_space[a b c]"] == "PASSED"
    assert o["test_tdd_a.py::test_kills"] == "PASSED"
    assert o["test_tdd_a.py::test_fails"] == "FAILED"
    assert o["test_tdd_a.py::test_xf"] == "XFAIL"
    assert o["test_tdd_a.py::test_sk"] == "SKIPPED"
    assert o["test_tdd_a.py::test_teardown"] == "ERROR"
    assert res["collection_errors"][0] == ["test_tdd_broken.py"]  # the healthy file still ran
    assert res["runs"][0] == res["runs"][1]


def test_mutant_kills_by_valid_ids(repo):
    muts = [{"id": 0, "path": "mod.py", "start": 26, "end": 31, "new": "x * 3"},   # killed by both
            {"id": 1, "path": "mod.py", "start": 26, "end": 31, "new": "x * 2"}]   # identity: survives
    assert open(repo / "mod.py").read()[26:31] == "x * 2"
    ids = ["test_tdd_a.py::test_space[hello world]", "test_tdd_a.py::test_kills"]
    res = runner.mutants(CMD, ["test_tdd_a.py"], muts, ids, root=str(repo))
    assert [r["killed"] for r in res["results"]] == [True, False]
    assert res["results"][0]["failing"] == sorted(ids)
    assert open(repo / "mod.py").read() == "def double(x):\n    return x * 2\n"  # restored
