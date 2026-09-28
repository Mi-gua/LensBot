from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from engine.deeplens.runtime import ensure_deeplens_import

DEEPLENS_EVALUATION_SEED = 0


def _deeplens_metric_metadata(
    *,
    efl_mm: float,
    r_sensor_mm: float,
    rfov_rad: float,
    distortion_field_samples_deg: list[float] | None = None,
) -> dict[str, Any]:
    if abs(efl_mm) > 1e-12:
        sensor_fov_deg = float(2.0 * math.degrees(math.atan(abs(r_sensor_mm / efl_mm))))
    else:
        sensor_fov_deg = float(2.0 * math.degrees(abs(rfov_rad)))
    rfov_deg = float(math.degrees(abs(rfov_rad)))

    return {
        "deeplens_metric_source": "deeplens_geolens",
        "deeplens_fov_deg": sensor_fov_deg,
        "deeplens_sensor_fov_deg": sensor_fov_deg,
        "deeplens_rfov_deg": rfov_deg,
        "deeplens_rfov_full_deg": float(2.0 * rfov_deg),
        "rfov_deg": rfov_deg,
        "deeplens_fov_definition": (
            "sensor-implied full field angle computed as 2*atan(r_sensor/foclen); "
            "deeplens_rfov_deg records the GeoLens ray-sampling half field angle."
        ),
        "deeplens_spot_unit": "um",
        "deeplens_spot_definition": (
            "polychromatic RGB RMS/geometric spot radius relative to the combined centroid "
            "from GeoLens.analysis_spot(num_field=11)"
        ),
        "deeplens_spot_valid_fraction_definition": (
            "fraction of launched RGB spot-analysis rays that reach the sensor"
        ),
        "deeplens_distortion_unit": "percent",
        "deeplens_distortion_definition": (
            "100 * (h_centroid - h_ideal) / h_ideal from valid ray bundles in "
            "GeoLens.calc_distortion_radial"
        ),
        "deeplens_distortion_field_samples_deg": distortion_field_samples_deg or [],
        "deeplens_mtf_definition": (
            "single-primary-wavelength geometric PSF MTF from an exact-angle "
            "infinite-conjugate ray bundle in GeoLens.mtf; "
            "not equivalent to Zemax diffraction FFT MTF"
        ),
        "deeplens_mtf_frequency_unit": "cycles/mm",
        "deeplens_mtf_field_samples_deg": [0.0, rfov_deg],
    }


def analyze_deeplens_final(final_json: str | Path) -> dict[str, Any]:
    import torch

    with torch.random.fork_rng():
        torch.manual_seed(DEEPLENS_EVALUATION_SEED)
        return _analyze_deeplens_final(final_json)


