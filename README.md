# Does a fresh agent write better tests?

This experiment tests whether a fresh agent writes stronger failing tests than the agent that planned the feature.
Short answer: no.
For Claude Sonnet 5.5 the planner's tests were slightly stronger, and for Qwen3.6 27B the result is inconclusive.

## Setup

Each task is a FeatureBench task: a real feature removed from a real Python repo, with a stubbed interface left in its place.
Every arm gets the same spec and stub, and writes pytest tests before any implementation exists.

- Arm A (planner): writes a design note for the implementation, then writes the tests in the same session
- Arm B (fresh writer): a new session with only the spec and the stub
- Arm C (fresh writer with the note): a new session that also gets arm A's design note

Both models run in the Pi coding agent CLI 1.0.4.
Qwen is served locally, and Sonnet runs through the Anthropic API.

Each suite is scored by its mutation score: the share of up to 100 sampled mutants of the developers' original implementation that at least 1 valid test kills.
A test is valid when it fails on the stub and passes 5 times in a row on the original implementation.

The primary comparison is B minus A.
H1 (the fresh writer writes stronger tests) is supported only when B beats A by at least 5 points, the Wilcoxon signed-rank test gives p < 0.025, and B's invalid-test rate is no more than 2 points above A's.

## Results

| Model | Tasks | B - A (points) | 97.5% interval | p | Verdict |
| --- | --- | --- | --- | --- | --- |
| Sonnet 5.5 | 63 | -3.3 | -5.8 to -0.7 | 0.00001 | Opposite to H1 |
| Qwen3.6 27B | 16 | -2.3 | -8.3 to +1.9 | 0.81 | Inconclusive |

Sonnet: A beat B on 38 of 63 tasks, tied on 16, and lost on 9.
The difference is significant but small, under the 5 point threshold the design set as a practical effect.
B's suites were about 14 tests smaller, but adjusted for suite size A is still ahead by 2.9 points.
Invalid-test rates were about the same in both arms.

Qwen: 16 tasks is too few to detect anything under about 7 to 10 points.
It leans the same way as Sonnet.

Arm C (Sonnet only) landed between A and B, and neither difference is significant (C - A = -1.6, p = 0.14, and B - C = -1.6, p = 0.09).
C wrote the smallest suites, about 19 tests fewer than A, and its invalid-test rate was 4.7 points higher.
Adjusted for suite size, C matches A (+0.5).
I think this means the design note gives a fresh agent most of what the planner knows about what to test, but it's a secondary comparison, so treat it as exploratory.

The full output is in results/main-sonnet.json and results/main-qwen.json.

## Deviations from the design

The design in EXPERIMENT.md was fixed before the pilot.
It called for 47 tasks with 3 runs each per model, which would have cost about $800 to $1,000 for Sonnet and taken 3 to 5 days for Qwen.
So the main run was cut down, and each change was logged before any main-run score was computed:

- 1 run per task instead of 3, because run-to-run noise in the pilot was small next to the differences between tasks
- Sonnet ran until it had spent $90, past the 30 drawn tasks and the 5 tasks per repo limit, and ended at $94.97 after 63 tasks
- Qwen ran arms A and B only, and stopped at midnight after 16 tasks
- The pilot's per-arm scores were viewed before these decisions

So these results are exploratory, not the preregistered test.
Every deviation is in the deviation log at the end of EXPERIMENT.md.

## Repo layout

- EXPERIMENT.md: the design and the deviation log
- harness/: task preparation, agent sessions, scoring, and analysis
- tasks/: filter records and mutant samples for each task
- draws/: seeds, task draws, and the tasks each model completed
- results/: analysis output for each model
- runs.sha256: hashes of every raw output file (the raw runs are too large for the repo)

Run everything through bin/h, which runs the command in the pinned harness image:

```bash
bin/h pytest -q tests
bin/h python -m harness.analyze runs/main/sonnet
```
