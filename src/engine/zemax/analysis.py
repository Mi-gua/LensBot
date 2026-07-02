from __future__ import annotations

import json
import math
import os
import random
import re
from itertools import islice
from pathlib import Path
from typing import Any, Callable


MTF_FULL_MAX_FREQUENCY_CY_MM = 50.0
MTF_DIAGNOSTIC_MIN_XMAX_CY_MM = 15.0
MTF_DIAGNOSTIC_MTF50_SCALE = 2.5


class PythonStandaloneApplication:
    class LicenseException(Exception):
        pass

    class ConnectionException(Exception):
        pass

    class InitializationException(Exception):
        pass

    class SystemNotPresentException(Exception):
        pass

    def __init__(self, path: str | None = None):
        import winreg

        import clr

        key = winreg.OpenKey(
            winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER),
            r"Software\Zemax",
            0,
            winreg.KEY_READ,
        )
        try:
            zemax_root = winreg.QueryValueEx(key, "ZemaxRoot")[0]
        finally:
            winreg.CloseKey(key)

        net_helper = os.path.join(
            os.sep, zemax_root, r"ZOS-API\Libraries\ZOSAPI_NetHelper.dll"
        )
        clr.AddReference(net_helper)
        import ZOSAPI_NetHelper

        if path is None:
            is_initialized = ZOSAPI_NetHelper.ZOSAPI_Initializer.Initialize()
        else:
            is_initialized = ZOSAPI_NetHelper.ZOSAPI_Initializer.Initialize(path)

        if not is_initialized:
            raise PythonStandaloneApplication.InitializationException(
                "Unable to locate Zemax OpticStudio."
            )

        zemax_dir = ZOSAPI_NetHelper.ZOSAPI_Initializer.GetZemaxDirectory()
        clr.AddReference(os.path.join(os.sep, zemax_dir, "ZOSAPI.dll"))
        clr.AddReference(os.path.join(os.sep, zemax_dir, "ZOSAPI_Interfaces.dll"))
        import ZOSAPI

        self.ZOSAPI = ZOSAPI
        self.TheConnection = ZOSAPI.ZOSAPI_Connection()
        if self.TheConnection is None:
            raise PythonStandaloneApplication.ConnectionException(
                "Unable to initialize .NET connection to ZOSAPI."
            )

        self.TheApplication = self.TheConnection.CreateNewApplication()
        if self.TheApplication is None:
            raise PythonStandaloneApplication.InitializationException(
                "Unable to acquire ZOSAPI application."
            )

        if self.TheApplication.IsValidLicenseForAPI is False:
            raise PythonStandaloneApplication.LicenseException(
                "License is not valid for ZOSAPI use."
            )

        self.TheSystem = self.TheApplication.PrimarySystem
        if self.TheSystem is None:
            raise PythonStandaloneApplication.SystemNotPresentException(
                "Unable to acquire Primary system."
            )

    def __del__(self):
        if getattr(self, "TheApplication", None) is not None:
            try:
                self.TheApplication.CloseApplication()
            except TypeError:
                pass
            self.TheApplication = None
        self.TheConnection = None

    def reshape(self, data: Any, x: int, y: int, transpose: bool = False) -> list[list[Any]]:
        if type(data) is not list:
            data = list(data)
        row_lengths = [y] * x
        iterator = iter(data)
        result = [list(islice(iterator, row_length)) for row_length in row_lengths]
        if transpose:
            return self.transpose(result)
        return result

    @staticmethod
    def transpose(data: Any) -> list[list[Any]]:
        if type(data) is not list:
            data = list(data)
        return list(map(list, zip(*data)))


def _as_float(value: Any) -> float:
    return float(value)


def _as_float_list(values: Any) -> list[float]:
    return [float(value) for value in list(values)]


