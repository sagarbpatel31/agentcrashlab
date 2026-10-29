from __future__ import annotations

import copy
import io
import json
import os
import shutil
import signal
import subprocess
import threading
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import providers, store
from .contracts import ROOT, ContractError, default_scenarios, inspect_agent, load_agent, validate_scenario
from .engine import get_run, reduce_failure, replay, run
from .repairs import create_repair, regression_test, report, verify

_campaign_lock = threading.Lock()
_cancellations = {}
_threads = {}


def agents():
    return [load_agent(p.name)[1] for p in sorted((ROOT / "examples").iterdir()) if (p / "manifest.json").exists()]


def launch(kind, operation):
    if not _campaign_lock.acquire(blocking=False):
        raise ContractError("Another campaign is running. Cancel it or wait for completion.")
    identifier = str(uuid.uuid4())
    cancel = threading.Event()
    _cancellations[identifier] = cancel
    job = store.put("job", {"id": identifier, "kind": kind, "status": "running", "created_at": store.now(), "run_ids": []})

    def worker():
        try:
            result = operation(job, cancel)
            job.update(status="cancelled" if cancel.is_set() else "completed", result=result)
        except Exception as exc:
            job.update(status="error", error=str(exc)[:1000])
        finally:
            job["finished_at"] = store.now()
            store.put("job", job)
            _cancellations.pop(identifier, None)
            _threads.pop(identifier, None)
            _campaign_lock.release()

    thread = threading.Thread(target=worker, daemon=True)
    _threads[identifier] = thread
    thread.start()
    return job


def campaign(body):
    agent_id = body.get("agent_id", "workspace")
    _, manifest = load_agent(agent_id)
    scenarios = body.get("scenarios", default_scenarios(manifest))
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 12:
        raise ContractError("A campaign needs 1–12 experiments")
    scenarios = [validate_scenario(s, manifest) for s in scenarios]
    mode, runner = body.get("mode", "offline"), body.get("runner", "fixture")
    provider, model = body.get("provider", "meta"), body.get("model")
    if mode == "live" and not next((p["configured"] for p in providers.configuration() if p["id"] == provider), False):
        raise ContractError("Selected provider is not configured")
    if mode == "live" and runner == "fixture":
        raise ContractError("Live agents need a Docker or Modal runner")
    reference = bool(body.get("reference", False))

    def perform(job, cancel):
        job.update(agent_id=agent_id, mode=mode, reference=reference)
        for scenario in scenarios:
            if cancel.is_set():
                break
            identifier = str(uuid.uuid4())
            job["run_ids"].append(identifier)
            store.put("job", job)
            run(agent_id, scenario, mode=mode, runner=runner, provider=provider, model=model, reference=reference, cancel=cancel, run_id=identifier)
        return {"run_ids": job["run_ids"]}

    return launch("reference" if reference else "campaign", perform)


