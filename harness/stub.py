"""Build the stub: every interface member missing from the undeveloped source, with a body of
`raise NotImplementedError`, inserted where it belongs (its class, or the end of the module)."""
import ast
import re
import textwrap


def _iface_module(code):
    code = re.sub(r"(?m)^(\s*)# <your code>\s*$", r"\1raise NotImplementedError", code)
    return code, ast.parse(code)


def _scope(body):
    """Statements of a scope, looking through if/try/with blocks but not into defs or classes."""
    for node in body:
        yield node
        if isinstance(node, (ast.If, ast.Try, ast.With)):
            for sub in ("body", "orelse", "handlers", "finalbody"):
                for child in getattr(node, sub, []):
                    yield from _scope(child.body if isinstance(child, ast.ExceptHandler) else [child])


def _name(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None


def _source(lines, node):
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return textwrap.dedent("\n".join(lines[start - 1 : node.end_lineno]))


def build(source, iface_codes):
    """Return `source` with every missing member of the interface blocks `iface_codes` added."""
    tree = ast.parse(source) if source.strip() else ast.Module(body=[], type_ignores=[])
    have = {_name(n): n for n in _scope(tree.body) if _name(n)}
    original = {id(n) for n in have.values()}
    inserts = []  # (after_line, indent, text); after_line None = end of module
    members = {}  # id(class node) -> member names it has, including ones added here
    for code in iface_codes:
        code, itree = _iface_module(code)
        ilines = code.split("\n")
        for node in itree.body:
            name = _name(node)
            target = have.get(name)
            if target is None:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    inserts.append((None, "", _source(ilines, node)))
                    # ponytail: a later block naming this new class again is ignored; merge if a task needs it
                    have[name] = node
                continue
            if not (isinstance(node, ast.ClassDef) and isinstance(target, ast.ClassDef)) or id(target) not in original:
                continue
            have_members = members.setdefault(id(target), {_name(n) for n in target.body})
            indent = " " * target.body[0].col_offset
            for member in node.body:
                mname = _name(member)
                if mname and mname not in have_members:
                    # Every member with this name, so a property and its setter travel together.
                    inserts.append((target.end_lineno, indent, _source(ilines, member)))
            have_members |= {_name(m) for m in node.body}

    lines = source.split("\n")
    tail = [text for after, _, text in inserts if after is None]
    by_line = {}
    for after, indent, text in inserts:
        if after is not None:
            by_line.setdefault(after, []).append(textwrap.indent(text, indent))
    for after in sorted(by_line, reverse=True):
        lines[after:after] = ["", *"\n\n".join(by_line[after]).split("\n")]
    out = "\n".join(lines).rstrip("\n")
    if tail:
        out += "\n\n\n" + "\n\n\n".join(tail)
    return out + "\n"
