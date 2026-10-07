"""FeatureBench task data at the pinned revision: rows, spec, interfaces, gold-patch lines."""
import json
import os
import re

REPO_ID = "LiberCoders/FeatureBench"
REVISION = "76b4a4566e04f4bcc13c35125d4f301791efa736"
FILENAME = "data/fast-00000-of-00001.parquet"
CACHE = os.path.join(os.path.dirname(__file__), "..", ".cache", "hf")


def load_rows():
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(REPO_ID, FILENAME, repo_type="dataset", revision=REVISION, cache_dir=CACHE)
    rows = pq.read_table(path).to_pylist()
    for r in rows:
        r["repo_settings"] = json.loads(r["repo_settings"])
    return {r["instance_id"]: r for r in rows}


# --- spec -------------------------------------------------------------------

def _cut(text, start, end):
    """Remove text from the line matching `start` up to (not including) the line matching `end`."""
    m = re.search(start, text, re.M)
    n = re.search(end, text[m.end():], re.M)
    return text[: m.start()] + text[m.end() + n.start():]


def strip_doctests(text):
    """Drop `>>>` examples and their output lines, then any Example(s) header left empty."""
    out, in_example = [], False
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith(">>>") or (in_example and s.startswith("...")):
            in_example = True
            continue
        if in_example and s and not s.startswith('"""') and not s.startswith("# <your code>"):
            continue  # expected output of the example
        in_example = False
        out.append(line)
    # An "Examples:" / numpydoc "Examples\n--------" header whose body is now empty.
    text = "\n".join(out)
    text = re.sub(r"\n[ \t]*Examples?:?[ \t]*\n(?:[ \t]*-+[ \t]*\n)?(?=[ \t]*\n|[ \t]*\"\"\")", "\n", text)
    return text


def spec(row):
    """The problem statement with the NOTE block, the Clarification block, and doctests removed."""
    ps = row["problem_statement"]
    ps = _cut(ps, r"^\*\*NOTE\*\*", r"^## Interface Descriptions")
    ps = _cut(ps, r"^### Clarification", r"^### Interface Description 1$")
    return strip_doctests(ps).rstrip() + "\n"


def interfaces(spec_text):
    """[(path under /testbed, python source)] for every interface block, in order."""
    return [(p, code) for p, code in re.findall(r"^Path: `/testbed/([^`]+)`\s*\n```python\n(.*?)\n```", spec_text, re.M | re.S)]


# --- gold patch ---------------------------------------------------------------

def _file_blocks(patch):
    """Split a unified diff into (path, block_text) per file."""
    blocks = re.split(r"(?m)^(?=diff --git )", patch)
    for b in blocks:
        m = re.match(r"diff --git a/(\S+) b/(\S+)", b)
        if m:
            yield m.group(1), b


def gold_patch(row):
    """FeatureBench's gold patch: the removal patch minus file blocks touching fail-to-pass test files.

    It is applied *reversed* (`git apply -R`) to the undeveloped repository, as preprocess_hf_patch does.
    """
    f2p = set(row["FAIL_TO_PASS"])
    return "".join(b for p, b in _file_blocks(row["patch"]) if p not in f2p)


def gold_added_lines(row):
    """{path: set of line numbers in the reference file} for lines the gold patch adds.

    Those are the removal patch's `-` lines, numbered on its old (complete) side.
    """
    out = {}
    for path, block in _file_blocks(gold_patch(row)):
        if not path.endswith(".py"):
            continue
        lines, old = set(), 0
        for line in block.split("\n"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", line)
            if m:
                old = int(m.group(1))
            elif old and line.startswith("-"):
                lines.add(old)
                old += 1
            elif old and line.startswith(" "):
                old += 1
        if lines:
            out[path] = lines
    return out
