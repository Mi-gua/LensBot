from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


@contextlib.contextmanager
def workspace_temp_dir():
    root = PROJECT_ROOT / ".cache" / "test-workspaces"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"tmp-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class PiToolRegistrationTest(unittest.TestCase):
    def test_optimization_runner_exposes_filesystem_tools_to_pi(self) -> None:
        from subagents.optimization import OptimizationRunner

        self.assertIn("powershell", OptimizationRunner.tool_names)
        self.assertNotIn("bash", OptimizationRunner.tool_names)
        self.assertIn("read_file", OptimizationRunner.tool_names)
        self.assertIn("write_file", OptimizationRunner.tool_names)
        self.assertIn("edit_file", OptimizationRunner.tool_names)

    def test_optimization_runner_exposes_domain_tools_to_pi(self) -> None:
        from subagents.optimization import OptimizationRunner

        for name in (
            "deeplens_adjust_structure",
            "deeplens_curriculum",
            "deeplens_finetune",
            "deeplens_inspect_checkpoint",
            "deeplens_adjust_strategy",
            "deeplens_analysis",
        ):
            self.assertIn(name, OptimizationRunner.tool_names)

    def test_tool_servers_register_filesystem_tools(self) -> None:
        from tools.deeplens.fake import FakeDeepLensToolServer
        from tools.server import RealDeepLensToolServer

        for server in (
            FakeDeepLensToolServer(PROJECT_ROOT),
            RealDeepLensToolServer(PROJECT_ROOT),
        ):
            names = set(server.registry.names())
            self.assertIn("powershell", names)
            self.assertNotIn("bash", names)
            self.assertIn("read_file", names)
            self.assertIn("write_file", names)
            self.assertIn("edit_file", names)

    def test_read_file_rejects_directory_paths_with_clear_message(self) -> None:
        from agent.tools import ToolContext
        from tools.read_file import ReadFileTool

        result = ReadFileTool().run(ToolContext(project_root=PROJECT_ROOT), path="src")

        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "path_is_directory")
        self.assertIn("specific file path", result.observation)

    def test_curriculum_tool_schema_accepts_replay_seed(self) -> None:
        from tools.deeplens.curriculum import DeepLensCurriculumTool

        params_schema = DeepLensCurriculumTool.input_schema["properties"]["params"]
        properties = params_schema["properties"]

        self.assertIn("exp_name", properties)
        self.assertIn("seed", properties)
        self.assertEqual(properties["seed"]["anyOf"], [{"type": "integer"}, {"type": "null"}])

    def test_deeplens_optimization_tools_do_not_expose_steps(self) -> None:
        from tools.deeplens.curriculum import DeepLensCurriculumTool
        from tools.deeplens.finetune import DeepLensFinetuneTool

        self.assertNotIn("steps", DeepLensCurriculumTool.input_schema["properties"])
        self.assertNotIn("steps", DeepLensFinetuneTool.input_schema["properties"])

    def test_curriculum_tool_does_not_expose_fine_tune_stage_config(self) -> None:
        from tools.deeplens.curriculum import DeepLensCurriculumTool

        params_schema = DeepLensCurriculumTool.input_schema["properties"]["params"]
        self.assertNotIn("fine_tune", params_schema["properties"])

    def test_finetune_tool_schema_accepts_pre_start_stage_override(self) -> None:
        from tools.deeplens.finetune import DeepLensFinetuneTool

        properties = DeepLensFinetuneTool.input_schema["properties"]
        self.assertIn("fine_tune", properties)
        self.assertIn("iterations", properties["fine_tune"]["properties"])

    def test_finetune_override_updates_session_params_before_finetune_starts(self) -> None:
        from subagents.types import load_default_params
        from tools.deeplens.finetune import apply_fine_tune_override

        class Session:
            phase = "curriculum_complete"
            params = load_default_params(PROJECT_ROOT)

        error = apply_fine_tune_override(Session, {"iterations": 750})

        self.assertIsNone(error)
        self.assertEqual(Session.params.fine_tune.iterations, 750)
        self.assertEqual(Session.params.fine_tune.test_per_iter, 100)

    def test_finetune_override_rejects_changes_after_finetune_started(self) -> None:
        from subagents.types import load_default_params
        from tools.deeplens.finetune import apply_fine_tune_override

        class Session:
            phase = "fine_tune"
            params = load_default_params(PROJECT_ROOT)

        error = apply_fine_tune_override(Session, {"iterations": 750})

        self.assertIsNotNone(error)
        assert error is not None
        self.assertFalse(error.ok)
        self.assertEqual(error.error.code, "fine_tune_already_started")

    def test_curriculum_tool_does_not_expose_runtime_run_id(self) -> None:
        from tools.deeplens.curriculum import DeepLensCurriculumTool

        self.assertNotIn("run_id", DeepLensCurriculumTool.input_schema["properties"])

    def test_strategy_tool_does_not_expose_continue_noop(self) -> None:
        from tools.deeplens.strategy import DeepLensAdjustStrategyTool

        action_schema = DeepLensAdjustStrategyTool.input_schema["properties"]["action"]
        self.assertNotIn("continue", action_schema["enum"])

    def test_convert_aspheric_to_spheric_is_noop_for_all_spheric_structure(self) -> None:
        from engine.deeplens.structure_seed import apply_structure_seed_adjustment

        params = {
            "foclen": 50,
            "fov": 35,
            "fnum": 2.8,
            "bfl": 18,
            "thickness": 120,
            "surf_list": [["Spheric", "Spheric"], ["Aperture"], ["Spheric", "Spheric"]],
        }

        result = apply_structure_seed_adjustment(
            {"params": params, "action": "convert_aspheric_to_spheric"}
        )

        self.assertFalse(result["changed"])
        self.assertEqual(result["surf_list"], params["surf_list"])
        self.assertEqual(result["structure_summary"]["structure_aspheric_count"], 0)

    def test_tool_request_carries_runtime_context_separately_from_arguments(self) -> None:
        from tools.server import parse_request

        request = parse_request(
            json.dumps(
                {
                    "type": "tool_request",
                    "request_id": "request-1",
                    "tool": "deeplens_curriculum",
                    "arguments": {"params": {"foclen": 50}},
                    "state": {},
                    "context": {"run_id": "run-1"},
                }
            )
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.context["run_id"], "run-1")
        self.assertNotIn("run_id", request.arguments)

    def test_real_tool_pi_contract_keeps_phase_running(self) -> None:
        from agent.tools import ToolResult
        from tools.server import _with_pi_contract

        with workspace_temp_dir() as tmp:
            result_dir = Path(tmp)
            curriculum_json = result_dir / "engines" / "deeplens" / "attempts" / "attempt-001-curriculum" / "curriculum.json"
            final_json = result_dir / "final" / "final.json"
            final_zmx = result_dir / "final" / "final.zmx"
            curriculum_json.parent.mkdir(parents=True, exist_ok=True)
            final_json.parent.mkdir(parents=True, exist_ok=True)
            curriculum_json.write_text("{}", encoding="utf-8")
            final_json.write_text("{}", encoding="utf-8")
            final_zmx.write_text("fake zmx", encoding="utf-8")

            curriculum = _with_pi_contract(
                "deeplens_curriculum",
                ToolResult.success(
                    "curriculum",
                    {
                        "session_id": "session-1",
                        "result_dir": str(result_dir),
                        "curriculum_json": str(curriculum_json),
                    },
                ),
            )
            analysis = _with_pi_contract(
                "deeplens_analysis",
                ToolResult.success(
                    "analysis",
                    {
                        "result_dir": str(result_dir),
                        "analysis_json": str(final_json),
                        "analysis_stage": "final",
                        "has_curriculum_json": True,
                        "has_final_json": True,
                    },
                ),
            )

        self.assertEqual(curriculum.state_patch.get("phase"), "running")
        self.assertEqual(analysis.state_patch.get("phase"), "running")

    def test_real_tool_pi_contract_defaults_curriculum_json_to_layered_path(self) -> None:
        from agent.tools import ToolResult
        from tools.server import _with_pi_contract

        with workspace_temp_dir() as tmp:
            result_dir = Path(tmp)
            curriculum_json = result_dir / "engines" / "deeplens" / "attempts" / "attempt-001-curriculum" / "curriculum.json"
            curriculum_json.parent.mkdir(parents=True, exist_ok=True)
            curriculum_json.write_text("{}", encoding="utf-8")

            result = _with_pi_contract(
                "deeplens_curriculum",
                ToolResult.success(
                    "curriculum",
                    {
                        "session_id": "session-1",
                        "result_dir": str(result_dir),
                    },
                ),
            )

        self.assertEqual(result.state_patch["artifacts"]["curriculum_json"], str(curriculum_json))
        self.assertTrue(result.metrics["has_curriculum_json"])

    def test_fake_deeplens_state_patches_do_not_encode_pipeline_phases(self) -> None:
        from tools.deeplens.fake import FakeDeepLensToolServer

        with workspace_temp_dir() as tmp:
            server = FakeDeepLensToolServer(tmp)
            curriculum = server.dispatch(
                "deeplens_curriculum",
                {"params": {"foclen": 50, "fov": 35, "fnum": 2.8, "bfl": 18}},
                {"phase": "running"},
                {"run_id": "fake-run"},
            )
            state = {
                "phase": "running",
                **(curriculum.state_patch or {}),
                "artifacts": (curriculum.state_patch or {}).get("artifacts", {}),
            }
            finetune = server.deeplens_finetune({}, state)
            state["artifacts"] = {**state["artifacts"], **((finetune.state_patch or {}).get("artifacts", {}))}
            analysis = server.deeplens_analysis({}, state)

        self.assertEqual(curriculum.state_patch.get("phase"), "running")
        self.assertEqual(finetune.state_patch.get("phase"), "running")
        self.assertEqual(analysis.state_patch.get("phase"), "running")

    def test_finish_contract_requires_analysis_artifact(self) -> None:
        from tools.deeplens.contract import finish_result

        result = finish_result(
            {
                "artifacts": {
                    "final_json": "results/run-1/final/final.json",
                    "final_zmx": "results/run-1/final/final.zmx",
                },
                "metrics": {
                    "analysis_stage": "final",
                    "has_final_json": True,
                },
            }
        )

        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "missing_final_artifacts")
        self.assertIn("analysis_json", result.error.details.get("missing", []))

    def test_reporting_summary_preserves_full_final_summary(self) -> None:
        from subagents.reporting import _build_summary

        final_summary = (
            "Smoke test validated the complete pipeline end-to-end. "
            "All final artifacts exported successfully; reduced iteration count means optical quality is not representative of full optimization. "
            "The result should be reviewed with the complete metrics before being treated as an acceptable lens."
        )

        self.assertGreater(len(final_summary), 180)
        self.assertEqual(_build_summary({"final_summary": final_summary}, accepted=True, issues=[]), final_summary)

    def test_final_deeplens_metrics_replace_stale_first_order_aliases(self) -> None:
        from subagents.optimization import _sync_final_state

        class Runtime:
            def bind_result_dir(self, ctx, result_dir: str) -> None:
                ctx.runtime_result_dir = result_dir

            def publish_artifact(self, path: str, *, ctx) -> None:
                pass

        class Ctx:
            metrics: dict[str, object] = {}
            design_result: dict[str, object] = {}
            runtime_result_dir = None

            def fail(self, message: str) -> None:
                raise AssertionError(message)

        state = {
            "phase": "finished",
            "active_result_dir": "results/run-1",
            "artifacts": {
                "final_json": "results/run-1/final/final.json",
                "final_zmx": "results/run-1/final/final.zmx",
                "analysis_json": "results/run-1/final/final.json",
            },
            "metrics": {
                "analysis_stage": "final",
                "has_final_json": True,
                "efl_mm": 52.0,
                "fnum": 2.9,
                "fov_deg": 43.0,
                "deeplens_efl_mm": 53.49,
                "deeplens_fnum": 2.35,
                "deeplens_fov_deg": 41.93,
            },
        }
        ctx = Ctx()

        _sync_final_state(ctx, Runtime(), state)

        self.assertEqual(ctx.metrics["efl_mm"], 53.49)
        self.assertEqual(ctx.metrics["fnum"], 2.35)
        self.assertEqual(ctx.metrics["fov_deg"], 41.93)
        self.assertEqual(ctx.metrics["pre_final_efl_mm"], 52.0)
        self.assertEqual(ctx.metrics["pre_final_fnum"], 2.9)
        self.assertEqual(ctx.metrics["pre_final_fov_deg"], 43.0)

    def test_preview_payload_uses_final_deeplens_fnum_before_stale_alias(self) -> None:
        from runtime.artifacts import build_preview_payload

        with workspace_temp_dir() as tmp:
            result_dir = Path(tmp)
            final_json = result_dir / "final" / "final.json"
            final_json.parent.mkdir(parents=True, exist_ok=True)
            final_json.write_text(
                json.dumps({"foclen": 53.49, "fnum": 2.35, "r_sensor": 20.48}),
                encoding="utf-8",
            )
            (result_dir / "final" / "final.png").write_bytes(b"fake")
            metrics = {
                "analysis_stage": "final",
                "fnum": 2.9,
                "deeplens_fnum": 2.35,
                "deeplens_fov_deg": 41.93,
            }

            payload = build_preview_payload(
                result_dir,
                metrics,
                url_builder=lambda path: str(path) if path else None,
                path_builder=lambda path: path,
            )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["fnum_display"], "2.35")

    def test_manifest_discovers_layered_zemax_verification_outputs(self) -> None:
        from runtime.artifacts import refresh_run_manifest

        with workspace_temp_dir() as tmp:
            result_dir = Path(tmp)
            zemax_dir = result_dir / "verification" / "zemax"
            zemax_dir.mkdir(parents=True, exist_ok=True)
            (zemax_dir / "zemax_report.json").write_text("{}", encoding="utf-8")
            (zemax_dir / "fft_mtf.png").write_bytes(b"fake")

            manifest = refresh_run_manifest(result_dir)

        self.assertIsNotNone(manifest)
        assert manifest is not None
        artifacts = {item["role"]: item for item in manifest["artifacts"]}
        self.assertEqual(artifacts["zemax_report"]["path"], str((zemax_dir / "zemax_report.json").resolve()))
        self.assertEqual(artifacts["zemax_mtf"]["path"], str((zemax_dir / "fft_mtf.png").resolve()))

    def test_manifest_ignores_legacy_flat_result_artifacts(self) -> None:
        from runtime.artifacts import refresh_run_manifest

        with workspace_temp_dir() as tmp:
            result_dir = Path(tmp)
            (result_dir / "display").mkdir()
            (result_dir / "zemax-analysis").mkdir()
            for path in (
                result_dir / "starting-point.json",
                result_dir / "curriculum.json",
                result_dir / "final.json",
                result_dir / "final.zmx",
                result_dir / "session.json",
                result_dir / "display" / "current.json",
                result_dir / "zemax-analysis" / "zemax_report.json",
            ):
                path.write_text("{}", encoding="utf-8")

            manifest = refresh_run_manifest(result_dir)

        self.assertIsNotNone(manifest)
        assert manifest is not None
        roles = {item["role"] for item in manifest["artifacts"]}
        self.assertNotIn("deeplens_starting_json", roles)
        self.assertNotIn("deeplens_curriculum_json", roles)
        self.assertNotIn("deeplens_final_json", roles)
        self.assertNotIn("zemax_lens_file", roles)
        self.assertNotIn("session_state", roles)
        self.assertNotIn("deeplens_current_json", roles)
        self.assertNotIn("zemax_report", roles)
        self.assertEqual("", manifest["phase"])

    def test_real_strategy_tool_redirects_engine_stdout_to_deeplens_log(self) -> None:
        from agent.tools import ToolContext
        from tools.deeplens.curriculum import SESSIONS
        from tools.deeplens.strategy import DeepLensAdjustStrategyTool

        class NoisyStrategySession:
            def __init__(self, result_dir: Path) -> None:
                self.result_dir = result_dir

            def adjust_strategy(self, strategy: dict[str, object]) -> dict[str, object]:
                print("Using CPU for DeepLens")
                return {
                    "session_id": "noisy-session",
                    "result_dir": str(self.result_dir),
                    "phase": "curriculum",
                    "strategy": {
                        "lr_scale": 1.0,
                        "focus_weight_scale": 1.0,
                        "rollback_count": 0,
                    },
                    "last_strategy": strategy,
                }

        with workspace_temp_dir() as tmp:
            result_dir = Path(tmp)
            session_id = "noisy-session"
            SESSIONS[session_id] = NoisyStrategySession(result_dir)  # type: ignore[assignment]
            try:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    result = DeepLensAdjustStrategyTool().run(
                        ToolContext(project_root=PROJECT_ROOT),
                        session_id=session_id,
                        action="rollback_to_best_checkpoint",
                    )

                self.assertTrue(result.ok)
                self.assertEqual("", stdout.getvalue())
                self.assertIn(
                    "Using CPU for DeepLens",
                    (
                        result_dir
                        / "engines"
                        / "deeplens"
                        / "deeplens.log"
                    ).read_text(encoding="utf-8"),
                )
            finally:
                SESSIONS.pop(session_id, None)


if __name__ == "__main__":
    unittest.main()
