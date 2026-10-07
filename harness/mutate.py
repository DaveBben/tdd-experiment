"""The committed AST mutator. Stdlib only: it runs inside the task container, on the container's Python.

Each mutant is 1 splice of the reference file: bytes [start, end) replaced by `new`.
Only nodes starting on a gold-patch added line are mutated. Docstrings, annotations, and f-string internals (whose
positions are unreliable before Python 3.12) are skipped.

    python mutate.py ROOT ADDED_LINES.json SEED TASK_ID > mutants.json
"""
import ast
import copy
import json
import random
import sys

CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq,
       ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}
ARITH = {ast.Add: [ast.Sub], ast.Sub: [ast.Add], ast.Mult: [ast.Div], ast.Div: [ast.Mult, ast.FloorDiv],
         ast.FloorDiv: [ast.Div], ast.Mod: [ast.Mult]}
STMT = (ast.Expr, ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Raise, ast.Break, ast.Continue)
SAMPLE = 100


def _skipped(tree):
    """ids of docstring nodes and every node inside an annotation or an f-string."""
    skip = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body \
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            skip.update(id(n) for n in ast.walk(body[0]))
        if isinstance(node, ast.JoinedStr):
            skip.update(id(n) for n in ast.walk(node))
        for a in (getattr(node, "returns", None), getattr(node, "annotation", None)):
            if a is not None:
                skip.update(id(n) for n in ast.walk(a))
    return skip


def _variants(node):
    """(operator name, replacement node) for each mutant of `node`."""
    if isinstance(node, ast.Compare):
        for i, op in enumerate(node.ops):
            if type(op) in CMP:
                m = copy.deepcopy(node)
                m.ops[i] = CMP[type(op)]()
                yield "comparison", m
    elif isinstance(node, (ast.BinOp, ast.AugAssign)) and type(node.op) in ARITH:
        for new in ARITH[type(node.op)]:
            m = copy.deepcopy(node)
            m.op = new()
            yield "arithmetic", m
    elif isinstance(node, ast.BoolOp):
        m = copy.deepcopy(node)
        m.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        yield "boolean", m
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        yield "boolean", node.operand
    elif isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            yield "constant", ast.Constant(not v)
        elif isinstance(v, int):
            yield "constant", ast.Constant(v + 1)
        elif isinstance(v, str) and v:
            yield "constant", ast.Constant("XX")
    if isinstance(node, ast.Return) and node.value is not None:
        yield "return", ast.Return(ast.Constant(None))
    if isinstance(node, STMT):
        yield "statement", ast.Pass()


def _offset(line_starts, lineno, col):
    return line_starts[lineno - 1] + col


def mutants_for_file(path, src, added):
    """Every compiling, non-identical mutant of `src` (bytes) whose node starts on a line in `added`."""
    tree = ast.parse(src)
    skip = _skipped(tree)
    line_starts, pos = [], 0
    for line in src.split(b"\n"):
        line_starts.append(pos)
        pos += len(line) + 1
    out = []
    for node in ast.walk(tree):
        if id(node) in skip or getattr(node, "lineno", None) not in added:
            continue
        for op, new in _variants(node):
            text = ast.unparse(new)
            if text == ast.unparse(node):
                continue
            if isinstance(node, ast.expr):
                text = "(" + text + ")"
            start = _offset(line_starts, node.lineno, node.col_offset)
            end = _offset(line_starts, node.end_lineno, node.end_col_offset)
            mutated = src[:start] + text.encode() + src[end:]
            try:
                compile(mutated, path, "exec")
            except SyntaxError:
                continue
            if ast.dump(ast.parse(mutated)) == ast.dump(tree):
                continue
            out.append({"path": path, "line": node.lineno, "op": op, "start": start, "end": end,
                        "old": src[start:end].decode(), "new": text})
    return out


def sample(mutants, seed, task_id):
    rng = random.Random(f"{seed}:{task_id}")
    idx = sorted(rng.sample(range(len(mutants)), min(SAMPLE, len(mutants))))
    return [dict(mutants[i], id=n) for n, i in enumerate(idx)]


def apply(src, m):
    """The mutated source bytes for mutant `m` of reference source bytes `src`."""
    return src[: m["start"]] + m["new"].encode() + src[m["end"]:]


def main(root, added_json, seed, task_id):
    added = json.load(open(added_json))
    pool = []
    for path in sorted(added):
        with open(f"{root}/{path}", "rb") as f:
            pool += mutants_for_file(path, f.read(), set(added[path]))
    chosen = sample(pool, int(seed), task_id)
    json.dump({"task": task_id, "pool": len(pool), "mutants": chosen}, sys.stdout, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:])
