from __future__ import annotations

import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any


MTF_FULL_MAX_FREQUENCY_CY_MM = 50.0
MTF_DISPLAY_MIN_FREQUENCY_CY_MM = 10.0
MTF_DISPLAY_MTF50_HEADROOM = 2.5
MTF_DISPLAY_FREQUENCY_STEPS_CY_MM = (10.0, 15.0, 20.0, 30.0, 40.0, 50.0)
LENSBOT_MPL_STYLE = {
    "font.family": "Segoe UI",
    "font.size": 9,
    "text.color": "#09090b",
    "axes.labelcolor": "#71717a",
    "axes.titlecolor": "#09090b",
    "axes.edgecolor": "#e4e4e7",
    "axes.linewidth": 0.8,
    "xtick.color": "#71717a",
    "ytick.color": "#71717a",
    "figure.facecolor": "#ffffff",
    "axes.facecolor": "#ffffff",
    "savefig.facecolor": "#ffffff",
}


def _clean_field_label(field_label: str, field_index: int) -> str:
    text = field_label.strip()
    if not text:
        return f"Field {field_index + 1}"

    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if match:
        return f"Field {field_index + 1} ({match.group(0)})"
    return text


def _full_mtf_xmax(mtf_series: list[dict[str, Any]]) -> float:
    frequencies = [
        float(value)
        for series in mtf_series
        for value in series.get("frequency_values", [])
        if math.isfinite(float(value)) and float(value) > 0
    ]
    if not frequencies:
        return MTF_FULL_MAX_FREQUENCY_CY_MM
    return min(max(frequencies), MTF_FULL_MAX_FREQUENCY_CY_MM)


def _suggest_mtf_display_xmax(
    mtf_series: list[dict[str, Any]], mtf_summary: dict[str, Any]
) -> float:
    full_xmax = _full_mtf_xmax(mtf_series)
    summary_series = mtf_summary.get("series", [])
    if len(summary_series) != len(mtf_series):
        return full_xmax

    crossings: list[float] = []
    for series in summary_series:
        for key in ("mtf50_tangential", "mtf50_sagittal"):
            value = series.get(key)
            if value is None:
                return full_xmax
            crossing = float(value)
            if not math.isfinite(crossing) or crossing <= 0:
                return full_xmax
            crossings.append(crossing)

    if not crossings:
        return full_xmax

    target = max(
        MTF_DISPLAY_MIN_FREQUENCY_CY_MM,
        MTF_DISPLAY_MTF50_HEADROOM * max(crossings),
    )
    return next(
        (
            min(step, full_xmax)
            for step in MTF_DISPLAY_FREQUENCY_STEPS_CY_MM
            if step >= target
        ),
        full_xmax,
    )


def _plot_mtf(axis: Any, report: dict[str, Any], display_xmax: float) -> None:
    colors = ("tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple")
    mtf_series = report["fft_mtf"]
    mtf_summary = report["mtf_summary"]["series"]
    axis_label = str(
        mtf_series[0].get("frequency_axis_label") or "Spatial frequency"
    )
    if "cy/mm" not in axis_label and "cycles" not in axis_label.lower():
        axis_label = f"{axis_label} (cy/mm)"

    for series, summary in zip(mtf_series, mtf_summary):
        index = int(series["series_index"])
        color = colors[index % len(colors)]
        label = _clean_field_label(str(series.get("field_label", "")), index)
        frequencies = series.get("frequency_values", [])
        axis.plot(
            frequencies,
            series["tangential"],
            color=color,
            linewidth=1.8,
            label=f"{label} T",
        )
        axis.plot(
            frequencies,
            series["sagittal"],
            color=color,
            linewidth=1.8,
            linestyle="--",
            label=f"{label} S",
        )
        for key in ("mtf50_tangential", "mtf50_sagittal"):
            crossing = summary.get(key)
            if crossing is not None:
                axis.scatter(
                    [float(crossing)],
                    [0.5],
                    s=28,
                    color=color,
                    edgecolor="white",
                    linewidth=0.7,
                    zorder=4,
                )

    axis.axhline(
        0.5,
        color="#64748b",
        linewidth=1.0,
        linestyle=":",
        label="MTF50",
    )
    axis.set_title(
        f"Polychromatic FFT MTF · display 0–{display_xmax:g} cy/mm",
        fontsize=13,
        pad=12,
    )
    axis.set_xlabel(axis_label)
    axis.set_ylabel("MTF (modulus of OTF)")
    axis.set_xlim(0, display_xmax)
    axis.set_ylim(0, 1.02)
    axis.grid(True, color="#cbd5e1", alpha=0.45, linewidth=0.8)
    axis.legend(fontsize=8, ncol=2, frameon=False)


