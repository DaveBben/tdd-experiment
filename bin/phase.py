"""Run one model's sessions and then score them: bin/h python bin/phase.py MODEL TASKS RUNS OUT [--aa] [--budget USD] [--stop-at ISO] [--no-c]"""
import sys
sys.path.insert(0, "/work")
from harness import run

model, tasks, runs, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
run.cmd_sessions(model, tasks, runs, out, **run.session_opts(sys.argv))
run.cmd_score(tasks, out)
print("PHASE COMPLETE", flush=True)
