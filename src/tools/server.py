from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tools import ToolContext, ToolRegistry, ToolResult
from tools.bash import PowerShellTool
from tools.deeplens import DEEPLENS_TOOLS
from tools.deeplens.artifacts import find_lens_artifacts
from tools.deeplens.contract import finish_result
from tools.edit_file import EditFileTool
from tools.read_file import ReadFileTool
from tools.write_file import WriteFileTool


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ToolRequest:
    request_id: str
    tool: str
    arguments: JsonObject
    state: JsonObject
    context: JsonObject


class RealDeepLensToolServer:
    """JSONL dispatch adapter backed by the canonical src/tools registry."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)
        self.registry = ToolRegistry()
        self.registry.register_tool(ReadFileTool())
        self.registry.register_tool(WriteFileTool())
        self.registry.register_tool(EditFileTool())
        self.registry.register_tool(PowerShellTool())
        for tool in DEEPLENS_TOOLS:
            self.registry.register_tool(tool)

    def dispatch(self, tool: str, arguments: JsonObject, state: JsonObject, context: JsonObject | None = None) -> ToolResult:
        if tool == "finish":
            return finish_result(state, arguments.get("verdict"))
        result = self.registry.call(
            tool,
            ctx=ToolContext(project_root=self.project_root, agent_context=context or {}),
            **arguments,
        )
        return _with_pi_contract(tool, result)


def main() -> int:
    parser = argparse.ArgumentParser(description="LensBot canonical JSONL tool server.")
    parser.add_argument("--project-root", default=str(Path.cwd()))
    args = parser.parse_args()

    server = RealDeepLensToolServer(args.project_root)
    for line in sys.stdin:
        if not line.strip():
            continue
        request_id = "unknown"
        try:
            request = parse_request(line)
            if request is None:
                continue
            request_id = request.request_id
            result = server.dispatch(request.tool, request.arguments, request.state, request.context)
        except Exception as exc:
            result = ToolResult.failure(
                f"Tool server error: {type(exc).__name__}: {exc}",
                code="server_error",
                error={"code": "server_error", "message": str(exc), "exception_type": type(exc).__name__},
            )
        print(response_line(request_id, result), flush=True)
    return 0


def parse_request(line: str) -> ToolRequest | None:
    message = json.loads(line)
    if message.get("type") != "tool_request":
        return None
    return ToolRequest(
        request_id=str(message["request_id"]),
        tool=str(message["tool"]),
        arguments=message.get("arguments") if isinstance(message.get("arguments"), dict) else {},
        state=message.get("state") if isinstance(message.get("state"), dict) else {},
        context=message.get("context") if isinstance(message.get("context"), dict) else {},
    )


def response_line(request_id: str, result: ToolResult) -> str:
    return json.dumps(
        _json_safe({
            "type": "tool_response",
            "request_id": request_id,
            "result": result.for_trace(),
        }),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def _json_safe(value: Any) -> Any:
    """Convert non-finite floats to JSON null at the JSONL process boundary."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _with_pi_contract(tool: str, result: ToolResult) -> ToolResult:
    data = result.data if isinstance(result.data, dict) else {}
    if result.state_patch or tool not in {"deeplens_curriculum", "deeplens_finetune", "deeplens_analysis"}:
        return result

    if tool == "deeplens_curriculum":
        curriculum_json = data.get("curriculum_json")
        if not curriculum_json and data.get("result_dir"):
            try:
                curriculum_json = find_lens_artifacts(Path("."), result_dir=data["result_dir"]).curriculum_json
            except ValueError:
                curriculum_json = None
        result.state_patch = {
            "phase": "running",
            "active_seed_id": data.get("seed_candidate_id"),
            "params_override": data.get("params"),
            "active_session_id": data.get("session_id"),
            "active_result_dir": data.get("result_dir"),
            "artifacts": {"curriculum_json": curriculum_json},
        }
        result.metrics = {
            "has_curriculum_json": bool(curriculum_json and Path(str(curriculum_json)).exists()),
            "curriculum_iter": data.get("curriculum_iter"),
            "curriculum_total": data.get("curriculum_total"),
            "iterations_requested": data.get("iterations_requested"),
            "iterations_executed": data.get("iterations_executed"),
            "source_lens": data.get("source_lens"),
            "optimizer_reinitialized": data.get("optimizer_reinitialized"),
        }
        return result

    if tool == "deeplens_finetune":
        result.state_patch = {
            "phase": "running",
            "active_session_id": data.get("session_id"),
            "active_result_dir": data.get("result_dir"),
            "artifacts": {
                "candidate_json": data.get("candidate_json"),
                "candidate_zmx": data.get("candidate_zmx"),
                "candidate_png": data.get("candidate_png"),
            },
        }
        result.metrics = {
            "fine_tune_iter": data.get("fine_tune_iter"),
            "fine_tune_total": data.get("fine_tune_total"),
            "iterations_requested": data.get("iterations_requested"),
            "iterations_executed": data.get("iterations_executed"),
            "source_lens": data.get("source_lens"),
            "candidate_id": data.get("candidate_id"),
            "optimizer_reinitialized": data.get("optimizer_reinitialized"),
            "strategy_lr_scale": data.get("lr_scale"),
        }
        return result

    artifact_patch = {"analysis_json": data.get("analysis_json")}
    if data.get("has_candidate_json") is True:
        artifact_patch["candidate_json"] = data.get("candidate_json")
        if data.get("candidate_zmx"):
            artifact_patch["candidate_zmx"] = data.get("candidate_zmx")
        if data.get("candidate_png"):
            artifact_patch["candidate_png"] = data.get("candidate_png")
    if data.get("has_final_json") is True:
        artifact_patch["final_json"] = data.get("final_json")
        if data.get("final_zmx"):
            artifact_patch["final_zmx"] = data.get("final_zmx")
    if data.get("curriculum_json"):
        artifact_patch["curriculum_json"] = data.get("curriculum_json")
    result.state_patch = {
        "phase": "running",
        "artifacts": artifact_patch,
    }
    result.metrics = data
    return result


if __name__ == "__main__":
    raise SystemExit(main())
