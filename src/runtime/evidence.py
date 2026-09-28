from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 3

_ARCHIVE_KEYS = (
    "analysis_stage",
    "efl_mm",
    "fnum",
    "fov_deg",
    "deeplens_efl_mm",
    "deeplens_fnum",
    "deeplens_fov_deg",
    "deeplens_spot_valid_pct_edge",
    "deeplens_rms_spot_um_center",
    "deeplens_rms_spot_um_edge",
    "deeplens_rms_spot_um_max",
    "deeplens_distortion_pct_edge",
    "deeplens_distortion_pct_abs_max",
    "deeplens_mtf50_center_tan_cy_mm",
    "deeplens_mtf50_center_sag_cy_mm",
    "deeplens_mtf50_edge_tan_cy_mm",
    "deeplens_mtf50_edge_sag_cy_mm",
    "zemax_status",
    "zemax_ok",
    "zemax_efl_mm",
    "zemax_fnum",
    "zemax_real_working_fnum",
    "zemax_fov_deg",
    "zemax_distortion_pct_edge",
    "zemax_distortion_pct_abs_max",
    "zemax_spot_rms_min_um",
    "zemax_spot_rms_edge_um",
    "zemax_spot_rms_max_um",
    "zemax_mtf50_center_tan_cy_mm",
    "zemax_mtf50_center_sag_cy_mm",
    "zemax_mtf50_edge_tan_cy_mm",
    "zemax_mtf50_edge_sag_cy_mm",
    "zemax_geometric_mtf50_center_tan_cy_mm",
    "zemax_geometric_mtf50_center_sag_cy_mm",
    "zemax_geometric_mtf50_edge_tan_cy_mm",
    "zemax_geometric_mtf50_edge_sag_cy_mm",
    "optimization_model_turns",
    "optimization_input_tokens",
    "optimization_output_tokens",
    "optimization_cache_read_tokens",
    "optimization_cache_write_tokens",
    "optimization_total_tokens",
    "reporting_input_tokens",
    "reporting_output_tokens",
    "reporting_total_tokens",
    "reporting_error",
)


