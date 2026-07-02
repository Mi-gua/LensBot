from __future__ import annotations

from typing import Any

from agent.tools import ToolContext, ToolResult
from tools.paths import resolve_under_root


class ReadFileTool:
    name = "read_file"
    description = "Read a text file under the project root."
    category = "filesystem"
    scope = "workflow"
    input_schema = {
        "type": "object",
        "required": ["path"],
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer", "default": 20000},
            "encoding": {"type": "string", "default": "utf-8"},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["path", "content"],
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "truncated": {"type": "boolean"},
        },
    }
    metadata = {"kind": "filesystem_read"}

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        path = resolve_under_root(ctx.project_root, kwargs.get("path"))
        if path is None:
            return ToolResult.failure("Path is outside the project root.", code="invalid_path")
        if path.is_dir():
            return ToolResult.failure(
                f"Path is a directory, not a file: {path}. Provide a specific file path.",
                code="path_is_directory",
                error={
                    "code": "path_is_directory",
                    "message": "Path is a directory. Provide a specific file path.",
                    "path": str(path),
                },
            )
        if not path.is_file():
            return ToolResult.failure(f"File not found: {path}", code="file_not_found")

        max_chars = int(kwargs.get("max_chars", 20000))
        content = path.read_text(encoding=str(kwargs.get("encoding") or "utf-8"), errors="replace")
        truncated = len(content) > max_chars
        data = {
            "path": str(path),
            "relative_path": str(path.relative_to(ctx.project_root)),
            "content": content[:max_chars],
            "truncated": truncated,
            "chars": len(content),
        }
        return ToolResult.success(f"Read {data['relative_path']}.", data)


__all__ = ["ReadFileTool"]
