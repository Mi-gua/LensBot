from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from agent.llm import OpenAIExtractor
from agent.prompts import workflow_agent_context, workflow_agent_prompt
from runtime.traces import trace_row as _trace_row
from subagents.types import LensDesignParams, SeedCandidate, clone_params, public_params_dict, target_params_dict


class SeedingNode:
    name = "Seeding"

    def __init__(self) -> None:
        self.planner = SeedPlanner()

    def run(self, ctx: Any, runtime: Any) -> None:
        if ctx.params is None:
            ctx.fail("No design parameters are available for seeding.")
            return

        available_tools = runtime.tool_names("retrieve_seed_cases", "read_seed_cases")
        objective = "Select and validate an initial optical seed."
        agent_context = workflow_agent_context(
            agent_name=self.name,
            objective=objective,
            memory=ctx.memory_snapshot,
            params=ctx.params,
            references=ctx.references,
        )
        system_prompt = workflow_agent_prompt(
            self.name,
            objective=objective,
            available_tools=available_tools,
            context=agent_context,
        )
        trace: list[dict[str, Any]] = []

        if not ctx.references:
            result = self._seed_from_references(ctx, runtime, system_prompt)
            trace.append(
                _trace_row(
                    agent=self.name,
                    turn=0,
                    thought=result["thought"],
                    action="retrieve_seed_cases",
                    action_input={"prompt": ctx.request.prompt or "", "target": target_params_dict(ctx.params)},
                    observation=result["observation"],
                    data=result.get("data", {}),
                    done=bool(result.get("done", False)),
                )
            )
        if not trace or not trace[-1].get("done"):
            selected = next((item for item in ctx.references if item.get("selected")), None)
            if selected and selected.get("applied"):
                message = (
                    f"Seed accepted from {selected.get('case_id')} after "
                    f"{len([item for item in ctx.seed_candidates if item.inspected])} candidate inspection(s)."
                )
            elif selected:
                message = (
                    f"Reference {selected.get('case_id')} was inspected but not applied; "
                    f"using current {len(ctx.params.surf_list)} surface groups."
                )
            else:
                message = f"No reference seed applied; using current {len(ctx.params.surf_list)} surface groups."
            trace.append(
                _trace_row(
                    agent=self.name,
                    turn=len(trace),
                    thought="Check whether the selected seed is ready for optimization.",
                    action="confirm_seed",
                    action_input={},
                    observation=message,
                    done=True,
                )
            )

        ctx.agent_trace.extend(trace)
        runtime.record_agent_trace(ctx, trace)
        _record_seed_selection_memory(ctx, runtime)

    def _seed_from_references(self, ctx: Any, runtime: Any, system_prompt: str) -> dict[str, Any]:
        retrieve_result = runtime.registry.call(
            "retrieve_seed_cases",
            ctx=runtime.tool_context(ctx, agent_name=self.name, system_prompt=system_prompt),
        )
        if not retrieve_result.ok:
            return {
                "thought": "Reference retrieval failed.",
                "observation": retrieve_result.message,
                "done": True,
            }

        retrieve_data = retrieve_result.data if isinstance(retrieve_result.data, dict) else {}
        candidates = _seed_candidates_from_payload(retrieve_data.get("candidates", []), ctx.params)
        if not candidates:
            return {
                "thought": "No local reference candidates are available.",
                "observation": "No local ZEMAX seed candidates were available.",
                "done": True,
            }

        selected_ids = self.planner.select_candidates(
            ctx.params,
            user_prompt=ctx.request.prompt or "",
            candidates=candidates,
            system_prompt=system_prompt,
        )
        selected_ids = _fill_candidate_ids(selected_ids, candidates, limit=3)
        selected_candidates = _selected_candidates(candidates, selected_ids)
        runtime.emit_event(
            ctx,
            "seeding.candidates.enter",
            count=len(selected_candidates),
            case_ids=_case_ids_text(selected_candidates),
        )

        selected_seed = deepcopy(ctx.params)
        selected_case_id = ""
        if selected_candidates:
            runtime.emit_event(
                ctx,
                "seeding.cases.reading",
                count=len(selected_candidates),
                case_ids=_case_ids_text(selected_candidates),
            )

        read_result = runtime.registry.call(
            "read_seed_cases",
            ctx=runtime.tool_context(ctx, agent_name=self.name, system_prompt=system_prompt),
            cases=[_case_read_request(candidate) for candidate in selected_candidates],
        )
        read_data = read_result.data if isinstance(read_result.data, dict) else {}
        read_rows = [row for row in read_data.get("cases", []) if isinstance(row, dict)]
        read_errors = [row for row in read_data.get("errors", []) if isinstance(row, dict)]
        read_by_key = _rows_by_candidate_or_case(read_rows)
        _record_read_errors(selected_candidates, read_errors)

        case_payloads: list[dict[str, Any]] = []
        for candidate in selected_candidates:
            candidate.inspected = True
            row = _row_for_candidate(read_by_key, candidate)
            if row is None:
                candidate.risks.append(read_result.message)
                continue
            case_payloads.append(_case_prompt_payload(candidate, row))

        learned: dict[str, Any] = {}
        if case_payloads:
            runtime.emit_event(ctx, "seeding.initializations.generating", count=len(case_payloads))
            learned = self.planner.propose_initializations(
                ctx.params,
                user_prompt=ctx.request.prompt or "",
                cases=case_payloads,
                system_prompt=system_prompt,
            )

        proposal_items = _initialization_items(learned)
        proposals_by_key = _rows_by_candidate_or_case(proposal_items)
        preferred_case_id = str(learned.get("preferred_case_id") or learned.get("case_id") or "").strip()
        fallback_case_id = ""

        for candidate in selected_candidates:
            proposal = _row_for_candidate(proposals_by_key, candidate)
            candidate_params = deepcopy(ctx.params)
            fallback_used = False
            if proposal is not None:
                candidate.applied = self.planner.apply_proposal(candidate_params, proposal)
            if not candidate.applied:
                fallback = _local_initialization_fallback(candidate, _row_for_candidate(read_by_key, candidate))
                if fallback:
                    candidate_params = deepcopy(ctx.params)
                    candidate.applied = self.planner.apply_proposal(candidate_params, fallback)
                    if candidate.applied:
                        proposal = fallback
                        fallback_used = True

            if candidate.applied:
                candidate.params = candidate_params
                if fallback_used:
                    candidate.risks.append(str(proposal.get("rationale") or "已根据参考案例生成本地初始结构。"))
                else:
                    candidate.risks.append(str(proposal.get("rationale") or "Accepted DeepLens initialization."))
                if not fallback_case_id:
                    fallback_case_id = candidate.case_id
            elif proposal is None:
                candidate.risks.append("LLM did not return an initialization for this case.")
            elif proposal:
                candidate.risks.append("LLM initialization did not pass DeepLens surface validation.")
            else:
                candidate.risks.append(_planner_error(self.planner) or "LLM did not return a parseable initialization.")

        selected_case_id = _selected_applied_case_id(selected_candidates, preferred_case_id) or fallback_case_id
        if selected_case_id:
            selected = next(candidate for candidate in selected_candidates if candidate.case_id == selected_case_id)
            if selected.params is not None:
                selected_seed = deepcopy(selected.params)

        references = [_reference_payload(candidate, selected_case_id=selected_case_id) for candidate in selected_candidates]

        ctx.params = selected_seed
        ctx.references.extend(references)
        ctx.seed_candidates = candidates
        runtime.publish_references(ctx.references)

        applied = len([candidate for candidate in selected_candidates if candidate.applied])
        if selected_case_id:
            status = f"已选择 {selected_case_id}"
            observation = (
                f"已选择 {len(selected_candidates)} 个候选、读取 {len(case_payloads)} 个案例，"
                f"生成 {applied} 个可用初始结构，并已选择 {selected_case_id}。"
            )
        else:
            status = "继续使用当前默认初始结构"
            observation = (
                f"已选择 {len(selected_candidates)} 个候选、读取 {len(case_payloads)} 个案例，"
                "但未生成可用初始结构；继续使用当前默认初始结构。"
            )
        runtime.emit_event(ctx, "seeding.initializations.done", applied=applied, count=len(selected_candidates), status=status)
        runtime.emit_event(ctx, "seeding.references.published")
        return {
            "thought": "Retrieve local references from the index, read selected cases in batch, and generate initial structures.",
            "observation": observation,
            "data": {
                "candidate_count": len(candidates),
                "selected_count": len(selected_candidates),
                "read_count": len(case_payloads),
                "applied_count": applied,
                "selected_case_id": selected_case_id,
            },
        }


