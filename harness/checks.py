"""Manipulation and isolation checks from EXPERIMENT.md "Manipulation check"."""
import ast
import json
import os
import re

from harness import data, docker, stub


def interface_names(spec_text):
    """Every function and class in the interface descriptions, with non-dunder methods."""
    names = set()
    for _, code in data.interfaces(spec_text):
        tree = stub._iface_module(code)[1]
        for node in tree.body:
            n = stub._name(node)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(n)
            if isinstance(node, ast.ClassDef):
                names |= {m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                          and not (m.name.startswith("__") and m.name.endswith("__"))}
    return sorted(names)


def design_note_ok(note, spec_text):
    """(ok, reasons): an entry for every interface name and at least 1 listed edge case."""
    if not note:
        return False, ["no design note"]
    missing = [n for n in interface_names(spec_text) if n not in note]
    edge = re.search(r"(?im)^#+\s*edge cases?\b.*\n((?:\s*\n)*)\s*([-*]|\d+\.)\s+\S", note)
    reasons = [f"missing entries: {missing}"] * bool(missing) + ["no edge cases listed"] * (not edge)
    return not reasons, reasons


def session_entries(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def no_compaction(session_path):
    return not any(e.get("type") == "compaction" for e in session_entries(session_path))


def tool_calls(session_path):
    """[(name, arguments, is_error)] in order, from Pi's session file."""
    calls, errors = [], {}
    for e in session_entries(session_path):
        m = e.get("message") or {}
        if m.get("role") == "assistant":
            calls += [b for b in m.get("content", []) if isinstance(b, dict) and b.get("type") == "toolCall"]
        elif m.get("role") == "toolResult":
            errors[m.get("toolCallId")] = m.get("isError")
    return [(b["name"], b.get("arguments") or {}, errors.get(b["id"])) for b in calls]


def isolation_suspects(row, session_path):
    """Successful reads of paths that were neither in the starting container nor written by the session.
    Paths used inside bash commands are listed for the hand check of transcripts."""
    calls = tool_calls(session_path)
    written = {_abs(a.get("path")) for n, a, _ in calls if n in ("write", "edit")}
    reads = sorted({_abs(a.get("path")) for n, a, err in calls if n == "read" and not err} - written - {None})
    if not reads:
        return []
    c = docker.start(docker.tag(row, "agent"), f"iso-{os.getpid()}-{abs(hash(session_path)) % 10**8}")
    try:
        docker.put(c, "/tmp/paths.json", json.dumps(reads))
        r = docker.run(c, "python3 -c \"import json,os;print(json.dumps([p for p in json.load(open('/tmp/paths.json'))"
                          " if not os.path.exists(p)]))\" 2>/dev/null || "
                          f"{docker.CONDA} && python -c \"import json,os;print(json.dumps([p for p in json.load(open('/tmp/paths.json'))"
                          " if not os.path.exists(p)]))\"")
        return json.loads(r.stdout)
    finally:
        docker.stop(c)


def _abs(p):
    if not p:
        return None
    return os.path.normpath(p if p.startswith("/") else os.path.join("/testbed", p))
