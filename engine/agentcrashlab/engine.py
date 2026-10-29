from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from . import providers, runners, store
from .contracts import ROOT, ContractError, digest, load_agent, validate_scenario
from .world import ToolError, World


def run(agent_id, scenario, *, mode="offline", runner="fixture", provider="meta", model=None, directory=None, entrypoint=None, reference=False, cancel=None, run_id=None, timeout=None):
    root, manifest = load_agent(agent_id)
    scenario = validate_scenario(scenario, manifest)
    task = {**manifest["task"], **scenario["task_overrides"]}
    if mode not in {"offline", "live"}:
        raise ContractError("Mode must be offline or live")
    if mode == "live" and not next((p["configured"] for p in providers.configuration() if p["id"] == provider), False):
        raise ContractError("Configure the selected provider before starting a live run")
    source_dir = Path(directory) if directory else root
    entrypoint = entrypoint or ("reference.py" if reference else "fixture.py" if mode == "offline" else manifest["entrypoint"])
    if runner == "fixture" and (directory or mode != "offline" or entrypoint not in {"fixture.py", "reference.py"}):
        raise ContractError("Fixture execution only permits included offline controllers; generated patches require Docker or Modal")
    source = (source_dir / entrypoint).read_text()
    identifier = run_id or str(uuid.uuid4())
    doc = {"id": identifier, "agent_id": agent_id, "scenario": scenario, "task": task, "manifest_hash": digest(manifest), "source_hash": digest(source), "mode": mode, "runner": runner, "provider": provider if mode == "live" else None, "model": model or next((p["model"] for p in providers.configuration() if p["id"] == provider), None) if mode == "live" else None, "status": "running", "started_at": store.now(), "assertions": [], "usage": {"model_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": None}, "reference": reference}
    store.put("run", doc)
    doc["source_kind"] = "candidate" if directory else "reference" if reference else "fixture" if mode == "offline" else "original"
    store.put("run", doc)
    trace = []

    def emit(kind, data):
        event = {"seq": len(trace), "kind": kind, "elapsed_ms": round((time.monotonic() - started) * 1000), **copy.deepcopy(data)}
        trace.append(event)
        store.event(identifier, event)

    started = time.monotonic()
    world = World(manifest, task, scenario, emit)
    process = None
    staging = None
    error, finished, cancelled, limit = None, False, False, False
    deadline = started + (timeout or int(os.environ.get("ACL_TIMEOUT_SECONDS", "60")))
    model_limit = int(os.environ.get("ACL_MODEL_CALL_LIMIT", "12"))
    try:
        staging = tempfile.TemporaryDirectory(prefix="acl-source-")
        execution_dir = Path(staging.name)
        filenames = [entrypoint] if runner == "fixture" else manifest["editable_files"]
        for filename in filenames:
            destination = execution_dir / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_dir / filename, destination)
        process = runners.start(execution_dir, entrypoint, task, runner, max(1, int(deadline - started)))
        requests = 0
        while True:
            if cancel and cancel.is_set():
                cancelled = True
                break
            if time.monotonic() >= deadline or requests >= 100:
                limit = True
                break
            message = process.receive(min(0.2, max(0.01, deadline - time.monotonic())))
            if message == "waiting":
                continue
            if message is None:
                error = "Agent exited before reporting completion"
                break
            if not isinstance(message, dict):
                raise ContractError("Agent emitted an invalid bridge message")
            requests += 1
            kind = message.get("kind")
            if kind == "finished":
                finished = True
                emit("finished", {"result": message.get("result")})
                break
            if kind == "agent_error":
                error = str(message.get("error", "Agent failed"))[:1000]
                break
            try:
                if kind == "tool":
                    result = world.call(message.get("name"), message.get("arguments"))
                    # Persist effects after each request, not just after completion.
                    doc["state"] = copy.deepcopy(world.state)
                    store.put("run", doc)
                elif kind == "sleep":
                    seconds = message.get("seconds", 0)
                    if not isinstance(seconds, (float, int)) or not 0 <= seconds <= 5:
                        raise ToolError("invalid_delay", "Retry delay must be between 0 and 5 seconds")
                    emit("retry_delay", {"seconds": seconds, "virtual": True})
                    result = {"elapsed": seconds}
                elif kind == "model":
                    if mode != "live":
                        # Candidate repairs can be tested with a declared deterministic
                        # model stub; these runs remain explicitly offline.
                        emit("model_fixture", {"detail": "Task-shaped deterministic response; no provider called"})
                        process.send({"result": {"content": json.dumps(task), "usage": {}, "cost_usd": None}})
                        continue
                    if doc["usage"]["model_calls"] >= model_limit:
                        limit = True
                        break
                    messages = message.get("messages")
                    if not isinstance(messages, list) or len(json.dumps(messages)) > 100_000:
                        raise ToolError("invalid_messages", "Invalid or oversized model input")
                    doc["usage"]["model_calls"] += 1
                    emit("model_request", {"provider": provider, "model": doc["model"]})
                    result = providers.complete(provider, model, messages)
                    usage = result["usage"]
                    doc["usage"]["input_tokens"] += usage.get("prompt_tokens", 0)
                    doc["usage"]["output_tokens"] += usage.get("completion_tokens", 0)
                    emit("model", {"provider": provider, "model": result["model"], "usage": usage, "cost_usd": None})
                else:
                    raise ToolError("invalid_request", "Unsupported bridge operation")
                process.send({"result": result})
            except ToolError as exc:
                doc["state"] = copy.deepcopy(world.state)
                store.put("run", doc)
                process.send({"error": {"code": exc.code, "message": str(exc), "retry_after": exc.retry_after}})
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:1000]
    finally:
        if process:
            try:
                process.close()
                doc["cleanup"] = "completed"
            except Exception as exc:
                doc["cleanup"] = "failed"
                error = error or f"Runner cleanup failed: {type(exc).__name__}"
        if staging:
            staging.cleanup()
    assertions = world.assertions()
    coverage = len(world.activated) == len(scenario["faults"])
    failures = [a for a in assertions if not a["passed"]]
    # An observed safety violation remains a failure even if later execution stops.
    safety_ids = {"one_workspace", "invite_after_membership", "one_publication", "requested_revision_only"}
    observed_violation = bool(world.violations) or (world.domain == "workspace" and len(world.state["workspaces"]) > 1) or (world.domain == "publisher" and len(world.state["publications"]) > 1)
    if observed_violation or (finished and failures):
        status = "fail"
    elif error:
        status = "error"
    elif cancelled or limit or not finished or not coverage:
        status = "inconclusive"
    else:
        status = "pass"
    doc.update(status=status, finished_at=store.now(), elapsed_ms=round((time.monotonic() - started) * 1000), assertions=assertions, fault_coverage={"planned": len(scenario["faults"]), "activated": len(world.activated), "faults": world.activated}, state=world.state, error=error, cancelled=cancelled, limit_reached=limit, completed=finished, first_failure=next((a for a in assertions if not a["passed"]), None) if status == "fail" else None)
    emit("evaluation", {"status": status, "assertions": assertions, "fault_coverage": doc["fault_coverage"]})
    doc["trace_hash"] = digest(trace)
    store.put("run", doc)
    return {**doc, "events": trace}


