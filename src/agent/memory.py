from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from schema import AgentInput, AgentResult


class AgentMemory:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.episodic_dir = root / "episodic"
        self.semantic_dir = root / "semantic"
        self.episodic_dir.mkdir(parents=True, exist_ok=True)
        self.semantic_dir.mkdir(parents=True, exist_ok=True)
        self.episodic_file = self.episodic_dir / "entries.jsonl"
        self.semantic_file = self.semantic_dir / "design_knowledge.md"
        if not self.semantic_file.exists():
            self.semantic_file.write_text("# LensBot Semantic Memory\n\n", encoding="utf-8")

    def create_snapshot(self) -> dict[str, Any]:
        return {"timeline": []}

    def append_episode(self, request: AgentInput, result: AgentResult) -> None:
        row = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "input": {
                "mode": request.mode,
                "prompt": request.prompt,
                "params": asdict(request.params) if request.params else None,
                "enable_patent_search": request.enable_patent_search,
            },
            "output": {
                "ok": result.ok,
                "summary": result.summary,
                "result_dir": result.result_dir,
                "curriculum_json": result.curriculum_json,
                "final_json": result.final_json,
                "log_file": result.log_file,
                "metrics": result.metrics,
                "references": result.references,
            },
        }
        with self.episodic_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def add_note(self, insight: str) -> None:
        if not insight.strip():
            return
        with self.semantic_file.open("a", encoding="utf-8") as handle:
            handle.write(f"- [{datetime.now().strftime('%Y-%m-%d %H:%M')}] {insight.strip()}\n")

    def load_recent_episodes(self, limit: int = 5) -> list[dict[str, Any]]:
        if not self.episodic_file.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.episodic_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-limit:]

    def load_semantic_notes(self, limit: int = 10) -> list[str]:
        if not self.semantic_file.exists():
            return []
        notes = [
            line.strip()
            for line in self.semantic_file.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("- ")
        ]
        return notes[-limit:]
