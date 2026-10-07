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
NETWORK = {"qwen": "tdd-net-qwen", "sonnet": "tdd-net-sonnet"}
GATEWAY = {"qwen": "tdd-gw-qwen", "sonnet": "tdd-gw-sonnet"}
QWEN_HOST = "192.168.1.16"  # ai-server.local; mDNS names do not resolve inside the gateway
MODELS = {
    "qwen": {"model": "llamacpp/qwen3.6-27b", "thinking": "high",
             "props": "http://ai-server.local:8080/upstream/qwen3.6-27b/props"},
    "sonnet": {"model": "anthropic/claude-sonnet-5-5", "thinking": "high"},
}
# Pilot limits (EXPERIMENT.md "Controlled variables"); the final values are set from the pilot.
LIMITS = {"design": {"turns": 120, "tokens": 7_700_000}, "tests": {"turns": 250, "tokens": 15_400_000}}  # from the pilot
# Arm A only, when the design phase ends with no note: 1 prompt to write it from what it learned (added after the pilot).
NOTE_LIMIT = {"turns": 10, "tokens": 2_000_000}
WALL_SECONDS = 2 * 3600
DEADLINE = None  # epoch seconds; a phase still running then is stopped with limit_reached "deadline"
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


def ensure_gateway(model_name):
    """The model's own internal network and gateway: a Qwen session cannot reach the Anthropic API, nor the reverse."""
    net, gw = NETWORK[model_name], GATEWAY[model_name]
    if docker.sh("network", "inspect", net, check=False).returncode:
        docker.sh("network", "create", "--internal", net, check=False)
    if docker.sh("inspect", gw, check=False).returncode == 0:
        docker.sh("start", gw)  # a no-op when it is already running
        return
    nginx = "nginx@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de"
    docker.sh("create", "--name", gw, "--restart", "unless-stopped", "-e", f"QWEN_HOST={QWEN_HOST}",
              "-e", "ANTHROPIC_API_KEY", "-e", "NGINX_ENVSUBST_FILTER=^(QWEN_HOST|ANTHROPIC_API_KEY)$", nginx)
    docker.sh("cp", os.path.join(ROOT, "docker", f"gateway-{model_name}"), f"{gw}:/etc/nginx/templates")
    docker.sh("network", "connect", "--alias", "gateway", net, gw)
    docker.sh("start", gw)


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
        self.lock = threading.Lock()  # the wall-clock timer sends abort from another thread

    def send(self, obj):
        with self.lock:
            self.n += 1
            obj["id"] = f"h{self.n}"
            self.p.stdin.write((json.dumps(obj) + "\n").encode())
            self.p.stdin.flush()

    def phase(self, phase, text):
        """Send 1 prompt and consume events until Pi settles. Returns the phase's counts.

        A limit (turns, tokens, or this phase's wall clock) aborts the phase and keeps what it wrote. The phase
        crashed only when Pi rejected the prompt, exited, or its final response ended in an error after Pi's own
        retries; an error Pi recovered from is recorded but is not a crash."""
        lim = NOTE_LIMIT if phase == "note" else LIMITS[phase]
        st = {"phase": phase, "turns": 0, "tokens": 0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
              "cost": 0.0, "limit_reached": None, "stop_reasons": [], "errors": [], "compactions": 0,
              "crash": None, "started_at": _now()}
        final_error = None

        secs, why = WALL_SECONDS, "wall"
        if DEADLINE is not None and DEADLINE - time.time() < secs:
            secs, why = max(0, DEADLINE - time.time()), "deadline"

        def wall():
            if not st["limit_reached"]:
                st["limit_reached"] = why
                self.send({"type": "abort"})

        timers = [threading.Timer(secs, wall), threading.Timer(secs + 300, self.p.kill)]
        for t in timers:
            t.start()
        try:
            self.send({"type": "prompt", "message": text})
            for line in self.p.stdout:  # LF-only framing, as Pi's RPC docs require
                self.log.write(line)
                try:
                    ev = json.loads(line)
                except ValueError:
                    st["errors"].append("unparsable RPC line")
                    continue
                t = ev.get("type")
                if t == "response" and not ev.get("success", True):
                    st["errors"].append(ev.get("error"))
                    if ev.get("command") == "prompt":
                        st["crash"] = f"prompt rejected: {ev.get('error')}"
                        break
                elif t == "message_end" and (ev.get("message") or {}).get("role") == "assistant":
                    m = ev["message"]
                    u = m.get("usage") or {}
                    for k, f in (("input", "input"), ("output", "output"), ("cache_read", "cacheRead"),
                                 ("cache_write", "cacheWrite")):
                        st[k] += u.get(f, 0) or 0
                    st["tokens"] = st["input"] + st["output"] + st["cache_read"] + st["cache_write"]
                    st["cost"] += (u.get("cost") or {}).get("total", 0) or 0
                    st["stop_reasons"].append(m.get("stopReason"))
                    final_error = m.get("errorMessage") or "error" if m.get("stopReason") == "error" else None
                    if final_error:
                        st["errors"].append(final_error)
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
                st["crash"] = "pi exited before settling"
        finally:
            for t in timers:
                t.cancel()
        if final_error and not st["limit_reached"] and not st["crash"]:
            st["crash"] = f"final response error: {final_error}"
        st["finished_at"] = _now()
        return st

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=60)
        except Exception:
            self.p.kill()


