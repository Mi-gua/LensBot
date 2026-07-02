from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_under_root(project_root: Path, raw_path: Any) -> Path | None:
    if raw_path is None:
        return None
    root = project_root.resolve()
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


__all__ = ["resolve_under_root"]
