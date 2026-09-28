from __future__ import annotations

import json
import os
import random
from itertools import islice
from pathlib import Path
from typing import Any, Callable

from .plotting import plot_report


MTF_FULL_MAX_FREQUENCY_CY_MM = 50.0
ZEMAX_STANDARD_SPOT_UNIT = "um"
ZEMAX_STANDARD_SPOT_UNIT_SOURCE = "zosapi_standard_spot"
SPOT_DIAGRAM_UNIT = "um"
SPOT_DIAGRAM_SOURCE = "zosapi_batch_ray_trace"


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


def _lens_unit_to_micrometers_scale(lens_unit: Any) -> float:
    scales = {
        "millimeters": 1_000.0,
        "centimeters": 10_000.0,
        "meters": 1_000_000.0,
        "inches": 25_400.0,
    }
    normalized_unit = str(lens_unit).strip().lower()
    try:
        return scales[normalized_unit]
    except KeyError as exc:
        raise RuntimeError(
            f"Unsupported OpticStudio lens unit for spot diagram: {lens_unit}"
        ) from exc


def _mtf50(freq_values: list[float], mtf_values: list[float]) -> float | None:
    if not freq_values or not mtf_values:
        return None

    pairs = list(zip(freq_values, mtf_values))
    for index, (_freq, mtf) in enumerate(pairs):
        if mtf > 0.5:
            continue
        if index == 0:
            x1, y1 = 0.0, 1.0
            x2, y2 = pairs[0]
            if abs(y2 - y1) < 1e-12:
                return float(x2)
            return float(x1 + (0.5 - y1) / (y2 - y1) * (x2 - x1))

        x1, y1 = pairs[index - 1]
        x2, y2 = pairs[index]
        if abs(y2 - y1) < 1e-12:
            return float(x2)

        t = (0.5 - y1) / (y2 - y1)
        return float(x1 + t * (x2 - x1))

    return None


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
    wavelengths = system.SystemData.Wavelengths
    for number in range(1, int(wavelengths.NumberOfWavelengths) + 1):
        wavelength = wavelengths.GetWavelength(number)
        if wavelength.IsPrimary:
            return int(wavelength.WavelengthNumber)
    raise RuntimeError("OpticStudio system has no primary wavelength.")


def _read_native_first_order_data(system: Any) -> dict[str, float]:
    efl, paraxial_fnum, real_fnum, image_height, magnification = (
        system.LDE.GetFirstOrderData(0.0, 0.0, 0.0, 0.0, 0.0)
    )
    return {
        "efl_mm": float(efl),
        "paraxial_working_fnum": float(paraxial_fnum),
        "real_working_fnum": float(real_fnum),
        "paraxial_image_height_mm": float(image_height),
        "paraxial_magnification": float(magnification),
    }


def _read_native_pupil_data(
    zos: PythonStandaloneApplication, system: Any
) -> dict[str, Any]:
    apodization_none = getattr(
        zos.ZOSAPI.Editors.LDE.PupilApodizationType, "None"
    )
    values = system.LDE.GetPupil(
        system.SystemData.Aperture.ApertureType,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        apodization_none,
        0.0,
    )
    return {
        "aperture_type": str(values[0]),
        "aperture_value": float(values[1]),
        "entrance_pupil_diameter_mm": float(values[2]),
        "entrance_pupil_position_mm": float(values[3]),
        "exit_pupil_diameter_mm": float(values[4]),
        "exit_pupil_position_mm": float(values[5]),
        "apodization_type": str(values[6]),
        "apodization_factor": float(values[7]),
    }


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
    field_type = str(fields.GetFieldType())
    return {
        "field_type": field_type,
        "fields": values,
        "max_field": max_radius,
        "fov_deg": max_radius * 2.0,
    }


def get_system_metrics(
    zos: PythonStandaloneApplication,
    system: Any,
) -> dict[str, Any]:
    wavelength = _get_primary_wavelength_number(system)
    field_summary = get_field_summary(system)
    first_order = _read_native_first_order_data(system)
    pupil = _read_native_pupil_data(zos, system)

    return {
        "metric_source": "zemax_zosapi",
        "primary_wavelength_number": wavelength,
        "efl_mm": first_order["efl_mm"],
        "efl_unit": "mm",
        "efl_source": "zosapi_first_order_data",
        "fnum": first_order["paraxial_working_fnum"],
        "fnum_source": "zosapi_first_order_paraxial_working_fnum",
        "real_working_fnum": first_order["real_working_fnum"],
        "paraxial_image_height_mm": first_order["paraxial_image_height_mm"],
        "paraxial_magnification": first_order["paraxial_magnification"],
        "pupil": pupil,
        "fov_deg": field_summary["fov_deg"],
        "fov_unit": "deg",
        "fov_source": "zemax_field_data",
        "field_type": field_summary["field_type"],
        "fields": field_summary["fields"],
        "distortion": get_distortion_metrics(
            zos,
            system,
            wavelength=wavelength,
        ),
    }