class SeedPlanner:
    _VALID_SURFACES = {"Spheric", "Aspheric", "Aperture", "ThinLens"}
    _DEEPLENS_ARGS = {"foclen", "fov", "fnum", "bfl", "thickness", "surf_list"}
    _CURRICULUM_FIELDS = {"iterations", "test_per_iter", "num_ring", "num_arm", "spp"}
    _FINE_TUNE_FIELDS = {"iterations", "test_per_iter", "num_ring", "num_arm", "spp"}

    def __init__(self) -> None:
        self.extractor = OpenAIExtractor()

    def select_candidates(
        self,
        params: LensDesignParams,
        *,
        user_prompt: str,
        candidates: list[SeedCandidate],
        system_prompt: str,
    ) -> list[str]:
        payload = {
            "task": "select_seed_candidates",
            "user_request": user_prompt,
            "target": public_params_dict(params),
            "instruction": "Pick 3 cases from the Markdown index. Return candidates with candidate_id and a short reason.",
            "candidates": [_candidate_brief(candidate) for candidate in candidates],
        }
        result = self.extractor.extract_json(json.dumps(payload, ensure_ascii=False), system_prompt)
        if not isinstance(result, dict):
            return []
        raw_ids = result.get("candidate_ids") or result.get("selected_cases") or result.get("candidates")
        if not isinstance(raw_ids, list):
            raw_ids = [result.get("candidate_id")]
        known = {candidate.candidate_id for candidate in candidates}
        selected = []
        for item in raw_ids:
            if isinstance(item, dict):
                candidate_id = str(item.get("candidate_id") or item.get("id") or "").strip()
                reason = short_reason(str(item.get("reason") or item.get("rationale") or "").strip())
            else:
                candidate_id = str(item or "").strip()
                reason = ""
            if candidate_id in known and candidate_id not in selected:
                selected.append(candidate_id)
                if reason:
                    next(candidate for candidate in candidates if candidate.candidate_id == candidate_id).reasons = [reason]
        return selected[:3]

    def propose_initializations(
        self,
        params: LensDesignParams,
        *,
        user_prompt: str,
        cases: list[dict[str, Any]],
        system_prompt: str,
    ) -> dict[str, Any]:
        prompt = json.dumps(
            {
                "task": "propose_deeplens_initializations",
                "user_request": user_prompt,
                "target": public_params_dict(params),
                "instruction": (
                    "Return exactly one initial_structures item for each selected case. "
                    "Preserve case_id and candidate_id. Pick preferred_case_id from the selected cases."
                ),
                "selected_cases": cases,
            },
            ensure_ascii=False,
        )
        return self.extractor.extract_json(prompt, system_prompt) or {}

    def apply_proposal(self, params: LensDesignParams, proposal: dict[str, Any]) -> bool:
        applied = False
        deeplens_args = proposal.get("deeplens_args", {})
        if not isinstance(deeplens_args, dict):
            deeplens_args = {}

        for key in self._DEEPLENS_ARGS:
            value = deeplens_args.get(key)
            if key == "surf_list":
                surf_list = self.normalize_surf_list(value)
                if surf_list:
                    params.surf_list = surf_list
                    applied = True
            elif key in {"foclen", "fov", "fnum", "bfl", "thickness"}:
                continue

        applied = self._apply_stage(params.curriculum, proposal.get("curriculum"), self._CURRICULUM_FIELDS) or applied
        applied = self._apply_stage(params.fine_tune, proposal.get("fine_tune"), self._FINE_TUNE_FIELDS) or applied
        return applied

    @classmethod
    def normalize_surf_list(cls, value: Any) -> list[list[str]]:
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


