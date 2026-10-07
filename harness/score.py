"""Lock a suite against the stub, mark invalid and flaky tests on the reference, and run the mutants.
Every step runs in a new container with no network.
"""
import json
import os
import uuid

from harness import data, docker

ROOT = docker.ROOT
RUNNER = os.path.join(ROOT, "harness", "runner.py")


def _container(row, kind):
    return docker.start(docker.tag(row, kind), f"score-{kind}-{uuid.uuid4().hex[:8]}")


def _copy_tests(c, tests):
    paths = []
    for root, _, files in os.walk(tests):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), tests)
            docker.run(c, f"mkdir -p \"$(dirname '/testbed/{rel}')\"")
            docker.put(c, f"/testbed/{rel}", open(os.path.join(root, f), "rb").read())
            paths.append(rel)
    return sorted(paths)


def _runner(c, cmd, mode, files, *args, timeout=12 * 3600):
    docker.put(c, "/tmp/runner.py", open(RUNNER).read())
    docker.put(c, "/tmp/files.json", json.dumps(files))
    r = docker.run(c, f"{docker.CONDA} && python /tmp/runner.py {mode} {json.dumps(cmd)} /tmp/files.json "
                      + " ".join(str(a) for a in args), timeout=timeout)
    return json.loads(r.stdout)


test_cmd = data.test_cmd


def _file(nodeid):
    return nodeid.split("::", 1)[0]


def lock(row, run_dir, tests_dir):
    """Run the suite against the stub and keep the tests that fail or error there. A file that cannot even be
    collected against the stub fails by definition, so all its tests are kept and are identified on the reference."""
    c = _container(row, "stub")
    try:
        files = _copy_tests(c, tests_dir)
        res = _runner(c, test_cmd(row), "outcomes", files, 1) if files else {"runs": [{}], "collection_errors": [[]]}
    finally:
        docker.stop(c)
    outcome, collect_errors = res["runs"][0], res["collection_errors"][0]
    locked = sorted(i for i, o in outcome.items() if o in ("FAILED", "ERROR"))
    out = {"files": files, "stub_outcomes": outcome, "locked": locked, "locked_files": sorted(collect_errors),
           "dropped_passing": sum(o == "PASSED" for o in outcome.values()),
           "dropped_other": sum(o not in ("PASSED", "FAILED", "ERROR") for o in outcome.values())}
    json.dump(out, open(os.path.join(run_dir, "locked.json"), "w"), indent=1)
    return out


def validate_and_kill(row, test_dir, files, mutants, locked=None, locked_files=(), repeats=5, copy=True):
    """5 reference runs, then the valid tests against every mutant, in 1 reference container.

    The suite's tests are `locked` plus every test of `locked_files`; with locked=None (the human reference),
    every test the files hold."""
    c = _container(row, "ref")
    try:
        if copy:
            _copy_tests(c, test_dir)
        ref = _runner(c, test_cmd(row), "outcomes", files, repeats) if files else \
            {"runs": [], "seconds": [], "collection_errors": []}
        seen = {i for run in ref["runs"] for i in run}
        if locked is None:
            ids = sorted(seen)
        else:
            ids = sorted(set(locked) | {i for i in seen if _file(i) in set(locked_files)})
        valid = [i for i in ids if all(run.get(i) == "PASSED" for run in ref["runs"])]
        flaky = [i for i in ids if i not in valid and any(run.get(i) == "PASSED" for run in ref["runs"])]
        docker.put(c, "/tmp/mutants.json", json.dumps({"mutants": mutants}))
        docker.put(c, "/tmp/ids.json", json.dumps(valid))
        if valid:
            kills = _runner(c, test_cmd(row), "mutants", sorted({_file(i) for i in valid}), "/tmp/mutants.json",
                            "/tmp/ids.json")
        else:
            kills = {"ref_seconds": None, "results": [{"id": m["id"], "killed": False, "timeout": False, "failing": []}
                                                      for m in mutants]}
    finally:
        docker.stop(c)
    killed = [r for r in kills["results"] if r["killed"]]
    return {
        "reference_runs": ref, "tests": ids, "valid": valid, "flaky": flaky, "kills": kills,
        "mutation_score": 100 * len(killed) / len(mutants),
        "invalid_rate": 100 * (len(ids) - len(valid)) / len(ids) if ids else 0.0,
        "suite_size": len(valid),
        "flaky_count": len(flaky),
        "timeout_kills": sum(r["timeout"] for r in killed),
        "killed_ids": sorted(r["id"] for r in killed),
    }


def score(row, run_dir, mutants, tests_dir):
    locked = lock(row, run_dir, tests_dir)
    res = validate_and_kill(row, tests_dir, locked["files"], mutants, locked["locked"], locked["locked_files"])
    res["dropped_passing"] = locked["dropped_passing"]
    json.dump(res, open(os.path.join(run_dir, "score.json"), "w"), indent=1)
    return res


def score_human(row, out_dir, mutants):
    """FeatureBench's fail-to-pass tests against the same mutants (they are in the reference image)."""
    os.makedirs(out_dir, exist_ok=True)
    res = validate_and_kill(row, out_dir, list(row["FAIL_TO_PASS"]), mutants, copy=False)
    json.dump(res, open(os.path.join(out_dir, "human_score.json"), "w"), indent=1)
    return res
