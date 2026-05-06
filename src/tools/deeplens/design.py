from __future__ import annotations

import contextlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from agent.settings import LensDesignParams
from engine.deeplens.autolens_rms import optimize_autolens_rms
from agent.tools import ToolContext, ToolResult


class DeepLensDesignTool:
    """Tool-layer adapter around the DeepLens optimizer."""

    name = "optimize_lens"
    description = "Optimize an optical lens with the configured algorithm engine."
    category = "algorithm"
    metadata = {"engine": "deeplens", "kind": "optimizer"}

    _ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
    _LOG_PREFIX_RE = re.compile(
        r"^(?:Using CUDA: |Failed to calculate distorted FoV by ray tracing, use effective FoV "
        r"|Lens written to |Ray spot analysis results for depth inf:|RMS radius: |Geo radius: "
        r"|Lens design constraints initialized with default values\.)"
    )

    class _NormalizedLogStream:
        def __init__(self, stream):
            self._stream = stream
            self._pending = ""
            self._last_was_newline = True

        def write(self, data):
            if not data:
                return 0
            cleaned = DeepLensDesignTool._ANSI_ESCAPE_RE.sub("", data).replace("\r", "\n")
            if self._pending and DeepLensDesignTool._LOG_PREFIX_RE.match(cleaned):
                self._pending += "\n"
            self._pending += cleaned
            self._drain_complete_lines()
            self._stream.flush()
            return len(data)

        def flush(self):
            if self._pending:
                self._write_text(self._pending)
                self._pending = ""
            self._stream.flush()

        def _drain_complete_lines(self):
            while "\n" in self._pending:
                line, self._pending = self._pending.split("\n", 1)
                self._write_text(line)
                if not self._last_was_newline:
                    self._stream.write("\n")
                    self._last_was_newline = True

        def _write_text(self, text):
            if not text:
                return
            self._stream.write(text)
            self._last_was_newline = False

        def isatty(self):
            return False

        @property
        def encoding(self):
            return getattr(self._stream, "encoding", "utf-8")

    @staticmethod
    def _mk_result_dir(base: Path | None = None) -> Path:
        result_root = base or Path(__file__).resolve().parents[3] / "results"
        result_root.mkdir(parents=True, exist_ok=True)
        current_time = datetime.now().strftime("%Y%m%d-%H%M%S")
        result_dir = result_root / current_time
        # If the same second is reused, add a deterministic numeric suffix.
        if result_dir.exists():
            index = 2
            while True:
                candidate = result_root / f"{current_time}-{index}"
                if not candidate.exists():
                    result_dir = candidate
                    break
                index += 1
        result_dir.mkdir(parents=True, exist_ok=False)
        return result_dir

    @staticmethod
    @contextlib.contextmanager
    def _redirect_engine_output(log_path: Path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", buffering=1) as log_fp:
            normalized = DeepLensDesignTool._NormalizedLogStream(log_fp)
            with contextlib.redirect_stdout(normalized), contextlib.redirect_stderr(normalized):
                yield
            normalized.flush()

    @staticmethod
    @contextlib.contextmanager
    def _isolated_root_logging():
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        try:
            yield
        finally:
            current_handlers = list(root.handlers)
            for handler in current_handlers:
                if handler in original_handlers:
                    continue
                root.removeHandler(handler)
                with contextlib.suppress(Exception):
                    handler.flush()
                with contextlib.suppress(Exception):
                    handler.close()
            root.setLevel(original_level)

    @staticmethod
    def _drop_closed_root_handlers() -> None:
        root = logging.getLogger()
        for handler in list(root.handlers):
            stream = getattr(handler, "stream", None)
            if stream is not None and getattr(stream, "closed", False):
                root.removeHandler(handler)
                with contextlib.suppress(Exception):
                    handler.close()

    @staticmethod
    def _normalize_starting-point_artifacts(result_dir: Path) -> None:
        for artifact in result_dir.glob("starting-point_*"):
            if not artifact.is_file():
                continue
            target = result_dir / f"starting-point{artifact.suffix}"
            if target.exists():
                target.unlink()
            artifact.rename(target)

    def run(
        self,
        params: LensDesignParams | None = None,
        ctx: ToolContext | None = None,
        progress_cb: Callable[[str], None] | None = None,
        artifact_cb: Callable[[str], None] | None = None,
        **kwargs,
    ) -> dict | ToolResult:
        params = params or kwargs["params"]
        if ctx is not None:
            progress_cb = progress_cb or ctx.progress_cb
            artifact_cb = artifact_cb or ctx.artifact_cb
        result_dir = self._mk_result_dir()
        log_file = result_dir / "run.log"

        def emit_artifact() -> None:
            if artifact_cb:
                artifact_cb(str(result_dir))

        if progress_cb:
            progress_cb("优化与评估：初始化镜头自动设计任务。")
        emit_artifact()

        with self._isolated_root_logging():
            with self._redirect_engine_output(log_file):
                if progress_cb:
                    progress_cb("优化与评估：执行课程学习和微调。")
                engine_result = optimize_autolens_rms(
                    params,
                    result_dir=result_dir,
                    artifact_cb=emit_artifact,
                )

        self._drop_closed_root_handlers()
        self._normalize_starting-point_artifacts(result_dir)
        emit_artifact()

        if progress_cb:
            progress_cb("优化与评估：设计完成，日志已归档。")

        data = {
            "result_dir": str(result_dir),
            "curriculum_json": engine_result["curriculum_json"],
            "final_json": engine_result["final_json"],
            "final_zmx": engine_result["final_zmx"],
            "log_file": str(log_file),
            "rfov": engine_result["rfov"],
            "fnum": engine_result["fnum"],
            "r_sensor": engine_result["r_sensor"],
        }
        if ctx is None:
            return data
        return ToolResult(True, "Lens optimization finished.", data)
