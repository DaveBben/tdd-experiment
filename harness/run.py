"""Orchestrator: filter tasks, draw, run sessions in the drawn order, score, and keep the ledger.

    bin/h python -m harness.run filter [REPO_PREFIX ...]        prepare + filter every task (of those repos)
    bin/h python -m harness.run draw-pilot                      -> draws/pilot.txt
    bin/h python -m harness.run draw-experiment N               -> draws/experiment.txt, draws/replacements.txt
    bin/h python -m harness.run sessions MODEL TASKS RUNS OUT [--aa] [--budget USD] [--stop-at ISO] [--no-c]
    bin/h python -m harness.run score TASKS OUT
    bin/h python -m harness.run ledger

Layout: OUT/<task>/<arm>/<run>/attempt-<k>/ holds 1 session's raw outputs; OUT/<task>/<arm>/<run>/
holds manifest.json, locked.json, and score.json for the attempt that counts.
"""
import concurrent.futures
import datetime
import fcntl
import glob
import hashlib
import json
import os
import random
import subprocess
import sys
import time
import traceback

from harness import checks, data, docker, prepare, score, session

ROOT = docker.ROOT
CAP_PER_REPO = 5
API_BACKOFF = 600
HALT_AFTER = 3  # consecutive pair errors: something is down, so stop instead of burning through pairs
REPLACEMENTS = 5
START_MARGIN = 20 * 60


def seed(name):
    return int(open(os.path.join(ROOT, "draws", f"{name}.seed")).read())


def repo(task):
    return task.split(".")[0]


def harness_commit():
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", ROOT, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


# --- filtering and draws --------------------------------------------------------

def cmd_filter(prefixes):
    """Prepare and filter tasks 1 image at a time. Images stay cached for the pilot and main run."""
    rows = data.load_rows()
    by_image = {}
    for t in sorted(rows):
        if (not prefixes or any(t.startswith(p) for p in prefixes)) and \
                not os.path.exists(os.path.join(ROOT, "tasks", t, "filter.json")):
            by_image.setdefault(docker.image_ref(rows[t]), []).append(t)
    for image, tasks in sorted(by_image.items()):
        docker.sh("pull", "--platform", "linux/amd64", image)
        for t in tasks:
            r = prepare.prepare(t, rows, seed("mutants"))
            print(t, "keep" if r["keep"] else "drop", {k: r[k]["exit"] for k in ("gold_f2p", "gold_p2p", "stub_p2p")},
              "leak files:", len(r["leak_hits"]), flush=True)


def ensure_prepared(row):
    """Re-create a drawn task's images when they were removed after filtering; preparation is deterministic."""
    if docker.sh("image", "inspect", docker.tag(row, "ref"), check=False).returncode == 0:
        return
    docker.sh("pull", "--platform", "linux/amd64", docker.image_ref(row))
    before = json.load(open(os.path.join(ROOT, "tasks", row["instance_id"], "filter.json")))
    mutants = open(os.path.join(ROOT, "tasks", row["instance_id"], "mutants.json")).read()
    after = prepare.prepare(row["instance_id"], {row["instance_id"]: row}, seed("mutants"))
    assert after["keep"] == before["keep"] and \
        open(os.path.join(ROOT, "tasks", row["instance_id"], "mutants.json")).read() == mutants, "preparation changed"


def kept_tasks():
    """Every task the filter keeps, decided afresh from its recorded report by the committed rule."""
    reports = [json.load(open(p)) for p in glob.glob(os.path.join(ROOT, "tasks", "*", "filter.json"))]
    assert len(reports) == 100, f"only {len(reports)} of 100 tasks filtered"
    return sorted(r["task"] for r in reports if prepare.decide(r))


def cmd_draw_pilot():
    kept = kept_tasks()
    random.Random(seed("pilot")).shuffle(kept)
    _write("pilot.txt", kept[:3])


def draw_order(pilot, rest, cap):
    per_repo, order = {}, []
    for t in pilot:
        per_repo[repo(t)] = per_repo.get(repo(t), 0) + 1
    for t in rest:
        if per_repo.get(repo(t), 0) < cap:
            per_repo[repo(t)] = per_repo.get(repo(t), 0) + 1
            order.append(t)
    return order


