from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TRANSCRIPT_EVENT_KINDS = {
    "assistant_message",
    "tool_call",
    "tool_result",
    "agent_end",
    "agent_error",
}


def trace_row(
    *,
    agent: str,
    turn: int,
    thought: str,
    action: str,
    action_input: dict[str, Any],
    observation: str,
    data: Any = None,
    done: bool = False,
    ok: bool = True,
) -> dict[str, Any]:
    return {
        "agent": agent,
        "turn": turn,
        "thought": thought,
        "action": action,
        "action_input": action_input,
        "tool_call": {"name": action, "arguments": action_input},
        "tool_result": {"ok": ok, "observation": observation, "data": data},
        "observation": observation,
        "done": done,
        "data": data,
    }


def append_timeline_event(result_dir: str | Path | None, event: dict[str, Any], *, index: int | None = None) -> None:
    if not result_dir or not event:
        return
    append_trace_event(
        result_dir,
        {
            "track": "timeline",
            "kind": "timeline_event",
            "index": index,
            "timeline": event,
        },
    )


def append_agent_event(result_dir: str | Path | None, row: Any) -> None:
    if not result_dir or row is None:
        return
    payload = _row_payload(row)
    if not payload:
        return
    payload["track"] = "agent"
    payload.setdefault("kind", "tool_turn")
    append_trace_event(result_dir, payload)


def append_trace_event(result_dir: str | Path | None, payload: dict[str, Any]) -> None:
    if not result_dir:
        return
    root = Path(result_dir)
    root.mkdir(parents=True, exist_ok=True)
    trace_path = _trace_path_for_track(root, str(payload.get("track") or "tools"))
    event = {
        "time": datetime.now().isoformat(timespec="seconds"),
        **payload,
    }
    event = _jsonable(event)
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_trace_payload(result_dir: str | Path | None) -> dict[str, list[dict[str, Any]]]:
    tracks: dict[str, list[dict[str, Any]]] = {"timeline": [], "agent": []}
    if not result_dir:
        return tracks
    trace_paths = _trace_paths(Path(result_dir))
    if not trace_paths:
        return tracks
    try:
        lines = [
            line
            for trace_path in trace_paths
            for line in trace_path.read_text(encoding="utf-8").splitlines()
        ]
    except OSError:
        return tracks
    seen: set[str] = set()
    agent_order: list[str] = []
    agent_events: dict[str, dict[str, Any]] = {}
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        track = str(event.get("track") or "global")
        if track == "react":
            track = "agent"
        key = _event_key(event)
        if track == "agent":
            if key not in agent_events:
                agent_order.append(key)
            agent_events[key] = event
            continue
        if key in seen:
            continue
        seen.add(key)
        tracks.setdefault(track, []).append(event)
    tracks["agent"] = [agent_events[key] for key in agent_order]
    return tracks


def _trace_path_for_track(root: Path, track: str) -> Path:
    event_dir = root / "events"
    event_dir.mkdir(parents=True, exist_ok=True)
    if track in {"timeline", "workflow"}:
        return event_dir / "workflow.jsonl"
    if track in {"agent", "react"}:
        return event_dir / "agent.jsonl"
    return event_dir / "tools.jsonl"


def _trace_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    event_dir = root / "events"
    if event_dir.exists():
        paths.extend(path for path in sorted(event_dir.glob("*.jsonl")) if path.is_file())
    return paths


def _row_payload(row: Any) -> dict[str, Any]:
    if hasattr(row, "for_trace"):
        row = row.for_trace()
    if not isinstance(row, dict):
        return {}
    native_payload = _native_transcript_payload(row)
    if native_payload:
        return native_payload
    tool_call = row.get("tool_call") if isinstance(row.get("tool_call"), dict) else {}
    tool_result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else row.get("data", {})
    if not isinstance(tool_result, dict):
        tool_result = {}
    tool_name = tool_call.get("name") or row.get("action") or row.get("tool")
    arguments = tool_call.get("arguments") or row.get("action_input") or row.get("arguments") or {}
    payload = {
        "agent": row.get("agent"),
        "turn": row.get("turn"),
        "thought": row.get("thought"),
        "tool": tool_name,
        "arguments": arguments,
        "tool_call": {"name": tool_name, "arguments": arguments},
        "tool_result": tool_result,
        "observation": row.get("observation") or tool_result.get("observation"),
        "ok": tool_result.get("ok", row.get("ok")),
        "done": row.get("done"),
        "artifacts": tool_result.get("artifacts", row.get("artifacts", [])),
        "metrics": tool_result.get("metrics", row.get("metrics", {})),
        "error": tool_result.get("error", row.get("error")),
    }
    for key in ("duration_ms", "timestamp"):
        if row.get(key) is not None:
            payload[key] = row.get(key)
    if row.get("data") is not None:
        payload["data"] = row.get("data")
    return payload


def _native_transcript_payload(row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("kind") or "")
    if kind not in TRANSCRIPT_EVENT_KINDS:
        return {}
    payload: dict[str, Any] = {
        "kind": kind,
        "agent": row.get("agent"),
        "turn": row.get("turn"),
        "sequence": row.get("sequence"),
        "timestamp": row.get("timestamp"),
    }
    for key in (
        "message_id",
        "role",
        "text",
        "delta",
        "tool",
        "tool_call_id",
        "arguments",
        "tool_call",
        "tool_result",
        "observation",
        "ok",
        "done",
        "duration_ms",
        "metrics",
        "artifacts",
        "error",
        "data",
        "status",
        "source_event_type",
        "assistant_event_type",
        "content_type",
        "content_index",
        "update_type",
        "delta_length",
        "stop_reason",
        "partial_result",
    ):
        if row.get(key) is not None:
            payload[key] = row.get(key)
    return {key: value for key, value in payload.items() if value is not None}


def _event_key(event: dict[str, Any]) -> str:
    if event.get("track") in {"agent", "react"}:
        kind = str(event.get("kind") or "tool_turn")
        if kind != "tool_turn":
            stable_id = (
                event.get("message_id")
                or event.get("tool_call_id")
                or event.get("sequence")
                or event.get("time")
                or event.get("timestamp")
            )
            return "|".join(
                str(value or "")
                for value in (
                    event.get("track"),
                    event.get("agent"),
                    kind,
                    event.get("turn"),
                    stable_id,
                )
            )
        tool_call = event.get("tool_call") if isinstance(event.get("tool_call"), dict) else {}
        tool = event.get("tool") or tool_call.get("name")
        return "|".join(
            str(event.get(key) or "")
            for key in ("track", "agent", "turn")
        ) + f"|{tool or ''}"
    timeline = event.get("timeline") if isinstance(event.get("timeline"), dict) else {}
    return "|".join(
        str(value or "")
        for value in (
            event.get("track"),
            event.get("index"),
            timeline.get("key"),
            timeline.get("message"),
        )
    )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {value}"
    try:
        json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)
    return value
