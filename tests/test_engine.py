import copy
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agentcrashlab import providers, runners, store
from agentcrashlab.contracts import ContractError, default_scenarios, inspect_agent, load_agent, validate_scenario
from agentcrashlab.engine import get_run, reduce_failure, replay, run
from agentcrashlab.repairs import create_repair, regression_test, verify
from agentcrashlab.service import export
from agentcrashlab.world import ToolError, World


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = store.DATA
        store.DATA = Path(self.temp.name)
        _, self.manifest = load_agent("workspace")
        self.lost = default_scenarios(self.manifest)[1]

    def tearDown(self):
        store.DATA = self.previous
        self.temp.cleanup()

    def test_duplicate_is_a_real_committed_effect_and_replays(self):
        result = run("workspace", self.lost)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(len(result["state"]["workspaces"]), 2)
        observations = [e for e in result["events"] if e["kind"] == "observation" and e["tool"] == "create_workspace"]
        self.assertEqual(observations[0]["error"]["code"], "timeout")
        self.assertTrue(replay(result["id"])["verified"])
        self.assertFalse(replay(result["id"])["model_called"])

    def test_reference_and_naive_controls_across_both_domains(self):
        for agent in ("workspace", "publisher"):
            _, manifest = load_agent(agent)
            for i, scenario in enumerate(default_scenarios(manifest)):
                with self.subTest(agent=agent, scenario=scenario["name"]):
                    original = run(agent, scenario)
                    reference = run(agent, scenario, reference=True)
                    self.assertEqual(reference["status"], "pass")
                    self.assertEqual(original["status"], "fail" if i in {1, 4} else "pass")
                    self.assertTrue(replay(original["id"])["verified"])

    def test_unactivated_fault_is_inconclusive(self):
        scenario = {"name": "Unreached fault", "faults": [{"kind": "rate_limit", "tool": "create_workspace", "occurrence": 15}]}
        result = run("workspace", scenario)
        self.assertEqual(result["status"], "inconclusive")
        self.assertTrue(all(a["passed"] for a in result["assertions"]))

    def test_replay_detects_tampering(self):
        result = run("workspace", self.lost)
        with store.connection() as db:
            db.execute("UPDATE events SET body=? WHERE run_id=? AND seq=0", (json.dumps({"seq": 0, "kind": "changed"}), result["id"]))
        with self.assertRaisesRegex(ContractError, "evidence changed"):
            replay(result["id"])

    def test_contract_validation(self):
        invalid = [
            {"faults": [{"kind": "stale_read", "tool": "create_workspace", "occurrence": 1}]},
            {"faults": [{"kind": "timeout_after_write", "tool": "list_members", "occurrence": 1}]},
            {"faults": [{"kind": "rate_limit", "tool": "not_a_tool", "occurrence": 1}]},
            {"faults": [{"kind": "rate_limit", "tool": "create_workspace", "occurrence": True}]},
            {"faults": [], "assertions": []},
            {"faults": [], "task_overrides": {"members": ["A", "A"]}},
        ]
        for scenario in invalid:
            with self.subTest(scenario=scenario), self.assertRaises(ContractError):
                validate_scenario(scenario, self.manifest)

    def test_local_provider_configuration_precedence(self):
        root = Path(self.temp.name)
        (root / ".env").write_text("META_MODEL=base-model\nBASETEN_MODEL=base-open-model\n")
        (root / ".env.local").write_text('META_MODEL="local-model"\n')
        with patch.dict(os.environ, {}, clear=True):
            providers.load_environment(root)
            self.assertEqual(os.environ["META_MODEL"], "local-model")
            self.assertEqual(os.environ["BASETEN_MODEL"], "base-open-model")
        with patch.dict(os.environ, {"META_MODEL": "shell-model"}):
            providers.load_environment(root)
            self.assertEqual(os.environ["META_MODEL"], "shell-model")

    def test_idempotency_key_conflict(self):
        world = World(self.manifest, self.manifest["task"], {"faults": []}, lambda *_: None)
        world.call("create_workspace", {"name": "A", "operation_key": "same"})
        self.assertEqual(world.call("create_workspace", {"name": "A", "operation_key": "same"})["id"], "ws_1")
        with self.assertRaises(ToolError):
            world.call("create_workspace", {"name": "B", "operation_key": "same"})
        self.assertEqual(len(world.state["workspaces"]), 1)

    def test_historical_violation_survives_later_correction(self):
        world = World(self.manifest, self.manifest["task"], {"faults": []}, lambda *_: None)
        world.call("create_workspace", {"name": "Orbital Design", "operation_key": "ws"})
        world.call("send_invite", {"workspace_id": "ws_1", "member": "Maya", "operation_key": "invite"})
        world.call("add_member", {"workspace_id": "ws_1", "member": "Maya", "operation_key": "member"})
        self.assertFalse(next(a for a in world.assertions() if a["id"] == "invite_after_membership")["passed"])

    def test_cancellation_and_timeout_close_runner(self):
        stop = threading.Event()
        stop.set()
        result = run("workspace", {"faults": []}, cancel=stop)
        self.assertEqual(result["status"], "inconclusive")
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["cleanup"], "completed")
        result = run("workspace", {"faults": []}, timeout=0.00001)
        self.assertEqual(result["status"], "inconclusive")

    def test_provider_failure_is_not_a_pass(self):
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}), patch("agentcrashlab.runners.start", side_effect=RuntimeError("Sandbox unavailable")):
            result = run("workspace", self.lost, mode="live", runner="modal")
        self.assertEqual(result["status"], "error")
        self.assertIn("Sandbox unavailable", result["error"])

    def test_no_credential_is_forwarded_to_child(self):
        from agentcrashlab.runners import LocalProcess
        with patch.dict(os.environ, {"MODEL_API_KEY": "must-not-leak"}), patch("subprocess.Popen") as popen:
            process = LocalProcess.__new__(LocalProcess)
            # Check the actual launch environment via a safe stub of Popen.
            proc = popen.return_value
            proc.stdout = iter([])
            process.__init__(load_agent("workspace")[0], "fixture.py", {}, "fixture", 3)
            self.assertNotIn("MODEL_API_KEY", popen.call_args.kwargs["env"])
            process.temp.cleanup()

    def test_repair_cannot_edit_evaluator_or_escape_allowlist(self):
        result = run("workspace", self.lost)
        for filename in ("../engine.py", "manifest.json", "reference.py", "/tmp/escape.py"):
            with self.subTest(filename=filename), self.assertRaises(ContractError):
                create_repair(result["id"], {filename: "async def run(ctx, task): return {}"}, "", "test")

    def test_repair_preserves_original_and_requires_isolation(self):
        result = run("workspace", self.lost)
        source = inspect_agent("workspace")["sources"]["agent.py"]
        candidate = source.replace('f"{key}:{attempt}"', "key")
        repair = create_repair(result["id"], {"agent.py": candidate}, "Stable keys", "test")
        self.assertIn("+", repair["patch"])
        self.assertEqual(inspect_agent("workspace")["sources"]["agent.py"], source)
        with self.assertRaisesRegex(ContractError, "isolated"):
            verify(repair["id"], "fixture")
        with self.assertRaisesRegex(ContractError, "generated patches require"):
            run("workspace", self.lost, directory=load_agent("workspace")[0])
        self.assertIn("RecoveryRegression", regression_test(repair))
        payload, mime, filename = export("repair", repair["id"], "zip")
        self.assertEqual(mime, "application/zip")
        self.assertTrue(payload.startswith(b"PK"))

    def test_three_repair_attempt_limit(self):
        result = run("workspace", self.lost)
        source = inspect_agent("workspace")["sources"]["agent.py"]
        for i in range(3):
            create_repair(result["id"], {"agent.py": source + f"\n# candidate {i}\n"}, "", "test")
        with self.assertRaisesRegex(ContractError, "three"):
            create_repair(result["id"], {"agent.py": source + "\n# fourth\n"}, "", "test")

    def test_reduction_removes_unnecessary_fault(self):
        scenario = {"name": "Two faults", "faults": [self.lost["faults"][0], {"kind": "rate_limit", "tool": "add_member", "occurrence": 1}]}
        original = run("workspace", scenario)
        reduced = reduce_failure(original["id"])
        self.assertEqual(reduced["scenario"]["faults"], self.lost["faults"])


if __name__ == "__main__":
    unittest.main()
