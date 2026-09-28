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
        "additionalProperties": False,
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "default": 60},
            "max_chars": {"type": "integer", "minimum": 1, "maximum": 20000, "default": 12000},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["returncode", "stdout", "stderr", "stdout_chars", "stderr_chars", "stdout_truncated", "stderr_truncated", "timed_out", "output_complete"],
        "additionalProperties": False,
        "properties": {
            "returncode": {"type": ["integer", "null"]},
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
            "stdout_chars": {"type": "integer"},
            "stderr_chars": {"type": "integer"},
            "stdout_truncated": {"type": "boolean"},
            "stderr_truncated": {"type": "boolean"},
            "timed_out": {"type": "boolean"},
            "output_complete": {"type": "boolean"},
        },
    }
    metadata = {"kind": "process", "shell": "powershell"}

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        command = str(kwargs.get("command") or "").strip()
        if not command:
            return ToolResult.failure("Command is empty.", code="empty_command")

        try:
            timeout = max(1, min(300, int(kwargs.get("timeout") or 60)))
            max_chars = max(1, min(20000, int(kwargs.get("max_chars") or 12000)))
        except (TypeError, ValueError):
            return ToolResult.failure("timeout and max_chars must be integers.", code="invalid_process_options")
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                cwd=ctx.project_root,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            data = _process_data(None, exc.stdout, exc.stderr, max_chars, timed_out=True)
            return ToolResult.failure(
                f"Command timed out after {timeout} seconds. Partial stdout={data['stdout_chars']} chars, stderr={data['stderr_chars']} chars.",
                code="command_timeout",
                data=data,
                error={"code": "command_timeout", "timeout": timeout},
            )
        data = _process_data(completed.returncode, completed.stdout, completed.stderr, max_chars, timed_out=False)
        if completed.returncode == 0:
            return ToolResult.success(
                f"Command exited with 0; stdout={len(completed.stdout)} chars, stderr={len(completed.stderr)} chars.", data
            )
        return ToolResult.failure(
            f"Command exited with {completed.returncode}.",
            code="nonzero_exit",
            data=data,
            error={"code": "nonzero_exit", "returncode": completed.returncode},
        )


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value or "")


def _truncate(value: str, max_chars: int) -> tuple[str, bool]:
    return value[:max_chars], len(value) > max_chars


def _process_data(returncode: int | None, stdout: Any, stderr: Any, max_chars: int, *, timed_out: bool) -> dict[str, Any]:
    stdout_text = _text(stdout)
    stderr_text = _text(stderr)
    bounded_stdout, stdout_truncated = _truncate(stdout_text, max_chars)
    bounded_stderr, stderr_truncated = _truncate(stderr_text, max_chars)
    return {
        "returncode": returncode,
        "stdout": bounded_stdout,
        "stderr": bounded_stderr,
        "stdout_chars": len(stdout_text),
        "stderr_chars": len(stderr_text),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "timed_out": timed_out,
        "output_complete": not timed_out and not stdout_truncated and not stderr_truncated,
    }


__all__ = ["PowerShellTool"]
