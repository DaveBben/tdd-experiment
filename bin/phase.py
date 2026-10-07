"""Run one model's sessions and then score them: bin/h python bin/phase.py MODEL TASKS RUNS OUT [--aa] [--budget USD]"""
import sys
sys.path.insert(0, "/work")
from harness import run

model, tasks, runs, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
budget = float(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else None
run.cmd_sessions(model, tasks, runs, out, aa="--aa" in sys.argv, budget=budget)
run.cmd_score(tasks, out)
print("PHASE COMPLETE", flush=True)
