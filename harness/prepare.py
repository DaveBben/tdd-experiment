"""Prepare a task: the `-stub` image for agent sessions, the `-ref` image for scoring, the filter checks,
and the mutant sample. Writes tasks/<task>/{spec.md, stub.diff, filter.json, mutants.json, added.json}.

    bin/h python -m harness.prepare TASK_ID [TASK_ID ...]
"""
import collections
import json
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
find / -xdev -name __pycache__ -type d -prune -exec rm -rf {{}} + 2>/dev/null || true""")


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


def leak_lines(row, spec_text, undeveloped):
    """The 20 longest distinct gold-added lines that appear neither in the spec every arm receives nor
    in the undeveloped, stubbed versions of the files the gold patch changes."""
    spec_lines = {l.strip() for l in spec_text.split("\n")}
    spec_lines |= {l.strip() for text in undeveloped for l in text.split("\n")}
    added = set()
    for path, block in data._file_blocks(data.gold_patch(row)):
        for line in block.split("\n"):
            if line.startswith("-") and not line.startswith("---"):
                s = line[1:].strip()
                if s and s not in spec_lines:
                    added.add(s)
    return sorted(added, key=lambda s: (-len(s), s))[:20]


def decide(r):
    """The task filter (EXPERIMENT.md "Objects", steps 1-3), from a recorded filter report."""
    return (r["gold_f2p"]["exit"] == 0 and r["gold_p2p"]["exit"] == 0 and r["stub_compiles"] and r["stub_imports"]
            and r["stub_p2p"]["exit"] == 0 and not r["leak_hits"])


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
        undeveloped = [(docker.get(st, f"{TB}/{p}") or b"").decode(errors="replace")
                       for p, _ in data._file_blocks(data.gold_patch(row))]
        lines = leak_lines(row, spec_text, undeveloped)
        docker.put(st, "/tmp/leak.txt", "\n".join(lines) + "\n")
        out_ = docker.run(st, "grep -rIoF -f /tmp/leak.txt / --exclude-dir=proc --exclude-dir=sys --exclude-dir=dev"
                              " 2>/dev/null; rm /tmp/leak.txt", check=False).stdout
        tracked = set(docker.run(st, f"cd {TB} && git ls-files").stdout.split("\n"))
        matched = collections.defaultdict(set)
        for line in out_.splitlines():
            path, _, text = line.partition(":")
            if path != "/tmp/leak.txt":
                matched[path].add(text)
        # Per file: how many of the candidate lines it holds, and whether it is tracked undeveloped source.
        report["leak_lines"] = len(lines)
        report["leak_hits"] = {p: {"lines": len(v), "tracked": p.startswith(TB + "/") and p[len(TB) + 1:] in tracked}
                               for p, v in sorted(matched.items())}
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