def _record_seed_selection_memory(ctx: Any, runtime: Any) -> None:
    try:
        runtime.memory.record_seed_selection_lessons(
            request=ctx.request,
            params=ctx.params,
            references=ctx.references,
            seed_candidates=ctx.seed_candidates,
        )
        ctx.memory_snapshot["seed_selection_lessons"] = runtime.memory.load_markdown_lessons("seed_selection")
    except Exception as exc:
        runtime.emit_event(ctx, "workflow.memory.skipped", error=exc)


def _fill_candidate_ids(selected_ids: list[str], candidates: list[SeedCandidate], *, limit: int) -> list[str]:
    filled = []
    known = {candidate.candidate_id for candidate in candidates}
    for candidate_id in selected_ids:
        if candidate_id in known and candidate_id not in filled:
            filled.append(candidate_id)
        if len(filled) >= limit:
            return filled
    for candidate in candidates:
        if candidate.candidate_id not in filled:
            filled.append(candidate.candidate_id)
        if len(filled) >= limit:
            break
    return filled


def _selected_candidates(candidates: list[SeedCandidate], selected_ids: list[str]) -> list[SeedCandidate]:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    selected: list[SeedCandidate] = []
    for candidate_id in selected_ids:
        candidate = by_id.get(candidate_id)
        if candidate is not None and candidate not in selected:
            selected.append(candidate)
    return selected


def _case_read_request(candidate: SeedCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "case_id": candidate.case_id,
        "path": candidate.path,
    }