def _first_non_empty_string(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _safe_getattr(obj: Any, name: str) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return None


def _extract_field_label(series: Any, series_index: int) -> str:
    description = _first_non_empty_string(
        _safe_getattr(series, "Description"),
        _safe_getattr(series, "SeriesLabel"),
        _safe_getattr(series, "Label"),
    )
    if description:
        return description
    return f"Field {series_index + 1}"


def _extract_frequency_axis_metadata(analysis: Any, results: Any) -> dict[str, str]:
    x_label = _first_non_empty_string(
        _safe_getattr(results, "XLabel"),
        _safe_getattr(analysis, "XLabel"),
        "Spatial frequency",
    )
    x_unit = _first_non_empty_string(
        _safe_getattr(results, "XUnits"),
        _safe_getattr(analysis, "XUnits"),
    )

    label_lower = x_label.lower()
    if x_unit and x_unit.lower() not in label_lower:
        axis_label = f"{x_label} ({x_unit})"
    else:
        axis_label = x_label

    return {
        "frequency_axis_label": axis_label,
        "frequency_unit": x_unit or "unknown",
    }


def _clean_field_label_for_legend(field_label: str, field_index: int) -> str:
    text = field_label.strip()
    if not text:
        return f"Field {field_index + 1}"

    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if match:
        return f"Field {field_index + 1} ({match.group(0)})"

    return text


def _mtf50(freq_values: list[float], mtf_values: list[float]) -> float | None:
    if not freq_values or not mtf_values:
        return None

    pairs = list(zip(freq_values, mtf_values))
    for index, (_freq, mtf) in enumerate(pairs):
        if mtf > 0.5:
            continue
        if index == 0:
            return float(pairs[0][0])

        x1, y1 = pairs[index - 1]
        x2, y2 = pairs[index]
        if abs(y2 - y1) < 1e-12:
            return float(x2)

        t = (0.5 - y1) / (y2 - y1)
        return float(x1 + t * (x2 - x1))

    return float(pairs[-1][0])


def summarize_mtf_metrics(mtf_series: list[dict[str, Any]]) -> dict[str, Any]:
    series_metrics = []
    for series in mtf_series:
        freq = [float(value) for value in series.get("frequency_values", [])]
        tangential = [float(value) for value in series.get("tangential", [])]
        sagittal = [float(value) for value in series.get("sagittal", [])]
        series_metrics.append(
            {
                "series_index": int(series.get("series_index", len(series_metrics))),
                "field_label": series.get("field_label", ""),
                "mtf50_tangential": _mtf50(freq, tangential),
                "mtf50_sagittal": _mtf50(freq, sagittal),
            }
        )

    if not series_metrics:
        return {"series": []}

    center = series_metrics[0]
    edge = series_metrics[-1]
    return {
        "series": series_metrics,
        "mtf50_center_tangential": center.get("mtf50_tangential"),
        "mtf50_center_sagittal": center.get("mtf50_sagittal"),
        "mtf50_edge_tangential": edge.get("mtf50_tangential"),
        "mtf50_edge_sagittal": edge.get("mtf50_sagittal"),
    }


def _get_primary_wavelength_number(system: Any) -> int:
    wavelengths = _safe_getattr(system.SystemData, "Wavelengths")
    primary = _safe_getattr(wavelengths, "PrimaryWavelength")
    try:
        value = int(primary)
        return value if value > 0 else 1
    except (TypeError, ValueError):
        return 1


def _get_operand_value(
    zos: PythonStandaloneApplication,
    system: Any,
    operand_name: str,
    *args: Any,
) -> float | None:
    try:
        operand_type = getattr(zos.ZOSAPI.Editors.MFE.MeritOperandType, operand_name)
        padded_args = list(args[:8]) + [0] * max(0, 8 - len(args))
        return float(system.MFE.GetOperandValue(operand_type, *padded_args[:8]))
    except Exception:
        return None


def _load_deeplens_sidecar(lens_file: Path) -> dict[str, Any]:
    sidecar = lens_file.with_suffix(".json")
    if not sidecar.exists():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _coerce_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _reasonable_fnum(value: Any) -> float | None:
    number = _coerce_float(value)
    if number is None or number <= 0 or number > 1000:
        return None
    return number


def get_field_summary(system: Any) -> dict[str, Any]:
    fields = system.SystemData.Fields
    field_count = int(fields.NumberOfFields)
    values = []
    for field_number in range(1, field_count + 1):
        field = fields.GetField(field_number)
        x = float(field.X)
        y = float(field.Y)
        values.append(
            {
                "field": field_number,
                "x": x,
                "y": y,
                "radius": (x * x + y * y) ** 0.5,
            }
        )

    max_radius = max((item["radius"] for item in values), default=0.0)
    field_type = str(_safe_getattr(fields, "FieldType") or "")
    return {
        "field_type": field_type,
        "fields": values,
        "max_field": max_radius,
        "fov_deg": max_radius * 2.0,
    }


def get_system_metrics(
    zos: PythonStandaloneApplication,
    system: Any,
    lens_file: str | Path | None = None,
) -> dict[str, Any]:
    image_surface = int(system.LDE.NumberOfSurfaces)
    wavelength = _get_primary_wavelength_number(system)
    field_summary = get_field_summary(system)
    sidecar = _load_deeplens_sidecar(Path(lens_file)) if lens_file else {}

    efl = _get_operand_value(zos, system, "EFFL", 0, wavelength, 0, 0, 0, 0, 0, 0)
    if efl is None:
        efl = _get_operand_value(zos, system, "EFLY", 0, wavelength, 0, 0, 0, 0, 0, 0)

    fnum_operand = _get_operand_value(zos, system, "FNUM", 0, wavelength, 0, 0, 0, 0, 0, 0)
    fnum = _reasonable_fnum(fnum_operand)
    fnum_source = "zemax_operand"
    if fnum is None:
        fnum = _reasonable_fnum(sidecar.get("fnum"))
        fnum_source = "deeplens_sidecar" if fnum is not None else "unavailable"
    if fnum is None and efl:
        aperture_value = _safe_getattr(system.SystemData.Aperture, "ApertureValue")
        try:
            aperture_value = float(aperture_value)
            if aperture_value > 0:
                fnum = _reasonable_fnum(abs(float(efl)) / aperture_value)
                if fnum is not None:
                    fnum_source = "efl_over_aperture"
        except (TypeError, ValueError):
            pass

    return {
        "efl_mm": efl,
        "fnum": fnum,
        "fnum_source": fnum_source,
        "fnum_operand_raw": fnum_operand,
        "fov_deg": field_summary["fov_deg"],
        "field_type": field_summary["field_type"],
        "fields": field_summary["fields"],
        "distortion": get_distortion_metrics(
            zos,
            system,
            image_surface=image_surface,
            wavelength=wavelength,
            field_summary=field_summary,
            efl_mm=efl,
        ),
    }


def get_distortion_metrics(
    zos: PythonStandaloneApplication,
    system: Any,
    *,
    image_surface: int,
    wavelength: int,
    field_summary: dict[str, Any],
    efl_mm: float | None,
) -> dict[str, Any]:
    max_field = float(field_summary.get("max_field") or 0.0)
    values = []
    for field in field_summary.get("fields", []):
        if max_field > 0:
            hx = float(field["x"]) / max_field
            hy = float(field["y"]) / max_field
        else:
            hx = 0.0
            hy = 0.0
        value = None
        actual_y = _get_operand_value(
            zos,
            system,
            "REAY",
            image_surface,
            wavelength,
            0,
            hy,
            0,
            0,
            0,
            0,
        )
        if actual_y is not None and efl_mm and abs(float(field["y"])) > 1e-12:
            ideal_y = abs(float(efl_mm)) * math.tan(math.radians(abs(float(field["y"]))))
            if abs(ideal_y) > 1e-12:
                value = (abs(float(actual_y)) / ideal_y - 1.0) * 100.0

        if value is None:
            value = _get_operand_value(
                zos,
                system,
                "DIST",
                image_surface,
                wavelength,
                hx,
                hy,
                0,
                0,
                0,
                0,
            )
        values.append(
            {
                "field": field["field"],
                "distortion_pct": value,
                "actual_image_y": actual_y,
                "field_y_deg": field["y"],
            }
        )

    finite_values = [
        abs(float(item["distortion_pct"]))
        for item in values
        if item.get("distortion_pct") is not None
    ]
    return {
        "by_field": values,
        "edge_pct": values[-1]["distortion_pct"] if values else None,
        "abs_max_pct": max(finite_values) if finite_values else None,
    }


def get_fft_mtf_metrics(zos: PythonStandaloneApplication, system: Any) -> list[dict[str, Any]]:
    analysis = system.Analyses.New_FftMtf()
    try:
        settings = analysis.GetSettings()
        settings.MaximumFrequency = MTF_FULL_MAX_FREQUENCY_CY_MM
        settings.SampleSize = zos.ZOSAPI.Analysis.SampleSizes.S_256x256

        analysis.ApplyAndWaitForCompletion()
        results = analysis.GetResults()
        axis_metadata = _extract_frequency_axis_metadata(analysis, results)

        metrics = []
        for series_index in range(results.NumberOfDataSeries):
            series = results.GetDataSeries(series_index)
            x_values = _as_float_list(series.XData.Data)
            y_values = zos.reshape(
                series.YData.Data,
                series.YData.Data.GetLength(0),
                series.YData.Data.GetLength(1),
                True,
            )

            tangential = [_as_float(value) for value in y_values[0]] if len(y_values) > 0 else []
            sagittal = [_as_float(value) for value in y_values[1]] if len(y_values) > 1 else []

            metrics.append(
                {
                    "series_index": int(series_index),
                    "field_label": _extract_field_label(series, series_index),
                    "frequency_axis_label": axis_metadata["frequency_axis_label"],
                    "frequency_unit": axis_metadata["frequency_unit"],
                    "frequency_values": x_values,
                    "frequency_cycles_per_mm": x_values,
                    "tangential": tangential,
                    "sagittal": sagittal,
                }
            )

        return metrics
    finally:
        analysis.Close()


def get_spot_metrics(zos: PythonStandaloneApplication, system: Any) -> list[dict[str, Any]]:
    analysis = system.Analyses.New_Analysis(
        zos.ZOSAPI.Analysis.AnalysisIDM.StandardSpot
    )
    try:
        settings = analysis.GetSettings()
        if hasattr(settings, "Field"):
            settings.Field.SetFieldNumber(0)
        if hasattr(settings, "Wavelength"):
            settings.Wavelength.SetWavelengthNumber(0)
        if hasattr(settings, "ReferTo"):
            settings.ReferTo = zos.ZOSAPI.Analysis.Settings.RMS.ReferTo.Centroid

        analysis.ApplyAndWaitForCompletion()
        results = analysis.GetResults()

        field_count = int(system.SystemData.Fields.NumberOfFields)
        metrics = []
        for field_number in range(1, field_count + 1):
            metrics.append(
                {
                    "field": field_number,
                    "wavelength": "all",
                    "rms_spot_radius": _as_float(
                        results.SpotData.GetRMSSpotSizeFor(field_number, 1)
                    ),
                    "geo_spot_radius": _as_float(
                        results.SpotData.GetGeoSpotSizeFor(field_number, 1)
                    ),
                }
            )

        return metrics
    finally:
        analysis.Close()


def summarize_spot_metrics(spot_metrics: list[dict[str, Any]]) -> dict[str, float]:
    if not spot_metrics:
        return {}

    rms_values = [float(item["rms_spot_radius"]) for item in spot_metrics]
    geo_values = [float(item["geo_spot_radius"]) for item in spot_metrics]

    return {
        "rms_spot_radius_min": min(rms_values),
        "rms_spot_radius_max": max(rms_values),
        "rms_spot_radius_edge": rms_values[-1],
        "geo_spot_radius_min": min(geo_values),
        "geo_spot_radius_max": max(geo_values),
        "geo_spot_radius_edge": geo_values[-1],
    }


def get_spot_diagram_points(
    zos: PythonStandaloneApplication,
    system: Any,
    rays_per_field_wave: int = 300,
    seed: int = 42,
) -> list[dict[str, Any]]:
    import clr  # noqa: F401 - pythonnet must load System types before importing them.
    from System import Double, Enum, Int32

    raytrace = system.Tools.OpenBatchRayTrace()
    try:
        image_surface = int(system.LDE.NumberOfSurfaces)
        ray_data = raytrace.CreateNormUnpol(
            rays_per_field_wave,
            zos.ZOSAPI.Tools.RayTrace.RaysType.Real,
            image_surface,
        )

        field_count = int(system.SystemData.Fields.NumberOfFields)
        wave_count = int(system.SystemData.Wavelengths.NumberOfWavelengths)
        max_field_y = max(
            abs(float(system.SystemData.Fields.GetField(index).Y))
            for index in range(1, field_count + 1)
        )
        rng = random.Random(seed)

        points = []
        for field_number in range(1, field_count + 1):
            field = system.SystemData.Fields.GetField(field_number)
            field_x = float(field.X)
            field_y = float(field.Y)
            hx = 0.0 if max_field_y == 0 else field_x / max_field_y
            hy = 0.0 if max_field_y == 0 else field_y / max_field_y

            for wavelength_number in range(1, wave_count + 1):
                ray_data.ClearData()
                for _ in range(rays_per_field_wave):
                    px = rng.uniform(-1.0, 1.0)
                    py = rng.uniform(-1.0, 1.0)
                    while px * px + py * py > 1.0:
                        px = rng.uniform(-1.0, 1.0)
                        py = rng.uniform(-1.0, 1.0)

                    ray_data.AddRay(
                        wavelength_number,
                        hx,
                        hy,
                        px,
                        py,
                        Enum.Parse(zos.ZOSAPI.Tools.RayTrace.OPDMode, "None"),
                    )

                raytrace.RunAndWaitForCompletion()
                ray_data.StartReadingResults()

                sys_int = Int32(1)
                sys_dbl = Double(1.0)
                output = ray_data.ReadNextResult(
                    sys_int,
                    sys_int,
                    sys_int,
                    sys_dbl,
                    sys_dbl,
                    sys_dbl,
                    sys_dbl,
                    sys_dbl,
                    sys_dbl,
                    sys_dbl,
                    sys_dbl,
                    sys_dbl,
                    sys_dbl,
                    sys_dbl,
                )

                x_values = []
                y_values = []
                while output[0]:
                    if output[2] == 0 and output[3] == 0:
                        x_values.append(float(output[4]))
                        y_values.append(float(output[5]))

                    output = ray_data.ReadNextResult(
                        sys_int,
                        sys_int,
                        sys_int,
                        sys_dbl,
                        sys_dbl,
                        sys_dbl,
                        sys_dbl,
                        sys_dbl,
                        sys_dbl,
                        sys_dbl,
                        sys_dbl,
                        sys_dbl,
                        sys_dbl,
                        sys_dbl,
                    )

                points.append(
                    {
                        "field": field_number,
                        "field_x": field_x,
                        "field_y": field_y,
                        "wavelength": wavelength_number,
                        "x": x_values,
                        "y": y_values,
                    }
                )

        return points
    finally:
        raytrace.Close()


def _plot_zemax_summary(report: dict[str, Any], output_dir: Path) -> Path:
    import matplotlib.pyplot as plt

    summary_path = output_dir / "zemax_summary.png"
    spot_summary = report.get("spot_summary", {})
    system_metrics = report.get("system_metrics", {})
    distortion = system_metrics.get("distortion", {}) if isinstance(system_metrics, dict) else {}
    mtf_summary = report.get("mtf_summary", {})
    rows = [
        ("Lens unit", report.get("lens_unit", "-")),
        ("EFL", _format_number(system_metrics.get("efl_mm"), "mm")),
        ("F/#", _format_number(system_metrics.get("fnum"))),
        ("FOV", _format_number(system_metrics.get("fov_deg"), "deg")),
        ("Distortion max", _format_number(distortion.get("abs_max_pct"), "%")),
        ("MTF50 edge T", _format_number(mtf_summary.get("mtf50_edge_tangential"), "cy/mm")),
        ("Fields", report.get("field_count", "-")),
        ("Wavelengths", report.get("wavelength_count", "-")),
        ("RMS min", _format_number(spot_summary.get("rms_spot_radius_min"), report.get("spot_unit"))),
        ("RMS max", _format_number(spot_summary.get("rms_spot_radius_max"), report.get("spot_unit"))),
        ("GEO min", _format_number(spot_summary.get("geo_spot_radius_min"), report.get("spot_unit"))),
        ("GEO max", _format_number(spot_summary.get("geo_spot_radius_max"), report.get("spot_unit"))),
    ]

    figure, axis = plt.subplots(figsize=(8, 5))
    axis.axis("off")
    axis.set_title("Zemax Analysis Summary", fontsize=15, pad=18)
    table = axis.table(
        cellText=[[label, str(value)] for label, value in rows],
        colLabels=["Metric", "Value"],
        loc="center",
        cellLoc="left",
        colLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.55)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#d1d5db")
        if row == 0:
            cell.set_facecolor("#111827")
            cell.set_text_props(color="white", weight="bold")
        elif col == 0:
            cell.set_facecolor("#f8fafc")
            cell.set_text_props(weight="bold")
    figure.tight_layout()
    figure.savefig(summary_path, dpi=180)
    plt.close(figure)
    return summary_path


def _format_number(value: Any, unit: str | None = None) -> str:
    if value in (None, ""):
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    suffix = f" {unit}" if unit else ""
    return f"{number:.6g}{suffix}"


def _finite_positive_frequencies(mtf_series: list[dict[str, Any]]) -> list[float]:
    finite_freqs: list[float] = []

    for series in mtf_series:
        freqs = series.get("frequency_values") or series.get("frequency_cycles_per_mm") or []
        for raw_freq in freqs:
            try:
                freq = float(raw_freq)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(freq) or freq <= 0:
                continue
            finite_freqs.append(freq)

    return finite_freqs


def _finite_mtf50_values(
    mtf_series: list[dict[str, Any]],
    mtf_summary: dict[str, Any] | None = None,
) -> list[float]:
    values: list[float] = []
    summary_series = []
    if isinstance(mtf_summary, dict):
        raw_summary_series = mtf_summary.get("series")
        if isinstance(raw_summary_series, list):
            summary_series = raw_summary_series

    for series_summary in summary_series:
        if not isinstance(series_summary, dict):
            continue
        for key in ("mtf50_tangential", "mtf50_sagittal"):
            try:
                value = float(series_summary.get(key))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value) and value > 0:
                values.append(value)

    if values:
        return values

    for series in mtf_series:
        freqs = [float(value) for value in series.get("frequency_values", [])]
        for key in ("tangential", "sagittal"):
            mtf_values = [float(value) for value in series.get(key, [])]
            value = _mtf50(freqs, mtf_values)
            if value is not None and math.isfinite(value) and value > 0:
                values.append(value)

    return values


