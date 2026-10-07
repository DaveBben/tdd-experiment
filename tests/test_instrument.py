"""Known-answer tests for the instrument: spec, stub, mutator, analysis."""
import ast
import json
import random

from harness import analyze, data, mutate, stub

# --- spec ---------------------------------------------------------------------

PS = """## Task
Do the thing.

**NOTE**:
- write code under /testbed/

## Interface Descriptions

### Clarification
Path: `/testbed/pkg/a.py`
```python
def f(x): ...
```

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/pkg/a.py`
```python
def f(x: int) -> int:
    \"\"\"
    Double x.

    Examples:
        >>> f(2)
        4

    Returns the double.
    \"\"\"
    # <your code>
```
"""


def test_spec_strips_note_clarification_and_doctests():
    s = data.spec({"problem_statement": PS})
    assert "NOTE" not in s and "Clarification" not in s and ">>>" not in s and "    4" not in s
    assert "Do the thing." in s and "Returns the double." in s and "Examples" not in s
    assert data.interfaces(s) == [("pkg/a.py", data.interfaces(s)[0][1])]
    assert "def f(x: int)" in data.interfaces(s)[0][1]


def test_gold_added_lines_are_removal_minus_lines_on_old_side():
    patch = (
        "diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n"
        "@@ -3,4 +3,4 @@\n ctx\n-gone1\n-gone2\n+\n+\n ctx\n"
        "diff --git a/tests/test_a.py b/tests/test_a.py\n--- a/tests/test_a.py\n+++ b/tests/test_a.py\n"
        "@@ -1,1 +1,1 @@\n-x\n+\n"
    )
    row = {"patch": patch, "FAIL_TO_PASS": ["tests/test_a.py"]}
    assert data.gold_added_lines(row) == {"pkg/a.py": {4, 5}}
    assert "tests/test_a.py" not in data.gold_patch(row)


# --- stub ---------------------------------------------------------------------

UNDEVELOPED = """import sys

if sys.version_info >= (3, 11):
    G = 1
else:

    class G(Exception):
        message: str




class K:
    x: int = 1

    def keep(self):
        return 1
"""

IFACE = """class G(Exception):
    message: str

    def __init__(self, message: str) -> None:
        \"\"\"Doc.\"\"\"
        # <your code>

class K:
    x: int = 1
    y: int = 2

    def keep(self):
        # <your code>

    @property
    def p(self):
        # <your code>

    @p.setter
    def p(self, v):
        # <your code>

def new_func(a):
    # <your code>
"""


def test_stub_inserts_missing_members_only():
    out = stub.build(UNDEVELOPED, [IFACE])
    tree = ast.parse(out)
    g = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "G")
    k = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "K")
    assert [stub._name(n) for n in g.body] == ["message", "__init__"]
    assert [stub._name(n) for n in k.body] == ["x", "keep", "y", "p", "p"]
    keep = k.body[1]
    assert isinstance(keep.body[0], ast.Return)  # existing code untouched
    assert stub._name(tree.body[-1]) == "new_func"
    assert out.count("raise NotImplementedError") == 4  # __init__, p, p.setter, new_func
    assert stub.build(UNDEVELOPED, [IFACE]) == out  # deterministic


def test_stub_of_missing_file_is_the_interface():
    out = stub.build("", ["def f(x):\n    # <your code>\n"])
    assert out == "\n\n\ndef f(x):\n    raise NotImplementedError\n"


# --- mutator ------------------------------------------------------------------

SRC = b'''def f(a: int = 1, b=2) -> "str":
    """Doc string."""
    if a < b and not a:
        a += 3
        return "hi"
    x = a * b
    print(f"v{a}")
    return x == None
'''


def ops(src, lines):
    return sorted((m["line"], m["op"], m["new"]) for m in mutate.mutants_for_file("m.py", src, lines))


def test_mutator_operators_on_known_source():
    got = ops(SRC, set(range(1, 10)))
    assert (3, "comparison", "(a <= b)") in got
    assert (3, "boolean", "(a < b or not a)") in got
    assert (3, "boolean", "(a)") in got  # not removed
    assert (4, "arithmetic", "a -= 3") in got
    assert (4, "constant", "(4)") in got
    assert (4, "statement", "pass") in got
    assert (5, "constant", "('XX')") in got
    assert (5, "return", "return None") in got
    assert (6, "arithmetic", "(a / b)") in got
    assert (8, "comparison", "(x != None)") in got
    assert (1, "constant", "(2)") in got and (1, "constant", "(3)") in got  # defaults mutate
    # Docstring, annotations, f-string internals: none.
    assert not any(line == 2 for line, _, _ in got)
    assert not any("XX" in new for line, _, new in got if line in (1, 7))
    assert not any(new == "('XX')" for line, _, new in got if line == 7)


def test_mutator_respects_added_lines_and_every_mutant_compiles_and_differs():
    assert all(line == 6 for line, _, _ in ops(SRC, {6}))
    for m in mutate.mutants_for_file("m.py", SRC, set(range(1, 10))):
        mutated = mutate.apply(SRC, m)
        compile(mutated, "m.py", "exec")
        assert ast.dump(ast.parse(mutated)) != ast.dump(ast.parse(SRC))


def test_mutant_sample_is_seeded_and_capped():
    pool = [{"i": i} for i in range(250)]
    a, b = mutate.sample(pool, 7, "t1"), mutate.sample(pool, 7, "t1")
    assert a == b and len(a) == 100 and [m["id"] for m in a] == list(range(100))
    assert mutate.sample(pool, 7, "t2") != a
    assert len(mutate.sample(pool[:30], 7, "t1")) == 30