def _plot_grid_distortion(axis: Any, report: dict[str, Any]) -> None:
    from matplotlib.colors import LinearSegmentedColormap

    grid = report["grid_distortion"]
    points = grid["points"]
    x_scale = max(abs(float(point["predicted_x"])) for point in points)
    y_scale = max(abs(float(point["predicted_y"])) for point in points)
    vector_scale = 10.0

    for coordinate, group_key in (("i", "j"), ("j", "i")):
        group_values = sorted({int(point[coordinate]) for point in points})
        for group_value in group_values:
            line = sorted(
                (
                    point
                    for point in points
                    if int(point[coordinate]) == group_value
                ),
                key=lambda point: int(point[group_key]),
            )
            axis.plot(
                [float(point["predicted_x"]) / x_scale for point in line],
                [float(point["predicted_y"]) / y_scale for point in line],
                color="#e4e4e7",
                linewidth=0.65,
                zorder=1,
            )

    i_values = sorted({int(point["i"]) for point in points})
    j_values = sorted({int(point["j"]) for point in points})
    i_sample = set(i_values[:: max(1, math.ceil(len(i_values) / 11))])
    j_sample = set(j_values[:: max(1, math.ceil(len(j_values) / 11))])
    vector_points = [
        point
        for point in points
        if int(point["i"]) in i_sample and int(point["j"]) in j_sample
    ]
    distortion_cmap = LinearSegmentedColormap.from_list(
        "lensbot_distortion",
        ("#dbeafe", "#bfdbfe", "#93c5fd", "#60a5fa"),
    )
    vectors = axis.quiver(
        [float(point["predicted_x"]) / x_scale for point in vector_points],
        [float(point["predicted_y"]) / y_scale for point in vector_points],
        [
            vector_scale
            * (float(point["actual_x"]) - float(point["predicted_x"]))
            / x_scale
            for point in vector_points
        ],
        [
            vector_scale
            * (float(point["actual_y"]) - float(point["predicted_y"]))
            / y_scale
            for point in vector_points
        ],
        [abs(float(point["distortion_pct"])) for point in vector_points],
        angles="xy",
        scale_units="xy",
        scale=1,
        cmap=distortion_cmap,
        width=0.0038,
        headwidth=3.25,
        headlength=3.8,
        alpha=0.86,
        zorder=2,
    )
    axis.text(
        0.5,
        1.025,
        (
            f"MAX {float(grid['max_abs_pct']):.2f}%    "
            f"RMS {float(grid['rms_pct']):.2f}%    "
            f"VECTOR SCALE ×{vector_scale:g}"
        ),
        transform=axis.transAxes,
        ha="center",
        va="bottom",
        fontsize=9,
        fontweight=600,
        color="#71717a",
    )
    colorbar = axis.figure.colorbar(
        vectors,
        ax=axis,
        orientation="horizontal",
        fraction=0.026,
        pad=0.045,
        shrink=0.78,
        aspect=38,
    )
    colorbar.set_label(
        "DISTORTION MAGNITUDE (%)",
        fontsize=7.5,
        color="#71717a",
        labelpad=5,
    )
    colorbar.ax.tick_params(labelsize=8, colors="#64748b", length=2)
    colorbar.outline.set_visible(False)
    axis.set_xlim(-1.16, 1.16)
    axis.set_ylim(-1.16, 1.16)
    axis.set_xticks([])
    axis.set_yticks([])
    axis.set_aspect("equal", adjustable="box")
    for spine in axis.spines.values():
        spine.set_color("#e4e4e7")
        spine.set_linewidth(0.8)


def _field_title(field_number: int, field_points: list[dict[str, Any]]) -> str:
    first = field_points[0]
    field_x = float(first["field_x"])
    field_y = float(first["field_y"])
    field_type = str(first["field_type"])
    if "angle" in field_type.lower():
        field_position = f"X={field_x:.4g}°, Y={field_y:.4g}°"
    else:
        field_position = f"X={field_x:.4g}, Y={field_y:.4g} ({field_type})"

    valid_count = sum(int(item["valid_ray_count"]) for item in field_points)
    requested_count = sum(int(item["requested_ray_count"]) for item in field_points)
    valid_pct = 100.0 * valid_count / requested_count
    return (
        f"Field {field_number} · {field_position}\n"
        f"valid rays {valid_count}/{requested_count} ({valid_pct:.1f}%)"
    )


