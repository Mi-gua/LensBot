from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


class PatentTool:
    def __init__(self, local_db_path: str | None = None) -> None:
        env_path = os.getenv("LENSBOT_LOCAL_PATENT_DB", "")
        self.local_db_path = Path(local_db_path or env_path) if (local_db_path or env_path) else None
        self.serpapi_key = os.getenv("SERPAPI_API_KEY", "").strip()

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        local_hits = self._search_local(query, top_k=top_k)
        if len(local_hits) >= top_k:
            return local_hits[:top_k]

        remote_hits = self._search_google_patents(query, top_k=top_k)
        merged = local_hits + remote_hits
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for hit in merged:
            key = f"{hit.get('patent_id','')}|{hit.get('url','')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(hit)
            if len(deduped) >= top_k:
                break
        return deduped

    def _search_google_patents(self, query: str, top_k: int) -> list[dict[str, Any]]:
        if not self.serpapi_key:
            return []

        import requests

        try:
            response = requests.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_patents",
                    "q": query,
                    "api_key": self.serpapi_key,
                    "num": max(3, top_k),
                },
                timeout=20,
            )
            response.raise_for_status()
            rows = response.json().get("organic_results", [])
        except Exception:
            return []

        return [
            {
                "source": "google_patents",
                "patent_id": row.get("patent_id", ""),
                "title": row.get("title", ""),
                "snippet": row.get("snippet", ""),
                "published": row.get("publication_date", ""),
                "url": row.get("link", ""),
                "score": 0.0,
            }
            for row in rows[:top_k]
        ]

    def _search_local(self, query: str, top_k: int) -> list[dict[str, Any]]:
        if self.local_db_path is None or not self.local_db_path.exists():
            return []
        keywords = self._tokenize(query)
        if not keywords:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        try:
            with self.local_db_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    blob = " ".join(
                        [
                            str(row.get("title", "")),
                            str(row.get("abstract", "")),
                            str(row.get("keywords", "")),
                            str(row.get("assignee", "")),
                        ]
                    ).lower()
                    score = self._score_text(blob, keywords)
                    if score <= 0:
                        continue
                    scored.append(
                        (
                            score,
                            {
                                "source": "local_patent_db",
                                "patent_id": str(row.get("patent_id", "")),
                                "title": str(row.get("title", "")),
                                "snippet": str(row.get("abstract", ""))[:240],
                                "published": str(row.get("published", "")),
                                "url": str(row.get("url", "")),
                                "score": round(score, 4),
                            },
                        )
                    )
        except Exception:
            return []

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token for token in re.split(r"[^a-zA-Z0-9\.\-/]+", text.lower()) if len(token) >= 2]

    @staticmethod
    def _score_text(blob: str, keywords: list[str]) -> float:
        if not blob:
            return 0.0
        score = 0.0
        for keyword in keywords:
            if keyword in blob:
                score += 1.0 + min(2.0, blob.count(keyword) * 0.2)
        return score / max(1, len(keywords))
