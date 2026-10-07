"""Runs inside a prepared stub container (stdlib only): find copies of the feature's code anywhere on disk.

    python leakscan.py CANDIDATES.json > hits.json

CANDIDATES.json maps each gold-patched file to its distinctive lines. Prints
{"hits": {file: {gold_file: distinct lines matched}}, "unscanned_archives": [...]}.
Plain files are searched with grep; zip-like archives (wheel, egg, zip) and tarballs are opened and their .py
members searched. Archives in formats the stdlib cannot open (.conda, .tar.zst) are listed as unscanned.
"""
import json
import os
import subprocess
import sys
import tarfile
import zipfile

SKIP = ("/proc", "/sys", "/dev")
ZIPS = (".whl", ".egg", ".zip", ".jar")
TARS = (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")
OTHER = (".conda", ".tar.zst")


def main(cand_path):
    cands = json.load(open(cand_path))
    owner = {}
    for gold, lines in cands.items():
        for l in lines:
            owner.setdefault(l, set()).add(gold)
    patterns = "/tmp/leak_patterns.txt"
    with open(patterns, "w") as f:
        f.write("\n".join(owner) + "\n")
    hits = {}

    def record(path, text):
        for gold in owner.get(text, ()):
            hits.setdefault(path, {}).setdefault(gold, set()).add(text)

    if owner:
        out = subprocess.run(["grep", "-rIoF", "-f", patterns, "/"] + [f"--exclude-dir={d[1:]}" for d in SKIP],
                             capture_output=True, text=True, errors="replace").stdout
        for line in out.splitlines():
            path, _, text = line.partition(":")
            if path not in (patterns, cand_path):
                record(path, text)

    unscanned = []
    for root, dirs, files in os.walk("/"):
        if root == "/":
            dirs[:] = [d for d in dirs if "/" + d not in SKIP]
        for name in files:
            path = os.path.join(root, name)
            low = name.lower()
            try:
                if low.endswith(ZIPS):
                    with zipfile.ZipFile(path) as z:
                        for m in z.namelist():
                            if m.endswith(".py"):
                                scan_text(f"{path}!{m}", z.read(m), owner, record)
                elif low.endswith(TARS):
                    with tarfile.open(path) as t:
                        for m in t.getmembers():
                            if m.isfile() and m.name.endswith(".py"):
                                scan_text(f"{path}!{m.name}", t.extractfile(m).read(), owner, record)
                elif low.endswith(OTHER):
                    unscanned.append(path)
            except Exception:  # noqa: BLE001 - an unreadable archive is listed, not fatal
                unscanned.append(path)
    os.remove(patterns)
    json.dump({"hits": {p: {g: len(v) for g, v in d.items()} for p, d in sorted(hits.items())},
               "unscanned_archives": sorted(unscanned)}, sys.stdout)


def scan_text(path, data, owner, record):
    text = data.decode("utf-8", "replace")
    for line in text.split("\n"):
        s = line.strip()
        if s in owner:
            record(path, s)


if __name__ == "__main__":
    main(sys.argv[1])