def cmd_draw_experiment(n):
    """EXPERIMENT.md "Objects" step 6: the per-repository limit is the smallest k >= 5 that yields n tasks plus
    REPLACEMENTS replacements; when no k does, every kept task is used and the shortfall is reported."""
    pilot = open(os.path.join(ROOT, "draws", "pilot.txt")).read().split()
    rest = [t for t in kept_tasks() if t not in pilot]
    random.Random(seed("experiment")).shuffle(rest)
    cap = CAP_PER_REPO
    while len(draw_order(pilot, rest, cap)) < n + REPLACEMENTS and cap < len(rest):
        cap += 1
    order = draw_order(pilot, rest, cap)
    print(f"per-repository limit {cap}: {len(order)} tasks available for n={n}")
    _write("experiment.txt", order[:n])
    _write("replacements.txt", order[n:])


def _write(name, tasks):
    open(os.path.join(ROOT, "draws", name), "w").write("\n".join(tasks) + "\n")
    print(f"draws/{name}: {len(tasks)} tasks")


# --- sessions -------------------------------------------------------------------

def run_arm(row, arm, model, run_dir, spec_text, note=None, check=None):
    """Run 1 arm, rerunning once after a crash or a failed check. Returns (attempt_dir, manifest)."""
    # Raw outputs are never overwritten: an attempt left by an interrupted harness keeps its directory.
    prior = len(glob.glob(os.path.join(run_dir, "attempt-*")))
    reason = "harness interrupted" if prior else None
    for tries in (1, 2):
        attempt = prior + tries
        adir = os.path.join(run_dir, f"attempt-{attempt}")
        info = session.run_session(row, arm, model, adir, spec_text, note)
        if any(ph.get("limit_reached") == "deadline" for ph in info["phases"]):
            return adir, {"attempt": attempt, "rerun_reason": reason, "excluded": "stopped at the deadline"}
        if (info["crashed"] or "").startswith(("harness error", "collect error")):
            # The harness, not the agent, failed: write no manifest, so the pair is retried on resume.
            raise RuntimeError(info["crashed"])
        if tries == 1 and (info["crashed"] or "").startswith("final response error"):
            time.sleep(API_BACKOFF)  # an API outage outlasted Pi's retries; give it time before the 1 rerun
        problem = info["crashed"] or (check(adir) if check else None)
        if not problem:
            return adir, {"attempt": attempt, "rerun_reason": reason, "excluded": None}
        reason = problem
    return adir, {"attempt": attempt, "rerun_reason": reason, "excluded": f"failed twice: {reason}"}


def design_check(spec_text):
    def check(adir):
        note = _read(os.path.join(adir, "design_note.md"))
        ok, reasons = checks.design_note_ok(note, spec_text)
        if not ok:
            return "design note: " + "; ".join(reasons)
        if not checks.no_compaction(os.path.join(adir, "session.jsonl")):
            return "design note not kept: compaction"
        return None
    return check


def write_manifest(row, model, run_dir, adir, extra):
    info = json.load(open(os.path.join(adir, "session.json")))
    phases = info["phases"]
    m = {"harness_commit": harness_commit(), "seed": seed("order"), "started_at": info["started_at"],
         "finished_at": info["finished_at"], "image": docker.image_ref(row), "model_id": info["model"],
         "thinking": info["thinking"], "cpus": docker.CPUS, "memory": docker.MEMORY,
         "attempt_dir": os.path.basename(adir), "turns": sum(p["turns"] for p in phases),
         "input_tokens": sum(p["input"] for p in phases), "output_tokens": sum(p["output"] for p in phases),
         "cache_read_tokens": sum(p["cache_read"] for p in phases), "cost": sum(p["cost"] for p in phases),
         "limit_reached": [p["limit_reached"] for p in phases], **extra}
    score.write_json(os.path.join(run_dir, "manifest.json"), m)


def excluded_manifest(run_dir, reason):
    os.makedirs(run_dir, exist_ok=True)
    score.write_json(os.path.join(run_dir, "manifest.json"), {
        "harness_commit": harness_commit(), "seed": seed("order"), "started_at": None, "finished_at": None,
        "excluded": reason})


def cmd_setup(tasks_file):
    """Prepare (if needed) and build every drawn task's images once, before parallel runs start."""
    rows = data.load_rows()
    for m in session.MODELS:
        session.ensure_gateway(m)
    for task in open(tasks_file).read().split():
        ensure_prepared(rows[task])
        session.build_agent_image(rows[task])
        print("ready", task, flush=True)


