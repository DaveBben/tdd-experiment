# Experiment: does a separate agent write stronger failing tests?

This experiment tests whether a fresh agent writes stronger failing tests for a feature than the agent that planned the feature's implementation.
Both arms write tests before any implementation exists, so the only difference is who writes the tests and what that writer remembers.
The primary measure is the mutation score of each test suite against the feature's reference implementation.
The method is a controlled benchmarking experiment without human participants, on real features from [FeatureBench](https://github.com/LiberCoders/FeatureBench).
It runs separately on 2 models, Qwen3.6 27B and Claude Sonnet 5.5, both in the Pi coding agent harness.

## Status

Design only: no run has happened yet.
Every open decision was settled on 2026-10-06, as listed in [settled decisions](#settled-decisions).
This file is tagged `design-v1` before the harness is built.
The task count and run count are then set from the pilot by the rules in [sample size](#sample-size).

## Why this question is open

No published study compares these 2 arms directly, as of 2026-10-06.
The nearest evidence is listed below.

* **AgentCoder ([arXiv 2312.13010](https://arxiv.org/abs/2312.13010)):** a separate test-designer agent that never saw the code beat a single agent that wrote code first, then tests.
  Test accuracy rose from 61.0% to 87.8% on HumanEval with GPT-3.5.
  The comparison changes 2 things at once: who writes the tests, and whether the writer saw the code.
* **Coding before testing ([arXiv 2607.05139](https://arxiv.org/abs/2607.05139)):** tests written by the same model after faulty code caught 14% of faults, against 25% for tests written independently.
* **Misguidance by buggy code ([arXiv 2607.22883](https://arxiv.org/abs/2607.22883)):** across 11 models, showing buggy code to the test writer raised tests that assert the bug from 0.46% to 3.84%.
* **Cross-model review ([arXiv 2610.01471](https://arxiv.org/abs/2610.01471)):** for reviewing artifacts, the same model in a fresh session scored an F1 close to a top different model's, 28.6% against 32.3%, with no significant difference.
  The different model found partly different errors.

Each of these studies shows that seeing the implementation weakens tests.
None isolates the effect of a separate writer when no implementation exists yet.
That is the setup a test-first workflow uses: one session plans the feature, then tests are written against its interface before any code.

### Theory

2 ideas predict opposite results.
A writer who did not plan the implementation should not share the planner's blind spots, so its tests should catch faults that the planner's tests miss.
Against that, independently written versions of the same program still failed on the same inputs ([Knight and Leveson, IEEE TSE 1986](https://doi.org/10.1109/TSE.1986.6312924)).
2 sessions of 1 model may likewise share blind spots, and the cross-model review result above fits that.

## Hypotheses

These hypotheses are fixed before any data is collected.

* **H1:** for each model, arm B suites have a higher mean mutation score than arm A suites, paired by task.
* **H0:** for each model, the paired mean difference in mutation score is zero.

H1 is directional because every study in [why this question is open](#why-this-question-is-open) points the same way.
The test is two-sided, so a difference that favours arm A is also detected and reported.
The result counts as support for H1 only when the [decision rule](#decision-rule) holds.

The 2 models give 2 tests of H1, each decided separately.
Each test uses a significance level of 2.5%, so the chance of any false positive across both stays at 5%.
This is the Bonferroni correction.

## Arms

The independent variable is who writes the failing tests.

| Arm | Test writer | Context when writing tests |
| --- | --- | --- |
| A, control | The session that planned the implementation | Spec, repository, stub, its design note |
| B, treatment | A fresh agent | Spec, repository, stub |
| C, context | A fresh agent | Spec, repository, stub, arm A's design note |

All arms get the same spec, the same undeveloped repository, and the same stub.
Arm B lacks only arm A's design note and conversation.
Arm C lacks only arm A's conversation: it gets arm A's design note from the same run, word for word, in its first message.
The primary comparison is B against A.
Arm C separates the 2 things that comparison bundles, as [secondary comparisons](#secondary-comparisons):
C against A changes only the fresh context, and B against C changes only the design note.

Arm B is a bare fresh agent with only the shared test-writing prompt.
The experiment therefore tests the principle of a separate test writer, and not any particular test-writing agent or its prompt.

### What arm A does before writing tests

Arm A first explores the repository and writes a short **design note**: the data structures, the algorithm for each function in the interface, the existing code it will reuse, and the edge cases it intends to handle.
It then writes the tests in the same session.

The design note is the manipulation.
It stands in for the implementation reasoning that a real planning session carries into test writing.
Without it, arms A and B would differ only by a short conversation, and a null result would say little.

FeatureBench fixes each feature's interface in its problem statement, so neither arm designs the interface.
The **stub** is made by a script from the [spec](#spec-for-each-task)'s interface descriptions: every listed function and class, at its listed path, with its signature, its docstring with doctest examples removed, and a body of `raise NotImplementedError`.
Every arm therefore starts from a byte-identical stub, and no text written by arm A reaches arm B.
Arm C receives only arm A's design note.

### Alternatives not compared

This experiment does not compare code-based test generators such as Pynguin and MuTAP ([Dakhel et al., IST 2024](https://doi.org/10.1016/j.infsof.2024.107468)).
Each one needs the code under test, and in a test-first workflow no code exists when the tests are written.

### Design and arm order

The design is a paired design with each task as a block.
Both arms run on every task, and each task's arm B score is compared with its own arm A score.
Pairing removes differences in difficulty between tasks from the comparison.

Treatments are not randomly assigned, because every task receives both.
Arm order is fixed so that the arms of a pair run back to back under the same model state.
A fixed order lets anything that changes between the 2 sessions act as a confound.
The [procedure](#procedure) limits this: arm B starts straight after arm A, and task and run pairs run in a random order.

## Controlled variables

The following are held constant across all arms:

* **Model:** within each replication, every arm and every role use the same model, described in [models](#models).
* **Harness:** both models run in the same pinned version of Pi, with the same system prompt and the same tools: read, write, edit, and bash.
  No Pi extension loads except the provider configuration, which is committed.
* **Tasks:** the same tasks, with the spec text identical for every arm.
  The task count is set in [sample size](#sample-size).
* **Stub:** the same scripted stub, byte for byte.
* **Test-writing prompt:** the same instruction text in every arm.
  Arm A sees it as its next turn, and arms B and C see it in their first message, after the spec and, for arm C, the design note.
* **Implementation state:** no implementation of the feature exists in either arm while tests are written.
* **Test framework:** `pytest`, matching FeatureBench's own tests.
* **Tools:** file read and write and a shell inside the task's container, including running the tests against the stub to confirm that they fail.
* **Environment:** the same container image per task, as described in [environment](#environment).
* **Limits:** the same turn limit and token limit for test writing in every arm.
  Both limits count from the test-writing prompt, so arm A's design phase does not use up its test-writing budget.
  Arm A's design phase has its own turn and token limit.
  A turn is 1 model response with its tool calls, and the token count is the sum over turns of each response's input and output tokens, cached tokens included.
  Pi has no built-in limits, so the harness counts both from Pi's event stream and aborts the session when either is reached.
  The pilot runs with generous limits: 100 turns and 5,000,000 tokens for the design phase, and 200 turns and 10,000,000 tokens for test writing.
  After the pilot, each limit is set to 1.5 times the largest value any pilot session used in that phase, over both models and all arms, rounded up to the next 10 turns or 100,000 tokens, and committed with `design-v2`.
  Each phase also has a wall-clock limit of 2 hours, which works like the other limits: the phase is aborted and what it wrote is kept.
  A session crashed only when Pi rejected a prompt, exited, or its final response ended in an error after Pi's own retries; a transient error that Pi recovered from is recorded but is not a crash.
* **Context compaction:** Pi's automatic compaction is turned off with `"compaction": {"enabled": false}` in the committed settings.
  Compaction would summarise arm A's design reasoning away, in arm A only.
  A session whose context overflows the model's context length ends there, and the [exclusion rules](#exclusions-and-missing-data) apply.
* **Runs:** 3 independent runs per task per arm, each starting from a new session in a new container.
  The run count is checked in [sample size](#sample-size).
* **Sampling settings:** the same for every arm within each model, and recorded, as described in [models](#models).

### Models

The whole experiment runs once per model, on the same tasks.

| Model | Served by | Pinned as |
| --- | --- | --- |
| Qwen3.6 27B | The experimenter's local llama.cpp server behind llama-swap, through an OpenAI-compatible API | `unsloth/Qwen3.6-27B-MTP-GGUF` at revision `5cb35eb3dcbf52dbce5f87dbc64df6aaffadcace`, file `Qwen3.6-27B-Q4_K_M.gguf`, llama.cpp build `b1-8ed274e`, context length 200,000 tokens, KV cache quantized to q4_0, MTP speculative decoding with 2 draft tokens, 1 slot |
| Claude Sonnet 5.5 | The Anthropic API | Model ID `claude-sonnet-5-5` |

Qwen3.6 27B has open weights, which meets the recommendation to include an open model as a baseline ([arXiv 2508.15503](https://arxiv.org/abs/2508.15503)).
Its sampling settings are set explicitly on the server: temperature 0.6, top-p 0.95, top-k 20, min-p 0, and repeat penalty 1.0.
Thinking is on: the server's default is off, and Pi turns it on for each request with `--thinking high`, which it sends as `chat_template_kwargs: {"enable_thinking": true}`.
Qwen3.6 has no effort levels, so for Qwen `high` only turns thinking on.
The harness records the server's `/props` output for every session, so a change in serving shows up in the manifests.
The server has 1 slot, so Qwen sessions run one at a time.
Sonnet runs with thinking effort `high`, set with `--thinking high`, because Pi cannot turn Sonnet's thinking off.
Pi sends no temperature, so the API's default sampling applies.

Limits such as the context length may differ between the 2 models, but are the same for every arm within a model.
The models also differ in size, serving, and quantization, so a comparison across models cannot isolate any one of these.
Comparisons across models are therefore exploratory.

### Environment

Every session and every test run happens in a Docker container built from the task's FeatureBench image.

* **Images:** each task's image from FeatureBench's Docker Hub organisation, pinned by digest.
  Any layer added on top, such as the agent harness or the mutation tool, comes from a Dockerfile committed to this repository with every version pinned.
* **Preparation:** a FeatureBench image holds the complete repository at the task's commit, its git history, and a second copy at `/root/my_repo`.
  Every container is prepared by the same committed script, which mirrors FeatureBench's own inference preparation.
  It applies the task's removal patch to `/testbed`, deletes the fail-to-pass test files, deletes `/root/my_repo`, every `__pycache__` directory, and `/testbed/.git`, starts a new git repository with 1 commit, and applies the stub.
  It also deletes `/root/.cache`, conda's package cache, and every conda environment except the task's own, because a pre-pilot review found released copies of the feature's package there: a cached pandas wheel and a second environment's sympy.
  Sessions therefore never see the developers' fail-to-pass tests.
* **Host:** an Apple M4 Max with 16 cores and 64 GB of memory, running Docker in a Colima virtual machine with 12 CPUs and 32 GB.
  The images are built for `linux/amd64` and run under emulation, which slows every run but applies equally to every arm.
* **A new container per session:** each arm A, arm B, and arm C session starts from a fresh container, so nothing from one session can reach another.
* **Network:** agent sessions may reach only their model's endpoint: the Anthropic API for Sonnet, and the local inference server for Qwen.
  Session containers sit on an internal Docker network whose only other member is a gateway that forwards to those 2 endpoints.
  The gateway adds the Anthropic API key, so no session container holds it.
  Test runs and mutant runs have no network.
* **Timeouts:** each test run against a mutant has a time limit of 3 times the suite's run time on the reference implementation, and at least that run time plus 10 seconds.
  A suite can run in under a second, and 3 times that would let ordinary start-up jitter count as a kill.
  The test command is FeatureBench's for each task, including its per-task exclusions with `-k`, and is the same for every arm.
  That reference run time is measured in the same batch as the suite's mutant runs, so both face the same machine load.
  A mutant that times out counts as killed, and timeout kills are counted separately for each arm.
* **Resources:** every container is limited to 4 CPUs and 8 GB of memory, and the limits are recorded.

## Measures

### Mutation score, primary

A **mutant** is a copy of the reference implementation with 1 small automated change, such as `>=` replaced by `>`.
A suite **kills** a mutant when at least 1 of its tests fails on that mutant.
The **mutation score** of a suite is the share of mutants it kills.

Mutants are made only in the lines that the task's gold patch adds, because those lines are the feature under test.
The rest of the repository is not mutated.

The mutator is a small script committed to this repository, so every operator can be audited.
It parses each changed file with Python's `ast` module and makes 1 mutant for each applicable operator at each node that starts on an added line:

* **Comparison:** `<` and `<=`, `>` and `>=`, `==` and `!=`, `in` and `not in`, `is` and `is not` swap.
* **Arithmetic:** `+` and `-`, `*` and `/`, `//` and `/` swap, and `%` becomes `*`, in binary and augmented assignments.
* **Boolean:** `and` and `or` swap, and a `not` is removed.
* **Constants:** `True` and `False` swap, an integer `k` becomes `k + 1`, and a non-empty string becomes `"XX"`.
* **Return:** a returned value becomes `None`.
* **Statement:** an expression statement, assignment, `raise`, `break`, or `continue` becomes `pass`.

Docstrings, type annotations, and the inside of f-strings are not mutated.
A change there almost never changes behaviour, so such a mutant would be equivalent and only dilute the score.
A mutant whose source equals the original after unparsing, or that fails to compile, is dropped before sampling.
Each task's mutants are a random sample of at most 100, drawn once with a seed.
Every suite, arm, and run on that task is scored against the same sample, so sampling error largely cancels in the paired difference.

The score is computed only from the suite's valid tests, defined below.
An invalid test fails on the correct implementation, so its failures on mutants say nothing about catching faults.

Mutation score stands in for test strength because it correlates with the detection of real faults ([Just et al., FSE 2014](https://doi.org/10.1145/2635868.2635929)).
That correlation weakens once suite size is controlled ([Papadakis et al., ICSE 2018](https://doi.org/10.1145/3180155.3180183)), so suite size is a pre-specified [covariate](#suite-size-covariate).

Mutants that no valid test from any suite, arm, or run, and no FeatureBench test, can kill are reported separately.
They are kept in the denominator, because equivalent-mutant detection is out of scope.

### Validity, guard

A test is **invalid** when it fails on the task's reference implementation, which is the undeveloped repository with the gold patch applied.
A test is **flaky** when it passes on some runs against the reference implementation and fails on others.
Each suite runs 5 times against the reference implementation, and a flaky test counts as invalid.
A flaky test would otherwise kill mutants at random, which would inflate the mutation score.
The same rule applies to FeatureBench's own tests in the [human reference](#human-reference-secondary).

The **invalid rate** of a suite is the share of its tests that are invalid, flaky ones included.
The count of flaky tests is also reported on its own.
A suite in which every test is invalid gets a mutation score of 0.

### Downstream pass rate, secondary

If the budget allows, a fresh coder agent implements each task against each locked suite.
It may not edit the tests.
Its implementation is then scored by the share of FeatureBench's fail-to-pass tests it passes, with every pass-to-pass test still passing.

This measure includes the coder's skill and is reported, not used in the decision rule.
FeatureBench reports about 7.5 million input tokens per implementation attempt, so this measure may run on 1 run per task only.

### Human reference, secondary

For each task, the mutation score of FeatureBench's fail-to-pass tests against the same mutants is reported.
Those tests come from the repository's own test suite and were written by its developers, so their score shows how close either arm comes to human-written tests.
It is not part of the decision rule.

### Suite size, covariate

The **suite size** is the count of valid tests in a suite.
A larger suite kills more mutants by size alone, so a higher mutation score could come from writing more tests rather than better ones.
Suite size is recorded for every suite and reported with the mutation score.

### Manipulation check

The comparison depends on arm A having design reasoning that arm B lacks.
These checks confirm it for every run:

* **Design note present:** a script confirms that arm A's design note has an entry for every function and class in the interface descriptions, and lists at least 1 edge case.
  A run that fails is rerun once in a new session.
  A run that fails again is excluded, and every exclusion is reported with its reason.
* **Design note isolated:** arms B and C each run in a new container that holds the undeveloped repository, the spec, and the stub, and nothing from arm A's session.
  Arm C's design note reaches it only through its first message.
  A script confirms that each transcript reads no file outside that container's starting contents.
* **Design note kept:** a script confirms that arm A's session file holds no `compaction` entry, so the design note was still in context when the tests were written.
  A run that fails is treated like a failed design-note check.

## Objects

The tasks come from FeatureBench, a benchmark of feature-level tasks built from real Python repositories ([arXiv 2602.10975](https://arxiv.org/abs/2602.10975), ICLR 2026).
Each task gives a problem statement with interface descriptions, an undeveloped repository with the feature's code removed, a gold patch that restores it, and developer-written tests.
The tests are split into fail-to-pass tests, which check the feature, and pass-to-pass tests, which check that the rest of the repository still works.

* **Dataset:** [`LiberCoders/FeatureBench`](https://huggingface.co/datasets/LiberCoders/FeatureBench) version 1.1, pinned at revision `76b4a4566e04f4bcc13c35125d4f301791efa736`.
* **Harness:** the FeatureBench repository, pinned at commit `8d4e347ec57546685c5a87e8676bf575db022ea6`.
* **Split:** the `fast` split, 100 tasks from 18 repositories that need no GPU.
* **Licence:** the dataset is MIT-licensed, and each repository keeps its own licence.
  A script downloads the data at the pinned revision, and the repository does not store a copy.
* **Gold patch:** the dataset's `patch` field is the removal patch, which turns the complete repository into the undeveloped one.
  The gold patch is that patch reversed, without any file block that touches a fail-to-pass test file, as FeatureBench's own `preprocess_hf_patch` builds it.

FeatureBench is used for 3 reasons.
Each task is a real feature, with a median of about 470 added lines across 8 files in the `fast` split, which gives arm A real implementation planning to do.
Its tests are developer-written, which gives the [human reference](#human-reference-secondary).
A test's outcome is read from pytest's own per-test reports, and test files are always run whole, so test IDs never pass through a command line.
A test file that cannot be collected against the stub fails there by definition, so all its tests are kept when the suite is locked, and each is then judged on the reference implementation like any other test.
Each task ships a Docker image, which gives a fixed environment.

The results report each task's repository, the added line count and file count of its gold patch, its fail-to-pass test count, and its mutant count before sampling.

Tasks are chosen in this order:

1. Drop every task whose gold patch fails more than 5% of its fail-to-pass tests in this experiment's container.
   A test that fails on the gold patch fails for the environment, mostly because test runs have no network, so it is excluded rather than dropping the task: it fails on every implementation alike.
   Such fail-to-pass tests are already invalid under [validity](#validity-guard), and such pass-to-pass tests are left out of step 2.
2. Drop every task whose scripted stub does not import cleanly, or breaks a pass-to-pass test that passes on the gold patch.
3. Drop every task whose prepared container still holds the feature's code outside the undeveloped source, as checked under [assumptions](#assumptions).
4. Draw 3 pilot tasks with a fixed random seed.
5. Run the pilot, then set the task count from [sample size](#sample-size) and commit it here.
6. Shuffle the rest with a second fixed seed, and take experiment tasks in that order until there are that many, skipping any task that would put more than k tasks from 1 repository in the set, pilot tasks included.
   k is the smallest number, at least 5, for which this yields the task count plus 5 replacements.
   The filter kept 86 tasks spread so unevenly that k = 5 allows only 44 experiment tasks, fewer than the planned 47, and the [task cap](#settled-decisions) was set so that it never binds below the planned count.
   The [repository clustering](#analysis) bootstrap reports how much the larger k matters.
   The tasks after them, in the same order, are the replacements used by the [exclusion rules](#exclusions-and-missing-data).
   The `fast` split's tasks are spread unevenly, from 21 tasks in 1 repository to 1 task in each of 8 others, so a limit of 5 allowed at most 52 tasks before filtering.

Each seed is recorded and committed in `draws/` before the draw that uses it, so the commit history shows that no draw was chosen after the fact.
Pilot tasks never appear in the experiment results.

### Fresh tasks

FeatureBench tasks come from popular repositories, with features created between May 2022 and September 2025.
The model has probably seen both the tasks and the repositories' code, so 5 fresh tasks are added as a contamination check.

Each fresh task is generated with FeatureBench's own data pipeline from repository commits made after the later of the 2 models' release dates.
Qwen3.6 27B was released on 2026-04-22 and Claude Sonnet 5.5 on 2026-09-28, so every fresh task comes from a commit made after 2026-09-28.
A model cannot have trained on code published after its release, so this bound holds even when a training cutoff is not published.
Each fresh task is committed before the pilot and is not published before the run.
When the pipeline yields fewer than 5 such tasks before the pilot, the experiment runs with those it yields, and the count is reported.
On 2026-10-07 the pipeline was not run before the pilot, so the experiment has 0 fresh tasks.
Running it means executing FeatureBench's pipeline code with an LLM behind it and building large images locally, which did not fit the overnight schedule the experimenter set.
The contamination check is therefore not available, and the results are reported with that limitation.

Fresh tasks run through the same procedure as experiment tasks.
Their results are reported separately and are not used in the decision rule, because 5 tasks are too few to decide on.
A difference between arms that appears on FeatureBench tasks but vanishes on fresh tasks points to memorisation.

### Sample size

The experiment task count `n` is set after the pilot and before the experiment draw.
It is the count needed for 80% power to detect a 5-point paired difference for 1 model, with the two-sided 2.5% significance level from the [hypotheses](#hypotheses).
Both models run the same `n` tasks.

```text
n = ((2.24 + 0.84) × σ / 5)² / 0.864 + 2.51
```

sample-size: alpha=0.025 power=0.80 delta=5 sigma=10 are=0.864 n=47

This line holds the planning values.
After the pilot, its σ and `n` are replaced by the values the pilot sets.

* **σ:** the standard deviation of the per-task differences in mutation score, each averaged over 3 runs, in percentage points.
  It is the larger of the 2 models' pilot estimates and 10 points, because 3 pilot tasks estimate it poorly.
* **0.864:** the lowest efficiency the Wilcoxon signed-rank test can have relative to the paired t-test, over all distributions.
  Dividing by it raises `n` by about 16%, which is conservative.
  Under normal data the efficiency is 0.955.
* **2.51:** a small-sample correction of z²/2, with z = 2.24, because the normal approximation understates `n` for small samples.
* **Example:** at σ = 10, `n` = 47.
  20 tasks are enough only when σ is at most about 6.3.

When `n` exceeds the [task cap](#settled-decisions), the experiment runs the cap.
A null result is then reported as inconclusive, and not as evidence of no effect.

The decision rule also requires an observed difference of at least 5 points.
That condition passes only about half the time when the true effect is exactly 5 points.
At this `n`, the full decision rule has 80% power when the true effect is about 6.4 points, from 5 × (1 + 0.84 / 3.08).
The experiment is therefore powered for a true effect of about 6.4 points.
5 points is the smallest observed difference it counts as a practical effect.

The 3 runs per task are a cost compromise, and the pilot checks them.
The pilot measures s²w, the run-to-run variance of each task's difference between arms, for each model.
When s²w / 3 is more than half of σ², run-to-run noise dominates, and the run count rises to 5 before the experiment draw.
σ² is then rescaled to σ² − s²w / 3 + s²w / 5, and `n` is recomputed from it.

### Spec for each task

The **spec** is the FeatureBench problem statement: its task description and its interface descriptions.
The implementation instructions are removed, because every arm writes tests and not code.
They are the `**NOTE**` block and the `### Clarification` block, which tell the agent to write code under `/testbed/` and repeat the first interface as an example.
Doctest examples in the interface docstrings are also removed, because they are ready-made test cases and would narrow the difference between arms.
A committed script makes both removals, and the stub is built from its output, so no doctest reaches either arm through the stub.

## Procedure

Each model's task and run pairs are executed in their own random order, drawn with a third fixed seed.
The 2 models may run at the same time, because their sessions share nothing.
The seed is recorded and committed in `draws/` before the first run.
Random order stops a change in the model or its API during the experiment from lining up with particular tasks.
Arms B and C for a run start straight after arm A for the same run, so all arms of a run face the same model state.
Arm C needs arm A's design note, so it always runs after arm A, and B and C run in a random order drawn from the same seed.
Every session's start time is recorded.

Each run of each task follows these steps:

1. Start a new container from the task's image, apply the scripted stub, and start an arm A session with the spec.
2. Have arm A write the design note, then the tests.
3. Run the suite against the stub, drop every test that passes, and lock the suite.
   The count of dropped tests is reported for each arm.
4. Run the design-note and design-note-kept checks from the [manipulation check](#manipulation-check).
5. Start a new container from the same image, apply the same stub, and start an arm B session with the spec.
6. Have arm B write the tests with the same prompt, then drop the tests that pass against the stub and lock the suite, as in step 3.
7. Start a new container in the same way, and start an arm C session with the spec and arm A's design note.
   Have arm C write the tests with the same prompt, then drop and lock as in step 3.
8. Run the isolation check from the [manipulation check](#manipulation-check) on arms B and C.
9. Run every suite 5 times against the reference implementation to mark invalid and flaky tests.
10. Run every suite's valid tests against every sampled mutant.
   On the first run of each task, also run its fail-to-pass tests against every sampled mutant for the [human reference](#human-reference-secondary).
11. Store every transcript, artifact, and score as raw files.

The pilot runs this procedure on 3 tasks with 3 runs each, on both models.
It checks that the harness works end to end, measures the cost of each session and of each mutant run, and gives the variance estimates for [sample size](#sample-size).
Its difference between arms is not analysed.

The pilot also runs an A/A check.
Each pilot run adds a second arm B session, B′, in its own new container.
The mean difference between B′ and B shows what the harness reports when both arms are the same, and should be close to 0.
A clearly nonzero mean points to a fault in the harness, which is fixed before the experiment draw.

One pilot run is published as a worked example: its spec, stub, design note, and every arm's tests.

## Analysis

Each model is analysed separately.
For each task, average each arm's mutation score and invalid rate over its valid runs, as defined in [exclusions](#exclusions-and-missing-data).
Then compare the arms paired by task.

* **Mean difference:** arm B minus arm A, in percentage points, with a 97.5% percentile bootstrap confidence interval over tasks.
  The bootstrap uses 10,000 resamples and a fourth fixed seed, committed in `draws/` before the first run.
* **Significance:** a two-sided Wilcoxon signed-rank test on the `n` paired differences, at a 2.5% significance level.
* **Wins, ties, and losses:** the count of tasks where arm B scores higher, the same, or lower.
* **Invalid rate:** the same mean difference and interval, for the guard.
* **Suite size:** the same mean difference and interval, for the covariate.
* **Size-adjusted difference:** a linear regression of each task's mutation score difference on its suite size difference.
  The intercept estimates the difference between arms at equal suite size.
  It is reported beside the primary result and is not part of the decision rule.
* **Repository clustering:** the bootstrap is repeated with whole repositories resampled instead of tasks.
  Tasks from 1 repository share code and conventions, so their differences may not be independent.
  It is reported beside the primary interval and is not part of the decision rule.

### Secondary comparisons

These comparisons are pre-specified and reported in full, but they do not affect the [decision rule](#decision-rule):

* **C minus A:** the effect of a fresh context, with the design note held.
* **B minus C:** the effect of the design note, with a fresh context held.

Each gets the same mean difference, 97.5% bootstrap interval, two-sided Wilcoxon signed-rank test, and wins, ties, and losses as the primary comparison.
They use the bootstrap seed with 1 and 2 added, so each has its own resamples.
The [sample size](#sample-size) is set for the primary comparison only, so these comparisons may be underpowered.
A non-significant result for either one is reported as inconclusive.

### Test choice

The Wilcoxon signed-rank test is used because the differences are paired, and mutation scores are bounded, so the differences are unlikely to be normal.
Tasks where both arms score the same are likely, so zero differences are kept with Pratt's method.
The test assumes the differences are roughly symmetric.
A histogram of the differences is checked, and when it is clearly skewed, a sign test is reported beside the Wilcoxon result.
The Wilcoxon test decides significance, because the [sample size](#sample-size) is computed for it.
The bootstrap interval reports the size of the effect.

### Exclusions and missing data

A **pair** is the arm A, arm B, and arm C sessions of 1 run of 1 task.
Exclusions always remove a whole pair, so every arm keeps the same runs.

* **Failed manipulation check:** an arm A session that fails the design-note or design-note-kept check is rerun once in a new session.
  When the rerun fails too, the pair is excluded.
* **Failed isolation check:** the pair is excluded.
* **Crash or API error:** a session that ends with a crash or an API error is rerun once in a new session.
  When the rerun fails too, the pair is excluded.
* **Context overflow:** a session whose context overflows is treated as a crash.
* **Limit reached:** a session that reaches its turn or token limit keeps the tests it wrote by then, and the pair is kept.
  The count is reported for each arm.
* **No valid tests:** the suite scores 0, as defined in [validity](#validity-guard), and the pair is kept.

A task is kept when at least 2 of its pairs remain.
Otherwise it is dropped and replaced by the next task in the experiment draw's order, so `n` stays fixed.
Every excluded pair and dropped task is reported with its arm and reason.

### Exploratory analysis

These analyses are labelled exploratory in the results and do not affect the decision rule:

* **Fresh tasks:** the mean difference and wins, ties, and losses on the [fresh tasks](#fresh-tasks).
* **Run order:** mutation score plotted against session start time for each arm, to show drift during the experiment.
* **Model difference:** the difference between the 2 models' mean effects, with a bootstrap interval over tasks.
  It is exploratory because the models differ in size, serving, and quantization at once.
* **Timeout kills:** the mean difference with mutants killed only by a timeout counted as surviving, to show how much machine load could move the result.

### Decision rule

H1 is supported for a model only when all 3 conditions hold for that model:

1. Arm B's mean mutation score exceeds arm A's by at least 5 percentage points.
2. The two-sided Wilcoxon signed-rank test gives p < 0.025, with the differences favouring arm B.
3. Arm B's mean invalid rate is no more than 2 percentage points above arm A's.

A difference under 5 points counts as no practical effect, even when it is significant.
A significant difference that favours arm A is reported as an effect opposite to H1.

## Assumptions

The design rests on these assumptions:

* **Design note:** the design note stands in for the implementation reasoning that a real planning session carries into test writing.
  The [manipulation check](#manipulation-check) confirms that it exists, but not that it matches real reasoning.
* **Mutation score:** mutation score measures test strength, as argued in [mutation score](#mutation-score-primary).
* **Reference implementations:** every gold patch left after filtering is correct, because it passes its fail-to-pass and pass-to-pass tests.
* **No implementation:** no implementation of the feature can be reached while either arm writes tests.
  The [preparation](#environment) removes the git history and the second copy that every image holds.
  Before the pilot, a script then searches each prepared container's whole filesystem, including the Python files inside wheels, eggs, zips, and tarballs, for each gold-patched file's distinctive lines.
  A file's distinctive lines are the lines of at least 30 characters that the gold patch adds to it, leaving out lines that also appear in the spec or anywhere in the undeveloped repository, because those reach every arm anyway.
  A file anywhere that holds at least a quarter of one gold file's distinctive lines, with a minimum of 3 and a maximum of 10, is a copy of it and drops the task, as does an archive the script cannot open that is named after the task's package.
  A planted copy of a gold file was detected both as a plain file and inside a wheel, and files that only share an idiom with the feature held 1 or 2 lines.
  Network access during sessions is limited to the model API, so the code cannot be fetched from the original repository.

## Threats to validity

Each threat is listed with the check or mitigation that addresses it.

### Construct validity

* **Mutation operators:** the mutation tool's operators define what counts as a fault.
  A different tool could rank suites differently.
* **Mutant sampling:** 100 sampled mutants estimate each suite's score with sampling error.
  Every suite on a task faces the same sample, so the error largely cancels in the paired difference.
* **Flaky tests:** a test that depends on time, randomness, or ordering can pass all 5 reference runs and still fail on a mutant by chance.
  Such a test would count a mutant as killed when the mutant did not cause the failure.
  5 runs catch most flaky tests, and the flaky count shows how common they are.
* **Suite size:** a higher mutation score can come from more tests rather than better ones.
  The size-adjusted difference in the [analysis](#analysis) estimates this.
* **Interface given:** FeatureBench fixes each interface, so arm A plans only the internals.
  The experiment tests implementation planning, and not interface design.

### Internal validity

* **Fresh context:** arm B lacks the design note, and it also starts with a shorter, fresh context.
  An effect could come from the fresh context rather than from the missing design reasoning.
  The primary comparison tests the 2 differences together.
  Arm C and the [secondary comparisons](#secondary-comparisons) separate them.
* **Fixed arm order:** arm A always runs first, so a change between the 2 sessions could look like an effect.
  The [design](#design-and-arm-order) limits this by running arm B straight after arm A.
  The A/A check in the [procedure](#procedure) shows what the harness reports when both arms are the same.
* **Context compaction:** compaction in arm A would remove the manipulation in that arm only.
  Compaction is turned off in [controlled variables](#controlled-variables), and the design-note-kept check confirms it for every run.
* **Selective exclusion:** excluding only the arm A runs that fail a check would keep only the arm A runs where the model complied.
  The [exclusion rules](#exclusions-and-missing-data) always remove whole pairs.
* **Implementation leak:** git history in an image, or network access, could expose the feature's code to either arm.
  The check under [assumptions](#assumptions) and the network rule in [environment](#environment) close both routes.

### External validity

* **Memorised repositories:** the repositories are popular, and the features were public before the model's training cutoff.
  Memorised implementations could shrink the difference between arms.
  The [fresh tasks](#fresh-tasks) check this, but 5 tasks detect only a large gap.
* **Repository range:** the `fast` split covers 18 Python repositories, mostly libraries for data science and developer tools.
  The result may not hold for applications or for other languages.
* **2 models:** the result may not hold for other models, although 2 models of different size and origin give some range.
* **One harness:** both models run in Pi.
  A harness with a different system prompt or different tools could change the result.
* **Prompt sensitivity:** one wording of the test-writing prompt is used.
  All prompts are committed so others can vary them.

### Conclusion validity

* **Power:** the decision rule has 80% power at a true effect of about 6.4 points, and about 50% at exactly 5 points, as explained in [sample size](#sample-size).
  A null result is reported as inconclusive, and never as evidence of no effect.
  When the task cap is below the `n` from sample size, power is lower still.
* **Run-to-run variance:** 3 runs per task may not cover the model's spread.
  The pilot checks this, and the per-run scores are published so others can judge it.
* **2 tests:** testing H1 on 2 models doubles the chance of a false positive.
  The Bonferroni correction in the [hypotheses](#hypotheses) holds it at 5%.
* **Clustering:** tasks from the same repository may not be independent, which would make the interval too narrow.
  The draw takes at most 5 tasks per repository, and the repository-level bootstrap in the [analysis](#analysis) shows how much this matters.
* **Machine load:** a mutant that times out counts as killed, so heavy load could inflate scores.
  Each suite's time limit comes from a reference run in the same batch, and the [exploratory analysis](#exploratory-analysis) reports the result without timeout kills.

## Reproducibility and audit

Everything needed to rerun or check the experiment is in this repository or pinned by it.

* **Pinned inputs:** the Sonnet model ID, the Qwen weights revision, quantization, and server version, the Pi version, the FeatureBench dataset revision and harness commit, every image digest, every tool version, the 3 draw seeds, the bootstrap seed, and the mutant-sampling seed.
* **Committed environment:** every Dockerfile, the spec and stub scripts, and the Pi settings file.
* **Preregistration:** this file is committed and tagged `design-v1` before the pilot, and the tag is pushed to a public remote for a timestamp.
  The settled task and run counts are committed and tagged `design-v2` before the experiment draw.
* **Committed prompts:** every prompt, as the exact text sent.
* **Raw outputs:** every transcript, design note, stub, test suite, and mutant result, unedited.
* **Scripted analysis:** 1 script computes every number in the results from the raw outputs.
* **No hand edits:** any manual change to an artifact or score is logged with the reason.
* **Cost:** tokens, spend, and compute time for each run are recorded.
* **Deviations:** any change to this design after the pilot is logged with its date and reason.
  Setting the task count and run count by the [sample size](#sample-size) rules is planned and is not a deviation.

## Settled decisions

These were settled on 2026-10-06, before the pilot:

* **Qwen serving details:** as listed in [models](#models).
* **Release dates:** Qwen3.6 27B on 2026-04-22, and Claude Sonnet 5.5 on 2026-09-28, which bound the [fresh tasks](#fresh-tasks).
* **Cross-model arm:** not run.
  2 sessions of 1 model may share blind spots, and this experiment does not test that.
* **Context arm:** run, as arm C.
* **Sizes:** 3 runs per task, a 5-point effect threshold, a 2-point validity margin, a planning σ of 10 points, and 100 mutants per task.
* **Task cap:** 49, the most that the per-repository limit in the [objects](#objects) permits, so the cap never binds below the `n` from [sample size](#sample-size).
* **Mutation tool:** the committed mutator described in [mutation score](#mutation-score-primary).
* **Pi version:** 1.0.4, pinned for the whole experiment.
  The pilot confirms that `compaction.enabled` set to `false` works.
* **Public remote:** a public GitHub repository, which receives the `design-v1` tag.
* **Seeds:** each is a random integer from Python's `secrets` module, committed in `draws/` before the draw that uses it.
  `draws/pilot.seed` draws the pilot tasks, `draws/experiment.seed` the experiment tasks, `draws/order.seed` the run order, `draws/bootstrap.seed` the bootstrap, and `draws/mutants.seed` the mutant samples.

## Open decisions

None.

## Deviation log

Changes made after the pilot started, each with its date, reason, and expected effect on the result.

* **2026-10-07, arm A design-note prompt.**
  In the pilot, Sonnet on the pandas task used up the design phase's token limit exploring before it wrote any note, in both attempts of every run, so those pairs were excluded.
  That would drop the largest tasks for 1 model only.
  When arm A's design phase now ends without a note, arm A gets 1 more prompt, committed in `prompts/design_note_now.md`, asking it to write the note from what it has learned, with a limit of 10 turns.
  The prompt has its own limits of 10 turns, 2,000,000 tokens, and the 2-hour wall clock, recorded with the others in each session's record.
  It changes only arm A's design phase, and the manipulation check still applies to the note.
* **2026-10-07, parallel scoring.**
  Scoring used 1 of the virtual machine's 12 cores, so suites are now scored 8 at a time, each in its own container.
  Machine load can still reach a score: pytest's per-test timeout and the hang watchdog are wall-clock limits, so under load a reference test can fail or time out, which changes validity and suite size, and a mutant run can fail by timeout as an ordinary kill.
  Each suite's mutant time limit is measured against its own reference run in the same container, timeout kills are counted separately, and jobs are queued task by task, so the arms of 1 task are scored at about the same time and face about the same load.
* **2026-10-07, hanging tests.**
  In the pilot, 1 agent-written test computed a number with 100 million digits on the reference implementation, in C code that pytest's per-test timeout cannot interrupt, so every reference run of its suite hung until the run limit and all 8 of its tests were lost.
  The test runner now watches each test from outside pytest and stops a test that runs longer than 60 seconds, or twice the task's own per-test timeout when that is longer; that test is marked as timed out, which makes it invalid, and the rest of the suite is run again without it, in a new process that skips the tests already decided.
  A test the process crashes in is marked as crashed and handled the same way, and a test file whose collection hangs counts as a collection error.
  A hanging test now invalidates only itself, the same way in every arm, and it is left out of that suite's mutant runs, where it would otherwise hang again.
  A process that has reported every test but does not exit is stopped after 10 seconds and keeps its outcomes.
  In a mutant run, a hang still counts as a kill.
* **2026-10-07, budget accounting.**
  The spending cap now counts every session's cost, reruns included; it had counted only the final attempt's.