def _suggest_mtf_diagnostic_xmax(
    mtf_series: list[dict[str, Any]],
    mtf_summary: dict[str, Any] | None = None,
) -> float | None:
    finite_freqs = _finite_positive_frequencies(mtf_series)

    if not finite_freqs:
        return None

    raw_max = max(finite_freqs)
    mtf50_values = _finite_mtf50_values(mtf_series, mtf_summary)
    if mtf50_values:
        diagnostic_xmax = max(MTF_DIAGNOSTIC_MIN_XMAX_CY_MM, MTF_DIAGNOSTIC_MTF50_SCALE * max(mtf50_values))
        return min(raw_max, diagnostic_xmax)

    return min(raw_max, MTF_FULL_MAX_FREQUENCY_CY_MM)


def _suggest_mtf_full_xmax(mtf_series: list[dict[str, Any]]) -> float:
    finite_freqs = _finite_positive_frequencies(mtf_series)
    if not finite_freqs:
        return MTF_FULL_MAX_FREQUENCY_CY_MM
    return min(max(finite_freqs), MTF_FULL_MAX_FREQUENCY_CY_MM)


def _plot_mtf_series(
    plt: Any,
    report: dict[str, Any],
    *,
    xlim_right: float | None,
    title: str,
) -> None:
    colors = ("tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple")
    mtf_series = report.get("fft_mtf", [])
    axis_label = "Spatial frequency"
    if mtf_series:
        axis_label = str(mtf_series[0].get("frequency_axis_label") or axis_label)
    if "cy/mm" not in axis_label and "cycles" not in axis_label.lower():
        axis_label = f"{axis_label} (cy/mm)"

    for series in mtf_series:
        idx = int(series["series_index"])
        color = colors[idx % len(colors)]
        label = _clean_field_label_for_legend(str(series.get("field_label", "")), idx)
        freq = series.get("frequency_values") or series.get("frequency_cycles_per_mm") or []
        plt.plot(freq, series["tangential"], color=color, label=f"{label} T")
        plt.plot(freq, series["sagittal"], color=color, linestyle="--", label=f"{label} S")

    plt.title(title)
    plt.xlabel(axis_label)
    plt.ylabel("MTF")
    plt.ylim(bottom=0)
    if xlim_right is not None and xlim_right > 0:
        plt.xlim(left=0, right=xlim_right)
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=8)
    plt.tight_layout()


