"""One Pi session in a new agent container, driven over RPC, with turn, token, and wall-clock limits.

Writes into RUN_DIR: events.jsonl (every RPC record), session.jsonl (Pi's session file),
design_note.md (arm A), tests/<path> (the new test_tdd_*.py files), changes.txt (every other change
the agent made, for audit), and session.json (counts, limits, stop reasons).
"""
import json
import os
import subprocess
import threading
import time
import urllib.request
import uuid

from harness import docker

ROOT = docker.ROOT
NETWORK, GATEWAY = "tdd-agents", "tdd-gateway"
QWEN_HOST = "192.168.1.16"  # ai-server.local; mDNS names do not resolve inside the gateway
MODELS = {
    "qwen": {"model": "llamacpp/qwen3.6-27b", "thinking": "high",
             "props": "http://ai-server.local:8080/upstream/qwen3.6-27b/props"},
    "sonnet": {"model": "anthropic/claude-sonnet-5-5", "thinking": "high"},
}
# Pilot limits (EXPERIMENT.md "Controlled variables"); the final values are set from the pilot.
LIMITS = {"design": {"turns": 100, "tokens": 5_000_000}, "tests": {"turns": 200, "tokens": 10_000_000}}
WALL_SECONDS = 2 * 3600
PI_ENV = {"PI_CODING_AGENT_DIR": "/root/.pi-agent", "PI_OFFLINE": "1", "PI_TELEMETRY": "0",
          "PI_SKIP_VERSION_CHECK": "1"}
PI_FLAGS = ["--mode", "rpc", "--tools", "read,write,edit,bash", "--no-extensions", "--no-mcp", "--no-skills",
            "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve",
            "--session", "/root/session.jsonl"]


def prompt(name):
    return open(os.path.join(ROOT, "prompts", name)).read()


def messages(arm, spec_text, note=None):
    """The exact user messages each arm receives, in order."""
    head = prompt("context.md") + spec_text
    if arm == "A":
        return [("design", head + prompt("design_note.md")), ("tests", prompt("tests.md"))]
    if arm == "C":
        head += prompt("arm_c_note.md").replace("{note}", note.strip())
    return [("tests", head + prompt("tests.md"))]


def ensure_gateway():
    if docker.sh("network", "inspect", NETWORK, check=False).returncode:
        docker.sh("network", "create", "--internal", NETWORK)
    if docker.sh("inspect", GATEWAY, check=False).returncode == 0:
        docker.sh("start", GATEWAY)  # a no-op when it is already running
        return
    nginx = "nginx@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de"
    docker.sh("create", "--name", GATEWAY, "-e", f"QWEN_HOST={QWEN_HOST}", "-e", "ANTHROPIC_API_KEY",
              "-e", "NGINX_ENVSUBST_FILTER=^(QWEN_HOST|ANTHROPIC_API_KEY)$", nginx)
    docker.sh("cp", os.path.join(ROOT, "docker", "gateway"), f"{GATEWAY}:/etc/nginx/templates")
    docker.sh("network", "connect", "--alias", "gateway", NETWORK, GATEWAY)
    docker.sh("start", GATEWAY)


def build_agent_image(row):
    docker.sh("build", "--platform", "linux/amd64", "-q", "-f", os.path.join(ROOT, "docker", "agent.Dockerfile"),
              "--build-arg", f"BASE={docker.tag(row, 'stub')}", "-t", docker.tag(row, "agent"), os.path.join(ROOT, "docker"))


