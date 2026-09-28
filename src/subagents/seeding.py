from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from agent.llm import OpenAIExtractor
from agent.prompts import workflow_agent_context, workflow_agent_prompt
from runtime.traces import trace_row as _trace_row
from subagents.types import LensDesignParams, SeedCandidate, clone_params, design_contract_dict, target_params_dict


class SeedingNode:
    name = "Seeding"

    def __init__(self) -> None:
        self.planner = SeedPlanner()

    def run(self, ctx: Any, runtime: Any) -> None:
        if ctx.params is None:
            ctx.fail("No design parameters are available for seeding.")
            return

        available_tools = runtime.tool_names("retrieve_seed_cases", "read_seed_cases")
        objective = "Prepare candidate optical structures for the optimization agent."
        agent_context = workflow_agent_context(
            agent_name=self.name,
            objective=objective,
            memory=ctx.memory_snapshot,
            params=_seed_target_payload(ctx.params),
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
            if ctx.delivery_status == "failed" and self.planner.extractor.last_error:
                extractor = self.planner.extractor
                runtime.record_workflow_artifact(ctx, self.name, "llm_failure", {
                    "error": extractor.last_error,
                    "model": extractor.model,
                    "finish_reason": extractor.last_finish_reason,
                    "usage": extractor.last_usage,
                    "content": extractor.last_content,
                })
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
                    ok=ctx.delivery_status != "failed",
                )
            )
        ctx.agent_trace.extend(trace)
        runtime.record_agent_trace(ctx, trace)
        if ctx.delivery_status != "failed":
            _record_seed_selection_memory(ctx, runtime)

    def _seed_from_references(self, ctx: Any, runtime: Any, system_prompt: str) -> dict[str, Any]:
        retrieve_result = runtime.registry.call(
            "retrieve_seed_cases",
            ctx=runtime.tool_context(ctx, agent_name=self.name, system_prompt=system_prompt),
        )
        if not retrieve_result.ok:
            ctx.fail(retrieve_result.message)
            return {
                "thought": "Reference retrieval failed.",
                "observation": retrieve_result.message,
                "done": True,
            }

        retrieve_data = retrieve_result.data if isinstance(retrieve_result.data, dict) else {}
        candidates = _seed_candidates_from_payload(retrieve_data.get("candidates", []), ctx.params)
        if not candidates:
            ctx.fail("镜头库没有可用参考案例。")
            return {
                "thought": "No local reference candidates are available.",
                "observation": "No local ZEMAX seed candidates were available.",
                "done": True,
            }

        shortlist_ids = self.planner.shortlist_candidates(
            ctx.params,
            user_prompt=ctx.request.prompt or "",
            candidates=candidates,
            system_prompt=system_prompt,
        )
        shortlist = _candidates_by_id(candidates, shortlist_ids)
        if not shortlist:
            ctx.fail(_planner_error(self.planner) or "未选出候选参考案例。")
            return {"thought": "Select reference cases.", "observation": ctx.failure_summary, "done": True}
        runtime.emit_event(
            ctx,
            "seeding.candidates.enter",
            count=len(shortlist),
            case_ids=_case_ids_text(shortlist),
        )

        runtime.emit_event(
            ctx,
            "seeding.cases.reading",
            count=len(shortlist),
            case_ids=_case_ids_text(shortlist),
        )

        read_result = runtime.registry.call(
            "read_seed_cases",
            ctx=runtime.tool_context(ctx, agent_name=self.name, system_prompt=system_prompt),
            cases=[_case_read_request(candidate) for candidate in shortlist],
        )
        read_data = read_result.data if isinstance(read_result.data, dict) else {}
        read_rows = [row for row in read_data.get("cases", []) if isinstance(row, dict)]
        read_errors = [row for row in read_data.get("errors", []) if isinstance(row, dict)]
        read_by_key = _rows_by_candidate_or_case(read_rows)
        _record_read_errors(shortlist, read_errors)

        case_payloads: list[dict[str, Any]] = []
        for candidate in shortlist:
            candidate.inspected = True
            row = _row_for_candidate(read_by_key, candidate)
            if row is None:
                candidate.risks.append(read_result.message)
                continue
            case_payloads.append(_case_prompt_payload(candidate, row))

        learned: dict[str, Any] = {}
        if case_payloads:
            runtime.emit_event(ctx, "seeding.initialization.selecting", count=len(case_payloads))
            learned = self.planner.propose_initializations(
                ctx.params,
                user_prompt=ctx.request.prompt or "",
                cases=case_payloads,
                system_prompt=system_prompt,
            )

        proposals = {
            str(item.get("candidate_id")): item
            for item in learned.get("initial_structures", [])
            if isinstance(item, dict)
        }
        for candidate in shortlist:
            proposal = proposals.get(candidate.candidate_id)
            if proposal is None:
                continue
            params = deepcopy(ctx.params)
            if self.planner.apply_proposal(params, proposal):
                candidate.params = params
                candidate.risks.extend(_proposal_notes(proposal))

        ctx.seed_candidates = shortlist
        ctx.references.extend(_reference_payload(candidate, selected_case_id="") for candidate in shortlist)
        runtime.publish_references(ctx.references)
        ready = sum(candidate.params is not None for candidate in shortlist)
        if not ready:
            ctx.fail(_planner_error(self.planner) or "未生成可供 DeepLens 使用的候选结构。")
        else:
            runtime.emit_event(ctx, "seeding.initialization.ready", count=ready)
        return {
            "thought": "Prepare reference structures for the optimization agent to choose from.",
            "observation": ctx.failure_summary if not ready else f"已整理 {ready} 个可用候选结构，由优化智能体选择起点。",
            "data": {"candidate_count": len(shortlist), "ready_count": ready},
            "done": True,
        }