def plot_report(
    report: dict[str, Any],
    output_dir: str | Path,
    spot_diagram_points: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    mpl_config_dir = output_root / ".mplconfig"
    mpl_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_config_dir))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures: list[dict[str, str]] = []

    mtf_series = report.get("fft_mtf", [])

    mtf_path = output_root / "fft_mtf.png"
    plt.figure(figsize=(10, 6))
    mtf_xmax = _suggest_mtf_diagnostic_xmax(mtf_series, report.get("mtf_summary"))
    _plot_mtf_series(plt, report, xlim_right=mtf_xmax, title="FFT MTF diagnostic")
    plt.tight_layout()
    plt.savefig(mtf_path, dpi=180)
    plt.close()

    mtf_full_path = output_root / "fft_mtf_full.png"
    plt.figure(figsize=(10, 6))
    _plot_mtf_series(plt, report, xlim_right=_suggest_mtf_full_xmax(mtf_series), title="FFT MTF full range")
    plt.tight_layout()
    plt.savefig(mtf_full_path, dpi=180)
    plt.close()

    figures.append({"key": "fft_mtf", "title": "FFT MTF", "path": str(mtf_path)})

    field_numbers = sorted({int(item["field"]) for item in report.get("spot_metrics", [])})
    rms_by_field = []
    geo_by_field = []
    for field_number in field_numbers:
        field_items = [
            item for item in report["spot_metrics"] if int(item["field"]) == field_number
        ]
        rms_by_field.append(
            sum(float(item["rms_spot_radius"]) for item in field_items) / len(field_items)
        )
        geo_by_field.append(
            sum(float(item["geo_spot_radius"]) for item in field_items) / len(field_items)
        )

    spot_path = output_root / "spot_summary.png"
    x_values = list(range(len(field_numbers)))
    bar_width = 0.36
    plt.figure(figsize=(8, 5))
    plt.bar(
        [x - bar_width / 2 for x in x_values],
        rms_by_field,
        width=bar_width,
        label="RMS radius",
        color="tab:blue",
    )
    plt.bar(
        [x + bar_width / 2 for x in x_values],
        geo_by_field,
        width=bar_width,
        label="GEO radius",
        color="tab:orange",
    )
    plt.title("Spot Radius by Field")
    plt.xlabel("Field")
    plt.ylabel(f"Spot radius ({report.get('spot_unit', 'mm')})")
    plt.xticks(x_values, [str(field_number) for field_number in field_numbers])
    plt.grid(True, axis="y", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(spot_path, dpi=180)
    plt.close()
    figures.append({"key": "spot_summary", "title": "Spot Radius", "path": str(spot_path)})

    if spot_diagram_points:
        diagram_path = output_root / "spot_diagram.png"
        field_numbers = sorted({int(item["field"]) for item in spot_diagram_points})
        wavelength_numbers = sorted({int(item["wavelength"]) for item in spot_diagram_points})
        figure, axes = plt.subplots(
            1,
            len(field_numbers),
            figsize=(5 * len(field_numbers), 5),
            squeeze=False,
        )
        wave_colors = ("tab:blue", "tab:green", "tab:red", "tab:purple", "tab:orange")

        for axis, field_number in zip(axes[0], field_numbers):
            field_points = [
                item for item in spot_diagram_points if int(item["field"]) == field_number
            ]
            all_x = [float(value) for item in field_points for value in item["x"]]
            all_y = [float(value) for item in field_points for value in item["y"]]
            centroid_x = sum(all_x) / len(all_x) if all_x else 0.0
            centroid_y = sum(all_y) / len(all_y) if all_y else 0.0
            for item in field_points:
                color = wave_colors[(int(item["wavelength"]) - 1) % len(wave_colors)]
                axis.scatter(
                    [float(value) - centroid_x for value in item["x"]],
                    [float(value) - centroid_y for value in item["y"]],
                    s=4,
                    alpha=0.65,
                    color=color,
                    label=f"W{item['wavelength']}",
                )

            first = field_points[0]
            axis.set_title(
                "Field {field}\nX={x:.4g}, Y={y:.4g} deg".format(
                    field=field_number,
                    x=float(first["field_x"]),
                    y=float(first["field_y"]),
                )
            )
            axis.set_xlabel(f"Image X relative to centroid ({report.get('spot_unit', 'mm')})")
            axis.set_ylabel(f"Image Y relative to centroid ({report.get('spot_unit', 'mm')})")
            axis.grid(True, alpha=0.3)
            axis.set_aspect("equal", adjustable="datalim")

        handles, labels = axes[0][0].get_legend_handles_labels()
        if handles:
            figure.legend(
                handles,
                labels,
                loc="upper center",
                bbox_to_anchor=(0.5, 0.94),
                ncol=len(wavelength_numbers),
            )
        figure.suptitle("Spot Diagram", y=0.99)
        figure.tight_layout(rect=(0, 0, 1, 0.88))
        figure.savefig(diagram_path, dpi=180)
        plt.close(figure)
        figures.append({"key": "spot_diagram", "title": "Spot Diagram", "path": str(diagram_path)})
    else:
        summary_path = _plot_zemax_summary(report, output_root)
        figures.append({"key": "zemax_summary", "title": "Zemax Summary", "path": str(summary_path)})

    return figures


class ZemaxAnalysisEngine:
    """OpticStudio/ZOS-API analysis engine for exported final.zmx files."""

    def analyze(
        self,
        final_zmx: str | Path | None,
        result_dir: str | Path | None = None,
        progress_cb: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        if not final_zmx:
            return {
                "ok": False,
                "status": "skipped",
                "final_zmx": None,
                "error": "No final.zmx path was provided.",
            }

        lens_file = Path(final_zmx).resolve()
        if not lens_file.exists():
            return {
                "ok": False,
                "status": "skipped",
                "final_zmx": str(lens_file),
                "error": f"Lens file not found: {lens_file}",
            }

        output_dir = Path(result_dir).resolve() / "verification" / "zemax" if result_dir else lens_file.parent / "verification" / "zemax"
        output_dir.mkdir(parents=True, exist_ok=True)

        def emit(message: str) -> None:
            if progress_cb:
                progress_cb(message)

        emit("Zemax 分析：载入 final.zmx。")
        try:
            zos = PythonStandaloneApplication()
        except Exception as exc:
            return {
                "ok": False,
                "status": "unavailable",
                "final_zmx": str(lens_file),
                "lens_file": str(lens_file),
                "error": str(exc),
            }

        try:
            system = zos.TheSystem
            system.LoadFile(str(lens_file), False)

            emit("Zemax 分析：执行 FFT MTF 与 Spot 分析。")
            report: dict[str, Any] = {
                "ok": True,
                "status": "complete",
                "final_zmx": str(lens_file),
                "lens_file": str(lens_file),
                "lens_unit": str(system.SystemData.Units.LensUnits),
                "spot_unit": "um",
                "system_metrics": get_system_metrics(zos, system, lens_file=lens_file),
                "field_count": int(system.SystemData.Fields.NumberOfFields),
                "wavelength_count": int(system.SystemData.Wavelengths.NumberOfWavelengths),
                "spot_metrics": get_spot_metrics(zos, system),
                "spot_summary": {},
                "fft_mtf": get_fft_mtf_metrics(zos, system),
            }
            report["spot_summary"] = summarize_spot_metrics(report["spot_metrics"])
            report["mtf_summary"] = summarize_mtf_metrics(report["fft_mtf"])

            spot_diagram_points: list[dict[str, Any]] | None = None
            try:
                emit("Zemax 分析：生成 Spot Diagram。")
                spot_diagram_points = get_spot_diagram_points(zos, system)
                report["spot_diagram_points"] = spot_diagram_points
            except Exception as exc:
                report["spot_diagram_error"] = str(exc)

            emit("Zemax 分析：绘制分析图。")
            report["figures"] = plot_report(report, output_dir, spot_diagram_points)
            report["figure_files"] = [item["path"] for item in report["figures"]]

            report_path = output_dir / "zemax_report.json"
            report["report_file"] = str(report_path)
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            emit("Zemax 分析：结果和图像已归档。")
            return report
        except Exception as exc:
            return {
                "ok": False,
                "status": "failed",
                "final_zmx": str(lens_file),
                "lens_file": str(lens_file),
                "error": str(exc),
            }
        finally:
            del zos