def spent(out):
    """Spend over every session, reruns included."""
    total = 0.0
    for p in glob.glob(os.path.join(out, "*", "*", "*", "attempt-*", "session.json")):
        total += sum(ph.get("cost") or 0 for ph in json.load(open(p)).get("phases", []))
    return total


def cmd_sessions(model, tasks_file, runs, out, aa=False, budget=None, stop_at=None, arm_c=True):
    """stop_at: epoch seconds. No pair starts within START_MARGIN of it, and a pair still running then is
    stopped and excluded."""
    rows = data.load_rows()
    tasks = open(tasks_file).read().split()
    rng = random.Random(f"{seed('order')}:{model}")
    pairs = [(t, r) for t in tasks for r in range(1, runs + 1)]
    rng.shuffle(pairs)
    later = ["B"] + (["C"] if arm_c else []) + (["B2"] if aa else [])
    session.DEADLINE = stop_at
    orders = [rng.sample(later, len(later)) for _ in pairs]
    session.ensure_gateway(model)
    for task in tasks:
        session.build_agent_image(rows[task])  # cached and cheap; guarantees the image matches the prepared stub
    errors_in_a_row = 0
    for (task, r), order in zip(pairs, orders):
        row = rows[task]
        if budget is not None and spent(out) >= budget:
            print(f"BUDGET STOP: spent {spent(out):.2f} of {budget}", flush=True)
            return
        if stop_at is not None and time.time() >= stop_at - START_MARGIN:
            print("DEADLINE STOP", flush=True)
            return
        spec_text = open(os.path.join(ROOT, "tasks", task, "spec.md")).read()
        base = lambda arm: os.path.join(out, task, arm, str(r))
        done = lambda arm: os.path.exists(os.path.join(base(arm), "manifest.json"))
        if all(done(a) for a in ["A", *order]):
            continue
        print(f"{task} run {r}: A then {order}", flush=True)
        try:
            run_pair(row, model, base, order, spec_text, done)
        except Exception as e:  # noqa: BLE001 - log it and go on; the pair stays incomplete and is visible
            errors_in_a_row += 1
            print(f"PAIR ERROR {task} run {r}: {e!r}\n{traceback.format_exc()}", flush=True)
            if errors_in_a_row >= HALT_AFTER:
                print(f"HALT: {HALT_AFTER} pair errors in a row", flush=True)
                return
            time.sleep(API_BACKOFF)
            continue
        errors_in_a_row = 0
        print(f"done {task} run {r}; spent {spent(out):.2f}", flush=True)
        cmd_ledger()


def run_pair(row, model, base, order, spec_text, done):
    if done("A"):
        extra = json.load(open(os.path.join(base("A"), "manifest.json")))
        adir = os.path.join(base("A"), extra.get("attempt_dir", ""))
    else:
        adir, extra = run_arm(row, "A", model, base("A"), spec_text, check=design_check(spec_text))
        write_manifest(row, model, base("A"), adir, extra)
    if extra["excluded"]:
        for arm in [a for a in order if not done(a)]:
            excluded_manifest(base(arm), "pair excluded: arm A " + extra["excluded"])
        return
    note = _read(os.path.join(adir, "design_note.md"))
    for arm in order:
        if done(arm):
            continue
        pi_arm = "B" if arm == "B2" else arm
        bdir, bextra = run_arm(row, pi_arm, model, base(arm), spec_text, note=note if arm == "C" else None)
        try:
            bextra["isolation_suspects"] = checks.isolation_suspects(
                row, os.path.join(bdir, "session.jsonl"), os.path.join(bdir, "container_diff.txt"))
        except Exception as e:  # noqa: BLE001 - an unchecked session cannot be trusted
            bextra["isolation_suspects"] = None
            bextra["isolation_check_error"] = repr(e)
            bextra["excluded"] = bextra["excluded"] or "isolation check could not run"
        if bextra["isolation_suspects"] and not bextra["excluded"]:
            bextra["excluded"] = "isolation check"
        write_manifest(row, model, base(arm), bdir, bextra)


# --- scoring --------------------------------------------------------------------