def _plot_spot_diagram(
    plt: Any,
    points: list[dict[str, Any]],
    output_path: Path,
) -> None:
    field_numbers = sorted({int(item["field"]) for item in points})
    wavelength_numbers = sorted({int(item["wavelength"]) for item in points})
    figure, axes = plt.subplots(
        1,
        len(field_numbers),
        figsize=(5 * len(field_numbers), 5),
        squeeze=False,
    )
    wave_colors = ("#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c")
    wave_markers = ("o", "^", "s", "D", "P")
    centered_fields: dict[
        int, list[tuple[dict[str, Any], list[float], list[float]]]
    ] = {}
    global_extent_um = 0.0

    for field_number in field_numbers:
        field_points = [
            item for item in points if int(item["field"]) == field_number
        ]
        all_x = [
            float(value) for item in field_points for value in item["x_um"]
        ]
        all_y = [
            float(value) for item in field_points for value in item["y_um"]
        ]
        centroid_x = sum(all_x) / len(all_x) if all_x else 0.0
        centroid_y = sum(all_y) / len(all_y) if all_y else 0.0
        centered_fields[field_number] = []
        for item in field_points:
            centered_x = [float(value) - centroid_x for value in item["x_um"]]
            centered_y = [float(value) - centroid_y for value in item["y_um"]]
            centered_fields[field_number].append((item, centered_x, centered_y))
            if centered_x:
                global_extent_um = max(
                    global_extent_um, max(abs(value) for value in centered_x)
                )
            if centered_y:
                global_extent_um = max(
                    global_extent_um, max(abs(value) for value in centered_y)
                )

    global_extent_um = max(global_extent_um * 1.08, 1.0)
    for axis, field_number in zip(axes[0], field_numbers):
        field_points = [item for item, _, _ in centered_fields[field_number]]
        for item, centered_x, centered_y in centered_fields[field_number]:
            wavelength_index = int(item["wavelength"]) - 1
            axis.scatter(
                centered_x,
                centered_y,
                s=9,
                alpha=0.6,
                color=wave_colors[wavelength_index % len(wave_colors)],
                marker=wave_markers[wavelength_index % len(wave_markers)],
                linewidths=0,
                label=f"{float(item['wavelength_nm']):.0f} nm",
            )

        axis.scatter(
            [0],
            [0],
            marker="+",
            s=70,
            linewidths=1.2,
            color="#0f172a",
            zorder=5,
        )
        axis.set_title(_field_title(field_number, field_points), fontsize=10, pad=10)
        axis.set_xlabel("Image X relative to centroid (µm)")
        axis.set_ylabel("Image Y relative to centroid (µm)")
        axis.set_xlim(-global_extent_um, global_extent_um)
        axis.set_ylim(-global_extent_um, global_extent_um)
        axis.grid(True, color="#cbd5e1", alpha=0.45, linewidth=0.8)
        axis.set_aspect("equal", adjustable="box")

    handles, labels = axes[0][0].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.90),
        ncol=len(wavelength_numbers),
    )
    figure.suptitle(
        "Polychromatic Spot Diagram · common scale", y=0.99, fontsize=13
    )
    figure.subplots_adjust(
        left=0.055,
        right=0.985,
        bottom=0.13,
        top=0.73,
        wspace=0.22,
    )
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def plot_report(
    report: dict[str, Any],
    output_dir: str | Path,
    spot_diagram_points: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    mpl_config_dir = Path(tempfile.gettempdir()) / "lensbot-matplotlib"
    mpl_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_config_dir))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    matplotlib.rcParams.update(LENSBOT_MPL_STYLE)

    mtf_display_xmax = _suggest_mtf_display_xmax(
        report["fft_mtf"], report["mtf_summary"]
    )
    mtf_path = output_root / "fft_mtf.png"
    mtf_figure, mtf_axis = plt.subplots(figsize=(10, 6))
    _plot_mtf(mtf_axis, report, mtf_display_xmax)
    mtf_figure.tight_layout()
    mtf_figure.savefig(mtf_path, dpi=180)
    plt.close(mtf_figure)

    distortion_path = output_root / "distortion.png"
    distortion_figure, distortion_axis = plt.subplots(figsize=(8, 5))
    _plot_grid_distortion(distortion_axis, report)
    distortion_figure.tight_layout()
    distortion_figure.savefig(distortion_path, dpi=180)
    plt.close(distortion_figure)

    figures: list[dict[str, Any]] = [
        {
            "key": "fft_mtf",
            "title": "FFT MTF",
            "path": str(mtf_path),
            "display_xmax_cy_mm": mtf_display_xmax,
        },
        {
            "key": "distortion",
            "title": "Distortion",
            "path": str(distortion_path),
        },
    ]
    if spot_diagram_points:
        diagram_path = output_root / "spot_diagram.png"
        _plot_spot_diagram(plt, spot_diagram_points, diagram_path)
        figures.append(
            {
                "key": "spot_diagram",
                "title": "Spot Diagram",
                "path": str(diagram_path),
            }
        )
    return figures
