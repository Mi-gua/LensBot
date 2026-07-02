from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.tools import ToolContext, ToolResult
from subagents.seeding import (
    case_path,
    extract_case_metadata,
    load_index_entries,
    retrieve_candidates,
)


class RetrieveSeedCasesTool:
    """Return local ZEMAX index entries for the Seeding subagent."""

    name = "retrieve_seed_cases"
    description = "List local ZMX references from the Markdown index for LLM selection."
    category = "general"
    scope = "seed_design"
    input_schema = {
        "type": "object",
        "properties": {},
    }
    output_schema = {
        "type": "object",
        "required": ["candidates"],
        "properties": {"candidates": {"type": "array", "items": {"type": "SeedCandidatePayload"}}},
    }
    metadata = {"kind": "case_retrieval"}

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.cases_dir = project_root / "cases"
        self.index_path = self.cases_dir / "ZEMAX Index.md"

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        if not self.index_path.exists():
            return ToolResult.failure(
                f"ZEMAX index was not found: {self.index_path}",
                code="case_index_missing",
                data={"index_path": str(self.index_path)},
                recoverable=False,
            )

        entries = load_index_entries(self.index_path)
        if not entries:
            return ToolResult.failure(
                "ZEMAX index does not contain usable case entries.",
                code="case_index_empty",
                data={"index_path": str(self.index_path)},
            )

        candidates = retrieve_candidates(cases_dir=self.cases_dir, entries=entries)
        return ToolResult.success(
            "Loaded local ZEMAX case index.",
            {"candidates": candidates},
        )


class ReadSeedCasesTool:
    """Read selected local ZEMAX cases in one tool call."""

    name = "read_seed_cases"
    description = "Read multiple local ZMX references selected from the Markdown index."
    category = "filesystem"
    scope = "seed_design"
    input_schema = {
        "type": "object",
        "properties": {
            "cases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "case_id": {"type": "string"},
                        "path": {"type": "string"},
                    },
                },
            },
        },
    }
    output_schema = {
        "type": "object",
        "required": ["cases"],
        "properties": {
            "cases": {"type": "array", "items": {"type": "object"}},
            "errors": {"type": "array", "items": {"type": "object"}},
        },
    }
    metadata = {"kind": "case_batch_read"}

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.cases_dir = project_root / "cases"

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        requested = kwargs.get("cases")
        if not isinstance(requested, list) or not requested:
            return ToolResult.failure(
                "No seed cases were supplied for batch reading.",
                code="seed_case_batch_empty",
                data={"cases": []},
            )

        cases: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for item in requested:
            if not isinstance(item, dict):
                errors.append({"code": "seed_case_invalid", "message": "Seed case entry must be an object."})
                continue
            case_id = str(item.get("case_id") or "").strip()
            raw_path = str(item.get("path") or "").strip()
            payload, error = _read_case_payload(self.cases_dir, case_id=case_id, raw_path=raw_path)
            if error:
                error["candidate_id"] = str(item.get("candidate_id") or "")
                errors.append(error)
                continue
            payload["candidate_id"] = str(item.get("candidate_id") or "")
            cases.append(payload)

        data = {"cases": cases, "errors": errors}
        if not cases:
            return ToolResult.failure(
                "No selected seed cases could be read.",
                code="seed_case_batch_unreadable",
                data=data,
            )
        return ToolResult.success(f"Read {len(cases)} seed case(s).", data)


def _read_case_payload(cases_dir: Path, *, case_id: str, raw_path: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    path = Path(raw_path) if raw_path else case_path(cases_dir, case_id)
    if path is None:
        return {}, {
            "code": "seed_case_missing",
            "message": f"Seed case was not found: {case_id or raw_path}",
            "case_id": case_id,
            "path": raw_path,
        }

    try:
        resolved = path.resolve()
        cases_root = cases_dir.resolve()
    except OSError as exc:
        return {}, {"code": "seed_case_path_error", "message": str(exc), "case_id": case_id, "path": raw_path}

    if cases_root not in resolved.parents and resolved != cases_root:
        return {}, {
            "code": "seed_case_outside_cases",
            "message": f"Seed case path is outside cases directory: {resolved}",
            "case_id": case_id,
            "path": str(resolved),
            "cases_dir": str(cases_root),
            "recoverable": False,
        }
    if not resolved.exists() or resolved.suffix.lower() != ".zmx":
        return {}, {
            "code": "seed_case_unreadable",
            "message": f"Seed case is not a readable ZMX file: {resolved}",
            "case_id": case_id,
            "path": str(resolved),
        }

    text = resolved.read_text(encoding="utf-8", errors="ignore")
    metadata = extract_case_metadata(resolved, text=text)
    return {
        "case_id": case_id or resolved.stem,
        "path": str(resolved),
        "zmx_text": text,
        "metadata": metadata,
    }, None
