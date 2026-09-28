from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from subagents.types import (
    CurriculumParams,
    RECOMMENDED_OPTIMIZATION_REVIEW_TURNS,
    FineTuneParams,
    LensDesignParams,
    SeedCandidate,
    build_agent_input,
    clone_params,
    design_contract_dict,
    load_default_config,
    load_default_params,
    params_from_public_dict,
    public_params_dict,
)


@dataclass
class AgentInput:
    mode: str
    prompt: str | None = None
    params: LensDesignParams | None = None
    max_turns: int | None = None
    recommended_max_turns: int = RECOMMENDED_OPTIMIZATION_REVIEW_TURNS


@dataclass
class AgentResult:
    ok: bool
    summary: str
    result_dir: str | None = None
    curriculum_json: str | None = None
    candidate_json: str | None = None
    candidate_zmx: str | None = None
    candidate_png: str | None = None
    final_json: str | None = None
    final_zmx: str | None = None
    summary_report_file: str | None = None
    log_file: str | None = None
    metrics_file: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    references: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    memory_snapshot: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "AgentInput",
    "AgentResult",
    "CurriculumParams",
    "FineTuneParams",
    "LensDesignParams",
    "SeedCandidate",
    "build_agent_input",
    "clone_params",
    "design_contract_dict",
    "load_default_config",
    "load_default_params",
    "params_from_public_dict",
    "public_params_dict",
]
