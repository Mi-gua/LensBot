from __future__ import annotations

import json
import mimetypes
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from runtime.result import layered_workspace_index
from runtime.traces import load_trace_payload


DisplayUrlBuilder = Callable[[Path | None], str | None]
DisplayPathBuilder = Callable[[str | None], str | None]


@dataclass
class ArtifactRecord:
    path: str
    kind: str
    role: str
    source: str
    stage: str = ""
    label: str = ""
    title: str = ""
    subtitle: str = ""
    preview: bool = True
    order: int = 100
    mime_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mime_type"] = self.mime_type or mimetypes.guess_type(self.path)[0] or ""
        return payload


def refresh_run_manifest(
    result_dir: str | Path | None,
    *,
    metrics: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    phase: str | None = None,
    trim_transient: bool = True,
) -> dict[str, Any] | None:
    if not result_dir:
        return None
    root = Path(result_dir)
    if not root.exists():
        return None

    if trim_transient:
        prune_transient_outputs(root)

    artifacts = _discover_key_artifacts(root)
    layers = layered_workspace_index(root)
    payload = {
        "schema_version": 2,
        "result_dir": str(root.resolve()),
        "phase": phase or _load_session_phase(root),
        "params": params or _load_session_params(root),
        "artifacts": [artifact.to_json() for artifact in artifacts],
        "layers": layers,
    }
    if metrics:
        payload["metrics_keys"] = sorted(metrics.keys())
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def build_preview_payload(
    result_dir: str | Path | None,
    metrics: dict[str, Any] | None,
    *,
    url_builder: DisplayUrlBuilder,
    path_builder: DisplayPathBuilder,
) -> dict[str, Any] | None:
    if not result_dir:
        return None
    root = Path(result_dir)
    manifest = refresh_run_manifest(root, metrics=metrics or {})
    if not manifest:
        return None

    metric_map = metrics or {}
    artifacts = [_attach_display_fields(item, url_builder, path_builder) for item in manifest.get("artifacts", [])]
    by_role = _by_role(artifacts)
    traces = load_trace_payload(root)
    optimization_stages = _optimization_stages(root, traces)
    zemax_figures = [
        item
        for role in ("zemax_mtf", "zemax_spot_summary", "zemax_spot_diagram", "zemax_summary")
        for item in by_role.get(role, [])[:1]
    ]

    starting_json = _first_path(by_role, "deeplens_adjusted_structure_json") or _first_path(by_role, "deeplens_starting_json")
    final_json = _first_path(by_role, "deeplens_final_json")
    starting_data = _load_json_dict(Path(starting_json)) if starting_json else {}
    final_data = _load_json_dict(Path(final_json)) if final_json else {}
    zemax_report = _first(by_role, "zemax_report")
    zemax_report_data = _load_json_dict(Path(zemax_report["path"])) if zemax_report else {}
    zemax_status = _zemax_status(metric_map, zemax_report_data)
    zemax_error = metric_map.get("zemax_error") or zemax_report_data.get("error") or zemax_report_data.get("spot_diagram_error")

    payload = {
        "artifacts": artifacts,
        "run_trace": traces.get("global", []),
        "agent_trace": traces.get("agent", []),
        "deeplens_progress": _deeplens_progress(root),
        "starting_image_url": _first_url(by_role, "deeplens_adjusted_structure_image") or _first_url(by_role, "deeplens_starting_image"),
        "curriculum_image_url": _first_url(by_role, "deeplens_current_image") or _first_url(by_role, "deeplens_curriculum_image"),
        "final_image_url": _first_url(by_role, "deeplens_final_image"),
        "starting_json_path": _first_display_path(by_role, "deeplens_adjusted_structure_json") or _first_display_path(by_role, "deeplens_starting_json"),
        "starting_json_url": _first_url(by_role, "deeplens_adjusted_structure_json") or _first_url(by_role, "deeplens_starting_json"),
        "foclen_display": _format_value(final_data.get("foclen") or starting_data.get("foclen"), " mm"),
        "fnum_display": _format_value(_preview_fnum(metric_map, final_data, starting_data)),
        "fov_display": _format_value(_preview_fov_deg(metric_map), " deg"),
        "r_sensor_display": _format_value(
            metric_map.get("r_sensor") or final_data.get("r_sensor") or starting_data.get("r_sensor"),
            " mm",
        ),
        "structure_group_count_display": _format_value(metric_map.get("structure_group_count"), "", 0),
        "optimization_stages": optimization_stages,
        "zemax_figures": zemax_figures[:3],
        "zemax_status": zemax_status,
        "zemax_status_label": _zemax_status_label(zemax_status),
        "zemax_error": zemax_error,
        "zemax_report_path": zemax_report.get("display_path") if zemax_report else None,
        "zemax_report_url": zemax_report.get("url") if zemax_report else None,
    }
    return payload