def run_session(row, arm, model_name, run_dir, spec_text, note=None):
    """Run 1 arm's session in a new container and collect its outputs into run_dir.
    Any harness error becomes a crash of this session, never an exception that stops the run."""
    os.makedirs(run_dir, exist_ok=True)
    model = MODELS[model_name]
    info = {"arm": arm, "model": model["model"], "thinking": model["thinking"], "limits": {**LIMITS, "note": NOTE_LIMIT},
            "wall_seconds_per_phase": WALL_SECONDS, "started_at": _now(), "phases": [], "crashed": None}
    c = None
    try:
        if "props" in model:
            info["server_props"] = json.load(urllib.request.urlopen(model["props"], timeout=600))
        c = docker.start(docker.tag(row, "agent"), f"sess-{arm}-{uuid.uuid4().hex[:8]}", network=NETWORK[model_name])
        docker.sh("cp", os.path.join(ROOT, "pi"), f"{c}:/root/.pi-agent")
        drv = Driver(c, model, os.path.join(run_dir, "events.jsonl"))
        try:
            for phase, text in messages(arm, spec_text, note):
                st = drv.phase(phase, text)
                info["phases"].append(st)
                if st["crash"]:
                    info["crashed"] = st["crash"]
                    break
                if phase == "design" and docker.get(c, "/root/design_note.md") is None:
                    st = drv.phase("note", prompt("design_note_now.md"))
                    info["phases"].append(st)
                    if st["crash"]:
                        info["crashed"] = st["crash"]
                        break
        finally:
            drv.close()
        if drv.p.returncode not in (0, None) and not info["crashed"]:
            info["crashed"] = f"pi exited {drv.p.returncode}"
    except Exception as e:  # noqa: BLE001 - an unattended run must survive any single session's failure
        info["crashed"] = f"harness error: {e!r}"[:2000]
    finally:
        if c:
            try:
                collect(c, run_dir, arm)
            except Exception as e:  # noqa: BLE001
                info["crashed"] = info["crashed"] or f"collect error: {e!r}"[:2000]
            docker.stop(c)
    info["finished_at"] = _now()
    json.dump(info, open(os.path.join(run_dir, "session.json"), "w"), indent=1)
    return info


def collect(c, run_dir, arm):
    for src, dst in (("/root/session.jsonl", "session.jsonl"), ("/root/design_note.md", "design_note.md")):
        data = docker.get(c, src)
        if data is not None:
            open(os.path.join(run_dir, dst), "wb").write(data)
    # Untracked and ignored files both count: a test file in a git-ignored directory is still a new file.
    status = docker.run(c, "cd /testbed && git status --porcelain -z --untracked-files=all --ignored", check=False).stdout
    tests = [l[3:] for l in status.split("\0") if l[:3] in ("?? ", "!! ")
             and os.path.basename(l[3:]).startswith("test_tdd_") and l.endswith(".py")]
    for path in tests:
        content = docker.get(c, f"/testbed/{path}")
        if content is None:
            continue
        out = os.path.join(run_dir, "tests", path)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "wb").write(content)
    diff = docker.run(c, "cd /testbed && git diff", check=False).stdout
    open(os.path.join(run_dir, "changes.txt"), "w").write(status.replace("\0", "\n") + "\n" + diff)
    # Every path the session created or changed anywhere in the container, for the isolation check.
    open(os.path.join(run_dir, "container_diff.txt"), "w").write(docker.sh("diff", c, check=False).stdout)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
