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


HANG_SUITE = '''
import time
from mod import double

def test_a():
    assert double(1) == 2

def test_hang():
    sum(range(10**14))  # C code holding the GIL: no thread inside pytest can interrupt it

def test_z():
    assert double(5) == 10
'''


def test_hanging_test_invalidates_only_itself(repo, monkeypatch):
    (repo / "test_tdd_hang.py").write_text(HANG_SUITE)
    monkeypatch.setitem(runner.ENV, "TDD_HARD", "2")
    start = __import__("time").monotonic()
    res = runner.outcomes(CMD, ["test_tdd_hang.py"], 1, cwd=str(repo))
    assert res["runs"][0] == {"test_tdd_hang.py::test_a": "PASSED", "test_tdd_hang.py::test_hang": "TIMEOUT",
                              "test_tdd_hang.py::test_z": "PASSED"}
    assert __import__("time").monotonic() - start < 30


def test_mutant_that_hangs_is_a_timeout_kill(repo, monkeypatch):
    monkeypatch.setitem(runner.ENV, "TDD_HARD", "2")
    hang = {"id": 0, "path": "mod.py", "start": 26, "end": 31, "new": "__import__('time').sleep(1000)"}
    res = runner.mutants(CMD, ["test_tdd_a.py"], [hang], ["test_tdd_a.py::test_kills"], root=str(repo))
    assert res["results"][0]["killed"] and res["results"][0]["timeout"]
    assert open(repo / "mod.py").read() == "def double(x):\n    return x * 2\n"


def test_mutant_runs_skip_a_test_that_hung_on_the_reference(repo, monkeypatch):
    """Review finding: without the skip, every mutant hit the watchdog and counted as killed."""
    (repo / "test_tdd_hang.py").write_text(HANG_SUITE)
    monkeypatch.setitem(runner.ENV, "TDD_HARD", "2")
    identity = {"id": 0, "path": "mod.py", "start": 26, "end": 31, "new": "x * 2"}
    wrong = {"id": 1, "path": "mod.py", "start": 26, "end": 31, "new": "x * 3"}
    res = runner.mutants(CMD, ["test_tdd_hang.py"], [identity, wrong],
                         ["test_tdd_hang.py::test_a", "test_tdd_hang.py::test_z"], root=str(repo),
                         skip=["test_tdd_hang.py::test_hang"])
    assert [(r["killed"], r["timeout"]) for r in res["results"]] == [(False, False), (True, False)]


def test_collection_hang_loses_only_its_file(repo, monkeypatch):
    (repo / "test_tdd_colhang.py").write_text("sum(range(10**14))\n\ndef test_never():\n    pass\n")
    monkeypatch.setitem(runner.ENV, "TDD_HARD", "2")
    o, errors, _ = runner.run_all(CMD, ["test_tdd_a.py", "test_tdd_colhang.py"], cwd=str(repo))
    assert o["test_tdd_a.py::test_kills"] == "PASSED" and "test_tdd_colhang.py" in errors
    assert not any(k.startswith("test_tdd_colhang.py::") for k in o)


def test_crash_inside_a_test_is_crashed_and_the_rest_still_run(repo):
    (repo / "test_tdd_crash.py").write_text(
        "import os\nfrom mod import double\n\ndef test_a():\n    assert double(1) == 2\n\n"
        "def test_crash():\n    os._exit(3)\n\ndef test_z():\n    assert double(5) == 10\n")
    o, _, _ = runner.run_all(CMD, ["test_tdd_crash.py"], cwd=str(repo))
    assert o == {"test_tdd_crash.py::test_a": "PASSED", "test_tdd_crash.py::test_crash": "CRASHED",
                 "test_tdd_crash.py::test_z": "PASSED"}


def test_process_that_will_not_exit_keeps_its_outcomes(repo, monkeypatch):
    (repo / "test_tdd_noexit.py").write_text(
        "import threading, time\n\ndef test_t():\n    threading.Thread(target=time.sleep, args=(1000,)).start()\n")
    monkeypatch.setattr(runner, "EXIT_GRACE", 1)
    o, _, secs, timed_out, stuck = runner.pytest(CMD, ["test_tdd_noexit.py"], cwd=str(repo), timeout=60)
    assert o == {"test_tdd_noexit.py::test_t": "PASSED"} and not timed_out and stuck is None and secs < 30

