from __future__ import annotations

import sys
from pathlib import Path


def find_deeplens_root(start: Path | None = None) -> Path:
    """Locate the DeepLens project root from the current LensBot workspace."""
    anchor = (start or Path(__file__)).resolve()

    candidates: list[Path] = []
    for parent in anchor.parents:
        candidates.extend(
            [
                parent / "Optics" / "DeepLens",
                parent / "Lens" / "DeepLens",
                parent / "DeepLens",
            ]
        )

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists() and (candidate / "deeplens").exists():
            return candidate

    raise FileNotFoundError(
        "Cannot locate DeepLens from current LensBot workspace. "
        "Tried layouts: Optics/DeepLens, Lens/DeepLens, and sibling DeepLens."
    )


def ensure_deeplens_import(start: Path | None = None) -> Path:
    """Make the local DeepLens package importable by appending it to sys.path."""
    deeplens_root = find_deeplens_root(start=start)
    deeplens_root_str = str(deeplens_root)
    if deeplens_root_str not in sys.path:
        sys.path.insert(0, deeplens_root_str)
    return deeplens_root