def export(kind, identifier, format_):
    if kind == "run":
        doc = get_run(identifier)
    elif kind == "repair":
        doc = store.get("repair", identifier)
        doc = {**doc, "original_run": get_run(doc["run_id"]), "verification": [get_run(i) for i in doc["verification_runs"]]}
    else:
        raise ContractError("Unknown export kind")
    if format_ == "html":
        return report(doc).encode(), "text/html", "evidence.html"
    if format_ == "json":
        return json.dumps(doc, indent=2).encode(), "application/json", "evidence.json"
    if kind == "repair" and format_ == "patch":
        return doc["patch"].encode(), "text/plain", "candidate.patch"
    if kind == "repair" and format_ == "test":
        return regression_test(doc).encode(), "text/x-python", "test_recovery.py"
    if format_ == "zip":
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("evidence.json", json.dumps(doc, indent=2))
            archive.writestr("evidence.html", report(doc))
            if kind == "repair":
                archive.writestr("candidate.patch", doc["patch"])
                archive.writestr("test_recovery.py", regression_test(doc))
                for name, source in doc["files"].items():
                    archive.writestr("candidate/" + name, source)
        return output.getvalue(), "application/zip", "agentcrashlab-evidence.zip"
    raise ContractError("Unknown export format")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, data, status=200):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self):
        token = os.environ.get("ACL_INTERNAL_TOKEN")
        return bool(token) and self.headers.get("Authorization") == "Bearer " + token

    def do_GET(self):
        if not self.authorized():
            return self.respond({"error": "Unauthorized"}, 401)
        url = urlparse(self.path)
        parts = url.path.strip("/").split("/")
        try:
            if parts == ["health"]:
                return self.respond({"ok": True})
            if parts == ["bootstrap"]:
                catalog = agents()
                return self.respond({"agents": catalog, "metrics": {a["id"]: store.metrics(a["id"]) for a in catalog}, "providers": providers.configuration(), "runs": store.listing("run"), "jobs": store.listing("job"), "repairs": store.listing("repair"), "runners": {"docker_installed": bool(shutil.which("docker")), "modal_installed": __import__("importlib.util", fromlist=["find_spec"]).find_spec("modal") is not None}})
            if parts[0] == "agents" and len(parts) == 2:
                agent = inspect_agent(parts[1])
                return self.respond({**agent, "scenarios": default_scenarios(agent["manifest"])})
            if parts[0] == "runs" and len(parts) == 2:
                return self.respond(get_run(parts[1]))
            if parts[0] == "jobs" and len(parts) == 2:
                return self.respond(store.get("job", parts[1]))
            if parts[0] == "repairs" and len(parts) == 2:
                return self.respond(store.get("repair", parts[1]))
            if parts[0] == "export" and len(parts) == 3:
                format_ = parse_qs(url.query).get("format", ["json"])[0]
                payload, mime, name = export(parts[1], parts[2], format_)
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                return self.wfile.write(payload)
            self.respond({"error": "Not found"}, 404)
        except (KeyError, FileNotFoundError):
            self.respond({"error": "Not found"}, 404)
        except (ValueError, ContractError) as exc:
            self.respond({"error": str(exc)}, 400)

    def do_POST(self):
        if not self.authorized():
            return self.respond({"error": "Unauthorized"}, 401)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 <= length <= 500_000:
                return self.respond({"error": "Request too large"}, 413)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ContractError("Expected a JSON object")
            parts = urlparse(self.path).path.strip("/").split("/")
            if parts == ["campaigns"]:
                return self.respond(campaign(body), 202)
            if len(parts) == 3 and parts[0] == "runs" and parts[2] == "replay":
                return self.respond(replay(parts[1]))
            if len(parts) == 3 and parts[0] == "runs" and parts[2] == "reduce":
                return self.respond(launch("reduction", lambda job, cancel: reduce_failure(parts[1], cancel=cancel)), 202)
            if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "cancel":
                cancel = _cancellations.get(parts[1])
                if cancel:
                    cancel.set()
                return self.respond({"accepted": bool(cancel)})
            if parts == ["repairs"]:
                return self.respond(create_repair(body["run_id"], body["files"], body.get("explanation", ""), body.get("provenance", "user supplied"), body.get("usage")), 201)
            if parts == ["investigations"]:
                _, manifest = load_agent(body["agent_id"])
                body["scenarios"] = [validate_scenario(s, manifest) for s in body["scenarios"]]
                body.update(id=str(uuid.uuid4()), created_at=store.now())
                return self.respond(store.put("investigation", body), 201)
            if len(parts) == 3 and parts[0] == "repairs" and parts[2] == "verify":
                return self.respond(launch("verification", lambda job, cancel: verify(parts[1], body.get("runner", "modal"), cancel)), 202)
            self.respond({"error": "Not found"}, 404)
        except (ContractError, ValueError, KeyError, FileNotFoundError) as exc:
            self.respond({"error": str(exc)}, 400)
        except Exception as exc:
            self.respond({"error": f"Operation failed: {type(exc).__name__}"}, 500)


def serve(port=8765):
    # Interrupted jobs cannot silently look as though they are still executing.
    for job in store.listing("job"):
        if job["status"] == "running":
            job.update(status="error", error="The service restarted before this job completed")
            store.put("job", job)
    for result in store.listing("run"):
        if result["status"] == "running":
            result.update(status="inconclusive", error="The service restarted during execution")
            store.put("run", result)
    for repair in store.listing("repair"):
        if repair["status"] == "verifying":
            repair.update(status="inconclusive", error="The service restarted during verification")
            store.put("repair", repair)
    stop = threading.Event()

    def shutdown(*_):
        stop.set()
        for cancel in list(_cancellations.values()):
            cancel.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 0.25
    try:
        while not stop.is_set():
            server.handle_request()
    finally:
        shutdown()
        for thread in list(_threads.values()):
            thread.join(timeout=40)
        server.server_close()
