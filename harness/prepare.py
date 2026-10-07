"""Prepare a task: the `-stub` image for agent sessions, the `-ref` image for scoring, the filter checks,
and the mutant sample. Writes tasks/<task>/{spec.md, stub.diff, filter.json, mutants.json, added.json}.

    bin/h python -m harness.prepare TASK_ID [TASK_ID ...]
"""
import collections
import json
import math
import re
import os
import sys
import uuid

from harness import data, docker, stub

ROOT = docker.ROOT
TB = "/testbed"


def undevelop(c, row):
    """Mirror FeatureBench's inference preparation: removal patch applied, F2P tests, the second copy,
    bytecode, and history removed."""
    docker.put(c, "/tmp/removal.patch", row["patch"])
    f2p = " ".join(f"'{f}'" for f in row["FAIL_TO_PASS"])
    # FeatureBench's environment fix (featurebench/environment_fixes/mlflow.py): parallel package copies.
    extra = f"{TB}/libs/skinny/mlflow {TB}/libs/tracing/mlflow" if row["repo"] == "mlflow/mlflow" else ""
    docker.run(c, f"""set -e
cd {TB} && git apply --whitespace=nowarn /tmp/removal.patch && rm -f {f2p} /tmp/removal.patch
rm -rf /root/my_repo {TB}/.git {extra}
find / -xdev -name __pycache__ -type d -prune -exec rm -rf {{}} + 2>/dev/null || true
# Caches and environments that can hold a released copy of the package (wheels, conda packages, a 2nd env).
rm -rf /root/.cache /opt/miniconda3/pkgs
for env in /opt/miniconda3/envs/*; do [ "$(basename "$env")" = testbed ] || rm -rf "$env"; done""")


def git_snapshot(c):
    docker.run(c, f"""set -e
cd {TB} && git init -q && git add -A && git -c user.name=tdd -c user.email=tdd@local commit -qm undeveloped""")


def run_tests(c, cmd, files, timeout=1800):
    """{exit, failing: [node IDs that failed or errored], summary: pytest's last line}."""
    files = " ".join(f"'{f}'" for f in files)
    r = docker.run(c, f"{docker.CONDA} && {cmd} {files}", check=False, timeout=timeout)
    failing = sorted({m.group(2) for m in re.finditer(r"(?m)^(FAILED|ERROR) (\S+)", r.stdout)})
    lines = r.stdout.strip().splitlines()
    return {"exit": r.returncode, "failing": failing, "summary": lines[-1] if lines else ""}


