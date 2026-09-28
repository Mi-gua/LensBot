from __future__ import annotations

"""Bridge between LensBot's workflow and the local pi optimization agent."""

import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


JsonObject = dict[str, Any]
EmitCallback = Callable[[str], None]
EventCallback = Callable[[JsonObject], None]


class PiBridgeError(RuntimeError):
    """Raised when the pi sidecar cannot complete the optimization run."""


@dataclass
class PiBridgeResult:
    ok: bool
    session_id: str = ""
    message_count: int = 0
    final_state: JsonObject = field(default_factory=dict)
    events: list[JsonObject] = field(default_factory=list)
    error: str = ""


class PiOptimizationBridge:
    """Run one pi optimization session and return its final state."""

    def __init__(
        self,
        *,
        project_root: Path,
        context: JsonObject,
        tool_definitions: list[JsonObject],
        objective: str,
        max_turns: int | None,
        emit: EmitCallback | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        self.project_root = project_root
        self.context = context
        self.tool_definitions = tool_definitions
        self.objective = objective
        self.max_turns = max(1, int(max_turns)) if max_turns is not None else None
        self.emit = emit
        self.on_event = on_event
        self._events: list[JsonObject] = []
        self._last_state: JsonObject = {}

    def run(self) -> PiBridgeResult:
        runner = self.project_root / "src" / "pi-agent" / "src" / "pi-sidecar.ts"
        if not runner.exists():
            raise PiBridgeError(f"pi-agent sidecar not found: {runner}")

        env = os.environ.copy()
        env.setdefault("PI_OFFLINE", "1")
        env.setdefault("PYTHON", sys.executable)
        process = subprocess.Popen(
            ["node", str(runner)],
            cwd=str(self.project_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
        )
        stderr_thread = threading.Thread(target=self._drain_stderr, args=(process,), daemon=True)
        stderr_thread.start()

        try:
            self._send(
                process,
                {
                    "type": "start",
                    "project_root": str(self.project_root),
                    "objective": self.objective,
                    "max_turns": self.max_turns,
                    "context": self.context,
                    "tools": self.tool_definitions,
                    "model": {
                        "base_url": os.getenv("LENSBOT_OPENAI_BASE_URL", ""),
                        "api_key": os.getenv("LENSBOT_OPENAI_API_KEY", ""),
                        "model": os.getenv("LENSBOT_OPENAI_MODEL", ""),
                        "temperature": os.getenv("LENSBOT_OPENAI_TEMPERATURE", "0.3"),
                    },
                },
            )

            if process.stdout is None:
                raise PiBridgeError("pi runner stdout is not available")

            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise PiBridgeError(f"pi-agent sidecar emitted non-JSON output: {line}") from exc

                message_type = str(message.get("type") or "")
                if message_type == "tool_request":
                    raise PiBridgeError("pi-agent sidecar unexpectedly requested Python workflow tool execution")
                if message_type == "event":
                    self._record_event(message.get("event") or {})
                elif message_type == "log":
                    self._emit(str(message.get("message") or ""))
                elif message_type == "done":
                    data = message.get("data") if isinstance(message.get("data"), dict) else {}
                    self._close_stdin(process)
                    process.wait(timeout=10)
                    stderr_thread.join(timeout=1)
                    self._close_output_pipes(process)
                    return PiBridgeResult(
                        ok=not bool(data.get("error")),
                        session_id=str(data.get("session_id") or ""),
                        message_count=int(data.get("message_count") or 0),
                        final_state=data.get("state") if isinstance(data.get("state"), dict) else self._last_state,
                        events=self._events,
                        error=str(data.get("error") or ""),
                    )
                elif message_type == "error":
                    error = str(message.get("error") or "pi-agent sidecar failed")
                    raise PiBridgeError(error)

            exit_code = process.wait(timeout=10)
            stderr_thread.join(timeout=1)
            self._close_output_pipes(process)
            if exit_code != 0:
                raise PiBridgeError(f"pi-agent sidecar exited with code {exit_code}")
            raise PiBridgeError("pi-agent sidecar exited without a completion result")
        except Exception as exc:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            stderr_thread.join(timeout=1)
            self._close_stdin(process)
            self._close_output_pipes(process)
            return PiBridgeResult(
                ok=False, final_state=self._last_state, events=self._events,
                error=str(exc),
            )

    def _send(self, process: subprocess.Popen[str], message: JsonObject) -> None:
        if process.stdin is None:
            raise PiBridgeError("pi runner stdin is not available")
        process.stdin.write(json.dumps(message, ensure_ascii=False, default=str) + "\n")
        process.stdin.flush()

    def _close_stdin(self, process: subprocess.Popen[str]) -> None:
        if process.stdin is None or process.stdin.closed:
            return
        try:
            process.stdin.close()
        except OSError:
            pass

    def _close_output_pipes(self, process: subprocess.Popen[str]) -> None:
        for pipe in (process.stdout, process.stderr):
            if pipe is None or pipe.closed:
                continue
            try:
                pipe.close()
            except OSError:
                pass

    def _record_event(self, event: JsonObject) -> None:
        if not isinstance(event, dict):
            return
        state = event.get("state")
        if isinstance(state, dict):
            self._last_state = state
        event = {key: value for key, value in event.items() if key != "state"}
        self._events.append(event)
        if self.on_event:
            self.on_event(event)

    def _drain_stderr(self, process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            text = line.strip()
            if text:
                self._emit(text)

    def _emit(self, message: str) -> None:
        if self.emit and message:
            self.emit(f"[pi] {message}")


__all__ = ["PiBridgeError", "PiBridgeResult", "PiOptimizationBridge"]
