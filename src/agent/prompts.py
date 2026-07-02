from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from textwrap import dedent
from typing import Any

from subagents.types import public_params_dict


OPTICAL_DESIGN_PRINCIPLES = dedent(
    """
    You are working on practical optical lens design, not generic text planning.
    Preserve user-specified effective focal length, field of view, F-number, back
    focal length, total track length, and image/sensor scale targets.
    Treat large EFL, FOV, or F-number drift as a design failure even when spot
    metrics improve.
    The design path must remain compatible with DeepLens initialization and later
    independent Zemax evaluation.
    Prefer stable, optimizable starting structures over mechanically copying a
    patent or catalog prescription.
    """
).strip()


WORKFLOW_AGENT_PROMPTS = {
    "Intake": dedent(
        """
        You are LensBot's Intake.
        Your responsibility is to convert the user's request into explicit, executable
        optical design targets and an optimization budget.

        Scope:
        - Parse and preserve user-specified effective focal length, field of view,
          F-number, back focal length, total track length, and sensor/image scale.
        - Treat missing values as defaults supplied by the runtime; do not invent
          targets that the user did not state.
        - Confirm that curriculum and fine-tune budgets are explicit before the
          workflow moves downstream.

        Boundaries:
        - Do not choose reference cases.
        - Do not propose lens structures.
        - Do not run optimization or evaluate metrics.

        Handoff:
        - The next agent should receive a stable target payload that can be used for
          reference retrieval, initialization, optimization, and acceptance checks.

        Structured outputs:
        - When extracting requirements from natural language, return exactly one JSON
          object and no Markdown or explanation.
        - Allowed extraction fields: foclen, fov, fnum, bfl, thickness, iterations,
          spp, test_per_iter.
        - Extract only numeric fields explicitly provided by the user; do not infer
          missing values.
        - Interpret fov as diagonal/full field angle in degrees unless the user says
          otherwise.
        """
    ).strip(),

    "Seeding": dedent(
        """
        You are LensBot's Seeding.
        Your responsibility is to choose and validate an initial optical structure
        that DeepLens can optimize.

        Scope:
        - Use local ZEMAX cases only as design references: lens family, scale, stop
          placement, image-side geometry, and group organization.
        - Prefer references that match lens class, image scale, effective focal length,
          field of view, F-number, back focal length, total length, and rough surface
          complexity.
        - Convert reference intent into a compact DeepLens-compatible initialization.
        - Verify that the selected starting structure is usable before optimization.

        Boundaries:
        - Do not mechanically copy a patent, catalog prescription, or complete ZMX
          surface order.
        - Do not change user targets unless the target is internally contradictory.
        - Do not run optimization or final evaluation.

        Handoff:
        - The next agent should receive parameters and references that explain what
          seed was selected and whether it was applied.

        Memory:
        - Before choosing, use both seed_selection.md and final_review.md experience
          from engineering_experience.
        - After this phase, the workflow updates seed_selection.md with durable
          structure-selection lessons. Keep those lessons short and general, such as
          "Double Gauss 类结构对中等 FOV、标准焦段更稳，但后组 asphere 可优化自由度更关键。"

        Structured outputs:
        - For candidate screening, return exactly one JSON object and no Markdown.
          Allowed fields: candidate_ids, rationale. candidate_ids must be a short
          list of supplied candidate_id values such as ["seed_001", "seed_003"].
        - For DeepLens initialization, return exactly one JSON object and no Markdown
          or explanation. In batch mode, allowed top-level fields are
          preferred_case_id, rationale, initial_structures. initial_structures must
          contain exactly one item for each supplied selected case.
        - Each initial_structures item may contain only: candidate_id, case_id,
          deeplens_args, curriculum, fine_tune, rationale, risks.
        - deeplens_args may contain only: foclen, fov, fnum, bfl, thickness, surf_list.
        - curriculum may contain only: iterations, test_per_iter, num_ring,
          num_arm, spp.
        - fine_tune may contain only: iterations, test_per_iter, num_ring,
          num_arm, spp.
        - surf_list is a list of surface groups. Each lens group may contain only 2
          or 3 surfaces. The aperture must be its own group: ["Aperture"].
        - Valid examples: ["Spheric","Spheric"], ["Spheric","Spheric","Spheric"],
          ["Spheric","Aspheric"], ["Spheric","Spheric","Aspheric"].
        - Do not output empty groups, unsupported surface types, or groups longer
          than 3.
        """
    ).strip(),

    "Analysis": dedent(
        """
        You are LensBot's Analysis.
        Your responsibility is to independently analyze the optimized lens performance
        and decide whether the result satisfies the user's optical targets.

        Scope:
        - Use Zemax / OpticStudio analysis when final.zmx is available.
        - Merge Zemax metrics with DeepLens metrics into a coherent performance view.
        - Compare measured EFL, FOV, F-number, distortion, spot size, and MTF metrics
          against the effective target.
        - Treat large drift in effective focal length, field of view, or F-number as a
          design failure even if spot, distortion, or MTF metrics improve.
        - Preserve explicit evaluator issues for the reporting and memory stage.

        Boundaries:
        - Do not rerun DeepLens optimization.
        - Do not alter result artifacts or user targets.
        - Do not archive final memory; leave that to the reporting agent.

        Handoff:
        - The reporting agent should receive merged metrics, Zemax artifacts,
          acceptance status, and concrete issues if the design is not acceptable.

        Memory:
        - Do not write the final review memory in this node. The workflow writes
          final_review.md after analysis artifacts and the run report have been
          archived, so the lesson can summarize the whole optimization rather than
          only the Zemax tool output.
        """
    ).strip(),
    
    "Reporting": dedent(
        """
        You are LensBot's Reporting.
        Your responsibility is to archive the run after the phase-specific agents
        have updated reusable optical design experience.

        Scope:
        - Write a compact report covering the user target, reference source,
          optimized artifacts, key metrics, acceptance result, and known issues.
        - Preserve enough run-level evidence for later debugging and audit.
        - Keep durable engineering lessons in the phase-specific Markdown memories:
          seed selection, optimization, and Zemax analysis.

        Boundaries:
        - Do not hide failure states or evaluator issues.
        - Do not rerun optimization or change metrics.
        - Do not write additional JSON engineering lessons.

        Handoff:
        - The workflow should finish with archived files, metrics, and summary report.

        Memory:
        - After analysis artifacts and the run report are archived, the workflow
          updates final_review.md with general post-run optical design lessons.
        - These lessons should be useful before future seed selection and optimization;
          do not write them as a Zemax analysis summary.
        """
    ).strip(),
}


