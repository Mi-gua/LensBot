from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from agent.llm import OpenAIExtractor
from agent.settings import LensDesignParams
from agent.tools import ToolContext, ToolResult


class CaseTool:
    """Select and learn from local ZEMAX cases to seed DeepLens structures."""

    name = "seed_from_cases"
    description = "Select local ZMX references and seed algorithm parameters."
    category = "general"
    metadata = {"kind": "case_retrieval"}

    _VALID_SURFACES = {"Spheric", "Aspheric", "Aperture", "ThinLens"}
    _DEEPLENS_ARGS = {"foclen", "fov", "fnum", "bfl", "thickness", "surf_list"}
    _CURRICULUM_FIELDS = {
        "lrs",
        "iterations",
        "test_per_iter",
        "optim_mat",
        "match_mat",
        "shape_control",
        "num_ring",
        "num_arm",
        "spp",
        "scale_pupil",
        "aper_start_ratio",
        "weight_dropout",
        "w_focus",
        "w_reg",
    }
    _FINE_TUNE_FIELDS = {
        "lrs",
        "iterations",
        "test_per_iter",
        "centroid",
        "optim_mat",
        "shape_control",
        "num_ring",
        "num_arm",
        "spp",
        "scale_pupil",
        "weight_dropout",
        "w_focus",
        "w_reg",
        "num_warmup_steps",
    }

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.cases_dir = project_root / "cases"
        self.index_path = self.cases_dir / "ZEMAX Index.md"
        self.extractor = OpenAIExtractor()
        self.last_status = "not run"

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        seeded, references = self.seed_params(
            kwargs["params"],
            user_prompt=str(kwargs.get("prompt", "")),
            progress_cb=ctx.progress_cb,
            system_prompt=ctx.system_prompt,
        )
        return ToolResult(True, self.last_status, {"params": seeded, "references": references})

    def seed_params(
        self,
        params: LensDesignParams,
        *,
        user_prompt: str = "",
        progress_cb: Callable[[str], None] | None = None,
        system_prompt: str = "",
    ) -> tuple[LensDesignParams, list[dict[str, Any]]]:
        if not self.index_path.exists():
            self.last_status = f"ZEMAX Index does not exist: {self.index_path}"
            return params, []

        if progress_cb:
            progress_cb("初始结构选择：读取 ZEMAX 索引。")
        entries = self._load_index_entries()
        if not entries:
            self.last_status = "ZEMAX Index did not yield any case entries."
            return params, []
        if progress_cb:
            progress_cb(f"初始结构选择：已读取 {len(entries)} 个案例。")

        selected = self._select_case_with_llm(params, user_prompt, entries, system_prompt=system_prompt)
        if selected is None:
            return params, []
        if progress_cb:
            progress_cb(f"初始结构选择：选择参考案例 {selected['case_id']}。")
            progress_cb("初始结构选择：生成 DeepLens 初始结构。")

        learned = self._learn_params_with_llm(params, user_prompt, selected, system_prompt=system_prompt)

        seeded = deepcopy(params)
        applied = self._apply_proposal(seeded, learned)
        if not learned:
            error = getattr(self.extractor, "last_error", "")
            self.last_status = (
                f"Selected {selected['case_id']}, but the LLM did not return a parseable starting structure."
            )
            if error:
                self.last_status += f": {error}"
        elif not applied:
            self.last_status = (
                f"Selected {selected['case_id']}, but the proposed starting structure failed DeepLens validation."
            )

        return seeded, [
            {
                "source": "local_zemax_case",
                "case_id": selected["case_id"],
                "title": selected["title"],
                "snippet": selected["category"],
                "url": str(selected["path"]),
                "selected": True,
                "applied": applied,
                "selection_rationale": selected.get("rationale", ""),
                "design_rationale": learned.get("rationale", ""),
            }
        ]

    def _select_case_with_llm(
        self,
        params: LensDesignParams,
        user_prompt: str,
        entries: list[dict[str, str]],
        *,
        system_prompt: str,
    ) -> dict[str, Any] | None:
        prompt = json.dumps(
            {
                "task": "select_reference_case",
                "user_request": user_prompt,
                "target": self._target_payload(params),
                "index_markdown": self.index_path.read_text(encoding="utf-8"),
            },
            ensure_ascii=False,
        )
        result = self.extractor.extract_json(prompt, system_prompt)
        if not isinstance(result, dict):
            error = getattr(self.extractor, "last_error", "")
            self.last_status = f"LLM did not return case-selection JSON{f': {error}' if error else ''}"
            return None

        case_id = self._normalize_case_id(result.get("case_id", ""))
        if not case_id:
            self.last_status = "LLM case-selection result did not include a valid case_id."
            return None

        path = self._case_path(case_id)
        if path is None:
            self.last_status = f"LLM selected {case_id}, but no matching .zmx file exists in cases."
            return None

        selected = next((entry for entry in entries if entry["case_id"] == case_id), None)
        if selected is None:
            self.last_status = f"LLM selected {case_id}, but it is not present in ZEMAX Index."
            return None

        self.last_status = f"Selected {case_id}."
        return {**selected, "path": path, "rationale": str(result.get("rationale", ""))}

    def _learn_params_with_llm(
        self,
        params: LensDesignParams,
        user_prompt: str,
        selected: dict[str, Any],
        *,
        system_prompt: str,
    ) -> dict[str, Any]:
        zmx_text = selected["path"].read_text(encoding="utf-8", errors="ignore")
        prompt = json.dumps(
            {
                "task": "propose_deeplens_initialization",
                "user_request": user_prompt,
                "target": self._target_payload(params),
                "selected_case": {
                    "case_id": selected["case_id"],
                    "title": selected["title"],
                    "category": selected["category"],
                },
                "zmx_text": zmx_text,
            },
            ensure_ascii=False,
        )
        return self.extractor.extract_json(prompt, system_prompt) or {}

    def _apply_proposal(self, params: LensDesignParams, proposal: dict[str, Any]) -> bool:
        applied = False
        deeplens_args = proposal.get("deeplens_args", {})
        if not isinstance(deeplens_args, dict):
            deeplens_args = {}

        for key in self._DEEPLENS_ARGS:
            value = deeplens_args.get(key)
            if key == "surf_list":
                surf_list = self._normalize_surf_list(value)
                if surf_list:
                    params.surf_list = surf_list
                    applied = True
            elif isinstance(value, (int, float)) and value > 0:
                setattr(params, key, float(value))
                applied = True

        applied = self._apply_stage(params.curriculum, proposal.get("curriculum"), self._CURRICULUM_FIELDS) or applied
        applied = self._apply_stage(params.fine_tune, proposal.get("fine_tune"), self._FINE_TUNE_FIELDS) or applied
        return applied

    @staticmethod
    def _apply_stage(stage: Any, values: Any, allowed_fields: set[str]) -> bool:
        if not isinstance(values, dict):
            return False

        applied = False
        for key, value in values.items():
            if key not in allowed_fields or not hasattr(stage, key):
                continue
            current = getattr(stage, key)
            if isinstance(current, bool) and isinstance(value, bool):
                setattr(stage, key, value)
                applied = True
            elif isinstance(current, bool):
                continue
            elif isinstance(current, int) and isinstance(value, (int, float)) and value > 0:
                setattr(stage, key, int(value))
                applied = True
            elif isinstance(current, float) and isinstance(value, (int, float)) and value >= 0:
                setattr(stage, key, float(value))
                applied = True
            elif isinstance(current, list) and isinstance(value, list) and all(isinstance(item, (int, float)) for item in value):
                setattr(stage, key, [float(item) for item in value])
                applied = True
        return applied

    def _load_index_entries(self) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        category = ""
        section_note = ""
        for raw_line in self.index_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("## "):
                category = line.removeprefix("## ").strip()
                section_note = ""
                continue
            if category and line and not line.startswith("- ") and not line.startswith("#"):
                section_note = line
                continue
            match = re.match(r"-\s+([A-Z]_\d{3})\s+(.+)$", line)
            if match:
                entries.append(
                    {
                        "case_id": match.group(1),
                        "title": match.group(2).strip(),
                        "category": f"{category}. {section_note}".strip(),
                    }
                )
        return entries

    def _case_path(self, case_id: str) -> Path | None:
        for path in self.cases_dir.glob(f"{case_id}.*"):
            if path.suffix.lower() == ".zmx":
                return path
        return None

    @staticmethod
    def _normalize_case_id(value: Any) -> str:
        match = re.search(r"([A-Za-z]_\d{3})", str(value))
        return match.group(1).upper() if match else ""

    @staticmethod
    def _target_payload(params: LensDesignParams) -> dict[str, Any]:
        return {
            "foclen": params.foclen,
            "fov": params.fov,
            "fnum": params.fnum,
            "bfl": params.bfl,
            "thickness": params.thickness,
            "surf_list": params.surf_list,
            "curriculum": {
                field: getattr(params.curriculum, field)
                for field in sorted(CaseTool._CURRICULUM_FIELDS)
            },
            "fine_tune": {
                field: getattr(params.fine_tune, field)
                for field in sorted(CaseTool._FINE_TUNE_FIELDS)
            },
        }

    @classmethod
    def _normalize_surf_list(cls, value: Any) -> list[list[str]]:
        if not isinstance(value, list):
            return []

        normalized: list[list[str]] = []
        for item in value:
            if item == "Aperture":
                item = ["Aperture"]
            if not isinstance(item, list) or not item:
                return []

            surfaces = [str(surface) for surface in item]
            if any(surface not in cls._VALID_SURFACES for surface in surfaces):
                return []
            if surfaces == ["Aperture"] or surfaces == ["ThinLens"]:
                normalized.append(surfaces)
            elif 2 <= len(surfaces) <= 3 and "Aperture" not in surfaces and "ThinLens" not in surfaces:
                normalized.append(surfaces)
            else:
                return []
        return normalized
