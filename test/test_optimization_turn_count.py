from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.runtime.result import ResultWorkspace, layered_workspace_index
from src.runtime.traces import append_agent_event, append_timeline_event, load_trace_payload


class OptimizationTurnCountTest(unittest.TestCase):
    def test_result_workspace_exposes_layered_paths(self) -> None:
        scratch_root = PROJECT_ROOT / ".test-workspace" / "result-workspace-layout"
        shutil.rmtree(scratch_root, ignore_errors=True)
        try:
            workspace = ResultWorkspace.from_result_dir(scratch_root / "run")

            self.assertEqual(workspace.final_dir, workspace.root / "final")
            self.assertEqual(workspace.events_dir, workspace.root / "events")
            self.assertEqual(workspace.agents_dir, workspace.root / "agents")
            self.assertEqual(workspace.optimization_agent_dir, workspace.root / "agents" / "optimization")
            self.assertEqual(workspace.deeplens_dir, workspace.root / "engines" / "deeplens")
            self.assertEqual(workspace.deeplens_live_dir, workspace.root / "engines" / "deeplens" / "live")
            self.assertEqual(
                workspace.deeplens_attempt_dir("curriculum"),
                workspace.root / "engines" / "deeplens" / "attempts" / "attempt-001-curriculum",
            )
            self.assertTrue((workspace.root / "final").is_dir())
            self.assertTrue((workspace.root / "events").is_dir())
            self.assertTrue((workspace.root / "agents" / "optimization" / "workspace").is_dir())
            self.assertTrue((workspace.root / "engines" / "deeplens" / "attempts").is_dir())
        finally:
            shutil.rmtree(scratch_root, ignore_errors=True)

    def test_agent_end_event_does_not_increase_optimization_turn_count(self) -> None:
        scratch_root = PROJECT_ROOT / ".test-workspace" / "optimization-turn-count"
        shutil.rmtree(scratch_root, ignore_errors=True)
        try:
            workspace = ResultWorkspace.from_result_dir(scratch_root / "run")
            for row in (
                {"agent": "Optimization", "kind": "assistant_message", "turn": 0, "text": "start"},
                {"agent": "Optimization", "kind": "tool_call", "turn": 0, "tool": "deeplens_curriculum"},
                {"agent": "Optimization", "kind": "tool_result", "turn": 0, "tool": "deeplens_curriculum"},
                {"agent": "Optimization", "kind": "assistant_message", "turn": 12, "text": "final reasoning"},
                {"agent": "Optimization", "kind": "tool_call", "turn": 12, "tool": "finish"},
                {"agent": "Optimization", "kind": "tool_result", "turn": 12, "tool": "finish"},
                {"agent": "Optimization", "turn": 13, "done": True, "action": "agent_end"},
                {"agent": "Optimization", "kind": "agent_end", "turn": 13, "done": True},
            ):
                workspace.record_optimization_agent_turn(row)

            turns_view = json.loads((workspace.optimization_agent_dir / "views" / "turns.json").read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(scratch_root, ignore_errors=True)

        self.assertEqual(turns_view["turn_count"], 13)

    def test_optimization_agent_turns_are_written_under_agents_optimization(self) -> None:
        scratch_root = PROJECT_ROOT / ".test-workspace" / "optimization-agent-layout"
        shutil.rmtree(scratch_root, ignore_errors=True)
        try:
            workspace = ResultWorkspace.from_result_dir(scratch_root / "run")

            workspace.record_optimization_agent_turn(
                {"agent": "Optimization", "kind": "tool_call", "turn": 0, "tool": "deeplens_curriculum"}
            )

            self.assertTrue((workspace.optimization_agent_dir / "views" / "turns.json").exists())
            self.assertTrue((workspace.optimization_agent_dir / "ledger" / "events.jsonl").exists())
            self.assertEqual(
                [],
                list((workspace.root / "opti-agent" / "workspace").glob("turn-*.json")),
            )
        finally:
            shutil.rmtree(scratch_root, ignore_errors=True)

    def test_trace_events_are_split_by_track_under_events(self) -> None:
        scratch_root = PROJECT_ROOT / ".test-workspace" / "events-layout"
        shutil.rmtree(scratch_root, ignore_errors=True)
        try:
            result_dir = scratch_root / "run"
            append_timeline_event(result_dir, {"key": "workflow.start", "message": "start"}, index=0)
            append_agent_event(
                result_dir,
                {
                    "agent": "Optimization",
                    "turn": 0,
                    "tool_call": {"name": "deeplens_curriculum", "arguments": {}},
                    "tool_result": {"ok": True, "observation": "ok"},
                },
            )

            self.assertTrue((result_dir / "events" / "workflow.jsonl").exists())
            self.assertTrue((result_dir / "events" / "agent.jsonl").exists())
            self.assertFalse((result_dir / "traces.jsonl").exists())
            traces = load_trace_payload(result_dir)
        finally:
            shutil.rmtree(scratch_root, ignore_errors=True)

        self.assertEqual(len(traces["timeline"]), 1)
        self.assertEqual(len(traces["agent"]), 1)

    def test_layered_workspace_index_ignores_legacy_opti_agent_directory(self) -> None:
        scratch_root = PROJECT_ROOT / ".test-workspace" / "legacy-opti-agent-layout"
        shutil.rmtree(scratch_root, ignore_errors=True)
        try:
            result_dir = scratch_root / "run"
            legacy_workspace = result_dir / "opti-agent" / "workspace"
            legacy_workspace.mkdir(parents=True)
            (legacy_workspace / "turn-0000-tool-call.json").write_text("{}", encoding="utf-8")

            index = layered_workspace_index(result_dir)
        finally:
            shutil.rmtree(scratch_root, ignore_errors=True)

        self.assertEqual([], index["optimization_agent"]["turn_records"])

    def test_load_trace_payload_ignores_legacy_traces_jsonl(self) -> None:
        scratch_root = PROJECT_ROOT / ".test-workspace" / "legacy-traces-layout"
        shutil.rmtree(scratch_root, ignore_errors=True)
        try:
            result_dir = scratch_root / "run"
            result_dir.mkdir(parents=True)
            (result_dir / "traces.jsonl").write_text(
                '{"track":"timeline","index":0,"timeline":{"key":"legacy"}}\n',
                encoding="utf-8",
            )

            traces = load_trace_payload(result_dir)
        finally:
            shutil.rmtree(scratch_root, ignore_errors=True)

        self.assertEqual([], traces["timeline"])
        self.assertEqual([], traces["agent"])


if __name__ == "__main__":
    unittest.main()
