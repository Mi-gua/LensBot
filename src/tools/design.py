from __future__ import annotations

from typing import Callable

from engine.deeplens_rms import run_rms_design
from schema import LensDesignParams


class DesignTool:
    def run(
        self,
        params: LensDesignParams,
        progress_cb: Callable[[str], None] | None = None,
    ) -> dict:
        return run_rms_design(params, progress_cb=progress_cb)
