from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.llm import OpenAIExtractor
from agent.settings import AgentInput, AgentResult


class AgentMemory:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.design_runs_dir = root / "designrun"
        self.project_memory_file = root / "project.md"
        self.engineering_lessons_index = root / "lessons.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self._ensure_project_memory()
        self._ensure_lessons_store()
        self.extractor = OpenAIExtractor()

    def create_snapshot(self, request: AgentInput | None = None, params: Any | None = None) -> dict[str, Any]:
        return {
            "timeline": [],
            "project_memory": self.load_project_memory(),
            "current_task": self._task_memory(request, params),
            "recent_design_runs": self.load_recent_design_runs(limit=3, compact=True),
            "relevant_engineering_lessons": self.load_relevant_lessons(request, params, limit=6),
            "recent_engineering_lessons": self.load_recent_lessons(limit=3),
        }

    def refresh_task_context(
        self,
        snapshot: dict[str, Any],
        request: AgentInput,
        params: Any | None,
    ) -> None:
        snapshot["current_task"] = self._task_memory(request, params)
        snapshot["relevant_engineering_lessons"] = self.load_relevant_lessons(request, params, limit=6)

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
                    "- Design and optimize optical lens systems with workflow-level planning and node-level agent loops.",
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
        design_params = asdict(params) if params is not None else (asdict(request.params) if request.params else None)
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

    def record_engineering_lesson(
        self,
        request: AgentInput,
        result: AgentResult,
        params: Any | None = None,
        *,
        system_prompt: str = "",
    ) -> None:
        lesson = self._summarize_engineering_lesson(request, result, params=params, system_prompt=system_prompt)
        if not lesson:
            logging.warning("Engineering lesson was not written because LLM summarization failed.")
            return
        self._upsert_engineering_lesson(lesson, result=result)

    def load_recent_design_runs(self, limit: int = 5, *, compact: bool = False) -> list[dict[str, Any]]:
        rows = self._read_json_files(self.design_runs_dir)[-limit:]
        if not compact:
            return rows
        return [self._compact_run_memory(row) for row in rows]

    def load_recent_lessons(self, limit: int = 10) -> list[dict[str, Any]]:
        library = self._read_lessons_library()
        entries = sorted(
            library.get("entries", []),
            key=lambda item: item.get("updated_at") or item.get("created_at") or "",
        )
        recent = entries[-limit:]
        return [
            {
                "title": entry.get("title", ""),
                "content": self._render_lesson_summary(entry).strip(),
                "topic_key": entry.get("topic_key", ""),
                "category": entry.get("category", ""),
                "revision_count": entry.get("revision_count", 1),
                "updated_at": entry.get("updated_at"),
            }
            for entry in recent
        ]

    def load_relevant_lessons(
        self,
        request: AgentInput | None,
        params: Any | None,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        entries = self._read_lessons_library().get("entries", [])
        if not entries:
            return []

        query_terms = self._memory_query_terms(request, params)
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for entry in entries:
            text = self._lesson_search_text(entry)
            score = sum(1 for term in query_terms if term and term in text)
            score += self._param_relevance_score(entry, params)
            updated_at = str(entry.get("updated_at") or entry.get("created_at") or "")
            if score > 0:
                scored.append((score, updated_at, entry))

        if not scored:
            recent = sorted(entries, key=lambda item: item.get("updated_at") or item.get("created_at") or "")[-limit:]
            return [self._compact_lesson_memory(entry) for entry in recent]

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [self._compact_lesson_memory(entry) for _, _, entry in scored[:limit]]

    def _summarize_engineering_lesson(
        self,
        request: AgentInput,
        result: AgentResult,
        params: Any | None = None,
        *,
        system_prompt: str,
    ) -> dict[str, Any] | None:
        final_json = self._safe_read_json(result.final_json)
        existing_lessons = [
            {
                "topic_key": entry.get("topic_key"),
                "title": entry.get("title"),
                "category": entry.get("category"),
                "lesson": entry.get("lesson"),
                "signals": entry.get("signals", []),
                "guidance": entry.get("guidance", []),
                "revision_count": entry.get("revision_count", 1),
            }
            for entry in self._read_lessons_library().get("entries", [])
        ]
        lesson_context = {
            "task": "extract_reusable_engineering_lesson",
            "request": {
                "mode": request.mode,
                "prompt": request.prompt,
            },
            "design_params": asdict(params) if params is not None else (asdict(request.params) if request.params else None),
            "result": {
                "ok": result.ok,
                "summary": result.summary,
                "metrics": result.metrics,
                "paths": self._result_paths(result),
            },
            "final_structure": self._surface_summary(final_json),
            "existing_lessons": existing_lessons,
        }
        lesson = self.extractor.extract_json(
            json.dumps(lesson_context, ensure_ascii=False, indent=2),
            system_prompt,
        )
        if isinstance(lesson, dict):
            return lesson
        return None

    def _ensure_lessons_store(self) -> None:
        if self.engineering_lessons_index.exists():
            return

        entries = self._migrate_legacy_lessons()
        self._write_lessons_library({"version": 1, "entries": entries})

    def _migrate_legacy_lessons(self) -> list[dict[str, Any]]:
        legacy_notes = self.root / "lessons" / "notes.md"
        if not legacy_notes.exists():
            return []

        lines = legacy_notes.read_text(encoding="utf-8").splitlines()
        sections: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            if line.startswith("## "):
                if current:
                    sections.append(current)
                current = [line]
            elif current:
                current.append(line)
        if current:
            sections.append(current)

        migrated: list[dict[str, Any]] = []
        for idx, section in enumerate(sections, start=1):
            title_line = section[0][3:].strip()
            title = title_line.split("|", 1)[-1].strip() if "|" in title_line else title_line
            lesson_text = self._extract_markdown_section(section, "Lesson")
            signals = self._extract_markdown_list(section, "Signals")
            guidance = self._extract_markdown_list(section, "Guidance")
            topic_key = self._slugify(title) or f"legacy-note-{idx}"
            migrated.append(
                {
                    "id": topic_key,
                    "topic_key": topic_key,
                    "title": title or f"Legacy note {idx}",
                    "category": "legacy",
                    "lesson": lesson_text or "Legacy lesson migrated from notes.md.",
                    "applicability": [],
                    "signals": signals,
                    "guidance": guidance,
                    "parameter_hints": [],
                    "anti_patterns": [],
                    "source_run_ids": [],
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "revision_count": 1,
                }
            )
        return migrated

    @staticmethod
    def _extract_markdown_section(lines: list[str], heading: str) -> str:
        capture = False
        content: list[str] = []
        for line in lines[1:]:
            if line.startswith("### "):
                capture = line[4:].strip() == heading
                continue
            if capture and line.strip():
                content.append(line.strip())
        return " ".join(content).strip()

    @staticmethod
    def _extract_markdown_list(lines: list[str], heading: str) -> list[str]:
        capture = False
        content: list[str] = []
        for line in lines[1:]:
            if line.startswith("### "):
                capture = line[4:].strip() == heading
                continue
            if capture and line.strip().startswith("- "):
                content.append(line.strip()[2:].strip())
        return content

    def _read_lessons_library(self) -> dict[str, Any]:
        if not self.engineering_lessons_index.exists():
            return {"version": 1, "entries": []}
        try:
            data = json.loads(self.engineering_lessons_index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "entries": []}
        if not isinstance(data, dict):
            return {"version": 1, "entries": []}
        entries = data.get("entries")
        if not isinstance(entries, list):
            data["entries"] = []
        if "version" not in data:
            data["version"] = 1
        return data

    def _write_lessons_library(self, row: dict[str, Any]) -> None:
        self._write_pretty_json(self.engineering_lessons_index, row)

    def _upsert_engineering_lesson(
        self,
        lesson: dict[str, Any],
        *,
        result: AgentResult | None,
    ) -> None:
        normalized = self._normalize_lesson_entry(lesson)
        if not normalized:
            return
        if not normalized["should_record"]:
            return

        library = self._read_lessons_library()
        entries = library.get("entries", [])
        topic_key = normalized["topic_key"]
        now = datetime.now().isoformat(timespec="seconds")
        source_ref = self._lesson_source_ref(result)

        existing = next((entry for entry in entries if entry.get("topic_key") == topic_key), None)
        if existing:
            existing["title"] = normalized["title"] or existing.get("title", "")
            existing["category"] = normalized["category"] or existing.get("category", "")
            existing["lesson"] = normalized["lesson"] or existing.get("lesson", "")
            for field in ("applicability", "signals", "guidance", "parameter_hints", "anti_patterns"):
                existing[field] = self._merge_unique_strings(existing.get(field, []), normalized.get(field, []))
            existing["updated_at"] = now
            existing["revision_count"] = int(existing.get("revision_count", 1)) + 1
            existing["source_run_ids"] = self._merge_unique_strings(existing.get("source_run_ids", []), [source_ref] if source_ref else [])
        else:
            entries.append(
                {
                    "id": topic_key,
                    "topic_key": topic_key,
                    "title": normalized["title"],
                    "category": normalized["category"],
                    "lesson": normalized["lesson"],
                    "applicability": normalized["applicability"],
                    "signals": normalized["signals"],
                    "guidance": normalized["guidance"],
                    "parameter_hints": normalized["parameter_hints"],
                    "anti_patterns": normalized["anti_patterns"],
                    "source_run_ids": [source_ref] if source_ref else [],
                    "created_at": now,
                    "updated_at": now,
                    "revision_count": 1,
                }
            )

        entries.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "")
        library["version"] = 1
        library["entries"] = entries
        self._write_lessons_library(library)

    @staticmethod
    def _render_lesson_summary(entry: dict[str, Any]) -> str:
        title = entry.get("title", "Untitled lesson")
        lesson = str(entry.get("lesson", "")).strip()
        signals = AgentMemory._coerce_string_list(entry.get("signals"))[:2]
        guidance = AgentMemory._coerce_string_list(entry.get("guidance"))[:2]

        lines = [f"{title}: {lesson}"]
        if signals:
            lines.append("Signals: " + "; ".join(signals))
        if guidance:
            lines.append("Guidance: " + "; ".join(guidance))
        return "\n".join(lines)

    def _compact_lesson_memory(self, entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "topic_key": entry.get("topic_key", ""),
            "title": entry.get("title", ""),
            "category": entry.get("category", ""),
            "lesson": entry.get("lesson", ""),
            "applicability": self._coerce_string_list(entry.get("applicability"))[:3],
            "signals": self._coerce_string_list(entry.get("signals"))[:4],
            "guidance": self._coerce_string_list(entry.get("guidance"))[:4],
            "parameter_hints": self._coerce_string_list(entry.get("parameter_hints"))[:3],
            "anti_patterns": self._coerce_string_list(entry.get("anti_patterns"))[:3],
            "updated_at": entry.get("updated_at"),
            "revision_count": entry.get("revision_count", 1),
        }

    def _memory_query_terms(self, request: AgentInput | None, params: Any | None) -> set[str]:
        text = " ".join(
            [
                str(request.prompt or "") if request else "",
                str(getattr(params, "surf_list", "")),
            ]
        ).lower()
        terms = {
            token.strip(" ,.;:()[]{}<>/\\|").lower()
            for token in text.replace("_", " ").replace("-", " ").split()
            if len(token.strip(" ,.;:()[]{}<>/\\|")) >= 3
        }
        if params is not None:
            fov = self._as_float(getattr(params, "fov", None))
            fnum = self._as_float(getattr(params, "fnum", None))
            bfl = self._as_float(getattr(params, "bfl", None))
            thickness = self._as_float(getattr(params, "thickness", None))
            foclen = self._as_float(getattr(params, "foclen", None))
            if fov is not None:
                terms.add("wide") if fov >= 60 else terms.add("narrow")
                terms.add("fov")
            if fnum is not None:
                terms.add("fast") if fnum <= 2.8 else terms.add("slow")
                terms.add("fnum")
            if bfl is not None:
                terms.add("bfl")
                if foclen and bfl / max(abs(foclen), 1e-9) < 0.35:
                    terms.add("short")
                if thickness and bfl / max(abs(thickness), 1e-9) > 0.3:
                    terms.add("long")
            if thickness is not None and foclen:
                terms.add("compact") if thickness / max(abs(foclen), 1e-9) < 0.8 else terms.add("long")
        return terms

    def _param_relevance_score(self, entry: dict[str, Any], params: Any | None) -> int:
        if params is None:
            return 0
        text = self._lesson_search_text(entry)
        score = 0
        fov = self._as_float(getattr(params, "fov", None))
        fnum = self._as_float(getattr(params, "fnum", None))
        bfl = self._as_float(getattr(params, "bfl", None))
        thickness = self._as_float(getattr(params, "thickness", None))
        foclen = self._as_float(getattr(params, "foclen", None))
        if fov is not None and fov >= 60 and any(term in text for term in ("wide", "广角", "fov", "视场")):
            score += 2
        if fnum is not None and fnum <= 2.8 and any(term in text for term in ("fast", "高速", "f/", "f数")):
            score += 2
        if bfl is not None and any(term in text for term in ("bfl", "后焦", "后截距")):
            score += 1
        if foclen and thickness and thickness / max(abs(foclen), 1e-9) < 0.8 and any(
            term in text for term in ("compact", "紧凑", "telephoto", "远摄")
        ):
            score += 2
        return score

    @staticmethod
    def _lesson_search_text(entry: dict[str, Any]) -> str:
        chunks = [
            entry.get("topic_key", ""),
            entry.get("title", ""),
            entry.get("category", ""),
            entry.get("lesson", ""),
            " ".join(AgentMemory._coerce_string_list(entry.get("applicability"))),
            " ".join(AgentMemory._coerce_string_list(entry.get("signals"))),
            " ".join(AgentMemory._coerce_string_list(entry.get("guidance"))),
            " ".join(AgentMemory._coerce_string_list(entry.get("parameter_hints"))),
            " ".join(AgentMemory._coerce_string_list(entry.get("anti_patterns"))),
        ]
        return " ".join(str(chunk) for chunk in chunks).lower()

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _lesson_source_ref(result: AgentResult | None) -> str | None:
        if result is None:
            return None
        if result.result_dir:
            return Path(result.result_dir).name
        if result.metrics_file:
            return Path(result.metrics_file).stem
        return None

    @staticmethod
    def _merge_unique_strings(existing: list[Any], new_values: list[Any]) -> list[str]:
        merged: list[str] = []
        for value in [*existing, *new_values]:
            item = str(value).strip()
            if item and item not in merged:
                merged.append(item)
        return merged

    @staticmethod
    def _slugify(value: str) -> str:
        slug = value.strip().lower()
        slug = "".join(ch if ("a" <= ch <= "z") or ("0" <= ch <= "9") else "-" for ch in slug)
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug.strip("-")

    def _normalize_lesson_entry(self, lesson: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(lesson, dict):
            return None
        topic_key = self._slugify(str(lesson.get("topic_key", "")))
        title = str(lesson.get("title", "")).strip()
        category = str(lesson.get("category", "")).strip() or "general"
        normalized = {
            "should_record": bool(lesson.get("should_record", True)),
            "action": str(lesson.get("action", "create")).strip().lower(),
            "topic_key": topic_key,
            "title": title,
            "category": category,
            "lesson": str(lesson.get("lesson", "")).strip(),
            "applicability": self._coerce_string_list(lesson.get("applicability")),
            "signals": self._coerce_string_list(lesson.get("signals")),
            "guidance": self._coerce_string_list(lesson.get("guidance")),
            "parameter_hints": self._coerce_string_list(lesson.get("parameter_hints")),
            "anti_patterns": self._coerce_string_list(lesson.get("anti_patterns")),
        }
        if normalized["action"] not in {"create", "update", "skip"}:
            normalized["action"] = "create"
        if normalized["action"] == "skip":
            normalized["should_record"] = False
        if not normalized["topic_key"]:
            normalized["topic_key"] = self._slugify(title) or f"lesson-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        if not normalized["title"]:
            normalized["title"] = normalized["topic_key"].replace("-", " ").title()
        return normalized

    @staticmethod
    def _coerce_string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]