def get_run(identifier):
    return {**store.get("run", identifier), "events": store.events(identifier)}


def replay(identifier):
    original = get_run(identifier)
    _, manifest = load_agent(original["agent_id"])
    if digest(manifest) != original["manifest_hash"] or digest(original["events"]) != original["trace_hash"]:
        raise ContractError("Replay refused: manifest or recorded evidence changed")
    captured = []
    world = World(manifest, original["task"], original["scenario"], lambda kind, data: captured.append({"kind": kind, **copy.deepcopy(data)}))
    for event in original["events"]:
        if event["kind"] == "request":
            try:
                world.call(event["tool"], event["arguments"])
            except ToolError:
                pass
    expected = [{k: v for k, v in e.items() if k not in {"seq", "elapsed_ms"}} for e in original["events"] if e["kind"] in {"request", "effect", "fault", "observation", "deduplicated"}]
    verified = captured == expected and world.state == original["state"] and world.assertions() == original["assertions"]
    return {"verified": verified, "original_status": original["status"], "model_called": False, "detail": "Re-executed recorded tool actions; no fresh model inference", "run_id": identifier}


def reduce_failure(identifier, **options):
    original = get_run(identifier)
    root, manifest = load_agent(original["agent_id"])
    entrypoint = "reference.py" if original["reference"] else "fixture.py" if original["mode"] == "offline" else manifest["entrypoint"]
    if digest((root / entrypoint).read_text()) != original["source_hash"]:
        raise ContractError("Reduction requires the unchanged original agent source")
    if original["status"] != "fail" or not original["scenario"]["faults"]:
        raise ContractError("Only a failing experiment with faults can be reduced")
    scenario = copy.deepcopy(original["scenario"])
    retained = list(scenario["faults"])
    trials = []
    for fault in list(retained):
        candidate = {**scenario, "faults": [f for f in retained if f != fault], "name": "Reduction trial"}
        result = run(original["agent_id"], candidate, mode=original["mode"], runner=original["runner"], provider=original.get("provider") or "meta", model=original.get("model"), **options)
        trials.append(result["id"])
        if result["status"] == "fail" and result["first_failure"]["id"] == original["first_failure"]["id"]:
            retained = candidate["faults"]
    return {"scenario": {**scenario, "faults": retained}, "trials": trials, "minimality": "Single-fault deletion pass; not a global-minimum guarantee"}