def _analyze_deeplens_final(final_json: str | Path) -> dict[str, Any]:
    import numpy as np

    final_json = Path(final_json)
    ensure_deeplens_import(Path(__file__))
    try:
        from deeplens.optics import GeoLens
    except ModuleNotFoundError:
        from deeplens import GeoLens

    lens = GeoLens(filename=str(final_json))
    efl_mm = float(lens.foclen)
    r_sensor_mm = float(lens.r_sensor)
    rfov_rad = float(lens.rfov)
    d_sensor_mm = float(lens.d_sensor)
    last_surface_d_mm = float(lens.surfaces[-1].d)
    surface_positions_mm = np.asarray([float(surface.d) for surface in lens.surfaces], dtype=float)
    vertex_spacings_mm = np.diff(surface_positions_mm)
    surface_type_names = [type(surface).__name__ for surface in lens.surfaces]
    spot = lens.analysis_spot(num_field=11)

    distortion_result = lens.calc_distortion_radial(num_points=11)
    if len(distortion_result) == 3:
        distortion_fov, distortion, distortion_valid_fraction = distortion_result
    elif len(distortion_result) == 2:
        distortion_fov, distortion = distortion_result
        distortion_valid_fraction = np.isfinite(
            np.asarray(distortion, dtype=float)
        ).astype(float)
    else:
        raise ValueError(
            "calc_distortion_radial must return (field, distortion) or "
            "(field, distortion, valid_fraction)"
        )
    distortion_field_samples_deg = [
        float(value) for value in np.asarray(distortion_fov, dtype=float).reshape(-1)
    ]

    metrics: dict[str, Any] = {
        "deeplens_efl_mm": efl_mm,
        "deeplens_imgh_mm": r_sensor_mm,
        "deeplens_fnum": float(lens.fnum),
        "deeplens_ttl_mm": d_sensor_mm - float(lens.surfaces[0].d),
        "deeplens_bfl_mm": d_sensor_mm - last_surface_d_mm,
        "deeplens_track_definition": "axial vertex distance from first optical surface to sensor",
        "deeplens_bfl_definition": "axial vertex distance from last optical surface to sensor",
        "deeplens_surface_count": len(lens.surfaces),
        "deeplens_aspheric_surface_count": sum("asph" in name.lower() for name in surface_type_names),
        "deeplens_min_surface_vertex_spacing_mm": (
            float(np.min(vertex_spacings_mm)) if vertex_spacings_mm.size else None
        ),
        "deeplens_surface_vertex_spacing_definition": "minimum difference between consecutive loaded GeoLens surface vertex positions",
        "deeplens_evaluation_seed": DEEPLENS_EVALUATION_SEED,
        **_deeplens_metric_metadata(
            efl_mm=efl_mm,
            r_sensor_mm=r_sensor_mm,
            rfov_rad=rfov_rad,
            distortion_field_samples_deg=distortion_field_samples_deg,
        ),
        "spot_rms_um_center": float(spot.get("fov0.0", {}).get("rms", np.nan)),
        "spot_rms_um_mid": float(spot.get("fov0.5", {}).get("rms", np.nan)),
        "spot_rms_um_edge": float(spot.get("fov1.0", {}).get("rms", np.nan)),
        "spot_geo_radius_um_edge": float(spot.get("fov1.0", {}).get("radius", np.nan)),
        "deeplens_spot_valid_fraction_center": float(
            spot.get("fov0.0", {}).get("valid_fraction", np.nan)
        ),
        "deeplens_spot_valid_fraction_edge": float(
            spot.get("fov1.0", {}).get("valid_fraction", np.nan)
        ),
        "deeplens_spot_valid_fraction_samples": [
            float(value.get("valid_fraction", np.nan)) for value in spot.values()
        ],
    }
    metrics["deeplens_spot_valid_pct_edge"] = (
        100.0 * metrics["deeplens_spot_valid_fraction_edge"]
    )
    metrics["deeplens_spot_valid_fraction_min"] = float(
        np.nanmin(metrics["deeplens_spot_valid_fraction_samples"])
    )
    metrics["deeplens_rms_spot_um_center"] = metrics["spot_rms_um_center"]
    metrics["deeplens_rms_spot_um_edge"] = metrics["spot_rms_um_edge"]
    metrics["deeplens_rms_spot_um_max"] = float(
        np.nanmax([value["rms"] for value in spot.values()])
    )

    dist_pct = np.asarray(distortion, dtype=float) * 100.0
    metrics["distortion_pct_center"] = (
        float(dist_pct[0]) if distortion_valid_fraction[0] > 0 else None
    )
    metrics["distortion_pct_edge"] = (
        float(dist_pct[-1]) if distortion_valid_fraction[-1] > 0 else None
    )
    metrics["distortion_pct_abs_max"] = float(np.nanmax(np.abs(dist_pct)))
    metrics["deeplens_distortion_valid_fraction"] = [
        float(value) for value in distortion_valid_fraction
    ]
    metrics["deeplens_distortion_valid_fraction_min"] = float(
        np.nanmin(np.asarray(distortion_valid_fraction, dtype=float))
    )
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


def _mtf50(freq: Any, mtf: Any) -> float | None:
    import numpy as np

    freq_arr = np.asarray(freq, dtype=float)
    mtf_arr = np.asarray(mtf, dtype=float)
    if freq_arr.size == 0 or mtf_arr.size == 0:
        return None

    below = np.where(mtf_arr <= 0.5)[0]
    if below.size == 0:
        return None

    idx = int(below[0])
    if idx == 0:
        x1, y1 = 0.0, 1.0
        x2, y2 = float(freq_arr[0]), float(mtf_arr[0])
        if abs(y2 - y1) < 1e-12:
            return float(x2)
        return float(x1 + (0.5 - y1) / (y2 - y1) * (x2 - x1))

    x1, y1 = float(freq_arr[idx - 1]), float(mtf_arr[idx - 1])
    x2, y2 = float(freq_arr[idx]), float(mtf_arr[idx])
    if abs(y2 - y1) < 1e-12:
        return float(x2)

    t = (0.5 - y1) / (y2 - y1)
    return float(x1 + t * (x2 - x1))