def prune_transient_outputs(result_dir: Path) -> None:
    for folder_name in ("curriculum", "fine-tune"):
        folder = result_dir / folder_name
        if not folder.exists() or not folder.is_dir():
            continue
        for suffix in ("*.png", "*.json", "*.zmx"):
            for path in folder.glob(suffix):
                if path.is_file():
                    path.unlink()
        try:
            folder.rmdir()
        except OSError:
            pass


def _discover_key_artifacts(root: Path) -> list[ArtifactRecord]:
    records: list[ArtifactRecord] = []

    def add(relative: str | Path, *, kind: str, role: str, source: str, stage: str, title: str, subtitle: str = "", order: int) -> None:
        path = relative if isinstance(relative, Path) else Path(relative)
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            return
        if any(record.role == role for record in records):
            return
        records.append(
            ArtifactRecord(
                path=str(path.resolve()),
                kind=kind,
                role=role,
                source=source,
                stage=stage,
                label=title,
                title=title,
                subtitle=subtitle,
                order=order,
            )
        )

    curriculum_dir = Path("engines") / "deeplens" / "attempts" / "attempt-001-curriculum"
    live_dir = Path("engines") / "deeplens" / "live"
    final_dir = Path("final")
    add(curriculum_dir / "starting-point.json", kind="lens_json", role="deeplens_starting_json", source="deeplens", stage="starting", title="Starting lens JSON", order=10)
    add(curriculum_dir / "starting-point.png", kind="image", role="deeplens_starting_image", source="deeplens", stage="starting", title="Starting structure", order=11)
    add(live_dir / "adjusted-structure.json", kind="lens_json", role="deeplens_adjusted_structure_json", source="deeplens", stage="starting", title="Adjusted structure JSON", order=12)
    add(live_dir / "adjusted-structure.png", kind="image", role="deeplens_adjusted_structure_image", source="deeplens", stage="starting", title="Adjusted structure", order=13)
    add(live_dir / "current.json", kind="lens_json", role="deeplens_current_json", source="deeplens", stage="optimization", title="Current lens JSON", order=20)
    add(live_dir / "current.png", kind="image", role="deeplens_current_image", source="deeplens", stage="optimization", title="Current optimization snapshot", order=21)
    add(curriculum_dir / "curriculum.json", kind="lens_json", role="deeplens_curriculum_json", source="deeplens", stage="curriculum", title="Curriculum lens JSON", order=30)
    add(curriculum_dir / "curriculum.png", kind="image", role="deeplens_curriculum_image", source="deeplens", stage="curriculum", title="Curriculum result", order=31)
    add(final_dir / "final.json", kind="lens_json", role="deeplens_final_json", source="deeplens", stage="final", title="Final lens JSON", order=40)
    add(final_dir / "final.png", kind="image", role="deeplens_final_image", source="deeplens", stage="final", title="Final structure", order=41)
    add(final_dir / "final.zmx", kind="lens_zmx", role="zemax_lens_file", source="deeplens", stage="final", title="Zemax lens file", order=42)
    add("metrics.json", kind="metrics", role="metrics", source="workflow", stage="reporting", title="Metrics file", order=70)
    add("summary.md", kind="report", role="summary_report", source="workflow", stage="reporting", title="Summary report", order=71)
    add("workflow/timeline.json", kind="timeline", role="workflow_timeline", source="workflow", stage="workflow", title="Workflow timeline", order=72)
    add("agents/optimization/ledger/events.jsonl", kind="ledger", role="optimization_agent_ledger", source="optimization-agent", stage="optimization", title="Optimization agent ledger", order=73)
    add("agents/optimization/views/turns.json", kind="view", role="optimization_agent_turns_view", source="optimization-agent", stage="optimization", title="Optimization agent turns view", order=74)
    add("events/workflow.jsonl", kind="trace", role="workflow_events", source="runtime", stage="runtime", title="Workflow events", order=75)
    add("events/agent.jsonl", kind="trace", role="agent_events", source="runtime", stage="runtime", title="Agent events", order=76)
    add("events/tools.jsonl", kind="trace", role="tool_events", source="runtime", stage="runtime", title="Tool events", order=77)
    add("engines/deeplens/deeplens.log", kind="log", role="deeplens_log", source="deeplens", stage="optimization", title="DeepLens log", order=80)
    add("engines/deeplens/session.json", kind="state", role="session_state", source="deeplens", stage="optimization", title="Session state", order=81)
    add("manifest.json", kind="manifest", role="manifest", source="runtime", stage="runtime", title="Artifact manifest", order=90)

    zemax_specs = [
        ("fft_mtf.png", "zemax_mtf", "FFT MTF", "Tangential and sagittal MTF from OpticStudio", 50),
        ("spot_summary.png", "zemax_spot_summary", "Spot radius", "RMS and geometric spot radius by field", 51),
        ("spot_diagram.png", "zemax_spot_diagram", "Spot diagram", "Ray point cloud relative to centroid", 52),
        ("zemax_summary.png", "zemax_summary", "Zemax summary", "Fallback overview when spot tracing is unavailable", 53),
    ]
    for filename, role, title, subtitle, order in zemax_specs:
        add(Path("verification") / "zemax" / filename, kind="image", role=role, source="zemax", stage="analysis", title=title, subtitle=subtitle, order=order)
    add("verification/zemax/zemax_report.json", kind="report", role="zemax_report", source="zemax", stage="analysis", title="Zemax analysis report", order=54)

    return sorted(records, key=lambda item: (item.order, item.role, item.path))


