import argparse
import json
import os
import urllib.request
from pathlib import Path

from .contracts import default_scenarios, inspect_agent, load_agent
from .engine import get_run, reduce_failure, replay, run
from .repairs import verify
from .service import agents, export, serve
from .providers import load_environment


def main():
    load_environment()
    parser = argparse.ArgumentParser(prog="acl", description="AgentCrashLab: inspect, break, replay and verify Python agents")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("agents")
    for name in ("inspect", "demo", "campaign", "run"):
        p = sub.add_parser(name)
        p.add_argument("agent", nargs="?", default="workspace")
        if name in {"campaign", "run"}:
            p.add_argument("--mode", choices=["offline", "live"], default="offline")
            p.add_argument("--runner", choices=["fixture", "docker", "modal"], default="fixture")
            p.add_argument("--provider", choices=["meta", "baseten", "fireworks"], default="meta")
            p.add_argument("--model")
            p.add_argument("--scenario", type=Path)
    for name in ("replay", "reduce", "show"):
        sub.add_parser(name).add_argument("run_id")
    p = sub.add_parser("verify")
    p.add_argument("repair_id")
    p.add_argument("--runner", choices=["docker", "modal"], default="modal")
    for name in ("design", "repair"):
        p = sub.add_parser(name, help="Use the running local eve investigator")
        p.add_argument("target", help="Agent ID for design; failed run ID for repair")
        p.add_argument("--provider", choices=["meta", "baseten", "fireworks"], default="meta")
        p.add_argument("--model")
    p = sub.add_parser("export")
    p.add_argument("kind", choices=["run", "repair"])
    p.add_argument("id")
    p.add_argument("--format", choices=["json", "html", "zip", "patch", "test"], default="zip")
    p.add_argument("--output", required=True, type=Path)
    p = sub.add_parser("serve")
    p.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "serve":
        return serve(args.port)
    if args.command == "agents":
        result = agents()
    elif args.command == "inspect":
        result = inspect_agent(args.agent)
    elif args.command == "demo":
        _, manifest = load_agent(args.agent)
        scenario = default_scenarios(manifest)[1]
        naive = run(args.agent, scenario)
        reference = run(args.agent, scenario, reference=True)
        result = {"label": "Offline acceptance fixtures; reference is handwritten", "naive": naive, "reference": reference, "replay": replay(naive["id"])}
        if naive["status"] != "fail" or reference["status"] != "pass" or not result["replay"]["verified"]:
            print(json.dumps(result, indent=2))
            raise SystemExit(1)
    elif args.command in {"campaign", "run"}:
        _, manifest = load_agent(args.agent)
        scenarios = json.loads(args.scenario.read_text()) if args.scenario else default_scenarios(manifest)
        scenarios = scenarios if isinstance(scenarios, list) else [scenarios]
        result = [run(args.agent, s, mode=args.mode, runner=args.runner, provider=args.provider, model=args.model) for s in (scenarios if args.command == "campaign" else scenarios[:1])]
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if all(r["status"] == "pass" for r in result) else 1 if any(r["status"] == "fail" for r in result) else 2)
    elif args.command == "replay":
        result = replay(args.run_id)
    elif args.command == "reduce":
        result = reduce_failure(args.run_id)
    elif args.command == "show":
        result = get_run(args.run_id)
    elif args.command == "verify":
        result = verify(args.repair_id, args.runner)
    elif args.command in {"design", "repair"}:
        with urllib.request.urlopen("http://127.0.0.1:3000/api/lab/bootstrap", timeout=10) as response:
            config = json.load(response)
        model = args.model or next(p["model"] for p in config["providers"] if p["id"] == args.provider)
        target = get_run(args.target) if args.command == "repair" else None
        body = {"action": args.command, "agent_id": target["agent_id"] if target else args.target, "provider": args.provider, "model": model}
        if target:
            body["run_id"] = args.target
        request = urllib.request.Request("http://127.0.0.1:3000/api/investigate", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
    else:
        payload, _, _ = export(args.kind, args.id, args.format)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
        result = {"written": str(args.output.resolve())}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
