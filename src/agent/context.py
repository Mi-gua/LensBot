from __future__ import annotations

from settings import load_default_params
from schema import AgentInput, LensDesignParams, OptimizationControls


def build_agent_input(
    project_root,
    *,
    mode: str,
    nl_prompt: str,
    foclen: float,
    fov: float,
    fnum: float,
    bfl: float,
    thickness: float,
    iterations: int,
    spp: int,
    test_per_iter: int,
    enable_patent_search: bool,
) -> AgentInput:
    controls = OptimizationControls(
        iterations=int(iterations),
        spp=int(spp),
        test_per_iter=int(test_per_iter),
    )
    if mode == "自然语言输入":
        return AgentInput(
            mode="nl",
            prompt=nl_prompt.strip(),
            enable_patent_search=enable_patent_search,
            controls=controls,
        )

    defaults = load_default_params(project_root)
    params = LensDesignParams(
        foclen=float(foclen),
        fov=float(fov),
        fnum=float(fnum),
        bfl=float(bfl),
        thickness=float(thickness),
        surf_list=defaults.surf_list,
        lrs=defaults.lrs,
        iterations=defaults.iterations,
        spp=defaults.spp,
        test_per_iter=defaults.test_per_iter,
    )
    return AgentInput(
        mode="params",
        params=params,
        enable_patent_search=enable_patent_search,
        controls=controls,
    )
