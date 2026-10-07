"""Pilot rules from EXPERIMENT.md "Sample size" and "Controlled variables". Prints 1 JSON line.

    bin/h python -m harness.pilot runs-pilot/qwen runs-pilot/sonnet

The pilot's difference between arms is never analysed: this script reports only variances, the A/A
check, the sizes they set, the limits, and cost. It reads score.json and manifest.json as analyze.py does.
"""
import json
import math
import os
import statistics
import sys

from harness import analyze

Z_ALPHA, Z_POWER, DELTA, ARE, SIGMA_FLOOR = 2.24, 0.84, 5.0, 0.864, 10.0


def n_for(sigma):
    return math.ceil(((Z_ALPHA + Z_POWER) * sigma / DELTA) ** 2 / ARE + Z_ALPHA ** 2 / 2)


def variances(runs_dir):
    """σ: SD over tasks of B-A averaged over runs. s²w: mean over tasks of the variance of per-run B-A."""
    data = analyze.load(runs_dir)
    means, within = [], []
    for task, arms in data.items():
        d = [b["mutation_score"] - a["mutation_score"] for a, b in zip(arms["A"], arms["B"])]
        means.append(statistics.fmean(d))
        if len(d) > 1:
            within.append(statistics.variance(d))
    return statistics.stdev(means), statistics.fmean(within), len(data)


def aa_check(runs_dir):
    """Mean of B'-B over every pair with both, and its pre-set tolerance of 2 standard errors."""
    d = []
    for task in sorted(os.listdir(runs_dir)):
        for r in analyze._ls(runs_dir, task, "B2"):
            try:
                b = json.load(open(os.path.join(runs_dir, task, "B", r, "score.json")))
                b2 = json.load(open(os.path.join(runs_dir, task, "B2", r, "score.json")))
            except OSError:
                continue
            d.append(b2["mutation_score"] - b["mutation_score"])
    if len(d) < 2:
        return {"pairs": len(d), "ok": None}
    mean, se = statistics.fmean(d), statistics.stdev(d) / math.sqrt(len(d))
    return {"pairs": len(d), "mean": mean, "tolerance": 2 * se, "ok": abs(mean) <= 2 * se}


def usage(runs_dirs):
    """Largest turns and tokens per phase over every session, and cost and tokens per session."""
    peak = {"design": {"turns": 0, "tokens": 0}, "tests": {"turns": 0, "tokens": 0}}
    cost, sessions, limit_hits = 0.0, 0, 0
    for runs_dir in runs_dirs:
        for root, _, files in os.walk(runs_dir):
            if "session.json" not in files:
                continue
            info = json.load(open(os.path.join(root, "session.json")))
            sessions += 1
            for ph in info["phases"]:
                cost += ph["cost"]
                if ph["phase"] not in peak:
                    continue  # the note prompt has its own fixed limit
                peak[ph["phase"]]["turns"] = max(peak[ph["phase"]]["turns"], ph["turns"])
                peak[ph["phase"]]["tokens"] = max(peak[ph["phase"]]["tokens"], ph["tokens"])
                limit_hits += bool(ph["limit_reached"])
    limits = {ph: {"turns": math.ceil(1.5 * v["turns"] / 10) * 10, "tokens": math.ceil(1.5 * v["tokens"] / 1e5) * 100_000}
              for ph, v in peak.items()}
    return {"peak": peak, "final_limits": limits, "sessions": sessions, "cost": cost, "pilot_limit_hits": limit_hits}


def main(runs_dirs):
    per_model, sigmas, runs = {}, [], 3
    for d in runs_dirs:
        sigma, s2w, tasks = variances(d)
        per_model[d] = {"tasks": tasks, "sigma": sigma, "s2w": s2w, "aa": aa_check(d)}
        sigmas.append((sigma, s2w))
    sigma = max([SIGMA_FLOOR] + [s for s, _ in sigmas])
    # More runs when run-to-run noise dominates in either model: s²w/3 > σ²/2.
    if any(s2w / 3 > sigma ** 2 / 2 for _, s2w in sigmas):
        runs = 5
        s2w = max(s2w for _, s2w in sigmas)
        sigma = math.sqrt(max(sigma ** 2 - s2w / 3 + s2w / 5, 0))
    result = {"per_model": per_model, "sigma": sigma, "runs": runs, "n": n_for(sigma), **usage(runs_dirs)}
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    main(sys.argv[1:])
