from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

BRIDGE = Path(__file__).with_name("child.py")


class LocalProcess:
    def __init__(self, directory, entrypoint, task, runner, timeout):
        self.runner = runner
        staging = Path(__file__).resolve().parents[2] / ".agentcrashlab" / "staging"
        staging.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="acl-agent-", dir=staging)
        root = Path(self.temp.name)
        root.chmod(0o755)
        for file in directory.glob("*.py"):
            shutil.copy2(file, root / file.name)
        shutil.copy2(BRIDGE, root / "_bridge.py")
        self.container_name = "acl-" + root.name
        if runner == "docker":
            command = ["docker", "run", "--rm", "-i", "--name", self.container_name, "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "64", "--memory", "256m", "--cpus", "1", "--user", "65534:65534", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "-v", f"{root}:/agent:ro", "-w", "/agent", "python:3.13-slim", "python", "-I", "-u", "/agent/_bridge.py"]
            child_entry = f"/agent/{entrypoint}"
        else:
            command = [sys.executable, "-I", "-u", str(root / "_bridge.py")]
            child_entry = str(root / entrypoint)
        environment = {"PATH": os.environ.get("PATH", ""), "HOME": self.temp.name}
        if runner == "docker":
            environment.update({key: value for key, value in os.environ.items() if key in {"HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"}})
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1, env=environment)
        self.queue = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.send({"entrypoint": child_entry, "task": task})

    def _read(self):
        try:
            for line in self.proc.stdout:
                if len(line) > 1_000_000:
                    self.queue.put(RuntimeError("Agent emitted an oversized message"))
                    break
                self.queue.put(line)
        finally:
            self.queue.put(None)

    def receive(self, timeout):
        try:
            item = self.queue.get(timeout=timeout)
        except queue.Empty:
            return "waiting"
        if isinstance(item, Exception):
            raise item
        return json.loads(item) if item is not None else None

    def send(self, result):
        self.proc.stdin.write(json.dumps(result) + "\n")
        self.proc.stdin.flush()

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(timeout=5)
        for stream in (self.proc.stdin, self.proc.stdout):
            if stream:
                stream.close()
        if self.container_name and shutil.which("docker"):
            # Also clean up after a killed Docker client.
            if self.runner == "docker":
                subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True, timeout=10)
        self.temp.cleanup()


class ModalProcess:
    def __init__(self, directory, entrypoint, task, runner, timeout):
        try:
            import modal
        except ImportError:
            raise RuntimeError("Install the Modal extra: uv sync --extra modal") from None
        self.sandbox = None
        try:
            image = modal.Image.debian_slim(python_version="3.13").add_local_dir(str(directory), "/agent", copy=True).add_local_file(str(BRIDGE), "/bridge.py", copy=True)
            app = modal.App.lookup("agentcrashlab", create_if_missing=True)
            self.sandbox = modal.Sandbox.create(app=app, image=image, timeout=timeout + 30, block_network=True, cpu=1, memory=256)
            self.proc = self.sandbox.exec("python", "-I", "-u", "/bridge.py")
            self.queue = queue.Queue()
            threading.Thread(target=self._read, daemon=True).start()
            self.send({"entrypoint": "/agent/" + entrypoint, "task": task})
        except BaseException:
            self.close()
            raise

    def _read(self):
        try:
            for line in self.proc.stdout:
                self.queue.put(line)
        except Exception as exc:
            self.queue.put(exc)
        finally:
            self.queue.put(None)

    def receive(self, timeout):
        try:
            item = self.queue.get(timeout=timeout)
        except queue.Empty:
            return "waiting"
        if isinstance(item, Exception):
            raise item
        return json.loads(item) if item is not None else None

    def send(self, result):
        self.proc.stdin.write((json.dumps(result) + "\n").encode())
        self.proc.stdin.drain()

    def close(self):
        if self.sandbox:
            self.sandbox.terminate()


def start(directory, entrypoint, task, runner, timeout):
    if runner not in {"fixture", "docker", "modal"}:
        raise ValueError("Choose fixture, docker or modal execution")
    process = (ModalProcess if runner == "modal" else LocalProcess)(directory, entrypoint, task, runner, timeout)
    process.runner = runner
    return process