class Driver:
    """RPC client for 1 Pi process; logs every record."""

    def __init__(self, container, model, log):
        env = " ".join(f"{k}={v}" for k, v in PI_ENV.items())
        cmd = f"{docker.CONDA} && {env} pi --model {model['model']} --thinking {model['thinking']} {' '.join(PI_FLAGS)}"
        self.p = subprocess.Popen(["docker", "exec", "-i", container, "bash", "-c", cmd],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open(log + ".stderr", "wb"))
        self.log = open(log, "ab")
        self.n = 0

    def send(self, obj):
        self.n += 1
        obj["id"] = f"h{self.n}"
        self.p.stdin.write((json.dumps(obj) + "\n").encode())
        self.p.stdin.flush()

    def phase(self, phase, text):
        """Send 1 prompt and consume events until Pi settles. Returns the phase's counts."""
        lim = LIMITS[phase]
        st = {"phase": phase, "turns": 0, "tokens": 0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
              "cost": 0.0, "limit_reached": None, "stop_reasons": [], "errors": [], "compactions": 0}
        self.send({"type": "prompt", "message": text})
        for line in self.p.stdout:  # LF-only framing, as Pi's RPC docs require
            self.log.write(line)
            ev = json.loads(line)
            t = ev.get("type")
            if t == "response" and not ev.get("success", True):
                st["errors"].append(ev.get("error"))
                if ev.get("command") == "prompt":
                    break
            elif t == "message_end" and ev["message"].get("role") == "assistant":
                m = ev["message"]
                u = m.get("usage") or {}
                for k, f in (("input", "input"), ("output", "output"), ("cache_read", "cacheRead"), ("cache_write", "cacheWrite")):
                    st[k] += u.get(f, 0)
                st["tokens"] = st["input"] + st["output"] + st["cache_read"] + st["cache_write"]
                st["cost"] += (u.get("cost") or {}).get("total", 0)
                st["stop_reasons"].append(m.get("stopReason"))
                if m.get("stopReason") == "error":
                    st["errors"].append(m.get("errorMessage"))
            elif t == "turn_end":
                st["turns"] += 1
                if not st["limit_reached"] and (st["turns"] >= lim["turns"] or st["tokens"] >= lim["tokens"]):
                    st["limit_reached"] = "turns" if st["turns"] >= lim["turns"] else "tokens"
                    self.send({"type": "abort"})
            elif t and t.startswith("compaction"):
                st["compactions"] += 1
            elif t == "agent_settled":
                break
        else:
            st["errors"].append("pi exited before settling")
        return st

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=60)
        except Exception:
            self.p.kill()


def run_session(row, arm, model_name, run_dir, spec_text, note=None):
    """Run 1 arm's session in a new container and collect its outputs into run_dir."""
    os.makedirs(run_dir, exist_ok=True)
    model = MODELS[model_name]
    info = {"arm": arm, "model": model["model"], "thinking": model["thinking"], "limits": LIMITS,
            "wall_seconds": WALL_SECONDS, "started_at": _now(), "phases": [], "crashed": None}
    if "props" in model:
        info["server_props"] = json.load(urllib.request.urlopen(model["props"], timeout=600))
    name = f"sess-{arm}-{uuid.uuid4().hex[:8]}"
    c = docker.start(docker.tag(row, "agent"), name, network=NETWORK)
    try:
        docker.sh("cp", os.path.join(ROOT, "pi"), f"{c}:/root/.pi-agent")
        drv = Driver(c, model, os.path.join(run_dir, "events.jsonl"))
        wall = threading.Event()
        timer = threading.Timer(WALL_SECONDS, lambda: (wall.set(), drv.p.kill()))
        timer.start()
        try:
            for phase, text in messages(arm, spec_text, note):
                st = drv.phase(phase, text)
                info["phases"].append(st)
                if st["errors"] and not st["limit_reached"]:
                    info["crashed"] = st["errors"][-1]
                    break
        finally:
            timer.cancel()
            drv.close()
        if wall.is_set():
            info["crashed"] = "wall-clock limit"
        elif drv.p.returncode not in (0, None) and not info["crashed"]:
            info["crashed"] = f"pi exited {drv.p.returncode}"
        collect(c, run_dir, arm)
    finally:
        docker.stop(c)
    info["finished_at"] = _now()
    json.dump(info, open(os.path.join(run_dir, "session.json"), "w"), indent=1)
    return info


def collect(c, run_dir, arm):
    for src, dst in (("/root/session.jsonl", "session.jsonl"), ("/root/design_note.md", "design_note.md")):
        data = docker.get(c, src)
        if data is not None:
            open(os.path.join(run_dir, dst), "wb").write(data)
    status = docker.run(c, "cd /testbed && git status --porcelain --untracked-files=all", check=False).stdout
    tests = [l[3:] for l in status.splitlines() if l.startswith("?? ") and os.path.basename(l[3:]).startswith("test_tdd_")
             and l.endswith(".py")]
    for path in tests:
        out = os.path.join(run_dir, "tests", path)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "wb").write(docker.get(c, f"/testbed/{path}"))
    diff = docker.run(c, "cd /testbed && git diff", check=False).stdout
    open(os.path.join(run_dir, "changes.txt"), "w").write(status + "\n" + diff)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
