from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.deeplens.runtime import ensure_deeplens_import


def analyze_deeplens_final(final_json: str | Path) -> dict[str, Any]:
    import numpy as np

    final_json = Path(final_json)
    ensure_deeplens_import(Path(__file__))
    from deeplens.optics import GeoLens

    lens = GeoLens(filename=str(final_json))
    efl_mm = float(lens.foclen)
    r_sensor_mm = float(lens.r_sensor)
    rfov_rad = float(lens.rfov)
    if abs(efl_mm) > 1e-12:
        fov_deg = float(2.0 * np.rad2deg(np.arctan(abs(r_sensor_mm / efl_mm))))
    else:
        fov_deg = float(2.0 * np.rad2deg(rfov_rad))
    spot = lens.analysis_spot(num_field=11)
    metrics: dict[str, Any] = {
        "deeplens_efl_mm": efl_mm,
        "deeplens_fnum": float(lens.fnum),
        "deeplens_fov_deg": fov_deg,
        "spot_rms_um_center": float(spot.get("fov0.0", {}).get("rms", np.nan)),
        "spot_rms_um_mid": float(spot.get("fov0.5", {}).get("rms", np.nan)),
        "spot_rms_um_edge": float(spot.get("fov1.0", {}).get("rms", np.nan)),
        "spot_geo_radius_um_edge": float(spot.get("fov1.0", {}).get("radius", np.nan)),
    }
    metrics["deeplens_rms_spot_um_center"] = metrics["spot_rms_um_center"]
    metrics["deeplens_rms_spot_um_edge"] = metrics["spot_rms_um_edge"]
    metrics["deeplens_rms_spot_um_max"] = float(
        np.nanmax(
            [
                metrics["spot_rms_um_center"],
                metrics["spot_rms_um_mid"],
                metrics["spot_rms_um_edge"],
            ]
        )
    )

    _fov, distortion = lens.calc_distortion_radial(num_points=11)
    dist_pct = np.asarray(distortion, dtype=float) * 100.0
    metrics["distortion_pct_center"] = float(dist_pct[0])
    metrics["distortion_pct_edge"] = float(dist_pct[-1])
    metrics["distortion_pct_abs_max"] = float(np.max(np.abs(dist_pct)))
    metrics["deeplens_distortion_pct_edge"] = metrics["distortion_pct_edge"]
    metrics["deeplens_distortion_pct_abs_max"] = metrics["distortion_pct_abs_max"]

    mtf_center = lens.mtf(fov=0.0)
    mtf_edge = lens.mtf(fov=float(lens.rfov))
    metrics["mtf50_center_tan_cy_mm"] = _mtf50(mtf_center[0], mtf_center[1])
    metrics["mtf50_center_sag_cy_mm"] = _mtf50(mtf_center[0], mtf_center[2])
    metrics["mtf50_edge_tan_cy_mm"] = _mtf50(mtf_edge[0], mtf_edge[1])
    metrics["mtf50_edge_sag_cy_mm"] = _mtf50(mtf_edge[0], mtf_edge[2])
    metrics["deeplens_mtf50_center_tan_cy_mm"] = metrics["mtf50_center_tan_cy_mm"]
    metrics["deeplens_mtf50_center_sag_cy_mm"] = metrics["mtf50_center_sag_cy_mm"]
    metrics["deeplens_mtf50_edge_tan_cy_mm"] = metrics["mtf50_edge_tan_cy_mm"]
    metrics["deeplens_mtf50_edge_sag_cy_mm"] = metrics["mtf50_edge_sag_cy_mm"]
    return metrics


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