def build_result_evidence(
    result_dir: str | Path,
    metrics: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the canonical, presentation-ready evidence record for one run."""

    root = Path(result_dir)
    metric_map = _metric_values(metrics) if metrics else _load_archived_metrics(root)
    target_map = dict(params or _load_json(root / "workflow" / "intake" / "params.json"))
    final_path = _final_lens_path(root)
    final_lens = _load_json(final_path)
    lens_source_label = "最终结构" if final_path == root / "final" / "final.json" else "最新候选"
    zemax_path = root / "verification" / "zemax" / "zemax_report.json"
    zemax_report = _load_json(zemax_path)
    deeplens_efl = metric_map.get("deeplens_efl_mm") or metric_map.get("efl_mm")
    deeplens_fnum = metric_map.get("deeplens_fnum") or metric_map.get("fnum")

    core = [
        _metric_item(
            "efl_mm",
            "有效焦距",
            "mm",
            target_map.get("foclen"),
            _measurements(
                ("Zemax", metric_map.get("zemax_efl_mm"), _relative(zemax_path, root)),
                ("DeepLens", deeplens_efl, "metrics.json"),
                (lens_source_label, final_lens.get("foclen") if deeplens_efl is None else None, _relative(final_path, root)),
            ),
        ),
        _metric_item(
            "fnum",
            "工作 F 数",
            "",
            target_map.get("fnum"),
            _measurements(
                ("Zemax", metric_map.get("zemax_fnum"), _relative(zemax_path, root)),
                ("DeepLens", deeplens_fnum, "metrics.json"),
                ("最终结构", final_lens.get("fnum") if deeplens_fnum is None else None, _relative(final_path, root)),
            ),
        ),
        _metric_item(
            "fov_deg",
            "全视场",
            "deg",
            target_map.get("fov"),
            _measurements(
                ("Zemax", metric_map.get("zemax_fov_deg"), _relative(zemax_path, root)),
                ("DeepLens", metric_map.get("deeplens_fov_deg") or metric_map.get("fov_deg"), "metrics.json"),
            ),
        ),
        _metric_item(
            "total_track_mm",
            "总长 TTL（输入初值与最终实测）",
            "mm",
            None,
            _measurements(
                ("最终结构", final_lens.get("(d_sensor)"), _relative(final_path, root)),
                ("输入初值", target_map.get("thickness"), "metrics.json"),
            ),
        ),
        _metric_item(
            "back_focal_length_mm",
            "后焦距 BFL（输入初值与最终实测）",
            "mm",
            None,
            _measurements(
                ("最终结构", _back_focal_length(final_lens), _relative(final_path, root)),
                ("输入初值", target_map.get("bfl"), "metrics.json"),
            ),
        ),
    ]

    quality = [
        _metric_item(
            "rms_spot_max_um",
            "最大 RMS 光斑",
            "um",
            None,
            _measurements(
                ("Zemax", metric_map.get("zemax_spot_rms_max_um"), _relative(zemax_path, root)),
                ("DeepLens", metric_map.get("deeplens_rms_spot_um_max"), "metrics.json"),
            ),
        ),
        _metric_item(
            "fft_mtf50_center_tan_cy_mm",
            "中心 FFT MTF50",
            "cy/mm",
            None,
            _measurements(("Zemax", metric_map.get("zemax_mtf50_center_tan_cy_mm"), _relative(zemax_path, root))),
        ),
        _metric_item(
            "fft_mtf50_edge_tan_cy_mm",
            "边缘 FFT MTF50",
            "cy/mm",
            None,
            _measurements(("Zemax", metric_map.get("zemax_mtf50_edge_tan_cy_mm"), _relative(zemax_path, root))),
        ),
        _metric_item(
            "edge_valid_rays_pct",
            "边缘有效光线",
            "%",
            None,
            _measurements(
                ("Zemax", _zemax_edge_valid_pct(zemax_report), _relative(zemax_path, root)),
                ("DeepLens", metric_map.get("deeplens_spot_valid_pct_edge"), "metrics.json"),
            ),
        ),
        _metric_item(
            "distortion_abs_max_pct",
            "最大绝对畸变",
            "%",
            None,
            _measurements(
                ("Zemax", metric_map.get("zemax_distortion_pct_abs_max") or _nested(zemax_report, "grid_distortion", "max_abs_pct"), _relative(zemax_path, root)),
                ("DeepLens", metric_map.get("deeplens_distortion_pct_abs_max"), "metrics.json"),
            ),
        ),
    ]

    sections = [
        {"key": "specification", "title": "核心规格", "items": _present(core)},
        {"key": "image_quality", "title": "成像质量", "items": _present(quality)},
    ]
    evidence_count = sum(len(section["items"]) for section in sections)
    delivery = _delivery_record(root, metric_map)
    verdict = _agent_verdict(metric_map.get("agent_verdict"))
    delivery_prefix = {
        "failed": "产物提交失败；",
        "incomplete": "产物尚不完整；",
    }.get(delivery["status"], "")
    if verdict["status"] == "not_recorded":
        summary = (
            f"{delivery_prefix}已归一记录 {evidence_count} 项去重证据；"
            "该结果未包含结构化 Agent 判断。"
        )
    else:
        summary = f"{delivery_prefix}Agent 判断：{verdict['label']}。{verdict['reason']}"
    return {
        "schema_version": SCHEMA_VERSION,
        "delivery": delivery,
        "verdict": verdict,
        "summary": summary,
        "sections": sections,
        "sources": _sources(root, final_path, zemax_path),
    }


def compact_metrics_archive(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Archive scalar source measurements without transcripts or embedded reports."""

    values = compact_metric_values(metrics)
    delivery = metrics.get("delivery")
    if isinstance(delivery, dict):
        values["delivery"] = delivery
    verdict = metrics.get("agent_verdict")
    if isinstance(verdict, dict):
        values["agent_verdict"] = verdict
    return {
        "schema_version": 4,
        "values": values,
        "evidence_file": "evidence.json",
        "note": "Raw tool output is stored in agents/, events/, engines/, and verification/; it is referenced rather than embedded here.",
    }


def compact_metric_values(metrics: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metrics, Mapping):
        return {}
    return {key: metrics[key] for key in _ARCHIVE_KEYS if key in metrics and _scalar(metrics[key])}


def build_delivery_record(
    final_json: str | Path,
    final_zmx: str | Path,
    *,
    requested_status: str = "",
    source: str = "artifact_inventory",
) -> dict[str, Any]:
    """Describe required-artifact delivery without making an optical-quality verdict."""

    artifacts = {"final_json": Path(final_json), "final_zmx": Path(final_zmx)}
    missing = [name for name, path in artifacts.items() if not path.is_file()]
    status = (
        "failed"
        if requested_status == "failed"
        else ("ready" if not missing else "incomplete")
    )
    return {
        "status": status,
        "label": {
            "ready": "有效产物已提交",
            "incomplete": "产物尚不完整",
            "failed": "产物提交失败",
        }[status],
        "missing_artifacts": missing,
        "source": source,
        "meaning": "仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。",
    }


def _metric_item(
    key: str,
    label: str,
    unit: str,
    target: Any,
    measurements: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not measurements:
        return None
    primary, *supporting = measurements
    target_value = _number(target)
    value = _number(primary.get("value"))
    delta = None
    delta_pct = None
    if target_value not in {None, 0} and value is not None:
        delta = value - target_value
        delta_pct = (value - target_value) / abs(target_value) * 100.0
    return {
        "key": key,
        "label": label,
        "unit": unit,
        "target": target_value,
        "primary": primary,
        "supporting": supporting,
        "delta": round(delta, 8) if delta is not None else None,
        "delta_pct": round(delta_pct, 4) if delta_pct is not None else None,
    }


def _delivery_record(root: Path, metrics: Mapping[str, Any]) -> dict[str, Any]:
    raw = metrics.get("delivery")
    if not isinstance(raw, Mapping):
        raw = {}

    return build_delivery_record(
        root / "final" / "final.json",
        root / "final" / "final.zmx",
        requested_status=str(raw.get("status") or "").strip().lower(),
        source=str(raw.get("source") or "artifact_inventory"),
    )
def _agent_verdict(value: Any) -> dict[str, Any]:
    status = str(value.get("status") or "").strip().lower() if isinstance(value, Mapping) else ""
    if not isinstance(value, Mapping) or status not in {"pass", "fail", "uncertain"}:
        return {
            "status": "not_recorded",
            "label": "未记录 Agent 判断",
            "reason": "结果没有有效的结构化 Agent 判断，系统不从指标或摘要反推结论。",
            "stop_reason": "未记录停止原因。",
            "evidence": [],
            "source": "legacy_result",
        }
    raw_evidence = value.get("evidence")
    evidence = raw_evidence if isinstance(raw_evidence, list) else []
    return {
        "status": status,
        "label": {
            "pass": "结果通过",
            "fail": "结果未通过",
            "uncertain": "暂无法判断",
        }[status],
        "reason": str(value.get("reason") or "Agent 未提供判断理由。"),
        "stop_reason": str(value.get("stop_reason") or "Agent 未提供停止原因。"),
        "evidence": [str(item) for item in evidence if str(item).strip()][:8],
        "source": str(value.get("source") or "optimization_agent"),
    }


def _measurements(*rows: tuple[str, Any, str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for source, raw_value, path in rows:
        value = _number(raw_value)
        if value is None:
            continue
        identity = (source, round(value, 12))
        if identity in seen:
            continue
        seen.add(identity)
        result.append({"source": source, "value": value, "path": path})
    return result


def _present(items: Iterable[dict[str, Any] | None]) -> list[dict[str, Any]]:
    return [item for item in items if item is not None]


def _metric_values(metrics: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metrics, Mapping):
        return {}
    values = metrics.get("values")
    if isinstance(values, dict):
        return dict(values)
    return dict(metrics)


def _load_archived_metrics(root: Path) -> dict[str, Any]:
    return _metric_values(_load_json(root / "metrics.json"))


def _final_lens_path(root: Path) -> Path:
    final_path = root / "final" / "final.json"
    if final_path.is_file():
        return final_path
    candidates = sorted((root / "candidates").glob("candidate-*/lens.json"))
    return candidates[-1] if candidates else final_path


def _back_focal_length(lens: Mapping[str, Any]) -> Any:
    surfaces = lens.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        return None
    last = surfaces[-1]
    return last.get("d_next") if isinstance(last, dict) else None


def _zemax_edge_valid_pct(report: Mapping[str, Any]) -> float | None:
    points = report.get("spot_diagram_points")
    if not isinstance(points, list) or not points:
        return None
    field_numbers = [_number(row.get("field")) for row in points if isinstance(row, dict)]
    edge = max((value for value in field_numbers if value is not None), default=None)
    if edge is None:
        return None
    rows = [row for row in points if isinstance(row, dict) and _number(row.get("field")) == edge]
    requested = sum(_number(row.get("requested_ray_count")) or 0.0 for row in rows)
    valid = sum(_number(row.get("valid_ray_count")) or 0.0 for row in rows)
    return valid / requested * 100.0 if requested else None


def _sources(root: Path, final_path: Path, zemax_path: Path) -> list[dict[str, str]]:
    lens_is_final = final_path == root / "final" / "final.json"
    candidates = (
        (
            "final_lens" if lens_is_final else "candidate_lens",
            "最终镜头结构" if lens_is_final else "最新候选结构",
            final_path,
        ),
        ("zemax_report", "Zemax 独立验证", zemax_path),
        ("metrics", "标量指标归档", root / "metrics.json"),
        ("optimization_trace", "优化审计记录", root / "agents" / "optimization" / "views" / "turns.json"),
    )
    return [
        {"key": key, "label": label, "path": _relative(path, root)}
        for key, label, path in candidates
        if path.is_file()
    ]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _nested(value: Mapping[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return str(path)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


__all__ = [
    "build_delivery_record",
    "build_result_evidence",
    "compact_metric_values",
    "compact_metrics_archive",
]
