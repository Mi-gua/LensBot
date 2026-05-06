from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from agent.tools import ToolContext, ToolResult


class ReadFileTool:
    name = "read_file"
    description = "Read a UTF-8 text file under the project root."
    category = "system"
    metadata = {"kind": "filesystem"}

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        path = _resolve_under_root(ctx.project_root, kwargs.get("path"))
        if path is None:
            return ToolResult(False, "Path is outside the project root or missing.")
        if not path.is_file():
            return ToolResult(False, f"File not found: {path}")
        max_chars = int(kwargs.get("max_chars", 20000))
        text = path.read_text(encoding=kwargs.get("encoding", "utf-8"), errors="replace")
        return ToolResult(True, f"Read {path.relative_to(ctx.project_root)}.", text[:max_chars])


class ListDirTool:
    name = "list_dir"
    description = "List a directory under the project root."
    category = "system"
    metadata = {"kind": "filesystem"}

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        path = _resolve_under_root(ctx.project_root, kwargs.get("path", "."))
        if path is None:
            return ToolResult(False, "Path is outside the project root or missing.")
        if not path.is_dir():
            return ToolResult(False, f"Directory not found: {path}")
        rows = [
            {"name": item.name, "type": "dir" if item.is_dir() else "file"}
            for item in sorted(path.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower()))
        ]
        return ToolResult(True, f"Listed {path.relative_to(ctx.project_root)}.", rows)


class ShellCommandTool:
    name = "shell_command"
    description = "Run a bounded shell command in the project root."
    category = "system"
    metadata = {"kind": "process", "shell": "powershell"}

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        command = str(kwargs.get("command", "")).strip()
        if not command:
            return ToolResult(False, "Command is empty.")
        timeout = int(kwargs.get("timeout", 60))
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=ctx.project_root,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return ToolResult(
            completed.returncode == 0,
            f"Command exited with {completed.returncode}.",
            {
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )


def _resolve_under_root(project_root: Path, raw_path: Any) -> Path | None:
    if raw_path is None:
        return None
    root = project_root.resolve()
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved
