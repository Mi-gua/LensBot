from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
import uuid
import logging
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".cache" / "matplotlib"))
logging.getLogger("matplotlib").setLevel(logging.ERROR)
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

from agent.llm import LLM_PROVIDERS, get_runtime_llm_config
from agent.workflow import LensResearchAgent
from runtime.artifacts import build_preview_payload as build_runtime_preview_payload
from runtime.timeline import TimelineCatalog
from subagents.types import DEFAULT_OPTIMIZATION_MAX_TURNS, build_agent_input, load_default_params, public_params_dict


UI_ROOT = PROJECT_ROOT / "src" / "ui"
UI_TEMPLATE_PATH = UI_ROOT / "dashboard.html"
UI_ASSETS_ROOT = UI_ROOT / "assets"
HOST = "127.0.0.1"
PORT = 8000
CLIENT_DISCONNECT_ERRORS = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


def _cli_task_line(message: str) -> None:
    print(f"[LensBot] {message}", flush=True)


@dataclass
class RunState:
    run_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    next_event_id: int = 0
    done: bool = False
    condition: threading.Condition = field(default_factory=threading.Condition)

    def publish(self, event: dict[str, Any]) -> None:
        with self.condition:
            event_with_id = dict(event)
            event_with_id["id"] = self.next_event_id
            self.next_event_id += 1
            self.events.append(event_with_id)
            self.condition.notify_all()

    def close(self) -> None:
        with self.condition:
            self.done = True
            self.condition.notify_all()


RUNS: dict[str, RunState] = {}
RUNS_LOCK = threading.Lock()


def build_agent() -> LensResearchAgent:
    return LensResearchAgent(load_default_params(PROJECT_ROOT), PROJECT_ROOT)


def build_defaults_payload() -> dict[str, Any]:
    params = load_default_params(PROJECT_ROOT)
    llm = get_runtime_llm_config()
    return {
        "params": public_params_dict(params),
        "optimization": {"max_turns": DEFAULT_OPTIMIZATION_MAX_TURNS},
        "llm": {
            **llm,
            "providers": LLM_PROVIDERS,
        },
    }


def build_index_html() -> str:
    template = UI_TEMPLATE_PATH.read_text(encoding="utf-8")
    template = template.replace('/ui/dashboard.css"', f'{_ui_asset_url("dashboard.css")}"')
    template = template.replace('/ui/dashboard.js"', f'{_ui_asset_url("dashboard.js")}"')
    return template.replace("__DEFAULTS__", json.dumps(build_defaults_payload(), ensure_ascii=False))


def _ui_asset_url(relative_path: str) -> str:
    path = (UI_ROOT / relative_path).resolve()
    try:
        path.relative_to(UI_ROOT.resolve())
    except ValueError:
        return "/ui/" + relative_path.strip("/")
    cache_key = int(path.stat().st_mtime) if path.exists() else 0
    return "/ui/" + relative_path.strip("/") + f"?v={cache_key}"