def _attach_display_fields(
    item: dict[str, Any],
    url_builder: DisplayUrlBuilder,
    path_builder: DisplayPathBuilder,
) -> dict[str, Any]:
    path = Path(str(item.get("path") or ""))
    payload = dict(item)
    payload["url"] = url_builder(path)
    payload["display_path"] = path_builder(str(path))
    return payload


def _by_role(artifacts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_role: dict[str, list[dict[str, Any]]] = {}
    for item in artifacts:
        by_role.setdefault(str(item.get("role") or ""), []).append(item)
    return by_role


def _first(by_role: dict[str, list[dict[str, Any]]], role: str) -> dict[str, Any] | None:
    rows = by_role.get(role) or []
    return rows[0] if rows else None


def _first_url(by_role: dict[str, list[dict[str, Any]]], role: str) -> str | None:
    item = _first(by_role, role)
    return item.get("url") if item else None


def _first_path(by_role: dict[str, list[dict[str, Any]]], role: str) -> str | None:
    item = _first(by_role, role)
    return item.get("path") if item else None


def _first_display_path(by_role: dict[str, list[dict[str, Any]]], role: str) -> str | None:
    item = _first(by_role, role)
    return item.get("display_path") if item else None


def _optimization_stages(root: Path, traces: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    view = _load_json_dict(root / "agents" / "optimization" / "views" / "turns.json")
    if view:
        agent_events = view.get("turns") if isinstance(view.get("turns"), list) else []
        transcript_events = view.get("transcript_events") if isinstance(view.get("transcript_events"), list) else []
        turn_count = _optimization_turn_count([*agent_events, *transcript_events], view.get("turn_count"))
        if agent_events or transcript_events:
            return [
                {
                    "key": "optimization_agent_trace",
                    "title": "Optimization transcript",
                    "status": "complete" if any(event.get("done") for event in [*agent_events, *transcript_events] if isinstance(event, dict)) else "running",
                    "summary": f"Recorded {turn_count} optimization turns.",
                    "data": {
                        "agent_events": agent_events[-24:],
                        "transcript_events": transcript_events[-80:],
                        "turn_count": turn_count,
                    },
                }
            ]

    optimization_events = [event for event in traces.get("agent", []) if event.get("agent") == "Optimization"]
    transcript_events = [
        event
        for event in optimization_events
        if event.get("kind") in {"assistant_message", "tool_call", "tool_result", "agent_end", "agent_error"}
    ]
    agent_events = [
        event
        for event in optimization_events
        if event.get("kind") in {None, "", "tool_turn"} or not event.get("kind")
    ]
    if optimization_events:
        turn_count = _optimization_turn_count(optimization_events)
        return [
            {
                "key": "optimization_agent_trace",
                "title": "Optimization transcript",
                "status": "complete" if any(event.get("done") for event in optimization_events) else "running",
                "summary": f"Recorded {turn_count} optimization turns.",
                "data": {
                    "agent_events": agent_events[-24:],
                    "transcript_events": transcript_events[-80:],
                    "turn_count": turn_count,
                },
            }
        ]

    session = _load_json_dict(_session_path(root))
    if not session:
        return []
    return [
        {
            "key": "runtime_session_state",
            "title": "Live optimization state",
            "status": session.get("phase") or "session",
            "summary": _session_summary(session),
            "data": {"session": session},
        }
    ]


def _optimization_turn_count(events: list[dict[str, Any]], raw_count: Any = None) -> int:
    countable_turns = [
        int(event.get("turn"))
        for event in events
        if not _is_optimization_completion_event(event)
        and (isinstance(event.get("turn"), int) or str(event.get("turn") or "").isdigit())
    ]
    if not countable_turns:
        return _int_or_none(raw_count) or 0
    computed_count = max(countable_turns) + 1
    raw = _int_or_none(raw_count)
    if raw is None:
        return computed_count
    completion_turns = [
        int(event.get("turn"))
        for event in events
        if _is_optimization_completion_event(event)
        and (isinstance(event.get("turn"), int) or str(event.get("turn") or "").isdigit())
    ]
    if completion_turns and max(completion_turns) >= computed_count and raw == max(completion_turns) + 1:
        return computed_count
    return max(raw, computed_count)


def _is_optimization_completion_event(event: dict[str, Any]) -> bool:
    kind = str(event.get("kind") or "")
    return kind in {"agent_end", "agent_error"} or event.get("done") is True


def _session_summary(session: dict[str, Any]) -> str:
    phase = str(session.get("phase") or "session")
    if phase == "curriculum":
        return f"Curriculum {session.get('curriculum_iter')}/{session.get('curriculum_total')}"
    if phase in {"fine_tune", "ready_to_finalize"}:
        return f"Fine tune {session.get('fine_tune_iter')}/{session.get('fine_tune_total')}"
    return phase


def _deeplens_progress(root: Path) -> dict[str, Any] | None:
    session = _load_json_dict(_session_path(root))
    if not session:
        return None

    phase = str(session.get("phase") or "").strip()
    if phase in {"curriculum", "curriculum_complete"}:
        tool = "deeplens_curriculum"
        label = "课程学习"
        current = _int_or_none(session.get("curriculum_iter"))
        total = _int_or_none(session.get("curriculum_total"))
    elif phase in {"fine_tune", "ready_to_finalize", "finalized"}:
        tool = "deeplens_finetune"
        label = "微调"
        current = _int_or_none(session.get("fine_tune_iter"))
        total = _int_or_none(session.get("fine_tune_total"))
    else:
        return None

    percent = None
    if current is not None and total and total > 0:
        percent = round(min(max(current, 0), total) / total * 100.0, 2)

    last_losses = session.get("last_losses") if isinstance(session.get("last_losses"), dict) else {}
    return {
        "phase": phase,
        "tool": tool,
        "label": label,
        "current": current,
        "total": total,
        "percent": percent,
        "running": phase in {"curriculum", "fine_tune"},
        "source": str(_session_path(root).relative_to(root)) if _session_path(root).is_relative_to(root) else str(_session_path(root)),
        "last_losses": last_losses,
    }


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_json_dict(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_session_phase(root: Path) -> str:
    return str(_load_json_dict(_session_path(root)).get("phase") or "")


def _load_session_params(root: Path) -> dict[str, Any]:
    data = _load_json_dict(_session_path(root)).get("params")
    return data if isinstance(data, dict) else {}


def _session_path(root: Path) -> Path:
    return root / "engines" / "deeplens" / "session.json"


def _zemax_status(metrics: dict[str, Any], report: dict[str, Any]) -> str:
    status = str(metrics.get("zemax_status") or report.get("status") or "").strip().lower()
    if status in {"complete", "unavailable", "failed", "skipped"}:
        return status
    if metrics.get("zemax_ok") is True or report.get("ok") is True:
        return "complete"
    if metrics.get("zemax_ok") is False or report.get("ok") is False:
        return "unavailable"
    return "pending"


def _zemax_status_label(status: str) -> str:
    return {
        "complete": "OpticStudio verification complete",
        "unavailable": "OpticStudio verification unavailable",
        "failed": "OpticStudio verification failed",
        "skipped": "OpticStudio verification skipped",
        "pending": "OpticStudio verification pending",
    }.get(status, "OpticStudio verification pending")


def _preview_fov_deg(metric_map: dict[str, Any]) -> float | None:
    value = metric_map.get("deeplens_fov_deg") or metric_map.get("fov_deg")
    if value in (None, ""):
        half_fov = metric_map.get("rfov_deg")
        if half_fov in (None, ""):
            return None
        value = float(half_fov) * 2.0
    return float(value)


def _preview_fnum(
    metric_map: dict[str, Any],
    final_data: dict[str, Any],
    starting_data: dict[str, Any],
) -> Any:
    for value in (
        metric_map.get("deeplens_fnum"),
        final_data.get("fnum"),
        metric_map.get("fnum"),
        starting_data.get("fnum"),
    ):
        if value not in (None, ""):
            return value
    return None


def _format_value(value: Any, suffix: str = "", digits: int = 2) -> str:
    if value in (None, ""):
        return "-"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{numeric:.{digits}f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"
