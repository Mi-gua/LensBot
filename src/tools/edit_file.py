from __future__ import annotations

from typing import Any

from agent.tools import ToolContext, ToolResult
from tools.paths import resolve_under_root


class EditFileTool:
    name = "edit_file"
    description = "Replace text in a file under the project root."
    category = "filesystem"
    scope = "workflow"
    input_schema = {
        "type": "object",
        "required": ["path", "old_text", "new_text"],
        "properties": {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
            "encoding": {"type": "string", "default": "utf-8"},
            "replace_all": {"type": "boolean", "default": False},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["path", "replacements"],
        "properties": {"path": {"type": "string"}, "replacements": {"type": "integer"}},
    }
    metadata = {"kind": "filesystem_edit"}

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        path = resolve_under_root(ctx.project_root, kwargs.get("path"))
        if path is None:
            return ToolResult.failure("Path is outside the project root.", code="invalid_path")
        if not path.is_file():
            return ToolResult.failure(f"File not found: {path}", code="file_not_found")

        old_text = str(kwargs.get("old_text") or "")
        if not old_text:
            return ToolResult.failure("old_text cannot be empty.", code="empty_old_text")
        new_text = str(kwargs.get("new_text") or "")
        encoding = str(kwargs.get("encoding") or "utf-8")
        replace_all = bool(kwargs.get("replace_all", False))

        content = path.read_text(encoding=encoding, errors="replace")
        count = content.count(old_text)
        if count == 0:
            return ToolResult.failure("old_text was not found.", code="text_not_found")
        if count > 1 and not replace_all:
            return ToolResult.failure(
                f"old_text appears {count} times; set replace_all=true or provide a more specific old_text.",
                code="ambiguous_edit",
                data={"matches": count},
            )

        updated = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)
        replacements = count if replace_all else 1
        path.write_text(updated, encoding=encoding)
        data = {
            "path": str(path),
            "relative_path": str(path.relative_to(ctx.project_root)),
            "replacements": replacements,
        }
        return ToolResult.success(f"Edited {data['relative_path']} ({replacements} replacement).", data, artifacts=[path])


__all__ = ["EditFileTool"]
