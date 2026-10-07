"""Runs inside a task container (stdlib only, the container's Python): test outcomes and mutant kills.

    python runner.py outcomes TEST_CMD FILES.json REPEATS        -> {"runs": [{nodeid: outcome}], "seconds": [...],
                                                                    "collection_errors": [[file, ...] per run]}
    python runner.py mutants TEST_CMD FILES.json MUTANTS.json IDS.json
                                                                 -> {"ref_seconds": s, "results": [{id, killed, timeout}]}

Test files are run whole, and node IDs are never passed to pytest: an ID with a space cannot survive a command
line. Outcomes come from a pytest plugin (tdd_outcomes, below), not from parsing pytest's text output. A test
is PASSED only when its setup, call, and teardown all pass; anything else (failed, error, skipped, xfail,
xpass) is reported as such. A test with no report in a run is MISSING.

The plugin logs each event as it happens. This process watches that log and kills pytest when 1 test runs
longer than HARD_TEST seconds: a watchdog inside pytest would stall with it when C code holds the GIL, which is
also why pytest-timeout cannot interrupt such a hang. For an outcomes run,
that test is TIMEOUT and the suite is run again without it and without the tests that already have an outcome,
until every test has one: a hanging test invalidates only itself. In a mutant run any hang is a kill.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time

PLUGIN_DIR = "/tmp/tdd_plugin"
LOG = "/tmp/tdd_events.jsonl"
SKIP = "/tmp/tdd_skip.json"
HARD_TEST = 60  # seconds for 1 test, and at least twice the task's own pytest --timeout (10 to 120 s)
EXIT_GRACE = 10  # seconds a process may take to exit after its session finished
RUN_LIMIT = 1800  # seconds for 1 pytest process; a backstop behind the watchdog
PLUGIN = '''
import json, os

_LOG = os.environ["TDD_LOG"]  # read now: a test may clear os.environ
_SKIP = os.environ.get("TDD_SKIP")
_f = open(_LOG, "a", buffering=1)


def _emit(**kw):
    _f.write(json.dumps(kw) + "\\n")
    _f.flush()


def pytest_collectstart(collector):
    _emit(collect=collector.nodeid)


def pytest_collectreport(report):
    _emit(collected=report.nodeid)
    if report.failed:
        _emit(collect_error=report.nodeid)


def pytest_sessionfinish(session):
    _emit(done=1)


def pytest_collection_modifyitems(session, config, items):
    if not _SKIP or not os.path.exists(_SKIP):
        return
    skip = set(json.load(open(_SKIP)))
    keep = [i for i in items if i.nodeid not in skip]
    gone = [i for i in items if i.nodeid in skip]
    if gone:
        config.hook.pytest_deselected(items=gone)
        items[:] = keep


def pytest_runtest_logstart(nodeid, location):
    _emit(start=nodeid)


def pytest_runtest_logfinish(nodeid, location):
    _emit(finish=nodeid)


def pytest_runtest_logreport(report):
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
    _emit(id=report.nodeid, outcome=outcome)
'''
RANK = {"PASSED": 0, "SKIPPED": 1, "XFAIL": 1, "XPASS": 1, "FAILED": 2, "ERROR": 2, "TIMEOUT": 2, "CRASHED": 2}
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TDD_LOG=LOG, TDD_HARD=str(HARD_TEST),
           PYTHONPATH=PLUGIN_DIR + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""))


def _q(s):
    return "'" + s.replace("'", "'\\''") + "'"


def pytest(cmd, files, timeout=RUN_LIMIT, cwd="/testbed", skip=()):
    """1 pytest process. Returns (outcomes {nodeid: outcome}, collection errors, seconds, timed_out, stuck), where
    stuck is None or (kind, nodeid): ("hang", id) for a test that ran past the watchdog, ("crash", id) for a test
    the process died in, ("collect", node) for a collector that hung. The worst phase wins: PASSED only when setup, call, and teardown
    all passed; a failure outranks a skip."""
    os.makedirs(PLUGIN_DIR, exist_ok=True)
    with open(os.path.join(PLUGIN_DIR, "tdd_outcomes.py"), "w") as f:
        f.write(PLUGIN)
    for p in (LOG, SKIP):
        if os.path.exists(p):
            os.remove(p)
    env = dict(ENV)
    if skip:
        with open(SKIP, "w") as f:
            json.dump(sorted(skip), f)
        env["TDD_SKIP"] = SKIP
    m = re.search(r"--timeout[= ](\d+)", cmd)
    hard = max(float(env["TDD_HARD"]), 2 * int(m.group(1)) if m else 0)
    start = time.monotonic()
    p = subprocess.Popen(f"{cmd} -p tdd_outcomes -p no:cacheprovider --continue-on-collection-errors "
                         + " ".join(_q(f) for f in files), shell=True, cwd=cwd, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, env=env, executable="/bin/bash", start_new_session=True)
    timed_out, stuck, pos = False, None, 0
    running, collecting, since, done_at = None, None, None, None
    while True:
        exited = True
        try:
            p.wait(timeout=0.5)  # returns at once when pytest exits
        except subprocess.TimeoutExpired:
            exited = False
        now = time.monotonic()
        if os.path.exists(LOG):  # follow the log: what is running, and since when
            with open(LOG, encoding="utf-8", errors="replace") as f:  # json.dumps output is ASCII
                f.seek(pos)
                chunk = f.read()
            whole = chunk.rfind("\n") + 1
            pos += whole
            for line in chunk[:whole].splitlines():
                ev = _parse(line)
                if "start" in ev:
                    running, since = ev["start"], now
                elif "finish" in ev:
                    running = None
                elif "collect" in ev:
                    collecting, since = ev["collect"], now
                elif "collected" in ev:
                    collecting = None
                elif "done" in ev:
                    done_at = now
        if exited:
            if running is not None and done_at is None:
                stuck = ("crash", running)  # the process died inside this test
            break
        if running is not None and now - since > hard:
            stuck = ("hang", running)
        elif collecting is not None and now - since > hard:
            stuck = ("collect", collecting)
        elif done_at is not None and now - done_at > EXIT_GRACE:
            pass  # every test reported; the process just will not exit
        elif now - start > timeout:
            timed_out = True
            stuck = ("hang", running) if running else ("collect", collecting) if collecting else None
        else:
            continue
        os.killpg(p.pid, signal.SIGKILL)  # the whole group: tests may have spawned processes
        p.wait()
        break
    seconds = time.monotonic() - start
    out, errors = {}, []
    if os.path.exists(LOG):
        for line in open(LOG, encoding="utf-8", errors="replace"):
            ev = _parse(line)
            if "id" in ev:
                prev = out.get(ev["id"])
                out[ev["id"]] = ev["outcome"] if prev is None or RANK[ev["outcome"]] > RANK[prev] else prev
            elif "collect_error" in ev:
                errors.append(ev["collect_error"])
    return out, errors, seconds, timed_out, stuck


def _parse(line):
    try:
        return json.loads(line)
    except ValueError:
        return {}  # a line cut off by the kill


def run_all(cmd, files, cwd="/testbed"):
    """Every test's outcome: a test that hangs or crashes is TIMEOUT or CRASHED, a file whose collection hangs is a
    collection error, and the suite runs again without them (and without tests already decided) until a pass ends
    cleanly. Returns ({id: outcome}, collection errors, seconds)."""
    merged, errors, total, skip, files = {}, set(), 0.0, set(), list(files)
    for _ in range(1000):  # bounded: each pass that does not end cleanly removes at least 1 test or file
        out, errs, secs, timed_out, stuck = pytest(cmd, files, cwd=cwd, skip=skip)
        total += secs
        errors |= set(errs)
        if stuck is None:
            if timed_out:
                break  # hung outside any test or collector: keep only what reported before the run limit
            merged.update({k: v for k, v in out.items() if k not in merged})
            break
        kind, node = stuck
        merged.update({k: v for k, v in out.items() if k not in merged and k != node})
        if kind in ("hang", "crash"):
            if node in merged:
                break  # cannot happen: a decided test is deselected; stop rather than loop
            merged[node] = "TIMEOUT" if kind == "hang" else "CRASHED"
            skip = set(merged)
        else:
            gone = [f for f in files if f == node or f.startswith(node.rstrip("/") + "/") or node in ("", ".")]
            if not gone:
                break
            errors |= set(gone)
            files = [f for f in files if f not in gone]
            skip = set(merged)
            if not files:
                break
    return merged, sorted(errors), total


def outcomes(cmd, files, repeats, cwd="/testbed"):
    runs, secs, errs = [], [], []
    for _ in range(repeats):
        o, e, s = run_all(cmd, files, cwd=cwd)
        runs.append(o)
        errs.append(e)
        secs.append(s)
    return {"runs": runs, "seconds": secs, "collection_errors": errs}


def mutants(cmd, files, muts, ids, root="/testbed", skip=()):
    """Each mutant is killed when any test in `ids` is not PASSED, or the run times out or hangs. Tests in `skip`
    (those that hung or crashed on the reference) are deselected in every run. Only tests that also pass in this
    run of the same files on the unmutated reference count; any other is reported."""
    ref, _, ref_seconds, ref_timed_out, ref_stuck = pytest(cmd, files, cwd=root, skip=skip)
    if ref_timed_out or ref_stuck:
        ref = {}  # the subset reference run itself failed: no test can be trusted, so none counts
    dropped = sorted(i for i in ids if ref.get(i) != "PASSED")
    ids = [i for i in ids if ref.get(i) == "PASSED"]
    limit = max(3 * ref_seconds, ref_seconds + 10)
    results = []
    for m in muts if ids else []:
        path = os.path.join(root, m["path"])
        with open(path, "rb") as f:
            src = f.read()
        try:
            with open(path, "wb") as f:
                f.write(src[: m["start"]] + m["new"].encode() + src[m["end"]:])
            o, _, _, timed_out, stuck = pytest(cmd, files, timeout=limit, cwd=root, skip=skip)
        finally:
            with open(path, "wb") as f:
                f.write(src)
        failing = sorted(i for i in ids if o.get(i, "MISSING") != "PASSED")
        timeout = timed_out or stuck is not None
        results.append({"id": m["id"], "killed": timeout or bool(failing), "timeout": timeout, "failing": failing})
    if not ids:
        results = [{"id": m["id"], "killed": False, "timeout": False, "failing": []} for m in muts]
    return {"ref_seconds": ref_seconds, "limit_seconds": limit, "results": results, "used_ids": ids,
            "dropped_not_passing_in_subset": dropped}


if __name__ == "__main__":
    mode, cmd, files_path = sys.argv[1:4]
    files = json.load(open(files_path))
    if mode == "outcomes":
        res = outcomes(cmd, files, int(sys.argv[4]))
    else:
        skip = json.load(open(sys.argv[6])) if len(sys.argv) > 6 else []
        res = mutants(cmd, files, json.load(open(sys.argv[4]))["mutants"], json.load(open(sys.argv[5])), skip=skip)
    json.dump(res, sys.stdout)
