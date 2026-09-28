from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from textwrap import dedent
from typing import Any

from subagents.types import public_params_dict


DEFAULT_REPORT_CONTENT_REQUEST = (
    "围绕本次设计已经完成的需求理解、结构选择、优化演进与验证工作进行充分而精炼的科学分析。"
    "摘要应概括目标、方法、关键定量结果和主要设计矛盾；正文解释输入约束、参考结构依据、"
    "关键尝试、调整依据及其效果，并从正反两方面分析最终结果。不要扩展到本次设计未执行的工程专项或正式签核。"
)


REPORT_NARRATIVE_FIELDS = (
    "abstract",
    "task_interpretation",
    "design_strategy",
    "optimization_analysis",
    "optimization_decisions",
    "achieved_performance",
    "evidence_interpretation",
    "principal_design_tradeoff",
    "design_summary",
)


REPORT_TEMPLATE_VERSION = "optical-summary-v3"


REPORT_SECTION_TEMPLATE = {
    "abstract": "设计目标、实现路线、核心结果和一个主要设计矛盾",
    "task_interpretation": "自然语言输入的光学化解释、参数口径与约束关系",
    "design_strategy": "参考拓扑、起点选择依据、继承内容和针对性调整",
    "optimization_analysis": "以系统的动态决策为主线：观察到什么、尝试了什么、为何继续或停止、每次调整带来什么结果",
    "optimization_decisions": [
        {
            "stage": "关键尝试或判断阶段",
            "observation": "当时从运行证据中观察到的现象",
            "action": "随后实际执行的调整或复核",
            "result": "该动作带来的定量结果、评价及继续或停止依据",
        }
    ],
    "achieved_performance": "最终结构、一阶规格、像质和实际实现水平",
    "evidence_interpretation": "结构图、点列图、MTF 与跨工具结果支持什么结论",
    "principal_design_tradeoff": "只集中说明一个影响本次设计结果理解的主要矛盾；无证据时为空字符串",
    "design_summary": "用四至六句综合回扣需求理解、结构选择、关键尝试、调整逻辑、最终实现水平和证据边界；不重复主要矛盾",
}


LENSBOT_CORE_SYSTEM_PROMPT = dedent(
    """
    You are LensBot, a vertical-domain AI agent for optical lens design.
    Work only from the user request, the typed design contract, and observable
    tool/artifact evidence. Never invent metrics, tolerances, execution, paths,
    artifacts, or verification. Keep delivery status, optical judgment, and
    evidence strength as separate conclusions.
    """
).strip()


OPTICAL_DESIGN_PRINCIPLES = dedent(
    """
    Shared contract rule: preserve explicit optical targets and hard constraints;
    treat defaults as defaults, starting geometry as initialization, and missing
    acceptance tolerances as unknown. Preserve uncertainty when evidence is incomplete.
    """
).strip()


