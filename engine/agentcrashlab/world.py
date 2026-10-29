from __future__ import annotations

import copy
from .contracts import digest


class ToolError(Exception):
    def __init__(self, code, message, retry_after=0):
        super().__init__(message)
        self.code, self.retry_after = code, retry_after


class World:
    """Only the parent process can mutate or evaluate the authoritative world."""

    def __init__(self, manifest, task, scenario, emit):
        self.domain, self.task = manifest["domain"], task
        self.tools = {t["name"]: t for t in manifest["tools"]}
        self.scenario, self.emit = scenario, emit
        self.state = copy.deepcopy(manifest["initial_state"])
        if self.domain == "publisher":
            self.state["artifact"].update(name=task["artifact"], revision=task["revision"])
        self.initial = copy.deepcopy(self.state)
        self.historical = copy.deepcopy(manifest.get("historical_state", self.initial))
        self.ledger, self.calls, self.activated = {}, {}, []
        self.history = [copy.deepcopy(self.state)]
        self.violations = []

    def call(self, name, args):
        if name not in self.tools or not isinstance(args, dict):
            raise ToolError("invalid_tool", "Unknown tool or invalid arguments")
        self.calls[name] = self.calls.get(name, 0) + 1
        occurrence = self.calls[name]
        call_id = f"{name}:{occurrence}"
        self.emit("request", {"call_id": call_id, "tool": name, "arguments": args})
        fault = next((f for f in self.scenario["faults"] if f["tool"] == name and f["occurrence"] == occurrence), None)
        try:
            if fault:
                self.activated.append(dict(fault))
                self.emit("fault", {"call_id": call_id, "fault_kind": fault["kind"], "tool": fault["tool"], "occurrence": fault["occurrence"]})
                if fault["kind"] == "timeout_before_write":
                    raise ToolError("timeout", "The service response timed out")
                if fault["kind"] == "rate_limit":
                    raise ToolError("rate_limit", "The service temporarily rate limited this call", 1)
                if fault["kind"] == "stale_read":
                    result = self.read(name, args, self.historical)
                    self.emit("observation", {"call_id": call_id, "tool": name, "result": result, "stale": True})
                    return result
            result = self.execute(name, args, call_id)
            if fault and fault["kind"] == "timeout_after_write":
                raise ToolError("timeout", "The service response timed out")
            self.emit("observation", {"call_id": call_id, "tool": name, "result": result})
            return result
        except ToolError as exc:
            self.emit("observation", {"call_id": call_id, "tool": name, "error": {"code": exc.code, "message": str(exc), "retry_after": exc.retry_after}})
            raise

    def read(self, name, args, state):
        if name == "list_workspaces":
            return [copy.deepcopy(w) for w in state["workspaces"] if w["name"] == args.get("name")]
        if name == "list_members":
            return [copy.deepcopy(m) for m in state["members"] if m["workspace_id"] == args.get("workspace_id")]
        if name == "get_artifact":
            return copy.deepcopy(state["artifact"])
        if name == "list_publications":
            return copy.deepcopy(state["publications"])
        raise ToolError("invalid_tool", "Unknown read tool")

    def execute(self, name, args, call_id):
        if self.tools[name]["effect"] == "read":
            return self.read(name, args, self.state)
        key = args.get("operation_key")
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise ToolError("invalid_arguments", "Writes require a nonempty operation_key")
        identity = (name, key)
        signature = digest({k: v for k, v in args.items() if k != "operation_key"})
        if identity in self.ledger:
            cached = self.ledger[identity]
            if cached[0] != signature:
                raise ToolError("key_conflict", "Operation key was reused with different arguments")
            self.emit("deduplicated", {"call_id": call_id, "operation_key": key})
            return copy.deepcopy(cached[1])
        if name == "create_workspace":
            if not isinstance(args.get("name"), str):
                raise ToolError("invalid_arguments", "name is required")
            result = {"id": f"ws_{len(self.state['workspaces']) + 1}", "name": args["name"]}
            self.state["workspaces"].append(result)
        elif name == "add_member":
            if args.get("workspace_id") not in {w["id"] for w in self.state["workspaces"]} or args.get("member") not in self.task["members"]:
                raise ToolError("invalid_arguments", "Unknown workspace or task member")
            result = {"workspace_id": args["workspace_id"], "member": args["member"]}
            self.state["members"].append(result)
        elif name == "send_invite":
            result = {"workspace_id": args.get("workspace_id"), "member": args.get("member")}
            if result not in self.state["members"]:
                self.violations.append("invite_after_membership")
            self.state["invites"].append(result)
        elif name == "publish_artifact":
            revision = args.get("revision")
            if not isinstance(revision, str):
                raise ToolError("invalid_arguments", "revision is required")
            result = {"artifact": self.task["artifact"], "revision": revision, "id": f"pub_{len(self.state['publications']) + 1}"}
            self.state["publications"].append(result)
            if revision != self.task["revision"]:
                self.violations.append("requested_revision_only")
        else:
            raise ToolError("invalid_tool", "Unknown write tool")
        self.ledger[identity] = (signature, copy.deepcopy(result))
        self.history.append(copy.deepcopy(self.state))
        self.emit("effect", {"call_id": call_id, "tool": name, "result": result, "state": copy.deepcopy(self.state)})
        return copy.deepcopy(result)

    def assertions(self):
        if self.domain == "workspace":
            workspaces = [w for w in self.state["workspaces"] if w["name"] == self.task["name"]]
            valid_id = workspaces[0]["id"] if len(workspaces) == 1 else None
            expected = sorted(self.task["members"])
            members = [m["member"] for m in self.state["members"] if m["workspace_id"] == valid_id]
            invites = [m["member"] for m in self.state["invites"] if m["workspace_id"] == valid_id]
            checks = [("one_workspace", len(workspaces) == 1 and len(self.state["workspaces"]) == 1, f"Expected 1 workspace; observed {len(self.state['workspaces'])}"), ("exact_membership", sorted(members) == expected, f"Expected members {expected}; observed {members}"), ("one_invite_per_member", sorted(invites) == expected and len(self.state["invites"]) == len(expected), f"Expected one invite per member; observed {len(self.state['invites'])}"), ("invite_after_membership", "invite_after_membership" not in self.violations, "Invitations must follow membership creation")]
        else:
            publications = self.state["publications"]
            checks = [("one_publication", len(publications) == 1, f"Expected 1 publication; observed {len(publications)}"), ("requested_revision_only", bool(publications) and all(p["revision"] == self.task["revision"] for p in publications) and "requested_revision_only" not in self.violations, f"Only revision {self.task['revision']} may be published"), ("artifact_preserved", self.state["artifact"] == self.initial["artifact"], "Publication must preserve the source artifact")]
        return [{"id": name, "passed": passed, "detail": detail} for name, passed, detail in checks]
