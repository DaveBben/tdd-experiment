"""Runs inside a task container (stdlib only, the container's Python): test outcomes and mutant kills.

    python runner.py outcomes TEST_CMD FILES.json REPEATS        -> {"runs": [{nodeid: outcome}], "seconds": [...],
                                                                    "collection_errors": [[file, ...] per run]}
    python runner.py mutants TEST_CMD FILES.json MUTANTS.json IDS.json
                                                                 -> {"ref_seconds": s, "results": [{id, killed, timeout}]}

Test files are run whole, and node IDs are never passed to pytest: an ID with a space cannot survive a command
line. Outcomes come from a pytest plugin (tdd_outcomes, below), not from parsing pytest's text output. A test
is PASSED only when its setup, call, and teardown all pass; anything else (failed, error, skipped, xfail,
xpass) is reported as such. A test with no report in a run is MISSING.
"""
import json
import os
import subprocess
import sys
import time

PLUGIN_DIR = "/tmp/tdd_plugin"
PLUGIN = '''
import json, os

_PATH = os.environ["TDD_OUTCOMES"]  # read now: a test may clear os.environ
_RANK = {"PASSED": 0, "SKIPPED": 1, "XFAIL": 1, "XPASS": 1, "FAILED": 2, "ERROR": 2}
_out = {}
_collect_errors = []


def pytest_collectreport(report):
    if report.failed:
        _collect_errors.append(report.nodeid)


def pytest_runtest_logreport(report):
    prev = _out.get(report.nodeid)
    if report.when == "call":
        if hasattr(report, "wasxfail"):
            outcome = "XPASS" if report.passed else "XFAIL"
        else:
            outcome = report.outcome.upper()
    elif report.failed:
        outcome = "ERROR"
    elif report.skipped:
        outcome = "SKIPPED"
    else:
        outcome = "PASSED"
    # The worst phase wins: PASSED only when setup, call, and teardown all passed; a failure outranks a skip.
    _out[report.nodeid] = outcome if prev is None or _RANK[outcome] > _RANK[prev] else prev


def pytest_sessionfinish(session):
    with open(_PATH, "w") as f:
        json.dump({"tests": _out, "collection_errors": _collect_errors}, f)
'''
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TDD_OUTCOMES="/tmp/tdd_outcomes.json",
           PYTHONPATH=PLUGIN_DIR + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""))
RUN_LIMIT = 1800  # seconds for 1 run of a suite on the reference; a hang beyond this marks every test MISSING


def _q(s):
    return "'" + s.replace("'", "'\\''") + "'"


def pytest(cmd, files, timeout=RUN_LIMIT, cwd="/testbed"):
    """({nodeid: outcome}, [files that failed to collect], seconds, timed_out)."""
    os.makedirs(PLUGIN_DIR, exist_ok=True)
    with open(os.path.join(PLUGIN_DIR, "tdd_outcomes.py"), "w") as f:
        f.write(PLUGIN)
    if os.path.exists(ENV["TDD_OUTCOMES"]):
        os.remove(ENV["TDD_OUTCOMES"])
    start = time.monotonic()
    try:
        subprocess.run(f"{cmd} -p tdd_outcomes -p no:cacheprovider --continue-on-collection-errors "
                       + " ".join(_q(f) for f in files), shell=True, cwd=cwd, capture_output=True,
                       timeout=timeout, env=ENV, executable="/bin/bash")
    except subprocess.TimeoutExpired:
        return {}, [], time.monotonic() - start, True
    seconds = time.monotonic() - start
    try:
        with open(ENV["TDD_OUTCOMES"]) as f:
            res = json.load(f)
    except (OSError, ValueError):
        return {}, list(files), seconds, False  # pytest died before the session finished
    return res["tests"], res["collection_errors"], seconds, False


def outcomes(cmd, files, repeats, cwd="/testbed"):
    runs, secs, errs = [], [], []
    for _ in range(repeats):
        o, e, s, _ = pytest(cmd, files, cwd=cwd)
        runs.append(o)
        errs.append(e)
        secs.append(s)
    return {"runs": runs, "seconds": secs, "collection_errors": errs}


def mutants(cmd, files, muts, ids, root="/testbed"):
    """Each mutant is killed when any test in `ids` is not PASSED, or the run times out. Only tests that also
    pass in this run of the same file subset on the unmutated reference count; any other is reported."""
    ref, _, ref_seconds, _ = pytest(cmd, files, cwd=root)
    dropped = sorted(i for i in ids if ref.get(i) != "PASSED")
    ids = [i for i in ids if ref.get(i) == "PASSED"]
    limit = max(3 * ref_seconds, ref_seconds + 10)
    results = []
    for m in muts:
        path = os.path.join(root, m["path"])
        with open(path, "rb") as f:
            src = f.read()
        try:
            with open(path, "wb") as f:
                f.write(src[: m["start"]] + m["new"].encode() + src[m["end"]:])
            o, _, _, timed_out = pytest(cmd, files, timeout=limit, cwd=root)
        finally:
            with open(path, "wb") as f:
                f.write(src)
        failing = sorted(i for i in ids if o.get(i, "MISSING") != "PASSED")
        results.append({"id": m["id"], "killed": timed_out or bool(failing), "timeout": timed_out,
                        "failing": failing})
    return {"ref_seconds": ref_seconds, "limit_seconds": limit, "results": results, "used_ids": ids,
            "dropped_not_passing_in_subset": dropped}


if __name__ == "__main__":
    mode, cmd, files_path = sys.argv[1:4]
    files = json.load(open(files_path))
    if mode == "outcomes":
        res = outcomes(cmd, files, int(sys.argv[4]))
    else:
        res = mutants(cmd, files, json.load(open(sys.argv[4]))["mutants"], json.load(open(sys.argv[5])))
    json.dump(res, sys.stdout)