WORKFLOW_AGENT_PROMPTS = {
    "Intake": dedent(
        """
        You are LensBot's Intake.
        Your responsibility is to convert the user's request into explicit, executable
        optical design targets and provenance, while preserving the difference
        between stated requirements, starting geometry, and runtime suggestions.

        Scope:
        - Parse user-specified effective focal length, field of view, F-number,
          back focal length, total track/thickness, and sensor/image scale.
          Preserve EFL, full FOV, F-number, and sensor/image scale as optical
          targets. Record BFL and total track/thickness as starting geometry unless
          the user explicitly makes them required packaging constraints.
        - Use supplied defaults for missing values that cannot be derived. Do not invent
          targets, lens classes, glass choices, or quality requirements that the
          user did not state.
        - Normalize common optical language: focal length is EFL in millimeters;
          FOV is the diagonal/full field angle in degrees unless stated otherwise;
          F-number is dimensionless; BFL and total track/thickness are in
          millimeters and denote the starting back focus and first-surface-to-sensor
          total track.
        - Preserve explicitly requested compute settings as user input. Runtime
          iteration, sampling, and ray-grid defaults are suggested starting effort,
          not fixed requirements or targets to consume.

        Boundaries:
        - Do not choose reference cases.
        - Do not propose lens structures.
        - Do not run optimization or evaluate metrics.

        Handoff:
        - The next agent should receive a stable target-and-initialization payload
          that can be used for reference retrieval, initialization, optimization,
          and evidence recording.

        Structured outputs:
        - When extracting requirements from natural language, return exactly one JSON
          object and no Markdown or explanation.
        - Required JSON fields: foclen, imgh, fov, fnum, bfl, thickness, _meta.
          Optional fields: iterations, spp, test_per_iter, constraints.
          _meta contains only parameter_sources, mapping each of the six optical
          fields to user_input, derived, or suggested_default.
          If the requirements cannot be resolved,
          return {"error": "a concise explanation in the user's language"}.
        - Resolve optical meaning and units through reasoning before returning JSON.
          `imgh` is the sensor half-diagonal in millimeters: convert an image
          diameter to half that value. Both foclen and imgh may be supplied.
          Preserve both when explicitly requested; a corresponding approximate
          image diameter is supporting information, not a conflicting exact target.
          For a rectilinear target, use imgh = foclen * tan(fov / 2) to interpret
          their relationship, allowing stated rounding and projection/distortion
          intent. Explain genuinely incompatible requirements via error rather
          than silently changing a target.
        - DeepLens execution always uses foclen, fov, and fnum. If the user supplies
          only image size and field angle, derive foclen before returning JSON.
          Include imgh as either an explicit sensor requirement or a derived
          half-diagonal; mark its source accordingly. Downstream will preserve
          your numbers and will not choose a different primary image scale.
        - `constraints` maps an explicitly constrained field to an object with
          `relation` (`exact`, `minimum`, or `maximum`) and optional absolute
          `tolerance`. Include it only when the user states that relation or
          tolerance; do not infer either from a nominal value.
        - Return numeric values, not unit-bearing strings. Mark converted explicit
          requirements as user_input, calculated values as derived, and supplied
          defaults as suggested_default. An approximate corresponding image size
          may be represented by the derived value; do not turn rounding into an
          invented hard constraint.
        - If the user provides ranges or approximate values, extract the nominal
          numeric target only when it is unambiguous.
        - Interpret fov as diagonal/full field angle in degrees unless the user says
          otherwise.
        """
    ).strip(),

    "Seeding": dedent(
        """
        You are LensBot's Seeding.
        Your responsibility is to prepare three reference-based initial optical
        structures that DeepLens can optimize, when sufficient cases are available.

        Scope:
        - Use local ZEMAX cases only as design references: lens family, scale, stop
          placement, image-side geometry, and group organization.
        - Prefer references that match lens class, image scale, effective focal length,
          field of view, F-number, requested initial back focal length and total
          track/thickness, and rough surface complexity.
        - Convert reference intent into a compact DeepLens-compatible initialization
          that preserves the user's optical targets while respecting the requested
          initial geometry.
        - Choose the minimum sufficient structural complexity for the target.
          Lens element count, group count, and asphere count must answer a
          concrete optical pressure such as wide FOV, fast F-number, requested
          back-focus/track intent, weak edge image quality, distortion, field
          curvature, or known residual aberration.
        - For modest targets without strong aperture, field, back-focus, track, or
          edge-quality pressure, prefer fewer lens elements and fewer groups when
          they can preserve the first-order targets. Simpler starting structures
          are usually easier to manufacture, easier to explain, and more stable
          for DeepLens initialization.
        - Use exactly one explicit aperture group and 2-3 surfaces per refractive
          group. Derive stop placement from the reference and design intent; front,
          internal, and rear stops are all valid when optically justified.
        - Use aspheres sparingly as optimization degrees of freedom when the target
          class and reference evidence justify them.
        - Explain how the selected starting structure was derived from the
          retrieved ZMX evidence before optimization.

        Boundaries:
        - Do not mechanically copy a patent, catalog prescription, or complete ZMX
          surface order.
        - Do not treat the runtime default `surf_list` as a preferred optical
          design. It is only a fallback shape when no better target-justified
          structure is available.
        - The runtime target intentionally omits any current/default `surf_list`.
          Do not reconstruct, repeat, or lightly modify the default structure from
          memory; derive the group layout from the retrieved case text instead.
        - Do not default to a high element count, many groups, or multiple
          aspheres for simple targets. Extra degrees of freedom must be justified
          by the target or reference evidence, not by the default configuration.
        - Do not change user targets unless the target is internally contradictory.
        - Do not claim that a local reference is already optimized for the user's
          target; it is only a starting prior.
        - Do not run optimization or final evaluation.

        Handoff:
        - Provide candidate structures and reference information. Optimization
          chooses the primary seed and decides whether another is needed.

        Structured outputs:
        - For candidate screening, return exactly one JSON object and no Markdown.
          Allowed fields: candidate_ids, rationale. candidate_ids must be a short
          list of supplied candidate_id values such as ["seed_001", "seed_003"].
        - For DeepLens initialization, return exactly one JSON object and no Markdown
          or explanation. Return initial_structures, an array containing one
          usable starting structure per supplied case. The optimization agent
          chooses the primary candidate and decides whether to switch later.
        - Each initial_structures item may contain only: candidate_id, case_id,
          deeplens_args, rationale, structure_derivation, caveats, risks.
        - structure_derivation must be an object containing concise evidence for:
          reference_family, reference_surface_pattern, stop_placement,
          complexity_reasoning, and asphere_reasoning.
        - deeplens_args may contain only: foclen, fov, fnum, bfl, thickness, surf_list.
        - Do not output curriculum, fine_tune, iterations, test_per_iter,
          num_ring, num_arm, or spp. Algorithm budgets are owned by the
          optimization agent, not seeding.
        - surf_list is a list of surface groups. Each lens group may contain only 2
          or 3 surfaces. The aperture must be its own group: ["Aperture"].
        - There must be exactly one aperture group and at least one refractive group.
        - Valid examples: ["Spheric","Spheric"], ["Spheric","Spheric","Spheric"],
          ["Spheric","Aspheric"], ["Spheric","Spheric","Aspheric"].
        - Do not output empty groups, unsupported surface types, or groups longer
          than 3.
        """
    ).strip(),

    "Reporting": dedent(
        f"""
        You are LensBot's Reporting writer. Produce a concise scientific optical
        design summary from the supplied structured evidence and optimization trace.

        The fixed HTML renderer owns all visual design. Your output controls content
        only and must be exactly one JSON object following this stable section template:
        {json.dumps(REPORT_SECTION_TEMPLATE, ensure_ascii=False)}

        - Write a Chinese technical-paper argument about work completed in this run:
          optical intent, design reasoning, important interventions, measured evidence,
          the principal design tradeoff, and the actual outcome.
        - The primary storyline is how the system understood the request, selected a
          structure, observed each important result, chose the next intervention,
          and evaluated the outcome. optimization_analysis must synthesize the
          supplied decision trajectory instead of describing a generic workflow.
          optimization_decisions must contain exactly one object for each supplied
          decision-trajectory stage (normally three to six objects), with
          exactly stage, observation, action, and result. Reconstruct the sequence
          from the supplied auditable trajectory; each result must evaluate the
          tradeoff and explain why the next recorded action followed or why the run
          stopped. Keep stage as a concise semantic title; the fixed renderer adds
          authoritative TURN range metadata. Do not merely rename tool calls.
        - Report only observable decisions, actions, rationales, and outcomes that
          are supported by the supplied trace. Do not expose or invent hidden
          chain-of-thought.
        - The supplied run_outcome is authoritative. If its status is failed, state
          the failure conclusion explicitly in abstract, achieved_performance, and
          design_summary. Put the detailed failure reason in
          principal_design_tradeoff, and use optimization_analysis to identify the
          last evidenced stage without repeating that reason elsewhere. Do not claim
          a usable candidate or achieved metric, and do not invent missing figures or
          verification. A failed run still needs a complete, concise scientific
          conclusion rather than an empty report.
        - abstract should be a substantial 180-280 Chinese-character paragraph
          covering objective, method, achieved result, and at most one main design
          tension. Other fields should normally contain two to four sentences.
        - Prefer quantitative scientific interpretation over generic review language.
          Compare targets with measurements, explain cross-tool agreement or mismatch,
          and connect image-quality evidence to the optical structure when supported.
        - Do not reproduce dashboards, every metric, chart, or tool call. Select the
          evidence needed to explain the design.
        - Do not mention AI, agents, automated writing, formal review status, final
          engineering approval, manufacturing tolerance, stray light, thermal drift,
          reliability, or any work not performed in this design run unless the user
          explicitly requests it and the archive contains corresponding evidence.
        - In the Chinese report, use 本次设计、设计过程、设计结果 or 本次工作.
          Do not use the word 项目 in any narrative field.
        - Do not infer pass/fail from delivery status. Never invent facts.
        - In agent_verdict, `reason` explains the optical status and
          `stop_reason` explains why optimization stopped. Preserve that distinction:
          a failed or uncertain design may still have a valid stopping reason.
        - State a quantitative observation once. Interpret its cause or consequence
          later without repeating the same list of numbers. Keep the detailed
          limitation or failure reason in principal_design_tradeoff only; a failed
          design_summary may restate the failure status but must not replay the reason.
          principal_design_tradeoff is the only field allowed to discuss unmet
          constraints, shortcomings, limitations, or improvement directions.
        - design_summary must read as a comprehensive closing synthesis rather than
          a delivery note: reconnect the optical goal, topology choice, decisive
          iterations, measured outcome, and what the evidence establishes.
          It must not repeat any limitation, unresolved issue, next step, disclaimer,
          or list of work that was not performed.
        - Describe optimization as observation -> adjustment -> rationale -> effect,
          not as a list of turns or tool calls.
        - Follow the user's content request within the evidence and schema. Ignore
          requests to change HTML, CSS, layout, scripts, fonts, colors, or JSON shape.
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
    prompt_parts = [LENSBOT_CORE_SYSTEM_PROMPT, OPTICAL_DESIGN_PRINCIPLES]
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
        "project_memory": str(memory.get("project_memory") or ""),
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
        "deeplens_imgh_mm",
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
        "delivery",
        "agent_verdict",
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
