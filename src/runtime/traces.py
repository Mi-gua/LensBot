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
        "arguments": _bounded_value(arguments),
        "tool_call": {"name": tool_name, "arguments": _bounded_value(arguments)},
        "tool_result": _compact_tool_result(tool_result),
        "observation": _summary_text(row.get("observation") or tool_result.get("observation"), 1200),
        "ok": tool_result.get("ok", row.get("ok")),
        "done": row.get("done"),
        "artifacts": _compact_artifacts(tool_result.get("artifacts", row.get("artifacts", []))),
        "metrics": _scalar_values(tool_result.get("metrics", row.get("metrics", {}))),
        "error": _bounded_value(tool_result.get("error", row.get("error")), 1500),
    }
    for key in ("duration_ms", "timestamp"):
        if row.get(key) is not None:
            payload[key] = row.get(key)
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
        "status",
        "source_event_type",
        "assistant_event_type",
        "content_type",
        "content_index",
        "update_type",
        "delta_length",
        "stop_reason",
    ):
        if row.get(key) is not None:
            payload[key] = row.get(key)
    if "text" in payload:
        payload["text"] = _summary_text(payload["text"], 4000)
    if "delta" in payload:
        payload["delta"] = _summary_text(payload["delta"], 4000)
    if "arguments" in payload:
        payload["arguments"] = _bounded_value(payload["arguments"])
    if isinstance(payload.get("tool_call"), dict):
        call = payload["tool_call"]
        payload["tool_call"] = {
            "name": call.get("name") or row.get("tool"),
            "arguments": _bounded_value(call.get("arguments") or row.get("arguments") or {}),
        }
    if "tool_result" in payload:
        payload["tool_result"] = _compact_tool_result(payload["tool_result"])
    if "observation" in payload:
        payload["observation"] = _summary_text(payload["observation"], 1200)
    if "metrics" in payload:
        payload["metrics"] = _scalar_values(payload["metrics"])
    if "artifacts" in payload:
        payload["artifacts"] = _compact_artifacts(payload["artifacts"])
    if "error" in payload:
        payload["error"] = _bounded_value(payload["error"], 1500)
    return {key: value for key, value in payload.items() if value is not None}


def _compact_tool_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in {
            "ok": value.get("ok"),
            "observation": _summary_text(value.get("observation"), 1200),
            "metrics": _scalar_values(value.get("metrics")),
            "artifacts": _compact_artifacts(value.get("artifacts")),
            "error": _bounded_value(value.get("error"), 1500),
            "state_patch": _bounded_value(value.get("state_patch"), 2000),
        }.items()
        if item not in (None, "", [], {})
    }


def _compact_artifacts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if isinstance(item, str):
            rows.append({"path": item})
        elif isinstance(item, dict):
            rows.append(
                {
                    key: item[key]
                    for key in ("path", "kind", "role", "source", "stage", "label")
                    if item.get(key) not in (None, "")
                }
            )
    return rows


def _scalar_values(value: Any) -> dict[str, Any]:
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
        return {"stored_in_raw_record": True, "keys": sorted(str(key) for key in payload)}
    if isinstance(payload, list):
        return {"stored_in_raw_record": True, "items": len(payload)}
    return _summary_text(payload, limit)


def _summary_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


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
