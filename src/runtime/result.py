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
        root = _unique_result_root(Path(project_root), run_id)
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
            self.candidates_dir,
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

    @property
    def candidates_dir(self) -> Path:
        return self.root / "candidates"

    def deeplens_attempt_dir(self, stage: str, index: int = 1) -> Path:
        return self.deeplens_dir / "attempts" / f"attempt-{max(1, int(index)):03d}-{safe_path_part(stage)}"

    def candidate_dir(self, index: int) -> Path:
        return self.candidates_dir / f"candidate-{max(1, int(index)):03d}"

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
            "decision_summary": _summary_text(row.get("thought") or row.get("decision_summary"), 600),
            "observation": _summary_text(row.get("observation") or _tool_result(row).get("observation"), 1000),
            "ok": _tool_result(row).get("ok", row.get("ok")),
            "done": row.get("done"),
            "record_path": _relative_to_root(record_path, self.root),
            "artifact_id": artifact_id(record_path, self.root),
            "artifact_refs": _compact_artifact_refs(_artifact_refs(row)),
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
                rows.append(_turn_view(data, path, self.root))
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
        text = new_run_id()
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-_") or "lensbot-run"


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _unique_result_root(project_root: Path, run_id: Any) -> Path:
    root = project_root / "results"
    name = safe_run_id(run_id)
    path = root / name
    index = 2
    while path.exists():
        path = root / f"{name}-{index}"
        index += 1
    return path


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


def _turn_view(row: JsonObject, record_path: Path, root: Path) -> JsonObject:
    kind = str(row.get("kind") or "tool_turn")
    tool_call = row.get("tool_call") if isinstance(row.get("tool_call"), dict) else {}
    tool_result = _tool_result(row)
    view: JsonObject = {
        "agent": row.get("agent"),
        "kind": kind,
        "turn": row.get("turn"),
        "sequence": row.get("sequence"),
        "tool": _tool_name(row),
        "tool_call_id": row.get("tool_call_id"),
        "status": row.get("status"),
        "ok": row.get("ok", tool_result.get("ok")),
        "done": row.get("done"),
        "duration_ms": row.get("duration_ms"),
        "record_path": _relative_to_root(record_path, root),
    }
    if kind == "assistant_message":
        view["text"] = _summary_text(row.get("text") or row.get("delta"), 4000)
        view["message_id"] = row.get("message_id")
    elif kind == "tool_call":
        view["arguments"] = _bounded_value(row.get("arguments") or tool_call.get("arguments") or {})
        view["tool_call"] = {"name": _tool_name(row), "arguments": view["arguments"]}
    elif kind == "tool_result":
        view["observation"] = _summary_text(row.get("observation") or tool_result.get("observation"), 1200)
        view["metrics"] = _scalar_values(row.get("metrics") or tool_result.get("metrics"))
        view["artifacts"] = _compact_artifact_refs(row.get("artifacts") or tool_result.get("artifacts") or [])
        view["error"] = _bounded_value(row.get("error") or tool_result.get("error"), 1500)
    else:
        view["thought"] = _summary_text(row.get("thought"), 1200)
        view["observation"] = _summary_text(row.get("observation") or tool_result.get("observation"), 1200)
        view["text"] = _summary_text(row.get("text"), 1200)
    return {key: value for key, value in view.items() if value not in (None, "", [], {})}


def _compact_artifact_refs(artifacts: Any) -> list[JsonObject]:
    if not isinstance(artifacts, list):
        return []
    result = []
    for item in artifacts:
        if isinstance(item, str):
            result.append({"path": item})
            continue
        if not isinstance(item, dict):
            continue
        result.append(
            {
                key: item[key]
                for key in ("path", "kind", "role", "source", "stage", "label")
                if item.get(key) not in (None, "")
            }
        )
    return result


def _scalar_values(value: Any) -> JsonObject:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if item is None or isinstance(item, (str, int, float, bool))
    }


def _bounded_value(value: Any, limit: int = 4000) -> Any:
    if value in (None, "", [], {}):
        return None
    payload = _jsonable(value)
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= limit:
        return payload
    if isinstance(payload, dict):
        return {"stored_in_record": True, "keys": sorted(str(key) for key in payload)}
    if isinstance(payload, list):
        return {"stored_in_record": True, "items": len(payload)}
    return _summary_text(payload, limit)


def _summary_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


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
    "new_run_id",
    "safe_run_id",
]
