from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tools import ToolContext, ToolRegistry, ToolResult
from tools.bash import PowerShellTool
from tools.deeplens import DEEPLENS_TOOLS
from tools.deeplens.contract import finish_result
from tools.deeplens.fake import FakeDeepLensToolServer
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
            return finish_result(state)
        result = self.registry.call(
            tool,
            ctx=ToolContext(project_root=self.project_root, agent_context=context or {}),
            **arguments,
        )
        return _with_pi_contract(tool, result)


def main() -> int:
    parser = argparse.ArgumentParser(description="LensBot canonical JSONL tool server.")
    parser.add_argument("--fake", action="store_true", help="Use deterministic fake DeepLens tools.")
    parser.add_argument("--real", action="store_true", help="Use real DeepLens tools from src/tools.")
    parser.add_argument("--project-root", default=str(Path.cwd()))
    args = parser.parse_args()

    if args.fake == args.real:
        raise SystemExit("Choose exactly one tool mode: --fake or --real.")

    server = FakeDeepLensToolServer(args.project_root) if args.fake else RealDeepLensToolServer(args.project_root)
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
        {
            "type": "tool_response",
            "request_id": request_id,
            "result": result.for_trace(),
        },
        ensure_ascii=False,
        default=str,
    )


def _with_pi_contract(tool: str, result: ToolResult) -> ToolResult:
    data = result.data if isinstance(result.data, dict) else {}
    if result.state_patch or tool not in {"deeplens_curriculum", "deeplens_finetune", "deeplens_analysis"}:
        return result

    if tool == "deeplens_curriculum":
        curriculum_json = data.get("curriculum_json")
        if not curriculum_json and data.get("result_dir"):
            curriculum_json = str(
                Path(str(data["result_dir"]))
                / "engines"
                / "deeplens"
                / "attempts"
                / "attempt-001-curriculum"
                / "curriculum.json"
            )
        result.state_patch = {
            "phase": "running",
            "active_session_id": data.get("session_id"),
            "active_result_dir": data.get("result_dir"),
            "artifacts": {"curriculum_json": curriculum_json},
        }
        result.metrics = {
            "has_curriculum_json": bool(curriculum_json and Path(str(curriculum_json)).exists()),
            "curriculum_iter": data.get("curriculum_iter"),
            "curriculum_total": data.get("curriculum_total"),
        }
        return result

    if tool == "deeplens_finetune":
        result.state_patch = {
            "phase": "running",
            "artifacts": {
                "final_json": data.get("final_json"),
                "final_zmx": data.get("final_zmx"),
            },
        }
        result.metrics = {
            "fine_tune_iter": data.get("fine_tune_iter"),
            "fine_tune_total": data.get("fine_tune_total"),
        }
        return result

    result.state_patch = {
        "phase": "running",
        "artifacts": {"analysis_json": data.get("analysis_json")},
    }
    result.metrics = data
    return result


if __name__ == "__main__":
    raise SystemExit(main())
