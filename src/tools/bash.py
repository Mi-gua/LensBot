from __future__ import annotations

import subprocess
from typing import Any

from agent.tools import ToolContext, ToolResult


class PowerShellTool:
    name = "powershell"
    description = "Run a bounded PowerShell command in the project root."
    category = "process"
    scope = "workflow"
    input_schema = {
        "type": "object",
        "required": ["command"],
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "default": 60},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["returncode", "stdout", "stderr"],
        "properties": {
            "returncode": {"type": "integer"},
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
        },
    }
    metadata = {"kind": "process", "shell": "powershell"}

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        command = str(kwargs.get("command") or "").strip()
        if not command:
            return ToolResult.failure("Command is empty.", code="empty_command")

        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=ctx.project_root,
            text=True,
            capture_output=True,
            timeout=int(kwargs.get("timeout") or 60),
            check=False,
        )
        data = {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        if completed.returncode == 0:
            return ToolResult.success(f"Command exited with {completed.returncode}.", data)
        return ToolResult.failure(
            f"Command exited with {completed.returncode}.",
            code="nonzero_exit",
            data=data,
            error={"code": "nonzero_exit", "returncode": completed.returncode},
        )


__all__ = ["PowerShellTool"]
