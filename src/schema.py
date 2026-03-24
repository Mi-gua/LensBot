from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OptimizationControls:
    iterations: int = 30
    spp: int = 128
    test_per_iter: int = 5


@dataclass
class LensDesignParams:
    foclen: float
    fov: float
    fnum: float
    bfl: float
    thickness: float
    surf_list: list[list[str]]
    lrs: list[float]
    iterations: int = 30
    spp: int = 128
    test_per_iter: int = 5


@dataclass
class AgentInput:
    mode: str
    prompt: str | None = None
    params: LensDesignParams | None = None
    enable_patent_search: bool = True
    controls: OptimizationControls | None = None


@dataclass
class AgentResult:
    ok: bool
    summary: str
    result_dir: str | None = None
    curriculum_json: str | None = None
    final_json: str | None = None
    log_file: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    references: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[str] = field(default_factory=list)
    memory_snapshot: dict[str, Any] = field(default_factory=dict)
