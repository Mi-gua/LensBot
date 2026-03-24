from __future__ import annotations

from ui import build_ui


def launch() -> None:
    demo = build_ui()
    demo.launch()