def _result_file_url(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    try:
        relative_path = path.resolve().relative_to((PROJECT_ROOT / "results").resolve())
    except ValueError:
        return None
    cache_key = int(path.stat().st_mtime)
    return "/results/" + "/".join(relative_path.parts) + f"?v={cache_key}"


def _display_workspace_path(path: str | None) -> str | None:
    if not path:
        return None
    try:
        workspace_root = PROJECT_ROOT.parents[2].resolve()
        relative_path = Path(path).resolve().relative_to(workspace_root)
        return relative_path.as_posix()
    except (ValueError, OSError):
        return path


def _build_preview_payload(result_dir: str | None, metrics: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not result_dir:
        return None

    root = Path(result_dir)
    if not root.exists():
        return None

    return build_runtime_preview_payload(
        root,
        metrics or {},
        url_builder=_result_file_url,
        path_builder=_display_workspace_path,
    )


def _resolve_preview_result_dir(value: str | None) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None

    parsed = urlparse(text)
    if parsed.path.startswith("/results/"):
        return _result_run_root(PROJECT_ROOT / parsed.path.removeprefix("/").replace("/", os.sep))

    raw_path = Path(parsed.path or text)
    candidates = [raw_path] if raw_path.is_absolute() else []
    if not raw_path.is_absolute():
        workspace_root = PROJECT_ROOT.parents[2].resolve()
        candidates.extend(
            [
                PROJECT_ROOT / raw_path,
                PROJECT_ROOT.parent / raw_path,
                workspace_root / raw_path,
            ]
        )
    for candidate in candidates:
        root = _result_run_root(candidate)
        if root is not None:
            return root
    return None


def _result_run_root(path: Path) -> Path | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None
    results_root = (PROJECT_ROOT / "results").resolve()
    try:
        relative = resolved.relative_to(results_root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    return results_root / relative.parts[0]


def _json_response(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _apply_llm_config(payload: dict[str, Any]) -> None:
    config = payload.get("llm")
    if not isinstance(config, dict):
        return
    mapping = {
        "base_url": "LENSBOT_OPENAI_BASE_URL",
        "api_key": "LENSBOT_OPENAI_API_KEY",
        "model": "LENSBOT_OPENAI_MODEL",
        "temperature": "LENSBOT_OPENAI_TEMPERATURE",
    }
    for key, env_name in mapping.items():
        value = config.get(key)
        if value in (None, ""):
            continue
        os.environ[env_name] = str(value)


def _start_run(payload: dict[str, Any]) -> str:
    run_id = uuid.uuid4().hex[:10]
    state = RunState(run_id=run_id)
    with RUNS_LOCK:
        RUNS[run_id] = state

    def worker() -> None:
        started_at = time.monotonic()
        try:
            state.publish({"event": "progress", **TimelineCatalog().event("run.received").for_trace()})
            run_payload = dict(payload)
            _apply_llm_config(run_payload)
            defaults = load_default_params(PROJECT_ROOT)
            agent = build_agent()
            curriculum = dict(run_payload.get("curriculum") or {})
            curriculum.setdefault("iterations", run_payload.get("iterations", defaults.curriculum.iterations))
            curriculum.setdefault("spp", run_payload.get("spp", defaults.curriculum.spp))
            curriculum.setdefault("test_per_iter", run_payload.get("test_per_iter", defaults.curriculum.test_per_iter))
            run_payload["curriculum"] = {key: value for key, value in curriculum.items() if value is not None}

            fine_tune = dict(run_payload.get("fine_tune") or {})
            fine_tune.setdefault("iterations", run_payload.get("fine_tune_iterations", defaults.fine_tune.iterations))
            fine_tune.setdefault("spp", run_payload.get("fine_tune_spp", defaults.fine_tune.spp))
            fine_tune.setdefault("test_per_iter", run_payload.get("fine_tune_test_per_iter", defaults.fine_tune.test_per_iter))
            run_payload["fine_tune"] = {key: value for key, value in fine_tune.items() if value is not None}
            agent_input = build_agent_input(PROJECT_ROOT, payload=run_payload)
            _cli_task_line("\u5149\u5b66\u8bbe\u8ba1\u5e73\u53f0\u5df2\u5c31\u7eea\u3002")

            def publish_artifact(result_dir: str) -> None:
                state.publish(
                    {
                        "event": "artifact",
                        "result_dir": _display_workspace_path(result_dir),
                        "result_dir_url": _result_file_url(Path(result_dir)),
                        "preview": _build_preview_payload(result_dir),
                    }
                )

            def publish_references(references: list[dict[str, Any]]) -> None:
                state.publish(
                    {
                        "event": "references",
                        "references": references,
                    }
                )

            result = agent.run(
                agent_input,
                progress_cb=lambda payload: state.publish({"event": "progress", **payload}),
                artifact_cb=publish_artifact,
                reference_cb=publish_references,
                transcript_cb=lambda row: state.publish({"event": "transcript", "transcript": row}),
            )
            state.publish(
                {
                    "event": "result",
                    "ok": result.ok,
                    "summary": result.summary,
                    "result_dir": _display_workspace_path(result.result_dir),
                    "result_dir_url": _result_file_url(Path(result.result_dir)) if result.result_dir else None,
                    "curriculum_json": _display_workspace_path(result.curriculum_json),
                    "curriculum_json_url": _result_file_url(Path(result.curriculum_json)) if result.curriculum_json else None,
                    "candidate_json": _display_workspace_path(result.candidate_json),
                    "candidate_json_url": _result_file_url(Path(result.candidate_json)) if result.candidate_json else None,
                    "candidate_zmx": _display_workspace_path(result.candidate_zmx),
                    "candidate_zmx_url": _result_file_url(Path(result.candidate_zmx)) if result.candidate_zmx else None,
                    "candidate_png": _display_workspace_path(result.candidate_png),
                    "candidate_png_url": _result_file_url(Path(result.candidate_png)) if result.candidate_png else None,
                    "final_json": _display_workspace_path(result.final_json),
                    "final_json_url": _result_file_url(Path(result.final_json)) if result.final_json else None,
                    "final_zmx": _display_workspace_path(result.final_zmx),
                    "final_zmx_url": _result_file_url(Path(result.final_zmx)) if result.final_zmx else None,
                    "summary_report_file": _display_workspace_path(result.summary_report_file),
                    "summary_report_file_url": _result_file_url(Path(result.summary_report_file)) if result.summary_report_file else None,
                    "metrics_file": _display_workspace_path(result.metrics_file),
                    "metrics_file_url": _result_file_url(Path(result.metrics_file)) if result.metrics_file else None,
                    "log_file": _display_workspace_path(result.log_file),
                    "log_file_url": _result_file_url(Path(result.log_file)) if result.log_file else None,
                    "metrics": result.metrics,
                    "preview": _build_preview_payload(result.result_dir, result.metrics),
                    "references": result.references,
                    "timeline": result.timeline,
                }
            )
            elapsed = time.monotonic() - started_at
            if result.ok:
                _cli_task_line(f"任务 {run_id} 已完成，用时 {elapsed:.1f}s。")
            else:
                _cli_task_line(f"任务 {run_id} 失败，用时 {elapsed:.1f}s。原因：{result.summary or '未返回失败原因'}")
        except Exception as exc:  # pragma: no cover - UI boundary
            elapsed = time.monotonic() - started_at
            _cli_task_line(f"任务 {run_id} 失败，用时 {elapsed:.1f}s。原因：{type(exc).__name__}: {exc}")
            state.publish({"event": "run_error", **TimelineCatalog().event("run.error", error=exc).for_trace()})
        finally:
            state.publish({"event": "done"})
            state.close()

    threading.Thread(target=worker, daemon=True).start()
    return run_id


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "LensBotDashboard/1.0"

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = build_index_html().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            return
        if parsed.path == "/api/defaults":
            body = json.dumps(build_defaults_payload(), ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return
        if parsed.path.startswith("/results/"):
            file_path = self._resolve_result_path(parsed.path)
            if file_path is None or not file_path.is_file():
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return
            self.send_response(HTTPStatus.OK)
            mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.end_headers()
            return
        if parsed.path.startswith("/ui/"):
            file_path = self._resolve_ui_path(parsed.path)
            if file_path is None or not file_path.is_file():
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return
            self.send_response(HTTPStatus.OK)
            mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_header("Content-Type", mime_type)
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.end_headers()
            return
        if parsed.path.startswith("/assets/"):
            file_path = self._resolve_asset_path(parsed.path)
            if file_path is None or not file_path.is_file():
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return
            self.send_response(HTTPStatus.OK)
            mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.end_headers()
            return
        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = build_index_html().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if parsed.path == "/api/defaults":
            _json_response(self, build_defaults_payload())
            return

        if parsed.path == "/api/preview":
            query = parse_qs(parsed.query)
            result_dir = _resolve_preview_result_dir(query.get("result_dir", [""])[0])
            if result_dir is None:
                _json_response(self, {"error": "\u672a\u627e\u5230\u8fd0\u884c\u9884\u89c8\u76ee\u5f55\u3002"}, status=404)
                return
            _json_response(
                self,
                {
                    "result_dir": _display_workspace_path(str(result_dir)),
                    "result_dir_url": _result_file_url(result_dir),
                    "preview": _build_preview_payload(str(result_dir)),
                },
            )
            return

        if parsed.path == "/api/stream":
            query = parse_qs(parsed.query)
            run_id = query.get("run_id", [""])[0]
            last_event_id = query.get("last_event_id", [self.headers.get("Last-Event-ID", "")])[0]
            with RUNS_LOCK:
                state = RUNS.get(run_id)
            if state is None:
                _json_response(self, {"error": "\u672a\u627e\u5230\u8fd0\u884c\u4efb\u52a1\u3002"}, status=404)
                return
            self._stream_run(state, last_event_id=last_event_id)
            return

        if parsed.path.startswith("/results/"):
            file_path = self._resolve_result_path(parsed.path)
            if file_path is None or not file_path.is_file():
                _json_response(self, {"error": "\u672a\u627e\u5230\u6587\u4ef6\u3002"}, status=404)
                return
            mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.end_headers()
            with file_path.open("rb") as handle:
                self.wfile.write(handle.read())
            return

        if parsed.path.startswith("/ui/"):
            file_path = self._resolve_ui_path(parsed.path)
            if file_path is None or not file_path.is_file():
                _json_response(self, {"error": "\u672a\u627e\u5230\u6587\u4ef6\u3002"}, status=404)
                return
            mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.end_headers()
            with file_path.open("rb") as handle:
                self.wfile.write(handle.read())
            return

        if parsed.path.startswith("/assets/"):
            file_path = self._resolve_asset_path(parsed.path)
            if file_path is None or not file_path.is_file():
                _json_response(self, {"error": "\u672a\u627e\u5230\u6587\u4ef6\u3002"}, status=404)
                return
            mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.end_headers()
            with file_path.open("rb") as handle:
                self.wfile.write(handle.read())
            return

        _json_response(self, {"error": "\u672a\u627e\u5230\u8bf7\u6c42\u3002"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/run":
            _json_response(self, {"error": "\u672a\u627e\u5230\u8bf7\u6c42\u3002"}, status=404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            _json_response(self, {"error": "\u8bf7\u6c42\u6570\u636e\u4e0d\u662f\u6709\u6548 JSON\u3002"}, status=400)
            return

        required = ["mode"]
        missing = [key for key in required if key not in payload]
        if missing:
            _json_response(self, {"error": f"\u7f3a\u5c11\u5b57\u6bb5\uff1a{', '.join(missing)}"}, status=400)
            return

        run_id = _start_run(payload)
        _json_response(self, {"run_id": run_id}, status=202)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _stream_run(self, state: RunState, *, last_event_id: str = "") -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            index = max(0, int(last_event_id) + 1) if last_event_id != "" else 0
        except ValueError:
            index = 0
        try:
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()
        except CLIENT_DISCONNECT_ERRORS:
            return

        while True:
            with state.condition:
                while index >= len(state.events) and not state.done:
                    state.condition.wait(timeout=1.0)
                    try:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    except CLIENT_DISCONNECT_ERRORS:
                        return

                pending = state.events[index:]
                is_done = state.done and index >= len(state.events)

            for event in pending:
                event_id = int(event.get("id", index))
                chunk = (
                    f"id: {event_id}\n"
                    f"event: {event['event']}\n"
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                ).encode("utf-8")
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except CLIENT_DISCONNECT_ERRORS:
                    return
            index += len(pending)

            if is_done or (state.done and index >= len(state.events)):
                return

    @staticmethod
    def _resolve_result_path(request_path: str) -> Path | None:
        relative = request_path.removeprefix("/results/").strip("/")
        if not relative:
            return None
        base = (PROJECT_ROOT / "results").resolve()
        candidate = (base / relative).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        return candidate

    @staticmethod
    def _resolve_asset_path(request_path: str) -> Path | None:
        relative = request_path.removeprefix("/assets/").strip("/")
        if not relative:
            return None
        base = UI_ASSETS_ROOT.resolve()
        candidate = (base / relative).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        return candidate

    @staticmethod
    def _resolve_ui_path(request_path: str) -> Path | None:
        relative = request_path.removeprefix("/ui/").strip("/")
        if not relative:
            return None
        base = UI_ROOT.resolve()
        candidate = (base / relative).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        return candidate


def run_server(host: str = HOST, port: int = PORT) -> None:
    configured_port = int(os.getenv("LENSBOT_PORT", str(port)))
    server = None
    bound_port = configured_port

    for candidate in range(configured_port, configured_port + 20):
        try:
            server = ThreadingHTTPServer((host, candidate), DashboardHandler)
            bound_port = candidate
            break
        except OSError:
            continue

    if server is None:
        raise OSError(
            f"\u65e0\u6cd5\u5728 {host} \u542f\u52a8 LensBot \u63a7\u5236\u53f0\u3002"
            f"\u5df2\u5c1d\u8bd5\u7aef\u53e3 {configured_port}-{configured_port + 19}\u3002"
        )

    print(f"LensBot \u63a7\u5236\u53f0\u5df2\u542f\u52a8\uff1ahttp://{host}:{bound_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

