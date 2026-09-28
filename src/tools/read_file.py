from __future__ import annotations

from typing import Any

from agent.tools import ToolContext, ToolResult
from tools.paths import resolve_under_root


class ReadFileTool:
    name = "read_file"
    description = (
        "Read a text file under the project root. Relative paths start at the project root; "
        "for skill references, use the absolute path resolved from the skill's location."
    )
    category = "filesystem"
    scope = "workflow"
    input_schema = {
        "type": "object",
        "required": ["path"],
        "additionalProperties": False,
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer", "default": 20000},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "encoding": {"type": "string", "default": "utf-8"},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["path", "relative_path", "content", "offset", "next_offset", "truncated", "chars", "returned_chars", "encoding"],
        "additionalProperties": False,
        "properties": {
            "path": {"type": "string"},
            "relative_path": {"type": "string"},
            "content": {"type": "string"},
            "offset": {"type": "integer"},
            "next_offset": {"type": ["integer", "null"]},
            "truncated": {"type": "boolean"},
            "chars": {"type": "integer"},
            "returned_chars": {"type": "integer"},
            "encoding": {"type": "string"},
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

        try:
            max_chars = int(kwargs.get("max_chars", 20000))
            offset = int(kwargs.get("offset", 0))
        except (TypeError, ValueError):
            return ToolResult.failure("max_chars and offset must be integers.", code="invalid_page")
        if not 1 <= max_chars <= 20000 or offset < 0:
            return ToolResult.failure("Use 1..20000 max_chars and a nonnegative offset.", code="invalid_page")
        encoding = str(kwargs.get("encoding") or "utf-8")
        try:
            content = path.read_text(encoding=encoding, errors="replace")
        except (LookupError, OSError) as exc:
            return ToolResult.failure(
                f"Could not read {path}: {exc}",
                code="file_read_failed",
                error={"code": "file_read_failed", "path": str(path), "message": str(exc)},
            )
        end = min(offset + max_chars, len(content))
        truncated = end < len(content)
        page = content[offset:end]
        data = {
            "path": str(path),
            "relative_path": str(path.relative_to(ctx.project_root.resolve())),
            "content": page,
            "offset": offset,
            "next_offset": end if truncated else None,
            "truncated": truncated,
            "chars": len(content),
            "returned_chars": len(page),
            "encoding": encoding,
        }
        return ToolResult.success(
            f"Read {data['relative_path']} at character {offset}; returned {len(page)} of {len(content)} characters.",
            data,
        )


__all__ = ["ReadFileTool"]
