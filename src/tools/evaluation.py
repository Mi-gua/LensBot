from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.deeplens import ensure_deeplens_import


class EvaluationTool:
    def evaluate(self, result_dir: str) -> dict[str, Any]:
        import numpy as np

        root = Path(result_dir)
        final_json = root / "final.json"
        curriculum_json = root / "curriculum.json"

        metrics: dict[str, Any] = {
            "has_final_json": final_json.exists(),
            "has_curriculum_json": curriculum_json.exists(),
            "result_dir": str(root),
        }

        metrics["artifact_score"] = (50 if curriculum_json.exists() else 0) + (50 if final_json.exists() else 0)
        if not final_json.exists():
            return metrics

        try:
            ensure_deeplens_import(Path(__file__))
            from deeplens.optics import GeoLens

            lens = GeoLens(filename=str(final_json))
            spot = lens.analysis_spot(num_field=11)
            metrics["spot_rms_um_center"] = float(spot.get("fov0.0", {}).get("rms", np.nan))
            metrics["spot_rms_um_mid"] = float(spot.get("fov0.5", {}).get("rms", np.nan))
            metrics["spot_rms_um_edge"] = float(spot.get("fov1.0", {}).get("rms", np.nan))
            metrics["spot_geo_radius_um_edge"] = float(spot.get("fov1.0", {}).get("radius", np.nan))

            _fov, distortion = lens.calc_distortion_radial(num_points=11)
            dist_pct = np.asarray(distortion, dtype=float) * 100.0
            metrics["distortion_pct_center"] = float(dist_pct[0])
            metrics["distortion_pct_edge"] = float(dist_pct[-1])
            metrics["distortion_pct_abs_max"] = float(np.max(np.abs(dist_pct)))

            mtf_center = lens.mtf(fov=0.0)
            mtf_edge = lens.mtf(fov=float(lens.rfov))
            metrics["mtf50_center_tan_cy_mm"] = self._mtf50(mtf_center[0], mtf_center[1])
            metrics["mtf50_center_sag_cy_mm"] = self._mtf50(mtf_center[0], mtf_center[2])
            metrics["mtf50_edge_tan_cy_mm"] = self._mtf50(mtf_edge[0], mtf_edge[1])
            metrics["mtf50_edge_sag_cy_mm"] = self._mtf50(mtf_edge[0], mtf_edge[2])
        except Exception as exc:
            metrics["iqa_error"] = str(exc)

        return metrics

    @staticmethod
    def _mtf50(freq: Any, mtf: Any) -> float:
        import numpy as np

        freq_arr = np.asarray(freq, dtype=float)
        mtf_arr = np.asarray(mtf, dtype=float)
        if freq_arr.size == 0 or mtf_arr.size == 0:
            return float("nan")

        below = np.where(mtf_arr <= 0.5)[0]
        if below.size == 0:
            return float(freq_arr[-1])

        idx = int(below[0])
        if idx == 0:
            return float(freq_arr[0])

        x1, y1 = float(freq_arr[idx - 1]), float(mtf_arr[idx - 1])
        x2, y2 = float(freq_arr[idx]), float(mtf_arr[idx])
        if abs(y2 - y1) < 1e-12:
            return float(x2)

        t = (0.5 - y1) / (y2 - y1)
        return float(x1 + t * (x2 - x1))