class SeedPlanner:
    _VALID_SURFACES = {"Spheric", "Aspheric", "Aperture", "ThinLens"}

    def __init__(self) -> None:
        self.extractor = OpenAIExtractor()

    def shortlist_candidates(
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
            "target": _seed_target_payload(params),
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
        structures: list[dict[str, Any]] = []
        for case in cases:
            prompt = json.dumps(
                {
                    "task": "prepare_deeplens_seeds",
                    "user_request": user_prompt,
                    "target": _seed_target_payload(params),
                    "instruction": (
                        "Return initial_structures with exactly one item for the supplied case. "
                        "Include candidate_id, case_id, deeplens_args.surf_list, rationale and "
                        "structure_derivation. Keep the evidence concise; do not repeat the source "
                        "prescription or input context. The optimization agent chooses which to optimize."
                    ),
                    "selected_cases": [case],
                },
                ensure_ascii=False,
            )
            result = self.extractor.extract_json(prompt, system_prompt)
            if result is None:
                return {}
            items = result.get("initial_structures")
            if (not isinstance(items, list) or len(items) != 1
                    or not isinstance(items[0], dict)
                    or items[0].get("candidate_id") != case.get("candidate_id")):
                self.extractor.last_error = "Expected one initialization for the supplied candidate."
                return {}
            structures.append(items[0])
        return {"initial_structures": structures}

    def apply_proposal(self, params: LensDesignParams, proposal: dict[str, Any]) -> bool:
        args = proposal.get("deeplens_args")
        if not isinstance(args, dict):
            return False
        surf_list = self.normalize_surf_list(args.get("surf_list"))
        if not surf_list:
            return False
        params.surf_list = surf_list
        return True



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


def _proposal_notes(proposal: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    rationale = str(proposal.get("rationale") or "").strip()
    if rationale:
        notes.append(rationale)
    derivation = proposal.get("structure_derivation")
    if isinstance(derivation, dict) and derivation:
        notes.append("structure_derivation=" + json.dumps(derivation, ensure_ascii=False, sort_keys=True))
    for key in ("caveats", "risks"):
        value = proposal.get(key)
        if isinstance(value, list):
            notes.extend(str(item) for item in value if item)
        elif value:
            notes.append(str(value))
    return notes or ["Accepted DeepLens initialization."]


def _seed_target_payload(params: LensDesignParams | None) -> dict[str, Any] | None:
    if params is None:
        return None
    return {
        "foclen": params.foclen,
        "fov": params.fov,
        "fnum": params.fnum,
        "bfl": params.bfl,
        "thickness": params.thickness,
        "design_contract": design_contract_dict(params),
    }





def _candidates_by_id(candidates: list[SeedCandidate], selected_ids: list[str]) -> list[SeedCandidate]:
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
