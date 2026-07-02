from __future__ import annotations

from pathlib import Path


def _enable_local_imports() -> None:
    src_root = Path(__file__).resolve().parent / "src"
    src_root_text = str(src_root)
    import sys

    if src_root_text not in sys.path:
        sys.path.insert(0, src_root_text)


def main() -> None:
    _enable_local_imports()
    from ui.gui import run_server

    run_server()


if __name__ == "__main__":
    main()
