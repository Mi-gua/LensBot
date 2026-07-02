from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ResultWorkspace:
    """Layered run workspace for workflow evidence and optimization agent turns."""

    root: Path

    @classmethod
    def start(cls, project_root: str | Path, run_id: Any) -> "ResultWorkspace":
        root = Path(project_root) / "results" / safe_run_id(run_id)
        workspace = cls(root=root)
        workspace.ensure()
        return workspace

    @classmethod
    def from_result_dir(cls, result_dir: str | Path) -> "ResultWorkspace":
        workspace = cls(root=Path(result_dir))
        workspace.ensure()
        return workspace

    def ensure(self) -> None:
        for path in (
            self.root,
            self.final_dir,
            self.events_dir,
            self.agents_dir,
            self.optimization_agent_dir,
            self.optimization_agent_dir / "workspace",
            self.optimization_agent_dir / "ledger",
            self.optimization_agent_dir / "views",
            self.deeplens_dir,
            self.deeplens_live_dir,
            self.deeplens_dir / "attempts",
            self.root / "workflow",
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def final_dir(self) -> Path:
        return self.root / "final"

    @property
    def events_dir(self) -> Path:
        return self.root / "events"

    @property
    def agents_dir(self) -> Path:
        return self.root / "agents"

    @property
    def optimization_agent_dir(self) -> Path:
        return self.agents_dir / "optimization"

    @property
    def deeplens_dir(self) -> Path:
        return self.root / "engines" / "deeplens"

    @property
    def deeplens_live_dir(self) -> Path:
        return self.deeplens_dir / "live"

    def deeplens_attempt_dir(self, stage: str, index: int = 1) -> Path:
        return self.deeplens_dir / "attempts" / f"attempt-{max(1, int(index)):03d}-{safe_path_part(stage)}"

    def write_workflow_artifact(self, node: str, name: str, payload: Any) -> Path:
        path = self.root / "workflow" / safe_path_part(node) / f"{safe_path_part(name)}.json"
        _write_json(path, payload)
        return path

    def write_timeline(self, timeline: list[JsonObject]) -> Path:
        path = self.root / "workflow" / "timeline.json"
        _write_json(path, timeline)
        return path

    def record_optimization_agent_turn(self, row: JsonObject) -> Path:
        self.ensure()
        payload = _jsonable(row)
        turn = _int_or(payload.get("turn"), 0)
        kind = safe_path_part(str(payload.get("kind") or "tool_turn"))
        tool = safe_path_part(_tool_name(payload) or "agent")
        path = self.optimization_agent_dir / "workspace" / f"turn-{turn:04d}-{kind}-{tool}.json"
        _write_json(path, payload)
        self._append_ledger(payload, path)
        self._write_turn_views()
        return path

    def _append_ledger(self, row: JsonObject, record_path: Path) -> None:
        ledger_path = self.optimization_agent_dir / "ledger" / "events.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "event": "optimization_agent.turn",
            "turn": row.get("turn"),
            "kind": row.get("kind") or "tool_turn",
            "tool": _tool_name(row),
            "decision_summary": row.get("thought") or row.get("decision_summary"),
            "observation": row.get("observation") or _tool_result(row).get("observation"),
            "ok": _tool_result(row).get("ok", row.get("ok")),
            "done": row.get("done"),
            "record_path": _relative_to_root(record_path, self.root),
            "artifact_id": artifact_id(record_path, self.root),
            "artifact_refs": _artifact_refs(row),
        }
        with ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_jsonable(event), ensure_ascii=False) + "\n")

    def _write_turn_views(self) -> None:
        rows = []
        for path in sorted((self.optimization_agent_dir / "workspace").glob("turn-*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                rows.append(data)
        transcript = [
            row
            for row in rows
            if str(row.get("kind") or "") in {"assistant_message", "tool_call", "tool_result", "agent_end", "agent_error"}
        ]
        tool_turns = [row for row in rows if row not in transcript]
        _write_json(
            self.optimization_agent_dir / "views" / "turns.json",
            {
                "schema_version": 1,
                "turns": tool_turns,
                "transcript_events": transcript,
                "turn_count": _turn_count(rows),
            },
        )


def safe_run_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        text = datetime.now().strftime("lensbot-%Y%m%d-%H%M%S-%f")
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-_") or "lensbot-run"


def safe_path_part(value: Any) -> str:
    return safe_run_id(str(value or "artifact")).lower()


def artifact_id(path: str | Path, root: str | Path | None = None) -> str:
    path_value = Path(path)
    basis = _relative_to_root(path_value, Path(root)) if root else str(path_value)
    return hashlib.sha1(basis.replace("\\", "/").encode("utf-8")).hexdigest()[:12]


def layered_workspace_index(root: str | Path) -> JsonObject:
    base = Path(root)
    workflow_root = base / "workflow"
    optimization_root = base / "agents" / "optimization"
    return {
        "workflow": {
            "artifacts": _indexed_files(workflow_root, base, "*.json"),
        },
        "optimization_agent": {
            "turn_records": _indexed_files(optimization_root / "workspace", base, "turn-*.json"),
            "ledger": _indexed_files(optimization_root / "ledger", base, "*.jsonl"),
            "views": _indexed_files(optimization_root / "views", base, "*.json"),
        },
    }


def _indexed_files(root: Path, base: Path, pattern: str) -> list[JsonObject]:
    if not root.exists():
        return []
    rows = []
    for path in sorted(root.rglob(pattern)):
        if not path.is_file():
            continue
        rows.append(
            {
                "id": artifact_id(path, base),
                "path": str(path.resolve()),
                "relative_path": _relative_to_root(path, base),
                "size_bytes": path.stat().st_size,
            }
        )
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _tool_name(row: JsonObject) -> str:
    tool_call = row.get("tool_call") if isinstance(row.get("tool_call"), dict) else {}
    return str(row.get("tool") or tool_call.get("name") or row.get("action") or "")


def _tool_result(row: JsonObject) -> JsonObject:
    result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
    return result


def _artifact_refs(row: JsonObject) -> list[JsonObject]:
    result = _tool_result(row)
    artifacts = result.get("artifacts") or row.get("artifacts") or []
    return artifacts if isinstance(artifacts, list) else []


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except (OSError, ValueError):
        return str(path)


def _int_or(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _turn_count(rows: list[JsonObject]) -> int:
    turns = [_int_or(row.get("turn"), -1) for row in rows if not _is_completion_row(row)]
    return max(turns) + 1 if turns else 0


def _is_completion_row(row: JsonObject) -> bool:
    kind = str(row.get("kind") or "")
    return kind in {"agent_end", "agent_error"} or row.get("done") is True


__all__ = [
    "ResultWorkspace",
    "artifact_id",
    "layered_workspace_index",
    "safe_run_id",
]
