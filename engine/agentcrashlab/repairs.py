from __future__ import annotations

import ast
import copy
import difflib
import html
import json
import shutil
import tempfile
import uuid
from pathlib import Path

from . import store
from .contracts import ContractError, digest, load_agent, source_path
from .engine import get_run, run


def create_repair(run_id, files, explanation, provenance, usage=None):
    original = get_run(run_id)
    if original["status"] != "fail":
        raise ContractError("A repair must be based on an observed failing run")
    if len([r for r in store.listing("repair") if r["run_id"] == run_id]) >= 3:
        raise ContractError("This failure already has three candidate repair attempts")
    root, manifest = load_agent(original["agent_id"])
    if not isinstance(files, dict) or not files or set(files) - set(manifest["editable_files"]):
        raise ContractError("Repair rejected: only manifest-declared agent source files may be edited")
    patch = ""
    originals = {}
    for name, source in files.items():
        if not isinstance(source, str) or len(source) > 100_000:
            raise ContractError("Repair source is invalid or too large")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ContractError(f"Repair is invalid Python: {exc.msg}") from None
        if not any(isinstance(n, ast.AsyncFunctionDef) and n.name == "run" for n in tree.body):
            raise ContractError("The repaired agent must retain async run(context, task)")
        before = source_path(root, name).read_text()
        original_tree = ast.parse(before)
        calls_model = lambda parsed: any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "model" for n in ast.walk(parsed))
        if calls_model(original_tree) and not calls_model(tree):
            raise ContractError("Repair rejected: the agent's model integration must be preserved")
        originals[name] = digest(before)
        patch += "".join(difflib.unified_diff(before.splitlines(keepends=True), source.splitlines(keepends=True), fromfile="a/" + name, tofile="b/" + name))
    if not patch:
        raise ContractError("Repair made no changes")
    return store.put("repair", {"id": str(uuid.uuid4()), "run_id": run_id, "agent_id": original["agent_id"], "files": files, "patch": patch, "original_hashes": originals, "manifest_hash": original["manifest_hash"], "explanation": str(explanation)[:8000], "provenance": provenance, "usage": usage or {}, "created_at": store.now(), "status": "unverified", "verification_runs": []})


def verify(repair_id, runner, cancel=None):
    if runner not in {"modal", "docker"}:
        raise ContractError("Generated code verification requires an isolated Modal or Docker runner")
    repair = store.get("repair", repair_id)
    original = get_run(repair["run_id"])
    root, manifest = load_agent(original["agent_id"])
    if digest(manifest) != repair["manifest_hash"] or any(digest(source_path(root, n).read_text()) != h for n, h in repair["original_hashes"].items()):
        raise ContractError("Source or evaluation contract changed; generate a new repair")
    scenario = original["scenario"]
    variations = [{"name": "Healthy control", "faults": []}, scenario]
    if manifest["domain"] == "workspace":
        overrides = [{"name": "Lunar Studio", "members": ["Ari"]}, {"name": "Field Notes", "members": ["Jules", "Sam", "Ren"]}]
    else:
        overrides = [{"artifact": "component-library", "revision": "v3"}, {"artifact": "release-bundle", "revision": "v4"}]
    variations.extend({**scenario, "name": f"Task variation {i+1}", "task_overrides": override, "seed": scenario["seed"] + i + 1} for i, override in enumerate(overrides))
    repair.update(status="verifying", verification_runs=[])
    store.put("repair", repair)
    with tempfile.TemporaryDirectory(prefix="acl-repair-") as temp:
        directory = Path(temp)
        for name in manifest["editable_files"]:
            destination = directory / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(repair["files"].get(name, source_path(root, name).read_text()))
        for test in variations:
            if cancel and cancel.is_set():
                break
            result = run(original["agent_id"], test, mode=original["mode"], provider=original.get("provider") or "meta", model=original.get("model"), runner=runner, directory=directory, entrypoint=manifest["entrypoint"], cancel=cancel)
            repair["verification_runs"].append(result["id"])
            store.put("repair", repair)
    results = [store.get("run", i) for i in repair["verification_runs"]]
    repair["status"] = "verified" if len(results) == len(variations) and all(r["status"] == "pass" for r in results) else "failed" if any(r["status"] == "fail" for r in results) else "inconclusive"
    repair["verification_mode"] = original["mode"]
    repair["verified_at"] = store.now()
    return store.put("repair", repair)


def regression_test(repair):
    original = get_run(repair["run_id"])
    # Evaluator assertions come from the frozen manifest, never model-generated code.
    return '''"""Regression exported by AgentCrashLab. Run in the AgentCrashLab checkout.
Apply candidate.patch to a disposable agent copy, then set ACL_AGENT_COPY to it.
Requires an available Docker runner. No assertion is supplied by the repair model.
"""
import json
import os
import unittest
from agentcrashlab.engine import run

SCENARIO = json.loads(%r)

class RecoveryRegression(unittest.TestCase):
    def test_recovery_contract(self):
        result = run(%r, SCENARIO, mode=%r, provider=%r, model=%r,
                     runner="docker", directory=os.environ["ACL_AGENT_COPY"], entrypoint="agent.py")
        self.assertEqual(result["status"], "pass", result)

if __name__ == "__main__":
    unittest.main()
''' % (json.dumps(original["scenario"]), original["agent_id"], original["mode"], original.get("provider") or "meta", original.get("model"))


def report(document):
    escaped = html.escape(json.dumps(document, indent=2))
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>AgentCrashLab evidence</title><style>body{{background:#101319;color:#e4e8ee;font:16px system-ui;max-width:1100px;margin:64px auto;padding:24px}}h1{{color:#b9f56b}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#1a1e26;padding:24px;border-radius:12px;font:13px monospace}}p{{color:#a5adb9}}</style><h1>AgentCrashLab / Evidence report</h1><p>Offline fixtures, live inference, recorded replay, and isolated verification are identified separately in this report. A verified repair only satisfies the recorded test matrix.</p><pre>{escaped}</pre></html>'''