def get_distortion_metrics(
    zos: PythonStandaloneApplication,
    system: Any,
    *,
    wavelength: int,
) -> dict[str, Any]:
    analysis = system.Analyses.New_FieldCurvatureAndDistortion()
    try:
        settings = (
            zos.ZOSAPI.Analysis.Settings.Aberrations.IAS_FieldCurvatureAndDistortion(
                analysis.GetSettings()
            )
        )
        settings.Wavelength.SetWavelengthNumber(wavelength)
        settings.IgnoreVignette = False
        analysis.ApplyAndWaitForCompletion()
        series = analysis.GetResults().GetDataSeries(0)
        fields = _as_float_list(series.XData.Data)
        data = zos.reshape(
            series.YData.Data,
            series.YData.Data.GetLength(0),
            series.YData.Data.GetLength(1),
            True,
        )
        distortion = [_as_float(value) for value in data[-1]]
        return {
            "field_samples_deg": fields,
            "distortion_pct": distortion,
            "edge_pct": distortion[-1],
            "abs_max_pct": max(abs(value) for value in distortion),
            "unit": "percent",
            "definition": "OpticStudio Field Curvature and Distortion analysis",
            "source": "zosapi_field_curvature_and_distortion",
        }
    finally:
        analysis.Close()


def _parse_grid_distortion_text(text: str) -> dict[str, Any]:
    points = []
    for line in text.splitlines():
        columns = line.replace("%", "").split()
        if len(columns) != 10:
            continue
        try:
            values = [float(value) for value in columns]
        except ValueError:
            continue
        points.append(
            {
                "i": int(values[0]),
                "j": int(values[1]),
                "field_x": values[2],
                "field_y": values[3],
                "field_radius": values[4],
                "predicted_x": values[5],
                "predicted_y": values[6],
                "actual_x": values[7],
                "actual_y": values[8],
                "distortion_pct": values[9],
            }
        )

    if not points:
        raise RuntimeError("OpticStudio Grid Distortion returned no numeric points.")

    distortion_values = [float(point["distortion_pct"]) for point in points]
    return {
        "points": points,
        "max_abs_pct": max(abs(value) for value in distortion_values),
        "rms_pct": (
            sum(value * value for value in distortion_values)
            / len(distortion_values)
        )
        ** 0.5,
    }


def get_grid_distortion_metrics(
    zos: PythonStandaloneApplication,
    system: Any,
    *,
    wavelength: int,
    text_path: Path,
) -> dict[str, Any]:
    analysis = system.Analyses.New_GridDistortion()
    try:
        settings = zos.ZOSAPI.Analysis.Settings.Aberrations.IAS_GridDistortion(
            analysis.GetSettings()
        )
        settings.Wavelength.SetWavelengthNumber(wavelength)
        settings.GridNumber = 9
        analysis.ApplyAndWaitForCompletion()

        text_path.parent.mkdir(parents=True, exist_ok=True)
        if not analysis.GetResults().GetTextFile(str(text_path)):
            raise RuntimeError("OpticStudio Grid Distortion text export failed.")

        metrics = _parse_grid_distortion_text(
            text_path.read_text(encoding="utf-16")
        )
        metrics.update(
            {
                "source": "zosapi_grid_distortion",
                "definition": "OpticStudio Grid Distortion analysis",
                "wavelength_number": wavelength,
                "coordinate_unit": str(system.SystemData.Units.LensUnits),
                "text_file": str(text_path),
            }
        )
        return metrics
    finally:
        analysis.Close()


def _read_mtf_series(
    zos: PythonStandaloneApplication, analysis: Any
) -> list[dict[str, Any]]:
    results = analysis.GetResults()
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
        metrics.append(
            {
                "series_index": int(series_index),
                "field_label": str(series.Description),
                "frequency_axis_label": "Spatial frequency (cycles/mm)",
                "frequency_unit": "cycles/mm",
                "frequency_values": x_values,
                "tangential": [_as_float(value) for value in y_values[0]],
                "sagittal": [_as_float(value) for value in y_values[1]],
            }
        )

    if metrics and metrics[0]["frequency_values"][-1] != MTF_FULL_MAX_FREQUENCY_CY_MM:
        raise RuntimeError("OpticStudio MTF frequency setting was not applied.")
    return metrics


def get_fft_mtf_metrics(
    zos: PythonStandaloneApplication, system: Any
) -> list[dict[str, Any]]:
    analysis = system.Analyses.New_FftMtf()
    try:
        settings = zos.ZOSAPI.Analysis.Settings.Mtf.IAS_FftMtf(
            analysis.GetSettings()
        )
        settings.Field.SetFieldNumber(0)
        settings.Wavelength.SetWavelengthNumber(0)
        settings.Type = zos.ZOSAPI.Analysis.Settings.Mtf.MtfTypes.Modulation
        settings.MaximumFrequency = MTF_FULL_MAX_FREQUENCY_CY_MM
        settings.SampleSize = zos.ZOSAPI.Analysis.SampleSizes.S_256x256

        analysis.ApplyAndWaitForCompletion()
        return _read_mtf_series(zos, analysis)
    finally:
        analysis.Close()