# --- analysis -----------------------------------------------------------------

def write_runs(tmp_path, effect, invalid_b=0.0, tasks=20, runs=3, seed=0, exclude=()):
    rng = random.Random(seed)
    for t in range(tasks):
        base = rng.uniform(30, 70)
        for r in range(1, runs + 1):
            for arm, shift, inv in (("A", 0, 0), ("B", effect, invalid_b), ("C", effect / 2, 0)):
                d = tmp_path / f"org__repo{t % 4}.task{t}" / arm / str(r)
                d.mkdir(parents=True)
                score = {"mutation_score": base + shift + rng.gauss(0, 2), "invalid_rate": inv,
                         "suite_size": 10 + rng.randint(0, 3)}
                (d / "score.json").write_text(json.dumps(score))
                excluded = "crash" if (t, r) in exclude and arm == "B" else None
                (d / "manifest.json").write_text(json.dumps({"excluded": excluded}))
    return str(tmp_path)


def test_analysis_verdicts_on_known_effects(tmp_path):
    assert analyze.main(write_runs(tmp_path / "s", 10))["verdict"] == "supported"
    assert analyze.main(write_runs(tmp_path / "z", 0))["verdict"] == "inconclusive"
    assert analyze.main(write_runs(tmp_path / "o", -10))["verdict"] == "opposite"
    assert analyze.main(write_runs(tmp_path / "g", 10, invalid_b=5))["verdict"] == "guard failed"
    small = analyze.main(write_runs(tmp_path / "m", 3))
    assert small["verdict"] == "inconclusive" and small["primary_B_minus_A"]["wilcoxon_p"] < 0.025


def test_analysis_estimates_and_is_deterministic(tmp_path):
    runs = write_runs(tmp_path, 10)
    r1, r2 = analyze.main(runs), analyze.main(runs)
    assert r1 == r2
    p = r1["primary_B_minus_A"]
    assert 9 < p["mean_diff"] < 11 and p["ci"][0] < p["mean_diff"] < p["ci"][1]
    assert p["wins_ties_losses"] == [20, 0, 0] and p["n"] == 20
    assert 4 < r1["secondary_C_minus_A"]["mean_diff"] < 6


def test_exclusion_drops_whole_pair_and_thin_tasks(tmp_path):
    runs = write_runs(tmp_path, 10, exclude={(0, 1), (1, 1), (1, 2)})
    data_ = analyze.load(runs)
    assert len(data_["org__repo0.task0"]["A"]) == 2  # pair 1 dropped from every arm
    assert "org__repo1.task1" not in data_  # 1 pair left: task dropped


# --- pilot rules -------------------------------------------------------------------

def test_sample_size_formula_matches_design():
    from harness import pilot
    assert pilot.n_for(10) == 47  # EXPERIMENT.md: "at σ = 10, n = 47"
    assert pilot.n_for(6.3) <= 20 < pilot.n_for(6.5)  # "20 tasks are enough only when σ is at most about 6.3"


def test_pilot_rules_on_synthetic_pilot(tmp_path):
    from harness import pilot
    runs = write_runs(tmp_path, 0, tasks=3)
    for b in (tmp_path).glob("*/B/*"):
        b2 = b.parent.parent / "B2" / b.name
        b2.mkdir(parents=True)
        (b2 / "score.json").write_text((b / "score.json").read_text())
    r = pilot.main([runs])
    m = r["per_model"][runs]
    assert m["tasks"] == 3 and m["aa"]["mean"] == 0 and m["aa"]["ok"]
    assert r["sigma"] == 10 and r["n"] == 47 and r["runs"] == 3  # small spread: the σ floor of 10 holds


# --- task filter rule --------------------------------------------------------------

def test_filter_rule():
    from harness import prepare
    base = {"gold_f2p": {"exit": 0, "failing": [], "summary": "== 40 passed in 1s =="},
            "gold_p2p": {"exit": 1, "failing": ["t.py::net"], "summary": ""},
            "stub_p2p": {"exit": 1, "failing": ["t.py::net"], "summary": ""},
            "stub_compiles": True, "stub_imports": True, "library": "pkg",
            "leak_candidates": {"pkg/a.py": 70, "pkg/b.py": 2},
            "leak_hits": {"/site/numpy/x.py": {"pkg/a.py": 2}}, "unscanned_archives": ["/x/other-1.0.conda"]}
    assert prepare.decide(base)  # env failure shared by gold and stub, idiom-only hit, unrelated archive: kept
    assert not prepare.decide({**base, "leak_hits": {"/env2/pkg/a.py": {"pkg/a.py": 10}}})  # copy of a.py
    assert prepare.decide({**base, "leak_hits": {"/env2/pkg/a.py": {"pkg/a.py": 9}}})
    assert not prepare.decide({**base, "leak_hits": {"/w.whl!pkg/b.py": {"pkg/b.py": 3}}})  # small file, threshold 3
    assert not prepare.decide({**base, "unscanned_archives": ["/x/pkg-2.0-py_0.conda"]})
    assert not prepare.decide({**base, "stub_p2p": {"exit": 1, "failing": ["t.py::net", "t.py::other"], "summary": ""}})
    assert not prepare.decide({**base, "gold_f2p": {"exit": 1, "failing": ["a", "b", "c"], "summary": "37 passed"}})
    assert prepare.decide({**base, "gold_f2p": {"exit": 1, "failing": ["a"], "summary": "39 passed"}})
    assert not prepare.decide({**base, "stub_imports": False})
