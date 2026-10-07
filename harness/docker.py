"""Thin docker CLI helpers. Every task container runs linux/amd64 with no network unless asked."""
import json
import os
import subprocess
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
CPUS, MEMORY = "4", "8g"  # the same for every container, recorded in each manifest
CONDA = "source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && cd /testbed"


def image_ref(row):
    digests = json.load(open(os.path.join(ROOT, "images.lock.json")))
    name = row["image_name"].split(":")[0]
    return f"{name}@{digests[name]}"


def tag(row, kind):
    return f"tdd-task:{row['instance_id']}-{kind}"


def sh(*args, check=True, input=None, timeout=None):
    r = subprocess.run(["docker", *args], capture_output=True, text=True, input=input, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f"docker {' '.join(args[:3])} failed ({r.returncode}): {r.stderr[-2000:]}")
    return r


def start(image, name, network="none", extra=()):
    sh("rm", "-f", name, check=False)
    sh("run", "-d", "--platform", "linux/amd64", "--name", name, "--network", network,
       "--cpus", CPUS, "--memory", MEMORY, *extra, image, "sleep", "infinity")
    return name


def run(container, script, check=True, timeout=None, env=()):
    """Run a bash script as root inside the container."""
    envs = [a for k in env for a in ("-e", k)]
    return sh("exec", *envs, container, "bash", "-c", script, check=check, timeout=timeout)


def put(container, path, data):
    """Write `data` (str or bytes) to `path` inside the container."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data.encode() if isinstance(data, str) else data)
    try:
        sh("cp", f.name, f"{container}:{path}")
    finally:
        os.unlink(f.name)


def get(container, path):
    r = subprocess.run(["docker", "exec", container, "cat", path], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def stop(container):
    sh("rm", "-f", container, check=False)