def get_geometric_mtf_metrics(
    zos: PythonStandaloneApplication,
    system: Any,
    *,
    wavelength: int,
) -> list[dict[str, Any]]:
    analysis = system.Analyses.New_GeometricMtf()
    try:
        settings = zos.ZOSAPI.Analysis.Settings.Mtf.IAS_GeometricMtf(
            analysis.GetSettings()
        )
        settings.Field.SetFieldNumber(0)
        settings.Wavelength.SetWavelengthNumber(wavelength)
        settings.MaximumFrequency = MTF_FULL_MAX_FREQUENCY_CY_MM
        settings.SampleSize = zos.ZOSAPI.Analysis.SampleSizes.S_256x256
        settings.MultiplyByDiffractionLimit = False

        analysis.ApplyAndWaitForCompletion()
        return _read_mtf_series(zos, analysis)
    finally:
        analysis.Close()


def get_spot_metrics(zos: PythonStandaloneApplication, system: Any) -> list[dict[str, Any]]:
    analysis = system.Analyses.New_StandardSpot()
    try:
        settings = zos.ZOSAPI.Analysis.Settings.Spot.IAS_Spot(
            analysis.GetSettings()
        )
        settings.Field.SetFieldNumber(0)
        settings.Wavelength.SetWavelengthNumber(0)
        settings.ReferTo = zos.ZOSAPI.Analysis.Settings.Spot.Reference.Centroid

        analysis.ApplyAndWaitForCompletion()
        results = analysis.GetResults()

        field_count = int(system.SystemData.Fields.NumberOfFields)
        return [
            {
                "field": field_number,
                "wavelength": "all",
                "reference": "centroid",
                "rms_spot_radius": _as_float(
                    results.SpotData.GetRMSSpotSizeFor(field_number, 1)
                ),
                "geo_spot_radius": _as_float(
                    results.SpotData.GetGeoSpotSizeFor(field_number, 1)
                ),
            }
            for field_number in range(1, field_count + 1)
        ]
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
        lens_unit = system.SystemData.Units.LensUnits
        coordinate_scale = _lens_unit_to_micrometers_scale(lens_unit)
        ray_data = raytrace.CreateNormUnpol(
            rays_per_field_wave,
            zos.ZOSAPI.Tools.RayTrace.RaysType.Real,
            image_surface,
        )

        field_count = int(system.SystemData.Fields.NumberOfFields)
        wave_count = int(system.SystemData.Wavelengths.NumberOfWavelengths)
        field_type = str(system.SystemData.Fields.GetFieldType())
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
                wavelength_nm = (
                    float(
                        system.SystemData.Wavelengths.GetWavelength(
                            wavelength_number
                        ).Wavelength
                    )
                    * 1_000.0
                )
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
                        x_values.append(float(output[4]) * coordinate_scale)
                        y_values.append(float(output[5]) * coordinate_scale)

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
                        "field_type": field_type,
                        "wavelength": wavelength_number,
                        "wavelength_nm": wavelength_nm,
                        "requested_ray_count": rays_per_field_wave,
                        "valid_ray_count": len(x_values),
                        "coordinate_unit": SPOT_DIAGRAM_UNIT,
                        "coordinate_source": SPOT_DIAGRAM_SOURCE,
                        "x_um": x_values,
                        "y_um": y_values,
                    }
                )

        return points
    finally:
        raytrace.Close()


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

            emit("Zemax 分析：执行 FFT MTF、Geometric MTF 与 Spot 分析。")
            system_metrics = get_system_metrics(zos, system)
            grid_distortion = get_grid_distortion_metrics(
                zos,
                system,
                wavelength=system_metrics["primary_wavelength_number"],
                text_path=output_dir / "grid_distortion.txt",
            )
            report: dict[str, Any] = {
                "ok": True,
                "status": "complete",
                "final_zmx": str(lens_file),
                "lens_file": str(lens_file),
                "metric_source": "zemax_zosapi",
                "lens_unit": str(system.SystemData.Units.LensUnits),
                "spot_unit": ZEMAX_STANDARD_SPOT_UNIT,
                "spot_unit_source": ZEMAX_STANDARD_SPOT_UNIT_SOURCE,
                "fft_mtf_definition": "polychromatic diffraction FFT MTF",
                "geometric_mtf_definition": (
                    "primary-wavelength geometric MTF without diffraction-limit multiplication"
                ),
                "system_metrics": system_metrics,
                "grid_distortion": grid_distortion,
                "field_count": int(system.SystemData.Fields.NumberOfFields),
                "wavelength_count": int(system.SystemData.Wavelengths.NumberOfWavelengths),
                "spot_metrics": get_spot_metrics(zos, system),
                "spot_summary": {},
                "fft_mtf": get_fft_mtf_metrics(zos, system),
                "geometric_mtf": get_geometric_mtf_metrics(
                    zos,
                    system,
                    wavelength=system_metrics["primary_wavelength_number"],
                ),
            }
            report["spot_summary"] = summarize_spot_metrics(report["spot_metrics"])
            report["mtf_summary"] = summarize_mtf_metrics(report["fft_mtf"])
            report["geometric_mtf_summary"] = summarize_mtf_metrics(
                report["geometric_mtf"]
            )

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
