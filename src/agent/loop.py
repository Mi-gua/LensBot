from __future__ import annotations

from pathlib import Path
from typing import Callable

from agent.memory import AgentMemory
from agent.tools import AgentTools
from schema import AgentInput, AgentResult, LensDesignParams


class LensResearchAgent:
    def __init__(self, default_params: LensDesignParams, project_root: Path):
        self.default_params = default_params
        self.project_root = project_root
        self.memory = AgentMemory(project_root / "src" / "memory")
        self.tools = AgentTools(default_params)

    def run(self, request: AgentInput, progress_cb: Callable[[str], None] | None = None) -> AgentResult:
        timeline: list[str] = []
        snapshot = self.memory.create_snapshot()

        def emit(message: str) -> None:
            timeline.append(message)
            snapshot["timeline"].append(message)
            if progress_cb:
                progress_cb(message)

        emit("解析输入")
        if request.mode == "nl":
            if not request.prompt:
                return self._finalize(request, AgentResult(ok=False, summary="自然语言输入为空"))
            params = self.tools.requirements.parse(request.prompt)
            emit("已完成自然语言参数解析")
        else:
            if request.params is None:
                return self._finalize(request, AgentResult(ok=False, summary="结构化参数输入为空"))
            params = request.params
            emit("已加载结构化参数")

        if request.controls is not None:
            params.iterations = int(request.controls.iterations)
            params.spp = int(request.controls.spp)
            params.test_per_iter = int(request.controls.test_per_iter)
            emit(
                "已应用优化预算 "
                f"(iterations={params.iterations}, spp={params.spp}, test_per_iter={params.test_per_iter})"
            )

        references: list[dict] = []
        if request.enable_patent_search:
            emit("开始专利检索")
            query = f"f{params.foclen}mm f/{params.fnum} fov {params.fov}"
            references = self.tools.patents.search(query)
            emit(f"专利检索完成，共 {len(references)} 条")
        else:
            emit("已跳过专利检索")

        emit("开始执行镜头设计")
        try:
            design_result = self.tools.design.run(params, progress_cb=emit)
        except Exception as exc:
            result = AgentResult(
                ok=False,
                summary=f"Lens design failed: {exc}",
                references=references,
                timeline=timeline,
                memory_snapshot=snapshot,
            )
            return self._finalize(request, result)

        emit("开始像质评估")
        metrics = self.tools.evaluation.evaluate(design_result["result_dir"])
        metrics.update(
            {
                "rfov": design_result.get("rfov"),
                "fnum": design_result.get("fnum"),
                "r_sensor": design_result.get("r_sensor"),
                "patent_hits": references,
            }
        )

        summary = (
            f"Lens design finished. Artifact score={metrics.get('artifact_score')}, "
            f"spot_rms_edge={metrics.get('spot_rms_um_edge')}um, "
            f"distortion_edge={metrics.get('distortion_pct_edge')}%, "
            f"MTF50_center_tan={metrics.get('mtf50_center_tan_cy_mm')} cy/mm."
        )
        result = AgentResult(
            ok=True,
            summary=summary,
            result_dir=design_result.get("result_dir"),
            curriculum_json=design_result.get("curriculum_json"),
            final_json=design_result.get("final_json"),
            log_file=design_result.get("log_file"),
            metrics=metrics,
            references=references,
            timeline=timeline,
            memory_snapshot=snapshot,
        )
        emit("任务完成")
        return self._finalize(request, result, params=params)

    def _finalize(
        self,
        request: AgentInput,
        result: AgentResult,
        params: LensDesignParams | None = None,
    ) -> AgentResult:
        self.memory.append_episode(request, result)
        if result.ok and params is not None:
            self.memory.add_note(
                f"Target f={params.foclen}mm F/{params.fnum} FoV={params.fov} "
                f"achieved artifact_score={result.metrics.get('artifact_score')}"
            )
        return result