def can_import(c, path):
    """True when the module at `path` imports, trying each dotted suffix of the path."""
    parts = path[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    tries = [".".join(parts[i:]) for i in range(len(parts))]
    script = "import importlib,sys\nfor m in %r:\n    try:\n        importlib.import_module(m); sys.exit(0)\n" \
             "    except ModuleNotFoundError: pass\nsys.exit(1)" % tries
    docker.put(c, "/tmp/can_import.py", script)
    return docker.run(c, f"{docker.CONDA} && python /tmp/can_import.py; r=$?; rm /tmp/can_import.py; exit $r",
                      check=False).returncode == 0


LEAK_MIN_CHARS = 30


def leak_candidates(row, spec_text):
    """{gold-patched .py file: its distinctive added lines}: stripped, at least 30 characters, not in the spec.
    Lines also present anywhere in the undeveloped repository are removed later, inside the container."""
    spec_lines = {l.strip() for l in spec_text.split("\n")}
    out = {}
    for path, block in data._file_blocks(data.gold_patch(row)):
        lines = set()
        for line in block.split("\n"):
            if line.startswith("-") and not line.startswith("---"):
                t = line[1:].strip()
                if len(t) >= LEAK_MIN_CHARS and t not in spec_lines:
                    lines.add(t)
        if path.endswith(".py") and lines:
            out[path] = sorted(lines)
    return out


def leak_threshold(n):
    """Lines of 1 gold file that a file must hold to count as a copy of it."""
    return min(10, max(3, math.ceil(0.25 * n)))


F2P_MAX_GOLD_FAIL = 0.05


def f2p_count(r):
    m = re.search(r"(\d+) passed", r["gold_f2p"]["summary"])
    return (int(m.group(1)) if m else 0) + len(r["gold_f2p"]["failing"])


def decide(r):
    """The task filter (EXPERIMENT.md "Objects", steps 1-3), from a recorded filter report.

    Tests that fail on the gold patch in this container fail for the environment (mostly network access),
    on gold and stub alike, so they are excluded rather than dropping the task."""
    n_f2p = f2p_count(r)
    gold_ok = n_f2p > 0 and len(r["gold_f2p"]["failing"]) <= F2P_MAX_GOLD_FAIL * n_f2p
    stub_breaks = set(r["stub_p2p"]["failing"]) - set(r["gold_p2p"]["failing"])
    return gold_ok and r["stub_compiles"] and r["stub_imports"] and not stub_breaks and not leaks(r)


def leaks(r):
    """Files holding a copy of a gold file, and unscanned archives named after the package. A task none of whose
    gold files has the 3 distinctive lines a copy must show cannot be checked, and counts as leaking."""
    n = r["leak_candidates"]
    if not any(k >= 3 for k in n.values()):
        return ["no gold file has 3 distinctive lines to search for"]
    found = [f"{p} <- {g}" for p, d in r["leak_hits"].items() for g, k in d.items() if k >= leak_threshold(n[g])]
    lib = r["library"].lower().replace("-", "_")
    return found + [a for a in r["unscanned_archives"] if lib in os.path.basename(a).lower().replace("-", "_")]


def prepare(task_id, rows, seed):
    row = rows[task_id]
    out = os.path.join(ROOT, "tasks", task_id)
    os.makedirs(out, exist_ok=True)
    cmd = data.test_cmd(row)
    spec_text = data.spec(row)
    open(os.path.join(out, "spec.md"), "w").write(spec_text)
    report = {"task": task_id, "image": docker.image_ref(row), "test_cmd": cmd}

    # Reference: undeveloped + gold patch (reversed removal), with the F2P tests restored for scoring.
    ref = docker.start(docker.image_ref(row), f"prep-ref-{uuid.uuid4().hex[:8]}")
    try:
        undevelop(ref, row)
        docker.put(ref, "/tmp/gold.patch", data.gold_patch(row))
        docker.put(ref, "/tmp/test.patch", row["test_patch"])
        docker.run(ref, f"cd {TB} && git apply -R --whitespace=nowarn /tmp/gold.patch /tmp/test.patch && rm /tmp/*.patch")
        report["gold_f2p"] = run_tests(ref, cmd, row["FAIL_TO_PASS"])
        report["gold_p2p"] = run_tests(ref, cmd, row["PASS_TO_PASS"])
        added = {p: sorted(v) for p, v in data.gold_added_lines(row).items()}
        json.dump(added, open(os.path.join(out, "added.json"), "w"))
        docker.put(ref, "/tmp/mutate.py", open(os.path.join(ROOT, "harness", "mutate.py")).read())
        docker.put(ref, "/tmp/added.json", json.dumps(added))
        m = docker.run(ref, f"{docker.CONDA} && python /tmp/mutate.py {TB} /tmp/added.json {seed} {task_id}"
                            " && rm /tmp/mutate.py /tmp/added.json")
        open(os.path.join(out, "mutants.json"), "w").write(m.stdout)
        report["mutant_pool"] = json.loads(m.stdout)["pool"]
        docker.sh("commit", ref, docker.tag(row, "ref"))
    finally:
        docker.stop(ref)

    # Stub: undeveloped + scripted stub, 1 git commit.
    st = docker.start(docker.image_ref(row), f"prep-stub-{uuid.uuid4().hex[:8]}")
    try:
        undevelop(st, row)
        by_path = collections.defaultdict(list)
        for path, code in data.interfaces(spec_text):
            by_path[path].append(code)
        diff = []
        for path, codes in sorted(by_path.items()):
            before = (docker.get(st, f"{TB}/{path}") or b"").decode()
            after = stub.build(before, codes)
            docker.run(st, f"mkdir -p \"$(dirname '{TB}/{path}')\"")
            docker.put(st, f"{TB}/{path}", after)
            diff.append(f"=== {path}\n{after}")
        open(os.path.join(out, "stub.txt"), "w").write("\n".join(diff))
        report["stub_compiles"] = docker.run(
            st, f"{docker.CONDA} && python -m py_compile " + " ".join(f"'{p}'" for p in by_path), check=False
        ).returncode == 0
        report["stub_imports"] = all(can_import(st, p) for p in by_path)
        report["stub_p2p"] = run_tests(st, cmd, row["PASS_TO_PASS"])
        docker.run(st, f"find {TB} -name __pycache__ -type d -prune -exec rm -rf {{}} + ; rm -rf {TB}/.pytest_cache")
        git_snapshot(st)
        cands = leak_candidates(row, spec_text)
        # Drop lines the undeveloped repository itself holds anywhere: they show nothing about a leak.
        docker.put(st, "/tmp/cand.txt", "\n".join({l for ls in cands.values() for l in ls}) + "\n")
        # Whole matching lines, then a substring test here: grep -o reports only the longest of overlapping patterns.
        repo_lines = docker.run(st, f"cd {TB} && git ls-files -z | LC_ALL=C xargs -0 grep -hF -f /tmp/cand.txt 2>/dev/null;"
                                    " rm /tmp/cand.txt", check=False).stdout.splitlines()
        every = {l for ls in cands.values() for l in ls}
        present = {cand for cand in every if any(cand in line for line in repo_lines)}
        cands = {g: [l for l in ls if l not in present] for g, ls in cands.items()}
        docker.put(st, "/tmp/leakscan.py", open(os.path.join(ROOT, "harness", "leakscan.py")).read())
        docker.put(st, "/tmp/cands.json", json.dumps(cands))
        scan = json.loads(docker.run(st, f"{docker.CONDA} && python /tmp/leakscan.py /tmp/cands.json;"
                                         " rm /tmp/leakscan.py /tmp/cands.json", timeout=7200).stdout)
        report["library"] = row["repo_settings"].get("library_name") or row["repo"].split("/")[1]
        report["leak_candidates"] = {g: len(ls) for g, ls in cands.items()}
        report["leak_hits"] = scan["hits"]
        report["unscanned_archives"] = scan["unscanned_archives"]
        docker.sh("commit", st, docker.tag(row, "stub"))
    finally:
        docker.stop(st)

    report["keep"] = decide(report)
    json.dump(report, open(os.path.join(out, "filter.json"), "w"), indent=1)
    return report


if __name__ == "__main__":
    rows = data.load_rows()
    seed = int(open(os.path.join(ROOT, "draws", "mutants.seed")).read())
    for t in sys.argv[1:]:
        r = prepare(t, rows, seed)
        print(t, "keep" if r["keep"] else "drop")
