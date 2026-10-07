"""The pre-specified analysis for 1 model. Prints 1 JSON line ending in a verdict.

    uv run python -m harness.analyze runs/<model> [--tasks selection.txt]

Reads RUNS/<task>/<arm>/<run>/score.json ({mutation_score, invalid_rate, suite_size}, in percent and
counts) and manifest.json (optional "excluded": reason). Exclusions remove whole pairs (1 run of
all arms), and a task needs at least 2 pairs, as in EXPERIMENT.md "Exclusions and missing data".
"""
import json
import os
import random
import statistics
import sys

from scipy import stats

ARMS = ("A", "B", "C")
SESOI, GUARD, ALPHA, RESAMPLES = 5.0, 2.0, 0.025, 10_000
ROOT = os.path.join(os.path.dirname(__file__), "..")


def load(runs_dir, tasks=None, arms=ARMS, min_pairs=2):
    """{task: {arm: [score dicts of kept pairs]}} for tasks with at least min_pairs kept pairs."""
    out = {}
    for task in sorted(tasks or os.listdir(runs_dir)):
        runs = sorted({r for a in arms for r in _ls(runs_dir, task, a) if r.isdigit()}, key=int)
        pairs = []
        for r in runs:
            pair = {}
            for a in arms:
                d = os.path.join(runs_dir, task, a, r)
                try:
                    manifest = json.load(open(os.path.join(d, "manifest.json")))
                except OSError:
                    break
                if manifest.get("excluded"):
                    break
                if not os.path.exists(os.path.join(d, "score.json")):
                    raise RuntimeError(f"{d} is not excluded but has no score.json: score it first")
                score = json.load(open(os.path.join(d, "score.json")))
                pair[a] = score
            else:
                pairs.append(pair)
        if len(pairs) >= min_pairs:
            out[task] = {a: [p[a] for p in pairs] for a in arms}
    return out


def _ls(*parts):
    p = os.path.join(*parts)
    return os.listdir(p) if os.path.isdir(p) else []


def per_task(data, key):
    return {t: {a: statistics.fmean(s[key] for s in by_arm) for a, by_arm in arms.items()} for t, arms in data.items()}


def bootstrap_ci(diffs, seed, clusters=None):
    """97.5% percentile interval of the mean difference, resampling tasks (or whole clusters)."""
    rng = random.Random(seed)
    groups = {}
    for i, c in enumerate(clusters or range(len(diffs))):
        groups.setdefault(c, []).append(diffs[i])
    keys = list(groups)
    means = []
    for _ in range(RESAMPLES):
        sample = [x for k in rng.choices(keys, k=len(keys)) for x in groups[k]]
        means.append(statistics.fmean(sample))
    means.sort()
    lo, hi = ALPHA / 2, 1 - ALPHA / 2
    return [means[int(lo * RESAMPLES)], means[int(hi * RESAMPLES) - 1]]


def compare(data, hi, lo, seed):
    """Arm `hi` minus arm `lo`, paired by task."""
    tasks = sorted(data)
    score, inv, size = (per_task(data, k) for k in ("mutation_score", "invalid_rate", "suite_size"))
    d = [score[t][hi] - score[t][lo] for t in tasks]
    d_inv = [inv[t][hi] - inv[t][lo] for t in tasks]
    d_size = [size[t][hi] - size[t][lo] for t in tasks]
    repos = [t.split(".")[0] for t in tasks]
    p = stats.wilcoxon(d, zero_method="pratt", alternative="two-sided").pvalue if any(d) else 1.0
    # Which arm the signed ranks favour (Pratt: zeros are ranked, then dropped from the sums).
    ranks = stats.rankdata([abs(x) for x in d])
    rank_sum = sum(r for r, x in zip(ranks, d) if x > 0) - sum(r for r, x in zip(ranks, d) if x < 0)
    nonzero = [x for x in d if x]
    sign_p = stats.binomtest(sum(x > 0 for x in nonzero), len(nonzero)).pvalue if nonzero else 1.0
    # Size-adjusted difference: intercept of d_score ~ d_size.
    adj = stats.linregress(d_size, d).intercept if len(set(d_size)) > 1 else None
    return {
        "n": len(tasks),
        "mean_diff": statistics.fmean(d),
        "ci": bootstrap_ci(d, seed),
        "ci_repo_cluster": bootstrap_ci(d, seed, repos),
        "wilcoxon_p": p,
        "signed_rank_direction": int(rank_sum > 0) - int(rank_sum < 0),
        "sign_test_p": sign_p,
        "wins_ties_losses": [sum(x > 0 for x in d), sum(x == 0 for x in d), sum(x < 0 for x in d)],
        "invalid_rate_diff": statistics.fmean(d_inv),
        "invalid_rate_ci": bootstrap_ci(d_inv, seed),
        "suite_size_diff": statistics.fmean(d_size),
        "suite_size_ci": bootstrap_ci(d_size, seed),
        "size_adjusted_diff": adj,
    }


def verdict(r):
    """EXPERIMENT.md decision rule. No equivalence test is pre-specified, so a null is inconclusive."""
    significant = r["wilcoxon_p"] < ALPHA
    if significant and r["signed_rank_direction"] < 0:
        return "opposite"
    if significant and r["signed_rank_direction"] > 0 and r["mean_diff"] >= SESOI:
        return "supported" if r["invalid_rate_diff"] <= GUARD else "guard failed"
    return "inconclusive"


def main(runs_dir, tasks=None):
    seed = int(open(os.path.join(ROOT, "draws", "bootstrap.seed")).read())
    # Main run (deviation log, 2026-10-07): 1 run per task, so a task is kept when its 1 pair is; arm C
    # is not run for every model.
    arms = ARMS if any(_ls(runs_dir, t, "C") for t in _ls(runs_dir)) else ("A", "B")
    data = load(runs_dir, tasks, arms, min_pairs=1)
    primary = compare(data, "B", "A", seed)
    result = {
        "runs_dir": runs_dir,
        "primary_B_minus_A": primary,
        "guard_ok": primary["invalid_rate_diff"] <= GUARD,
        "verdict": verdict(primary),
    }
    if "C" in arms:
        result["secondary_C_minus_A"] = compare(data, "C", "A", seed + 1)
        result["secondary_B_minus_C"] = compare(data, "B", "C", seed + 2)
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    args = sys.argv[1:]
    tasks = None
    if "--tasks" in args:
        i = args.index("--tasks")
        tasks = open(args[i + 1]).read().split()
        del args[i : i + 2]
    main(args[0], tasks)
