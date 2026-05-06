from __future__ import annotations

import os
import sys
from pathlib import Path


def find_deeplens_root(start: Path | None = None) -> Path:
    """Locate the external DeepLens workspace used by LensBot."""
    anchor = (start or Path(__file__)).resolve()

    env_root = os.environ.get("DEEPLENS_ROOT")
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root).expanduser())

    for parent in anchor.parents:
        candidates.extend(
            [
                parent / "Optics" / "DeepLens",
                parent / "Lens" / "DeepLens",
                parent / "Lens",
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
        "Tried DEEPLENS_ROOT, Optics/DeepLens, Lens/DeepLens, Lens, and sibling DeepLens."
    )


def ensure_deeplens_import(start: Path | None = None) -> Path:
    """Make the external DeepLens package importable for engine modules."""
    deeplens_root = find_deeplens_root(start=start)
    deeplens_root_str = str(deeplens_root)
    if deeplens_root_str not in sys.path:
        sys.path.insert(0, deeplens_root_str)
    return deeplens_root
