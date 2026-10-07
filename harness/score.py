"""Lock a suite against the stub, mark invalid and flaky tests on the reference, and run the mutants.
Every step runs in a new container with no network.
"""
import json
import os
import uuid

from harness import docker

ROOT = docker.ROOT
RUNNER = os.path.join(ROOT, "harness", "runner.py")


def _container(row, kind):
    return docker.start(docker.tag(row, kind), f"score-{kind}-{uuid.uuid4().hex[:8]}")


def _copy_tests(c, run_dir):
    tests = os.path.join(run_dir, "tests")
    paths = []
    for root, _, files in os.walk(tests):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), tests)
            docker.run(c, f"mkdir -p \"$(dirname '/testbed/{rel}')\"")
            docker.put(c, f"/testbed/{rel}", open(os.path.join(root, f), "rb").read())
            paths.append(rel)
    return sorted(paths)


def _runner(c, cmd, mode, targets, arg):
    docker.put(c, "/tmp/runner.py", open(RUNNER).read())
    docker.put(c, "/tmp/targets.json", json.dumps(targets))
    r = docker.run(c, f"{docker.CONDA} && python /tmp/runner.py {mode} {json.dumps(cmd)} /tmp/targets.json {arg}")
    return json.loads(r.stdout)


def test_cmd(row):
    s = row["repo_settings"]
    return f"{s['test_cmd']} --timeout={s['timeout_one']}"


def lock(row, run_dir):
    """Run the suite against the stub; keep only the tests that fail (or error) there."""
    c = _container(row, "stub")
    try:
        files = _copy_tests(c, run_dir)
        outcome = _runner(c, test_cmd(row), "outcomes", files, 1)["runs"][0] if files else {}
    finally:
        docker.stop(c)
    locked = sorted(i for i, o in outcome.items() if "::" in i and o in ("FAILED", "ERROR"))
    res = {"files": files, "stub_outcomes": outcome, "locked": locked,
           "dropped_passing": sum(o == "PASSED" for i, o in outcome.items() if "::" in i)}
    json.dump(res, open(os.path.join(run_dir, "locked.json"), "w"), indent=1)
    return res


def validate_and_kill(row, test_dir, targets, mutants, repeats=5, copy=True):
    """5 reference runs, then the valid tests against every mutant, in 1 reference container."""
    c = _container(row, "ref")
    try:
        if copy:
            _copy_tests(c, test_dir)
        ref = _runner(c, test_cmd(row), "outcomes", targets, repeats) if targets else {"runs": [], "seconds": []}
        ids = sorted({i for run in ref["runs"] for i in run if "::" in i})
        valid = [i for i in ids if all(run.get(i) == "PASSED" for run in ref["runs"])]
        flaky = [i for i in ids if i not in valid and any(run.get(i) == "PASSED" for run in ref["runs"])]
        docker.put(c, "/tmp/mutants.json", json.dumps({"mutants": mutants}))
        kills = _runner(c, test_cmd(row), "mutants", valid, "/tmp/mutants.json") if valid else \
            {"ref_seconds": None, "results": [{"id": m["id"], "killed": False, "timeout": False, "failing": []} for m in mutants]}
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


def score(row, run_dir, mutants):
    locked = lock(row, run_dir)
    res = validate_and_kill(row, run_dir, locked["locked"], mutants)
    res["dropped_passing"] = locked["dropped_passing"]
    json.dump(res, open(os.path.join(run_dir, "score.json"), "w"), indent=1)
    return res


def score_human(row, out_dir, mutants):
    """FeatureBench's fail-to-pass tests against the same mutants (they are in the reference image)."""
    res = validate_and_kill(row, out_dir, list(row["FAIL_TO_PASS"]), mutants, copy=False)
    json.dump(res, open(os.path.join(out_dir, "human_score.json"), "w"), indent=1)
    return res
