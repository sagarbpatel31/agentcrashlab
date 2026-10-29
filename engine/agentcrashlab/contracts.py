from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAULTS = {"timeout_before_write", "timeout_after_write", "rate_limit", "stale_read"}


class ContractError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def source_path(root: Path, relative: str) -> Path:
    if (root / relative).is_symlink():
        raise ContractError("Symlinked agent source is not supported")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.is_symlink():
        raise ContractError("Source must be an existing regular file inside the agent directory")
    if path.stat().st_size > 100_000:
        raise ContractError("Agent source exceeds the 100 KB limit")
    return path


def load_agent(agent_id: str):
    root = (ROOT / "examples" / agent_id).resolve()
    if root.parent != (ROOT / "examples").resolve():
        raise ContractError("Unknown agent")
    manifest = json.loads((root / "manifest.json").read_text())
    for filename in manifest["editable_files"]:
        source_path(root, filename)
    return root, manifest


def inspect_agent(agent_id):
    root, manifest = load_agent(agent_id)
    return {"manifest": manifest, "sources": {name: source_path(root, name).read_text() for name in manifest["editable_files"]}}


def validate_scenario(value, manifest):
    if not isinstance(value, dict) or set(value) - {"name", "description", "faults", "seed", "task_overrides"}:
        raise ContractError("Experiment contains unsupported fields")
    faults = value.get("faults", [])
    if not isinstance(faults, list) or len(faults) > 6:
        raise ContractError("An experiment supports at most six faults")
    tools = {t["name"]: t for t in manifest["tools"]}
    cleaned = []
    seen = set()
    for fault in faults:
        if not isinstance(fault, dict) or set(fault) != {"kind", "tool", "occurrence"}:
            raise ContractError("A fault needs kind, tool and occurrence")
        kind, tool, occurrence = fault["kind"], fault["tool"], fault["occurrence"]
        if kind not in FAULTS or tool not in tools or type(occurrence) is not int or not 1 <= occurrence <= 20:
            raise ContractError("Invalid fault kind, tool or occurrence")
        is_read = tools[tool]["effect"] == "read"
        if (kind == "stale_read" and not is_read) or (kind in {"timeout_before_write", "timeout_after_write"} and is_read):
            raise ContractError("The fault is incompatible with the tool's effect")
        key = (tool, occurrence)
        if key in seen:
            raise ContractError("Only one fault may target a particular call")
        seen.add(key)
        cleaned.append(dict(fault))
    overrides = value.get("task_overrides", {})
    if not isinstance(overrides, dict) or set(overrides) - {"name", "members", "artifact", "revision"}:
        raise ContractError("Unsupported task variation")
    if set(overrides) - set(manifest["task"]):
        raise ContractError("Task variation fields must belong to this agent's task")
    if "members" in overrides and (not isinstance(overrides["members"], list) or not 1 <= len(overrides["members"]) <= 10 or not all(isinstance(x, str) and len(x) <= 100 for x in overrides["members"])):
        raise ContractError("Members must be a short list of names")
    if "members" in overrides and len(set(overrides["members"])) != len(overrides["members"]):
        raise ContractError("Task members must be unique")
    for name, item in overrides.items():
        if name != "members" and (not isinstance(item, str) or not 1 <= len(item) <= 100):
            raise ContractError("Task variations must be short strings")
    seed = value.get("seed", 42)
    if type(seed) is not int or not 0 <= seed <= 2**31:
        raise ContractError("Seed must be a positive 32-bit integer")
    return {"name": str(value.get("name", "Untitled experiment"))[:100], "description": str(value.get("description", ""))[:2000], "faults": cleaned, "seed": seed, "task_overrides": overrides}


def default_scenarios(manifest):
    write = next(t["name"] for t in manifest["tools"] if t["effect"] == "write")
    read = next(t["name"] for t in manifest["tools"] if t["effect"] == "read")
    return [
        {"name": "Healthy control", "faults": []},
        {"name": "Response lost after commit", "faults": [{"kind": "timeout_after_write", "tool": write, "occurrence": 1}]},
        {"name": "Write never reached the service", "faults": [{"kind": "timeout_before_write", "tool": write, "occurrence": 1}]},
        {"name": "Temporary rate limit", "faults": [{"kind": "rate_limit", "tool": write, "occurrence": 1}]},
        {"name": "Stale service observation", "faults": [{"kind": "stale_read", "tool": read, "occurrence": 1}]},
    ]