def _case_prompt_payload(candidate: SeedCandidate, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "case_id": candidate.case_id,
        "title": candidate.title,
        "category": candidate.category,
        "path": row.get("path") or candidate.path,
        "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
        "zmx_text": str(row.get("zmx_text") or ""),
    }


def _rows_by_candidate_or_case(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "").strip()
        case_id = str(row.get("case_id") or "").strip()
        if candidate_id:
            indexed[f"candidate:{candidate_id}"] = row
        if case_id:
            indexed[f"case:{case_id}"] = row
    return indexed


def _row_for_candidate(indexed: dict[str, dict[str, Any]], candidate: SeedCandidate) -> dict[str, Any] | None:
    return indexed.get(f"candidate:{candidate.candidate_id}") or indexed.get(f"case:{candidate.case_id}")


def _record_read_errors(candidates: list[SeedCandidate], errors: list[dict[str, Any]]) -> None:
    if not errors:
        return
    indexed = _rows_by_candidate_or_case(errors)
    for candidate in candidates:
        row = _row_for_candidate(indexed, candidate)
        if row is not None:
            candidate.risks.append(str(row.get("message") or "Seed case could not be read."))


def _local_initialization_fallback(candidate: SeedCandidate, row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {}
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    surf_list = _surf_list_from_case_metadata(metadata)
    if not surf_list:
        return {}
    return {
        "candidate_id": candidate.candidate_id,
        "case_id": candidate.case_id,
        "deeplens_args": {"surf_list": surf_list},
        "curriculum": {},
        "fine_tune": {},
        "rationale": "LLM 初始化不可用，已根据参考案例的表面数量和孔径位置生成本地初始结构。",
    }


def _surf_list_from_case_metadata(metadata: dict[str, Any]) -> list[list[str]]:
    surface_count = _metadata_int(metadata, "surface_count")
    if surface_count <= 0:
        return []
    group_sizes = _valid_lens_group_sizes(max(2, surface_count))
    surface_total = sum(group_sizes)
    surfaces = ["Spheric"] * surface_total

    asphere_count = max(0, min(surface_total, _metadata_int(metadata, "asphere_count")))
    for index in range(surface_total - asphere_count, surface_total):
        surfaces[index] = "Aspheric"

    groups: list[list[str]] = []
    boundaries = [0]
    offset = 0
    for size in group_sizes:
        groups.append(surfaces[offset : offset + size])
        offset += size
        boundaries.append(offset)

    stop_index = _metadata_int(metadata, "stop_index")
    target = max(0, min(surface_total, stop_index - 1)) if stop_index > 0 else surface_total // 2
    insert_at = min(range(len(boundaries)), key=lambda index: (abs(boundaries[index] - target), index))
    return groups[:insert_at] + [["Aperture"]] + groups[insert_at:]


def _valid_lens_group_sizes(surface_count: int) -> list[int]:
    remaining = max(2, surface_count)
    sizes: list[int] = []
    while remaining > 0:
        if remaining in {2, 3}:
            sizes.append(remaining)
            break
        if remaining == 4:
            sizes.extend([2, 2])
            break
        size = 2 if remaining - 3 == 1 else 3
        sizes.append(size)
        remaining -= size
    return sizes


def _metadata_int(metadata: dict[str, Any], key: str) -> int:
    try:
        return int(metadata.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _initialization_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw = result.get("initial_structures") or result.get("structures") or result.get("candidates")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _selected_applied_case_id(candidates: list[SeedCandidate], preferred_case_id: str) -> str:
    if not preferred_case_id:
        return ""
    return next(
        (candidate.case_id for candidate in candidates if candidate.case_id == preferred_case_id and candidate.applied),
        "",
    )


def _planner_error(planner: Any) -> str:
    extractor = getattr(planner, "extractor", None)
    return str(getattr(extractor, "last_error", "") or "")


def _case_ids_text(candidates: list[SeedCandidate]) -> str:
    return ", ".join(candidate.case_id for candidate in candidates)


def _seed_candidates_from_payload(rows: list[dict[str, Any]], base_params: LensDesignParams) -> list[SeedCandidate]:
    candidates: list[SeedCandidate] = []
    for row in rows:
        params = _params_from_public(row.get("params"), base_params)
        candidates.append(
            SeedCandidate(
                candidate_id=str(row.get("candidate_id") or f"seed_{len(candidates) + 1:03d}"),
                case_id=str(row.get("case_id") or ""),
                title=str(row.get("title") or ""),
                category=str(row.get("category") or ""),
                path=row.get("path"),
                reasons=[str(item) for item in row.get("reasons", []) if item],
                risks=[str(item) for item in row.get("risks", []) if item],
                params=params,
                applied=bool(row.get("applied")),
                inspected=bool(row.get("inspected")),
            )
        )
    return candidates


def _params_from_public(value: Any, base_params: LensDesignParams) -> LensDesignParams | None:
    if not isinstance(value, dict):
        return None
    params = clone_params(base_params)
    surf_list = value.get("surf_list")
    if isinstance(surf_list, list) and surf_list:
        params.surf_list = surf_list
    for stage_name in ("curriculum", "fine_tune"):
        stage_values = value.get(stage_name)
        stage = getattr(params, stage_name)
        if not isinstance(stage_values, dict):
            continue
        for key in ("iterations", "test_per_iter", "num_ring", "num_arm", "spp"):
            if key in stage_values:
                setattr(stage, key, int(stage_values[key]))
    return params


def _candidate_brief(candidate: SeedCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "case_id": candidate.case_id,
        "title": candidate.title,
        "category": candidate.category,
        "reasons": candidate.reasons,
        "risks": candidate.risks,
    }


def _reference_payload(candidate: SeedCandidate, *, selected_case_id: str) -> dict[str, Any]:
    return {
        "source": "local_zemax_case",
        "candidate_id": candidate.candidate_id,
        "case_id": candidate.case_id,
        "title": candidate.title,
        "snippet": candidate.category,
        "url": candidate.path,
        "selected": candidate.case_id == selected_case_id,
        "applied": candidate.applied,
        "inspected": candidate.inspected,
        "selection_rationale": short_reason(candidate.reasons[0] if candidate.reasons else candidate.category),
        "design_rationale": short_reason(candidate.risks[0] if candidate.risks else ""),
    }


def short_reason(value: str, limit: int = 24) -> str:
    text = re.split(r"[銆?!?锛?\n]", str(value or "").strip(), maxsplit=1)[0].strip()
    return text[:limit]


def retrieve_candidates(*, cases_dir: Path, entries: list[dict[str, str]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entry in entries:
        case_id = entry["case_id"]
        path = case_path(cases_dir, case_id)
        if path is None:
            continue
        candidates.append(
            {
                "candidate_id": f"seed_{len(candidates) + 1:03d}",
                "case_id": case_id,
                "title": entry["title"],
                "category": entry["category"],
                "path": str(path),
                "reasons": [],
                "risks": [],
                "applied": False,
                "inspected": False,
                "params": None,
            }
        )
    return candidates


def load_index_entries(index_path: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    category = ""
    section_note = ""
    for raw_line in index_path.read_text(encoding="utf-8").splitlines():
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


def case_path(cases_dir: Path, case_id: str) -> Path | None:
    if not case_id:
        return None
    for path in cases_dir.glob(f"{case_id}.*"):
        if path.suffix.lower() == ".zmx":
            return path
    return None


def extract_case_metadata(path: Path, *, text: str | None = None) -> dict[str, Any]:
    text = text if text is not None else path.read_text(encoding="utf-8", errors="ignore")
    surface_matches = list(re.finditer(r"(?m)^SURF\s+(\d+)", text))
    surface_count = max(0, len(surface_matches) - 2)
    type_values = re.findall(r"(?m)^\s*TYPE\s+([A-Z0-9_]+)", text)
    asphere_count = sum(1 for value in type_values if "ASPH" in value or "BICON" in value)

    stop_index = None
    current_surface = None
    for line in text.splitlines():
        surf_match = re.match(r"SURF\s+(\d+)", line.strip())
        if surf_match:
            current_surface = int(surf_match.group(1))
        elif line.strip() == "STOP" and current_surface is not None:
            stop_index = current_surface
            break

    efl_values: list[float] = []
    for match in re.finditer(r"(?m)^\s*EFL[XY]?\s+(.+)$", text):
        for token in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?", match.group(1)):
            try:
                number = abs(float(token))
            except ValueError:
                continue
            if 0.1 <= number <= 10000:
                efl_values.append(number)

    fnum = None
    fnum_match = re.search(r"(?m)^\s*FNUM\s+([-+]?\d+(?:\.\d+)?)", text)
    if fnum_match:
        fnum = float(fnum_match.group(1))

    return {
        "native_efl": max(efl_values) if efl_values else None,
        "native_fnum": fnum,
        "surface_count": surface_count,
        "asphere_count": asphere_count,
        "stop_index": stop_index,
    }


__all__ = [
    "SeedingNode",
    "case_path",
    "extract_case_metadata",
    "load_index_entries",
    "retrieve_candidates",
]