SCORE_WORKERS = 8  # pytest is single-threaded; the VM has 12 cores, and a scorer needs under 1 GB


def cmd_score(tasks_file, *outs, workers=SCORE_WORKERS):
    """Score every unscored, non-excluded run under each OUT, and each task's human reference once, in parallel.
    Each job runs in its own container and writes only its own files."""
    rows = data.load_rows()
    jobs = []
    for task in open(tasks_file).read().split():
        row = rows[task]
        ensure_prepared(row)
        mutants = json.load(open(os.path.join(ROOT, "tasks", task, "mutants.json")))["mutants"]
        hdir = os.path.join(ROOT, "runs", "human", task)  # model-independent, scored once per task
        if not os.path.exists(os.path.join(hdir, "human_score.json")):
            jobs.append((f"human {task}", score.score_human, (row, hdir, mutants)))
        for out in outs:
            for mpath in sorted(glob.glob(os.path.join(out, task, "*", "*", "manifest.json"))):
                run_dir = os.path.dirname(mpath)
                m = json.load(open(mpath))
                if m.get("excluded") or os.path.exists(os.path.join(run_dir, "score.json")):
                    continue
                jobs.append((run_dir, score.score, (row, run_dir, mutants, os.path.join(run_dir, m["attempt_dir"], "tests"))))
    print(f"scoring {len(jobs)} jobs with {workers} workers", flush=True)

    def work(job):
        name, fn, args = job
        try:
            fn(*args)
            print("scored", name, flush=True)
        except Exception as e:  # noqa: BLE001 - an unscored run stays visible as a missing score.json
            print(f"SCORE ERROR {name}: {e!r}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        list(pool.map(work, jobs))
    cmd_ledger()


# --- ledger ---------------------------------------------------------------------

def cmd_ledger(runs_dir="runs", ledger="runs.sha256"):
    """Append a hash for every file under runs/ not yet in the ledger. Never rewrites a line."""
    runs_dir, ledger = os.path.join(ROOT, runs_dir), os.path.join(ROOT, ledger)
    lock = open(ledger + ".lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)  # the 2 models' runs append concurrently
    have = set()
    if os.path.exists(ledger):
        have = {l.split("  ", 1)[1].strip() for l in open(ledger) if l.strip()}
    new = []
    for root, _, files in os.walk(runs_dir):
        # A session still being written has no manifest yet: hash its files once its run is finished.
        parts = os.path.relpath(root, runs_dir).split(os.sep)
        attempt = next((i for i, p in enumerate(parts) if p.startswith("attempt-")), None)
        if attempt is not None and not os.path.exists(os.path.join(runs_dir, *parts[:attempt], "manifest.json")):
            continue
        for f in sorted(files):
            if ".tmp-" in f or f.endswith(".lock"):
                continue  # an atomic write in progress, or a lock: not raw output
            rel = os.path.relpath(os.path.join(root, f), os.path.dirname(ledger))
            if rel not in have:
                new.append(f"{hashlib.sha256(open(os.path.join(root, f), 'rb').read()).hexdigest()}  {rel}\n")
    with open(ledger, "a") as f:
        f.writelines(sorted(new, key=lambda l: l.split("  ", 1)[1]))


def session_opts(args):
    """--aa, --budget USD, --stop-at ISO-8601 time with offset, --no-c."""
    opt = lambda f: args[args.index(f) + 1] if f in args else None
    stop_at = opt("--stop-at")
    return {"aa": "--aa" in args, "budget": float(opt("--budget")) if opt("--budget") else None,
            "stop_at": datetime.datetime.fromisoformat(stop_at).timestamp() if stop_at else None,
            "arm_c": "--no-c" not in args}


def _read(path):
    return open(path, encoding="utf-8", errors="replace").read() if os.path.exists(path) else None


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "filter":
        cmd_filter(args)
    elif cmd == "draw-pilot":
        cmd_draw_pilot()
    elif cmd == "draw-experiment":
        cmd_draw_experiment(int(args[0]))
    elif cmd == "setup":
        cmd_setup(args[0])
    elif cmd == "sessions":
        cmd_sessions(args[0], args[1], int(args[2]), args[3], **session_opts(args))
    elif cmd == "score":
        cmd_score(args[0], *args[1:])
    elif cmd == "ledger":
        cmd_ledger()
