from __future__ import annotations

from typing import Any

from agent.tools import ToolContext, ToolResult
from tools.paths import resolve_under_root


class WriteFileTool:
    name = "write_file"
    description = "Write a text file under the project root."
    category = "filesystem"
    scope = "workflow"
    input_schema = {
        "type": "object",
        "required": ["path", "content"],
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "encoding": {"type": "string", "default": "utf-8"},
            "overwrite": {"type": "boolean", "default": True},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["path", "bytes"],
        "properties": {"path": {"type": "string"}, "bytes": {"type": "integer"}},
    }
    metadata = {"kind": "filesystem_write"}

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        path = resolve_under_root(ctx.project_root, kwargs.get("path"))
        if path is None:
            return ToolResult.failure("Path is outside the project root.", code="invalid_path")
        if path.exists() and not bool(kwargs.get("overwrite", True)):
            return ToolResult.failure(f"File already exists: {path}", code="file_exists")

        content = str(kwargs.get("content") or "")
        encoding = str(kwargs.get("encoding") or "utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=encoding)
        data = {
            "path": str(path),
            "relative_path": str(path.relative_to(ctx.project_root)),
            "bytes": len(content.encode(encoding, errors="replace")),
            "chars": len(content),
        }
        return ToolResult.success(f"Wrote {data['relative_path']}.", data, artifacts=[path])


__all__ = ["WriteFileTool"]