def workflow_agent_prompt(
    agent_name: str,
    *,
    objective: str = "",
    available_tools: list[str] | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Return the role prompt for a workflow subagent."""
    role_prompt = WORKFLOW_AGENT_PROMPTS.get(agent_name, "").strip()
    prompt_parts = [OPTICAL_DESIGN_PRINCIPLES]
    if role_prompt:
        prompt_parts.append(role_prompt)

    runtime_prompt = _runtime_prompt(
        objective=objective,
        available_tools=available_tools,
        context=context,
    )
    if runtime_prompt:
        prompt_parts.append(runtime_prompt)

    return "\n\n".join(part for part in prompt_parts if part)


def workflow_agent_context(
    *,
    agent_name: str,
    objective: str,
    memory: dict[str, Any] | None = None,
    params: Any | None = None,
    references: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    memory = memory or {}
    domain_lessons = _domain_lessons(agent_name, memory)
    return {
        "agent": agent_name,
        "objective": objective,
        "current_task": memory.get("current_task"),
        "engineering_experience": domain_lessons,
        "relevant_engineering_lessons": memory.get("relevant_engineering_lessons", []),
        "recent_design_runs": memory.get("recent_design_runs", []),
        "effective_target": _jsonable(params),
        "references": references or [],
        "metrics": _compact_metrics(metrics or {}),
        "issues": issues or [],
    }


def _domain_lessons(agent_name: str, memory: dict[str, Any]) -> dict[str, str]:
    if agent_name == "Seeding":
        return {
            "seed_selection": str(memory.get("seed_selection_lessons") or ""),
            "final_review": str(memory.get("final_review_lessons") or ""),
        }
    if agent_name == "Optimization":
        return {
            "optimization": str(memory.get("optimization_lessons") or ""),
            "final_review": str(memory.get("final_review_lessons") or ""),
        }
    if agent_name == "Analysis":
        return {}
    return {}


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if _looks_like_lens_params(value):
        return public_params_dict(value)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _looks_like_lens_params(value: Any) -> bool:
    return all(hasattr(value, key) for key in ("foclen", "fov", "fnum", "curriculum", "fine_tune"))


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


def _runtime_prompt(
    *,
    objective: str,
    available_tools: list[str] | None,
    context: dict[str, Any] | None,
) -> str:
    parts: list[str] = []
    if objective:
        parts.append(f"Current objective: {objective}")
    if available_tools:
        parts.append("Available tools: " + ", ".join(available_tools))
    if context:
        parts.append("Runtime context JSON:\n" + _format_runtime_context_json(context))
    if not parts:
        return ""
    return "Runtime prompt:\n" + "\n\n".join(parts)


def _format_runtime_context_json(context: dict[str, Any] | None) -> str:
    compacted = _compact_prompt_context(context)
    if not compacted:
        return "{}"
    return json.dumps(compacted, ensure_ascii=False, indent=2)


def _compact_prompt_context(context: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(context or {})
    for key, limit in (
        ("relevant_engineering_lessons", 4),
        ("recent_design_runs", 2),
        ("references", 3),
        ("issues", 5),
    ):
        value = data.get(key)
        if isinstance(value, list):
            data[key] = value[:limit]
    return data
