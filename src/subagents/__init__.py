from __future__ import annotations

from typing import Any


__all__ = [
    "AnalysisNode",
    "CurriculumParams",
    "FineTuneParams",
    "LensDesignParams",
    "OptimizationRunner",
    "ReportingNode",
    "SeedCandidate",
    "SeedingNode",
    "build_agent_input",
    "clone_params",
    "load_default_config",
    "load_default_params",
    "params_from_public_dict",
    "public_params_dict",
    "target_params_dict",
]


def __getattr__(name: str) -> Any:
    if name == "AnalysisNode":
        from subagents.analysis import AnalysisNode

        return AnalysisNode
    if name == "OptimizationRunner":
        from subagents.optimization import OptimizationRunner

        return OptimizationRunner
    if name == "ReportingNode":
        from subagents.reporting import ReportingNode

        return ReportingNode
    if name == "SeedingNode":
        from subagents.seeding import SeedingNode

        return SeedingNode
    if name in {"build_agent_input", "load_default_config", "load_default_params"}:
        from subagents import types

        return getattr(types, name)
    if name in {
        "CurriculumParams",
        "FineTuneParams",
        "LensDesignParams",
        "SeedCandidate",
        "clone_params",
        "params_from_public_dict",
        "public_params_dict",
        "target_params_dict",
    }:
        from subagents import types

        return getattr(types, name)
    raise AttributeError(name)
