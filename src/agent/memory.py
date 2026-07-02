from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from agent.llm import OpenAIExtractor
from agent.settings import AgentInput, AgentResult
from subagents.types import public_params_dict


LESSON_DOMAINS = {
    "seed_selection": "初始结构选择经验",
    "optimization": "DeepLens 优化经验",
    "final_review": "整体验证与通用镜头经验",
}


def run_memory_update(
    runtime: Any,
    ctx: Any,
    *,
    label: str,
    update: Callable[[], None],
) -> bool:
    try:
        update()
    except BaseException as exc:  # pragma: no cover - defensive boundary
        _emit_memory_skip(runtime, ctx, exc)
        return False
    return True


def _emit_memory_skip(runtime: Any, ctx: Any, error: Any) -> None:
    emit = getattr(runtime, "emit_event", None)
    if callable(emit):
        emit(ctx, "workflow.memory.skipped", error=error)


def _raw_markdown_response(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if _looks_like_lesson_markdown(text):
        return text
    return None


def _looks_like_lesson_markdown(text: str) -> bool:
    return ("#" in text and "\n-" in text) or text.startswith("- ")


class AgentMemory:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.design_runs_dir = root / "designrun"
        self.project_memory_file = root / "project.md"
        self.lessons_dir = root / "lessons"
        self.root.mkdir(parents=True, exist_ok=True)
        self._ensure_project_memory()
        self._ensure_markdown_lesson_files()
        self.extractor = OpenAIExtractor()

    def create_snapshot(self, request: AgentInput | None = None, params: Any | None = None) -> dict[str, Any]:
        return {
            "timeline": [],
            "project_memory": self.load_project_memory(),
            "current_task": self._task_memory(request, params),
            "recent_design_runs": self.load_recent_design_runs(limit=3, compact=True),
            "seed_selection_lessons": self.load_markdown_lessons("seed_selection"),
            "optimization_lessons": self.load_markdown_lessons("optimization"),
            "final_review_lessons": self.load_markdown_lessons("final_review"),
        }

    def refresh_task_context(
        self,
        snapshot: dict[str, Any],
        request: AgentInput,
        params: Any | None,
    ) -> None:
        snapshot["current_task"] = self._task_memory(request, params)
        snapshot["seed_selection_lessons"] = self.load_markdown_lessons("seed_selection")
        snapshot["optimization_lessons"] = self.load_markdown_lessons("optimization")
        snapshot["final_review_lessons"] = self.load_markdown_lessons("final_review")

    @staticmethod
    def _read_json_files(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []

        rows: list[dict[str, Any]] = []
        for item in sorted(path.glob("*.json")):
            try:
                rows.append(json.loads(item.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return rows

    @staticmethod
    def _write_pretty_json(path: Path, row: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _ensure_project_memory(self) -> None:
        if self.project_memory_file.exists():
            return
        self.project_memory_file.write_text(
            "\n".join(
                [
                    "# LensBot Project Memory",
                    "",
                    "## Role",
                    "",
                    "- Design and optimize optical lens systems with workflow-level planning and pi-backed optimization control.",
                    "",
                    "## Tool Boundaries",
                    "",
                    "- Algorithm engines live under `src/engine`.",
                    "- Tool adapters live under `src/tools` and are registered through the unified tool registry.",
                    "- UI should stay mostly independent from workflow internals.",
                    "",
                    "## Optical Design Priorities",
                    "",
                    "- Preserve explicit user targets for EFL, FOV, F-number, BFL, total length, and sensor size.",
                    "- Treat large drift in EFL/FOV/F-number as a design failure even when spot metrics improve.",
                    "- Prefer reusable optical lessons over single-run summaries.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def load_project_memory(self) -> str:
        try:
            return self.project_memory_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def load_markdown_lessons(self, domain: str) -> str:
        path = self._markdown_lesson_path(domain)
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def record_seed_selection_lessons(
        self,
        *,
        request: AgentInput,
        params: Any | None,
        references: list[dict[str, Any]],
        seed_candidates: list[Any],
    ) -> None:
        context = {
            "request": {"mode": request.mode, "prompt": request.prompt},
            "target": self._target_summary(params),
            "selected_references": [item for item in references if item.get("selected")][:3],
            "references": references[:8],
            "seed_candidates": [self._candidate_memory(item) for item in seed_candidates[:8]],
        }
        self._rewrite_markdown_lessons(
            domain="seed_selection",
            context=context,
            instruction=(
                "Update durable seed-selection experience. Keep lessons as short Markdown bullets "
                "about lens family choice, native first-order proximity, stop placement, surface "
                "complexity, and DeepLens-compatible starting structures."
            ),
        )

    def record_optimization_lessons(
        self,
        *,
        request: AgentInput,
        params: Any | None,
        seed_candidates: list[Any],
        design_result: dict[str, Any],
        metrics: dict[str, Any],
        agent_trace: list[dict[str, Any]],
    ) -> None:
        context = {
            "request": {"mode": request.mode, "prompt": request.prompt},
            "target": self._target_summary(params),
            "seed_candidates": [self._candidate_memory(item) for item in seed_candidates[:6]],
            "design_result": self._artifact_presence(design_result),
            "metrics": self._compact_metrics(metrics),
            "optimization_trace_tail": self._compact_trace(agent_trace, limit=24),
        }
        self._rewrite_markdown_lessons(
            domain="optimization",
            context=context,
            instruction=(
                "Update durable DeepLens optimization experience. Focus on seed characteristics, metric drift, "
                "continue/stop/retry signals, strategy-tool choices, budget choices, and visible tool failures. "
                "Do not recommend hidden optimizer internals, loss constants, or schedules that are not exposed "
                "to the workflow."
            ),
        )

    def record_final_review_lessons(
        self,
        *,
        request: AgentInput,
        params: Any | None,
        result: AgentResult,
        metrics: dict[str, Any],
        references: list[dict[str, Any]],
        accepted: bool,
        issues: list[str],
    ) -> None:
        context = {
            "request": {"mode": request.mode, "prompt": request.prompt},
            "target": self._target_summary(params),
            "run_summary": result.summary,
            "artifacts": self._result_artifact_presence(result),
            "references": references[:5],
            "accepted": accepted,
            "issues": issues,
            "metrics": self._compact_metrics(metrics),
            "final_structure": self._surface_summary(self._safe_read_json(result.final_json)),
        }
        self._rewrite_markdown_lessons(
            domain="final_review",
            context=context,
            instruction=(
                "Update durable post-run optical design experience. Extract general lessons from the whole "
                "completed workflow after final analysis and report archival: seed choice, optimization behavior, "
                "DeepLens-only evidence, Zemax-verified evidence, Zemax-unavailable caveats, lens-type "
                "characteristics, and final acceptance failures. This is not a Zemax report summary; write broad "
                "guidance useful before future seed selection and optimization."
            ),
        )

    @staticmethod
    def _make_entry_id(result: AgentResult) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        outcome = "success" if result.ok else "failure"
        return f"run-{stamp}-{outcome}"

    @staticmethod
    def _safe_read_json(path_str: str | None) -> dict[str, Any] | None:
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _surface_summary(lens_json: dict[str, Any] | None) -> dict[str, Any] | None:
        if not lens_json:
            return None

        surfaces = lens_json.get("surfaces", [])
        types = [surface.get("type", "Unknown") for surface in surfaces]
        materials = []
        for surface in surfaces:
            mat2 = surface.get("mat2")
            if isinstance(mat2, str):
                materials.append(mat2)

        return {
            "surface_count": len(surfaces),
            "surface_types": types,
            "surface_signature": " -> ".join(types),
            "materials": materials,
        }

    @staticmethod
    def _result_paths(result: AgentResult) -> dict[str, Any]:
        return {
            "result_dir": result.result_dir,
            "curriculum_json": result.curriculum_json,
            "final_json": result.final_json,
            "final_zmx": result.final_zmx,
            "summary_report_file": result.summary_report_file,
            "log_file": result.log_file,
            "metrics_file": result.metrics_file,
        }

    @staticmethod
    def _artifact_presence(design_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "has_result_dir": bool(design_result.get("result_dir")),
            "has_curriculum_json": bool(design_result.get("curriculum_json")),
            "has_analysis_json": bool(design_result.get("analysis_json")),
            "has_final_json": bool(design_result.get("final_json")),
            "has_final_zmx": bool(design_result.get("final_zmx")),
        }

    @staticmethod
    def _result_artifact_presence(result: AgentResult) -> dict[str, Any]:
        return {
            "has_result_dir": bool(result.result_dir),
            "has_curriculum_json": bool(result.curriculum_json),
            "has_final_json": bool(result.final_json),
            "has_final_zmx": bool(result.final_zmx),
            "has_summary_report": bool(result.summary_report_file),
            "has_metrics_file": bool(result.metrics_file),
        }

    def _task_memory(self, request: AgentInput | None, params: Any | None) -> dict[str, Any]:
        return {
            "request": {
                "mode": request.mode if request else None,
                "prompt": request.prompt if request else None,
            },
            "target": self._target_summary(params or (request.params if request and request.params else None)),
        }

    @staticmethod
    def _target_summary(params: Any | None) -> dict[str, Any] | None:
        if params is None:
            return None
        return {
            "foclen": getattr(params, "foclen", None),
            "fov": getattr(params, "fov", None),
            "fnum": getattr(params, "fnum", None),
            "bfl": getattr(params, "bfl", None),
            "thickness": getattr(params, "thickness", None),
            "surf_list": getattr(params, "surf_list", None),
            "curriculum_iterations": getattr(getattr(params, "curriculum", None), "iterations", None),
            "fine_tune_iterations": getattr(getattr(params, "fine_tune", None), "iterations", None),
        }

    @staticmethod
    def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "deeplens_efl_mm",
            "zemax_efl_mm",
            "fnum",
            "zemax_fnum",
            "deeplens_fov_deg",
            "zemax_fov_deg",
            "spot_rms_um_edge",
            "zemax_spot_rms_edge_um",
            "distortion_pct_edge",
            "zemax_distortion_pct_edge",
            "mtf50_edge_tan_cy_mm",
            "zemax_mtf50_edge_tan_cy_mm",
            "zemax_ok",
            "acceptance",
        ]
        return {key: metrics.get(key) for key in keys if key in metrics}

    def _compact_run_memory(self, row: dict[str, Any]) -> dict[str, Any]:
        outcome = row.get("outcome", {})
        structures = row.get("optimized_structures", {})
        return {
            "entry_id": row.get("entry_id"),
            "timestamp": row.get("timestamp"),
            "request": row.get("request", {}),
            "target": self._target_summary_dict(row.get("design_params")),
            "ok": outcome.get("ok"),
            "summary": outcome.get("summary"),
            "metrics": self._compact_metrics(outcome.get("metrics", {})),
            "final_structure": structures.get("final_summary"),
        }

    @staticmethod
    def _target_summary_dict(params: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(params, dict):
            return None
        return {
            "foclen": params.get("foclen"),
            "fov": params.get("fov"),
            "fnum": params.get("fnum"),
            "bfl": params.get("bfl"),
            "thickness": params.get("thickness"),
            "surf_list": params.get("surf_list"),
        }

    def record_design_run(
        self,
        request: AgentInput,
        result: AgentResult,
        params: Any | None = None,
    ) -> None:
        design_params = public_params_dict(params) if params is not None else public_params_dict(request.params)
        curriculum_json = self._safe_read_json(result.curriculum_json)
        final_json = self._safe_read_json(result.final_json)
        row = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "request": {
                "mode": request.mode,
                "prompt": request.prompt,
            },
            "design_params": design_params,
            "outcome": {
                "ok": result.ok,
                "summary": result.summary,
                "metrics": result.metrics,
                "references": result.references,
                "paths": self._result_paths(result),
            },
            "optimized_structures": {
                "curriculum_summary": self._surface_summary(curriculum_json),
                "final_summary": self._surface_summary(final_json),
                "curriculum_lens": curriculum_json,
                "final_lens": final_json,
            },
        }
        entry_id = self._make_entry_id(result)
        row["entry_id"] = entry_id
        self._write_pretty_json(self.design_runs_dir / f"{entry_id}.json", row)

    def load_recent_design_runs(self, limit: int = 5, *, compact: bool = False) -> list[dict[str, Any]]:
        rows = self._read_json_files(self.design_runs_dir)[-limit:]
        if not compact:
            return rows
        return [self._compact_run_memory(row) for row in rows]

    def _ensure_markdown_lesson_files(self) -> None:
        for domain, title in LESSON_DOMAINS.items():
            path = self._markdown_lesson_path(domain)
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "\n".join(
                    [
                        f"# {title}",
                        "",
                        "这些条目是跨项目复用的工程经验，不是单次运行日志。",
                        "请把经验写成短句，保留适用条件，并在新证据出现时修正旧条目。",
                        "",
                        "## 经验条目",
                        "",
                        "- 暂无稳定经验。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

    def _markdown_lesson_path(self, domain: str) -> Path:
        if domain not in LESSON_DOMAINS:
            raise ValueError(f"Unknown lesson domain: {domain}")
        return self.lessons_dir / f"{domain}.md"

    def _rewrite_markdown_lessons(self, *, domain: str, context: dict[str, Any], instruction: str) -> None:
        path = self._markdown_lesson_path(domain)
        current = self.load_markdown_lessons(domain)
        payload = {
            "task": "rewrite_markdown_engineering_lessons",
            "domain": domain,
            "domain_title": LESSON_DOMAINS[domain],
            "rules": [
                "Return exactly one JSON object with a markdown string field.",
                "Rewrite the whole Markdown file, preserving useful old lessons and revising them when new evidence contradicts them.",
                "Keep the file concise: prefer 6-14 bullets total.",
                "Write lessons as reusable engineering experience, not as one-off project reports.",
                "Prefer conditional lessons in the form `When ..., prefer/avoid ...` whenever evidence supports a condition.",
                "Separate confirmed lessons from weak signals; preserve existing lessons when the new evidence is weak.",
                "Do not include run IDs, artifact paths, timestamps, absolute paths, raw JSON, tables, run logs, or long numeric dumps.",
                "Use Markdown headings and bullet points only.",
            ],
            "current_markdown": current,
            "new_evidence": context,
        }
        system_prompt = "\n".join(
            [
                "You maintain LensBot's reusable optical engineering memory.",
                instruction,
                "Good style example: Double Gauss 类结构对中等 FOV、标准焦段更稳，但后组 asphere 可优化自由度更关键。",
                "The Markdown must stay directly useful to the next workflow agent.",
            ]
        )
        result = self.extractor.extract_json(json.dumps(payload, ensure_ascii=False, indent=2), system_prompt)
        markdown = result.get("markdown") if isinstance(result, dict) else None
        if not isinstance(markdown, str) or not markdown.strip():
            markdown = _raw_markdown_response(getattr(self.extractor, "last_content", ""))
        if not isinstance(markdown, str) or not markdown.strip():
            error = str(getattr(self.extractor, "last_error", "") or "").strip()
            suffix = f": {error}" if error else ""
            logging.warning("%s lessons were not updated because LLM markdown rewrite failed%s.", domain, suffix)
            return
        path.write_text(markdown.strip() + "\n", encoding="utf-8")

    @staticmethod
    def _candidate_memory(candidate: Any) -> dict[str, Any]:
        return {
            "candidate_id": getattr(candidate, "candidate_id", None),
            "case_id": getattr(candidate, "case_id", None),
            "title": getattr(candidate, "title", None),
            "category": getattr(candidate, "category", None),
            "reasons": getattr(candidate, "reasons", []),
            "risks": getattr(candidate, "risks", []),
            "applied": getattr(candidate, "applied", None),
            "inspected": getattr(candidate, "inspected", None),
        }

    @staticmethod
    def _compact_trace(agent_trace: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        rows = agent_trace[-limit:]
        compact: list[dict[str, Any]] = []
        for row in rows:
            tool_call = row.get("tool_call") if isinstance(row.get("tool_call"), dict) else {}
            tool_result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
            compact.append(
                {
                    "agent": row.get("agent"),
                    "turn": row.get("turn"),
                    "thought": row.get("thought"),
                    "action": tool_call.get("name") or row.get("action"),
                    "observation": row.get("observation"),
                    "ok": tool_result.get("ok"),
                    "error": tool_result.get("error"),
                }
            )
        return compact

