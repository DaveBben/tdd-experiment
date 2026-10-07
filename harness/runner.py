"""Runs inside a task container (stdlib only, the container's Python): test outcomes and mutant kills.

    python runner.py outcomes TEST_CMD TARGETS.json REPEATS      -> {"runs": [{nodeid: outcome}], "seconds": [...]}
    python runner.py mutants TEST_CMD IDS.json MUTANTS.json      -> {"ref_seconds": s, "results": [{id, killed, timeout}]}

Outcomes come from pytest's `-rA` summary lines, as FeatureBench reads them.
A run with no summary line for a test counts it as failed.
"""
import json
import os
import re
import subprocess
import sys
import time

LINE = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (\S+)")
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def pytest(cmd, targets, timeout=None):
    """({nodeid: outcome}, seconds, timed_out). Targets are test files or node IDs; a node ID target
    with no summary line is reported as MISSING."""
    start = time.monotonic()
    try:
        p = subprocess.run(f"{cmd} -p no:cacheprovider " + " ".join(_q(t) for t in targets), shell=True, cwd="/testbed",
                           capture_output=True, text=True, timeout=timeout, env=ENV, executable="/bin/bash")
    except subprocess.TimeoutExpired:
        return {}, time.monotonic() - start, True
    out = {}
    for line in p.stdout.splitlines():
        m = LINE.match(line)
        if m:
            # ERROR in teardown after PASSED: the test is not clean.
            out[m.group(2)] = m.group(1) if out.get(m.group(2)) in (None, "PASSED") else out[m.group(2)]
    for t in targets:
        if "::" in t:
            out.setdefault(t, "MISSING")
    return out, time.monotonic() - start, False


def _q(s):
    return "'" + s.replace("'", "'\\''") + "'"


def outcomes(cmd, targets, repeats):
    runs, secs = [], []
    for _ in range(repeats):
        o, s, _ = pytest(cmd, targets)
        runs.append(o)
        secs.append(s)
    return {"runs": runs, "seconds": secs}


def mutants(cmd, ids, muts):
    _, ref_seconds, _ = pytest(cmd, ids)
    results = []
    for m in muts:
        path = os.path.join("/testbed", m["path"])
        with open(path, "rb") as f:
            src = f.read()
        try:
            with open(path, "wb") as f:
                f.write(src[: m["start"]] + m["new"].encode() + src[m["end"]:])
            o, _, timed_out = pytest(cmd, ids, timeout=max(3 * ref_seconds, ref_seconds + 10))
        finally:
            with open(path, "wb") as f:
                f.write(src)
        o = {i: o.get(i, "MISSING") for i in ids}
        killed = timed_out or any(v != "PASSED" for v in o.values())
        results.append({"id": m["id"], "killed": killed, "timeout": timed_out,
                        "failing": sorted(k for k, v in o.items() if v != "PASSED")})
    return {"ref_seconds": ref_seconds, "results": results}


if __name__ == "__main__":
    mode, cmd, ids_path = sys.argv[1:4]
    ids = json.load(open(ids_path))
    if mode == "outcomes":
        res = outcomes(cmd, ids, int(sys.argv[4]))
    else:
        res = mutants(cmd, ids, json.load(open(sys.argv[4]))["mutants"])
    json.dump(res, sys.stdout)
