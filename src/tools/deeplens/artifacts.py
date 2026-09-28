from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DeepLensArtifacts:
    result_dir: str
    analysis_lens_json: str
    analysis_stage: str
    has_curriculum_json: bool
    has_candidate_json: bool
    has_candidate_zmx: bool
    has_final_json: bool
    has_final_zmx: bool
    candidate_json: str
    candidate_zmx: str
    candidate_png: str
    final_json: str
    final_zmx: str
    curriculum_json: str


def find_lens_artifacts(
    project_root: str | Path,
    *,
    result_dir: str | Path | None = None,
    lens_json: str | Path | None = None,
) -> DeepLensArtifacts:
    root = _resolve_result_dir(project_root, result_dir=result_dir, lens_json=lens_json)
    explicit_lens = _resolve_path(project_root, lens_json) if lens_json else None
    final_json = root / "final" / "final.json"
    final_zmx = root / "final" / "final.zmx"
    candidate_json = _latest_candidate_artifact(root, "lens.json")
    candidate_zmx = _candidate_sibling(candidate_json, "lens.zmx")
    candidate_png = _candidate_sibling(candidate_json, "lens.png")
    curriculum_candidates = _curriculum_candidates(root)
    curriculum_json = curriculum_candidates[0] if curriculum_candidates else None

    has_candidate_json = bool(candidate_json and candidate_json.exists())
    has_candidate_zmx = bool(candidate_zmx and candidate_zmx.exists())
    has_candidate_png = bool(candidate_png and candidate_png.exists())
    has_final_json = final_json.exists()
    has_final_zmx = final_zmx.exists()

    if explicit_lens is not None:
        analysis_lens = explicit_lens
        stage = _stage_for_lens(root, explicit_lens)
        if stage == "candidate":
            candidate_json = explicit_lens
            candidate_zmx = _candidate_sibling(candidate_json, "lens.zmx")
            candidate_png = _candidate_sibling(candidate_json, "lens.png")
            has_candidate_json = candidate_json.exists()
            has_candidate_zmx = bool(candidate_zmx and candidate_zmx.exists())
            has_candidate_png = bool(candidate_png and candidate_png.exists())
    elif has_final_json and has_final_zmx:
        analysis_lens = final_json
        stage = "final"
    elif has_candidate_json:
        analysis_lens = candidate_json
        stage = "candidate"
    elif has_final_json:
        analysis_lens = final_json
        stage = "final"
    else:
        analysis_lens = curriculum_json or root / "engines" / "deeplens" / "attempts" / "curriculum.json"
        stage = "curriculum"

    return DeepLensArtifacts(
        result_dir=str(root),
        analysis_lens_json=str(analysis_lens),
        analysis_stage=stage,
        has_curriculum_json=any(path.exists() for path in curriculum_candidates),
        has_candidate_json=has_candidate_json,
        has_candidate_zmx=has_candidate_zmx,
        has_final_json=has_final_json,
        has_final_zmx=has_final_zmx,
        candidate_json=str(candidate_json or ""),
        candidate_zmx=str(candidate_zmx) if has_candidate_zmx else "",
        candidate_png=str(candidate_png) if has_candidate_png else "",
        final_json=str(final_json),
        final_zmx=str(final_zmx) if has_final_zmx else "",
        curriculum_json=str(curriculum_json or ""),
    )


def infer_result_dir(lens_json: str | Path) -> Path:
    path = Path(lens_json).resolve()
    for parent in path.parents:
        if parent.name == "final":
            return parent.parent
        if parent.name.startswith("candidate-") and parent.parent.name == "candidates":
            return parent.parent.parent
        if parent.name == "deeplens" and parent.parent.name == "engines":
            return parent.parent.parent
    raise ValueError(f"Cannot infer DeepLens result_dir from lens artifact: {lens_json}")


def _resolve_result_dir(
    project_root: str | Path,
    *,
    result_dir: str | Path | None,
    lens_json: str | Path | None,
) -> Path:
    if result_dir:
        return _resolve_path(project_root, result_dir)
    if lens_json:
        return infer_result_dir(_resolve_path(project_root, lens_json))
    raise ValueError("result_dir or lens_json is required.")


def _resolve_path(project_root: str | Path, value: str | Path | None) -> Path:
    path = Path(str(value or ""))
    if path.is_absolute():
        return path
    return Path(project_root) / path


def _curriculum_candidates(result_dir: Path) -> list[Path]:
    attempts_root = result_dir / "engines" / "deeplens" / "attempts"
    candidates = [path for path in attempts_root.glob("attempt-*-*/curriculum.json") if path.is_file()]
    return sorted(candidates, key=lambda path: _attempt_index(path), reverse=True)


def _latest_candidate_artifact(result_dir: Path, filename: str) -> Path | None:
    candidates_root = result_dir / "candidates"
    candidates = [path for path in candidates_root.glob(f"candidate-*/{filename}") if path.is_file()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: _candidate_index(path), reverse=True)[0]


def _candidate_sibling(candidate_json: Path | None, filename: str) -> Path | None:
    if candidate_json is None:
        return None
    return candidate_json.parent / filename


def _attempt_index(path: Path) -> int:
    for part in path.parts:
        if part.startswith("attempt-"):
            pieces = part.split("-", 2)
            if len(pieces) >= 2:
                try:
                    return int(pieces[1])
                except ValueError:
                    return 0
    return 0


def _candidate_index(path: Path) -> int:
    for part in path.parts:
        if part.startswith("candidate-"):
            try:
                return int(part.split("-", 1)[1])
            except (IndexError, ValueError):
                return 0
    return 0


def _stage_for_lens(result_dir: Path, lens_json: Path) -> str:
    try:
        relative = lens_json.resolve().relative_to(result_dir.resolve())
    except ValueError:
        return "artifact"
    parts = set(relative.parts)
    if "final" in parts:
        return "final"
    if "candidates" in parts:
        return "candidate"
    if "attempts" in parts:
        return "attempt"
    return "artifact"


def load_artifact_session(artifacts: DeepLensArtifacts) -> dict[str, Any]:
    lens = Path(artifacts.analysis_lens_json)
    directory = lens.parent.parent if lens.parent.name == "checkpoints" else lens.parent
    snapshot = directory / "session.json"
    if snapshot.is_file():
        return load_json_object(snapshot)
    # Older runs only archived a run-level session snapshot.
    return load_json_object(Path(artifacts.result_dir) / "engines" / "deeplens" / "session.json")


def load_json_object(path: str | Path) -> dict[str, Any]:
    import json

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


__all__ = ["DeepLensArtifacts", "find_lens_artifacts", "infer_result_dir", "load_artifact_session", "load_json_object"]
