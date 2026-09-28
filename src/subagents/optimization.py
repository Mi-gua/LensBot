from __future__ import annotations

"""Optimization workflow node backed by the pi-native LensBot agent."""

import json
from typing import Any, Callable

from runtime.bridge import PiBridgeError, PiOptimizationBridge
from runtime.result import new_run_id
from subagents.types import RECOMMENDED_OPTIMIZATION_REVIEW_TURNS, design_contract_dict, public_params_dict
from tools.deeplens.curriculum import result_dir_for_run


class OptimizationRunner:
    """Run Optimization with pi-coding-agent and sync the final state."""

    name = "Optimization"
    objective = (
        "Choose a starting structure from the supplied candidates and optimize it for the design contract. Decide from measured results whether to refine it or try another candidate; do not optimize every candidate by default."
    )
    tool_names = [
        "powershell",
        "read_file",
        "write_file",
        "edit_file",
        "deeplens_adjust_structure",
        "deeplens_curriculum",
        "deeplens_finetune",
        "deeplens_inspect_checkpoint",
        "deeplens_adjust_strategy",
        "deeplens_analysis",
        "deeplens_compare_candidates",
    ]

    def __init__(
        self,
        *,
        max_turns: int | None = None,
        emit: Callable[[str], None] | None = None,
        objective: str | None = None,
    ) -> None:
        self.max_turns = max_turns
        self.emit = emit
        self.objective = objective or self.objective

    def run(self, ctx: Any, runtime: Any) -> None:
        if ctx.params is None:
            ctx.fail("No design parameters are available for optimization.")
            return

        available_tools = runtime.tool_names(*self.tool_names)
        if not available_tools:
            ctx.fail("No optimization tools are registered.")
            return

        run_id = _run_id(ctx)
        live_events = _LivePiEventRecorder(emit=self.emit, runtime=runtime, ctx=ctx, run_id=run_id)
        bridge = PiOptimizationBridge(
            project_root=runtime.project_root,
            context=_optimization_context(ctx, run_id=run_id),
            tool_definitions=runtime.registry.describe(available_tools),
            objective=self.objective,
            max_turns=getattr(ctx.request, "max_turns", None) or self.max_turns,
            emit=self.emit,
            on_event=live_events.handle,
        )

        try:
            result = bridge.run()
        except PiBridgeError as exc:
            ctx.fail(str(exc))
            return
        except Exception as exc:
            ctx.fail(f"pi optimization failed: {type(exc).__name__}: {exc}")
            return

        if result.session_id:
            ctx.metrics["pi_session_id"] = result.session_id
        if live_events.trace:
            ctx.metrics["optimization_trace"] = list(live_events.trace)
            trace = list(live_events.trace)
        else:
            trace = _trace_from_events(result.events)
            ctx.agent_trace.extend(trace)
            ctx.metrics["optimization_trace"] = trace
        _sync_final_state(
            ctx,
            runtime,
            result.final_state,
            failure_hint=result.error,
        )
        if not result.ok and ctx.delivery_status != "failed":
            ctx.fail(result.error or "Optimization process failed.")


def _sync_final_state(ctx: Any, runtime: Any, state: dict[str, Any], *, failure_hint: str = "") -> None:
    if not state:
        ctx.fail(failure_hint or "pi optimization finished without a final state.")
        return
    recorder = getattr(runtime, "record_workflow_artifact", None)
    if callable(recorder):
        recorder(ctx, "Optimization", "final_state", state)

    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    metrics = state.get("metrics") if isinstance(state.get("metrics"), dict) else {}
    result_dir = state.get("active_result_dir")
    if result_dir:
        runtime.bind_result_dir(ctx, str(result_dir))
        ctx.design_result["result_dir"] = str(result_dir)
        runtime.publish_artifact(str(result_dir), ctx=ctx)

    for key in (
        "curriculum_json",
        "candidate_json",
        "candidate_zmx",
        "candidate_png",
        "analysis_json",
        "final_json",
        "final_zmx",
        "final_png",
    ):
        value = artifacts.get(key)
        if value:
            ctx.design_result[key] = str(value)

    ctx.metrics.update(metrics)
    execution_params = state.get("params_override") or {}
    if ctx.params is not None and execution_params.get("surf_list"):
        ctx.params.surf_list = execution_params["surf_list"]
    active_seed_id = state.get("active_seed_id")
    _publish_seed_selection(ctx, runtime, active_seed_id, applied=True)
    _promote_final_deeplens_metrics(ctx.metrics)
    final_verdict = state.get("final_verdict")
    if isinstance(final_verdict, dict):
        ctx.metrics["agent_verdict"] = dict(final_verdict)
    if state.get("phase") != "finished":
        suffix = f" Reason: {failure_hint}" if failure_hint else ""
        ctx.fail(f"pi optimization stopped before finish: phase={state.get('phase')!r}.{suffix}")
        return

    if not ctx.design_result.get("final_json") or not ctx.design_result.get("final_zmx"):
        ctx.fail("pi optimization finished without final_json/final_zmx in state.")


def _publish_seed_selection(ctx: Any, runtime: Any, seed_id: Any, *, applied: bool = False) -> None:
    for candidate in ctx.seed_candidates:
        if applied:
            candidate.applied = bool(seed_id and candidate.candidate_id == seed_id)
    for reference in ctx.references:
        reference["selected"] = bool(seed_id and reference.get("candidate_id") == seed_id)
        if applied:
            reference["applied"] = reference["selected"]
    runtime.publish_references([dict(reference) for reference in ctx.references])


def _promote_final_deeplens_metrics(metrics: dict[str, Any]) -> None:
    if str(metrics.get("analysis_stage") or "").strip().lower() != "final":
        return

    for source_key, alias_key in (
        ("deeplens_efl_mm", "efl_mm"),
        ("deeplens_fnum", "fnum"),
        ("deeplens_fov_deg", "fov_deg"),
    ):
        value = metrics.get(source_key)
        if value in (None, ""):
            continue
        previous = metrics.get(alias_key)
        if previous not in (None, "") and previous != value:
            metrics.setdefault(f"pre_final_{alias_key}", previous)
        metrics[alias_key] = value


def _optimization_context(ctx: Any, *, run_id: str | None = None) -> dict[str, Any]:
    return {
        "run_id": run_id or _run_id(ctx),
        "execution_params": public_params_dict(ctx.params),
        "design_contract": design_contract_dict(ctx.params),
        "effort_policy": {
            "explicit_tool_call_limit": getattr(ctx.request, "max_turns", None),
            "recommended_review_point": getattr(ctx.request, "recommended_max_turns", RECOMMENDED_OPTIMIZATION_REVIEW_TURNS),
            "meaning": "The review point is general guidance, not a required number of calls or an optimization budget.",
        },
        "initial_structures": [_seed_candidate_payload(item) for item in ctx.seed_candidates if item.params is not None],
        "memory": _optimization_memory(ctx.memory_snapshot),
    }





def _run_id(ctx: Any) -> str:
    existing = getattr(ctx, "run_id", "")
    if existing:
        return str(existing)
    return new_run_id()


class _LivePiEventRecorder:
    def __init__(
        self,
        *,
        emit: Callable[[str], None] | None,
        runtime: Any,
        ctx: Any,
        run_id: str,
    ) -> None:
        self.emit = emit
        self.runtime = runtime
        self.ctx = ctx
        self.run_id = run_id
        self.pending_calls: dict[str, tuple[dict[str, Any], int]] = {}
        self.ctx_trace_indexes: dict[int, int] = {}
        self.persisted_turns: dict[int, str] = {}
        self.persisted_transcript_events: dict[str, str] = {}
        self.trace: list[dict[str, Any]] = []
        self.transcript: list[dict[str, Any]] = []
        self.current_message_id = 0
        self.current_message_turn: int | None = None
        self.current_message_text = ""
        self.sequence = 0
        self.usage_by_turn: dict[int, dict[str, Any]] = {}

    def handle(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "")
        if event_type == "message_update":
            self._handle_message_update(event)
            return
        if event_type == "tool_execution_start":
            self._handle_tool_start(event)
            return
        if event_type == "tool_execution_update":
            self._handle_tool_update(event)
            return
        if event_type == "tool_execution_end":
            self._handle_tool_end(event)
            return
        if event_type == "turn_end":
            self._handle_turn_end(event)
            return
        if event_type == "turn_start" and self.emit:
            self.emit("pi turn start")

    def _handle_turn_end(self, event: dict[str, Any]) -> None:
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        if not usage:
            return
        try:
            turn_index = int(event.get("turn_index", len(self.usage_by_turn)))
        except (TypeError, ValueError):
            turn_index = len(self.usage_by_turn)
        self.usage_by_turn[turn_index] = usage
        totals = _aggregate_model_usage(self.usage_by_turn.values())
        self.ctx.metrics.update(totals)

    def _handle_message_update(self, event: dict[str, Any]) -> None:
        if str(event.get("update_type") or "") != "text_delta":
            return
        delta = str(event.get("delta") or "")
        if not delta:
            return
        turn = len(self.trace)
        if self.current_message_turn != turn:
            self.current_message_turn = turn
            self.current_message_id += 1
            self.current_message_text = ""
        self.current_message_text += delta
        row = {
            "agent": OptimizationRunner.name,
            "kind": "assistant_message",
            "turn": turn,
            "sequence": self.sequence,
            "message_id": f"assistant-{self.current_message_id}",
            "role": "assistant",
            "text": self.current_message_text,
            "delta": delta,
            **_native_event_projection(event),
        }
        self._store_live_transcript_event(row)

    def _handle_tool_start(self, event: dict[str, Any]) -> None:
        tool_name = str(event.get("tool_name") or "")
        key = _tool_event_key(event, len(self.trace))
        turn = len(self.trace)
        self.pending_calls[key] = (event, turn)
        self.runtime.emit_event(self.ctx, "optimization.tool.start", tool=tool_name)
        result_dir = self._current_result_dir()
        if tool_name == "deeplens_curriculum":
            args = event.get("args") if isinstance(event.get("args"), dict) else {}
            _publish_seed_selection(self.ctx, self.runtime, args.get("seed_candidate_id"))
            result_dir = str(result_dir_for_run(self.runtime.project_root, str(args.get("run_id") or self.run_id)))
        self._store_turn(_tool_start_turn(event, turn=turn), result_dir)
        self._store_transcript_event(_tool_call_event(event, turn=turn, sequence=self.sequence), result_dir)
        if self.emit:
            self.emit(f"pi tool start: {tool_name}")

    def _handle_tool_update(self, event: dict[str, Any]) -> None:
        key = _tool_event_key(event, len(self.trace))
        start_event, turn = self.pending_calls.get(key, ({}, len(self.trace)))
        result_dir = _result_dir_from_tool_event(event) or self._current_result_dir()
        self._store_transcript_event(
            _tool_call_event(event, turn=turn, sequence=self.sequence, start_event=start_event),
            result_dir,
        )

    def _handle_tool_end(self, event: dict[str, Any]) -> None:
        status = "error" if event.get("is_error") else "ok"
        if self.emit:
            self.emit(f"pi tool end: {event.get('tool_name')} {status}")
        key = _tool_event_key(event, len(self.trace))
        start_event, turn = self.pending_calls.pop(key, ({}, len(self.trace)))
        row = _tool_turn_from_events(start_event, event, turn=turn)
        if (event.get("tool_name") or start_event.get("tool_name")) == "deeplens_curriculum":
            result = _normalized_tool_result(event)
            if result["ok"]:
                patch = result.get("state_patch") or {}
                _publish_seed_selection(self.ctx, self.runtime, patch.get("active_seed_id"), applied=True)
            else:
                active_seed_id = next((item.candidate_id for item in self.ctx.seed_candidates if item.applied), None)
                _publish_seed_selection(self.ctx, self.runtime, active_seed_id)
        result_dir = _result_dir_from_tool_event(event) or self._current_result_dir()
        self._store_transcript_event(_tool_result_event(event, turn=turn, sequence=self.sequence), result_dir)
        self._store_turn(row, result_dir)

    def _store_transcript_event(self, row: dict[str, Any], result_dir: str | None) -> None:
        row["sequence"] = row.get("sequence", self.sequence)
        self.sequence += 1
        event_id = str(row.get("message_id") or row.get("tool_call_id") or row.get("sequence"))
        for index, existing in enumerate(self.transcript):
            existing_id = str(existing.get("message_id") or existing.get("tool_call_id") or existing.get("sequence"))
            if existing.get("kind") == row.get("kind") and existing_id == event_id:
                self.transcript[index] = row
                break
        else:
            self.transcript.append(row)
        self.ctx.metrics["optimization_transcript"] = list(self.transcript)
        if result_dir:
            self.runtime.bind_result_dir(self.ctx, result_dir)
            self._flush_transcript(result_dir)
            self.runtime.publish_artifact(result_dir, ctx=self.ctx)

    def _store_live_transcript_event(self, row: dict[str, Any]) -> None:
        row["sequence"] = row.get("sequence", self.sequence)
        event_id = str(row.get("message_id") or row.get("tool_call_id") or row.get("sequence"))
        for index, existing in enumerate(self.transcript):
            existing_id = str(existing.get("message_id") or existing.get("tool_call_id") or existing.get("sequence"))
            if existing.get("kind") == row.get("kind") and existing_id == event_id:
                row["sequence"] = existing.get("sequence", row["sequence"])
                self.transcript[index] = row
                break
        else:
            self.sequence += 1
            self.transcript.append(row)
        self.ctx.metrics["optimization_transcript"] = list(self.transcript)
        publisher = getattr(self.runtime, "publish_transcript", None)
        if callable(publisher):
            publisher(self.ctx, row)

    def _store_turn(self, row: dict[str, Any], result_dir: str | None) -> None:
        turn = int(row.get("turn") or 0)
        if turn < len(self.trace):
            self.trace[turn] = row
        else:
            self.trace.append(row)
        if turn in self.ctx_trace_indexes:
            self.ctx.agent_trace[self.ctx_trace_indexes[turn]] = row
        else:
            self.ctx_trace_indexes[turn] = len(self.ctx.agent_trace)
            self.ctx.agent_trace.append(row)
        self.ctx.metrics["optimization_trace"] = list(self.trace)
        if result_dir:
            self.runtime.bind_result_dir(self.ctx, result_dir)
            self._flush_trace(result_dir)
            self.runtime.publish_artifact(result_dir, ctx=self.ctx)

    def _flush_transcript(self, result_dir: str) -> None:
        recorder = getattr(self.runtime, "record_agent_turn", None)
        if not callable(recorder):
            return
        for row in self.transcript:
            event_id = f"{row.get('kind')}|{row.get('message_id') or row.get('tool_call_id') or row.get('sequence')}"
            signature = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
            if self.persisted_transcript_events.get(event_id) == signature:
                continue
            recorder(self.ctx, row, result_dir=result_dir)
            self.persisted_transcript_events[event_id] = signature

    def _flush_trace(self, result_dir: str) -> None:
        recorder = getattr(self.runtime, "record_agent_turn", None)
        if not callable(recorder):
            return
        for index, row in enumerate(self.trace):
            signature = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
            if self.persisted_turns.get(index) == signature:
                continue
            recorder(self.ctx, row, result_dir=result_dir)
            self.persisted_turns[index] = signature

    def _current_result_dir(self) -> str | None:
        return (
            getattr(self.ctx, "runtime_result_dir", None)
            or self.ctx.design_result.get("result_dir")
            or None
        )

def _seed_candidate_payload(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "case_id": candidate.case_id,
        "title": candidate.title,
        "category": candidate.category,
        "path": candidate.path,
        "reasons": [str(item)[:180] for item in candidate.reasons[:3]],
        "risks": [str(item)[:180] for item in candidate.risks[:3]],
        "applied": candidate.applied,
        "inspected": candidate.inspected,
        "params": public_params_dict(candidate.params),
    }





def _aggregate_model_usage(rows: Any) -> dict[str, int]:
    totals = {
        "optimization_input_tokens": 0,
        "optimization_output_tokens": 0,
        "optimization_cache_read_tokens": 0,
        "optimization_cache_write_tokens": 0,
        "optimization_total_tokens": 0,
    }
    count = 0
    mapping = {
        "input": "optimization_input_tokens",
        "output": "optimization_output_tokens",
        "cacheRead": "optimization_cache_read_tokens",
        "cacheWrite": "optimization_cache_write_tokens",
        "totalTokens": "optimization_total_tokens",
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        count += 1
        for source, target in mapping.items():
            try:
                totals[target] += int(row.get(source) or 0)
            except (TypeError, ValueError):
                continue
    totals["optimization_model_turns"] = count
    return totals


def _optimization_memory(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "seed_selection_lessons": str(memory.get("seed_selection_lessons") or ""),
        "optimization_lessons": str(memory.get("optimization_lessons") or ""),
        "final_review_lessons": str(memory.get("final_review_lessons") or ""),
    }


def _trace_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    pending_calls: dict[str, dict[str, Any]] = {}
    for event in events:
        event_type = str(event.get("type") or "pi_event")
        if event_type == "tool_execution_start":
            pending_calls[_tool_event_key(event, len(trace))] = event
            continue
        if event_type == "tool_execution_end":
            key = _tool_event_key(event, len(trace))
            start_event = pending_calls.pop(key, {})
            trace.append(_tool_turn_from_events(start_event, event, turn=len(trace)))
            continue
    return trace


def _tool_event_key(event: dict[str, Any], fallback: int) -> str:
    return str(event.get("tool_call_id") or event.get("tool_name") or fallback)


def _tool_start_turn(event: dict[str, Any], *, turn: int) -> dict[str, Any]:
    tool_name = str(event.get("tool_name") or "tool")
    arguments = _tool_arguments(event)
    observation = f"{tool_name} is running."
    row = {
        "agent": OptimizationRunner.name,
        "turn": turn,
        "thought": _decision_summary(event) or f"Started {tool_name} from the current optimization state.",
        "tool_call": {"name": tool_name, "arguments": arguments},
        "tool_result": {
            "ok": True,
            "observation": observation,
            "metadata": {"status": "running"},
            "data": event,
        },
        "observation": observation,
        "done": False,
        "action": tool_name,
        "action_input": arguments,
        "data": event,
        "status": str(event.get("status") or "running"),
        **_native_event_projection(event),
    }
    timestamp = event.get("time") or event.get("timestamp")
    if timestamp:
        row["timestamp"] = timestamp
    return row


def _tool_call_event(
    event: dict[str, Any],
    *,
    turn: int,
    sequence: int,
    start_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    start_event = start_event or {}
    tool_name = str(event.get("tool_name") or start_event.get("tool_name") or "tool")
    arguments = _tool_arguments(event) or _tool_arguments(start_event)
    tool_call_id = str(event.get("tool_call_id") or f"{tool_name}-{turn}")
    row = {
        "agent": OptimizationRunner.name,
        "kind": "tool_call",
        "turn": turn,
        "sequence": sequence,
        "tool": tool_name,
        "tool_call_id": tool_call_id,
        "arguments": arguments,
        "tool_call": {"name": tool_name, "arguments": arguments},
        "status": str(event.get("status") or "running"),
        "data": event,
        **_native_event_projection(event),
    }
    if event.get("partial_result") is not None:
        row["partial_result"] = event.get("partial_result")
    timestamp = event.get("time") or event.get("timestamp")
    if timestamp:
        row["timestamp"] = timestamp
    return row


def _tool_turn_from_events(start_event: dict[str, Any], end_event: dict[str, Any], *, turn: int) -> dict[str, Any]:
    tool_name = str(end_event.get("tool_name") or start_event.get("tool_name") or "tool")
    arguments = _tool_arguments(start_event) or _tool_arguments(end_event)
    result = _normalized_tool_result(end_event)
    observation = str(result.get("observation") or tool_name)
    row = {
        "agent": OptimizationRunner.name,
        "turn": turn,
        "thought": str(
            _decision_summary(end_event)
            or _decision_summary(start_event)
            or f"Selected {tool_name} from the current optimization state."
        ),
        "tool_call": {"name": tool_name, "arguments": arguments},
        "tool_result": {**result, "data": end_event},
        "observation": observation,
        "done": False,
        "action": tool_name,
        "action_input": arguments,
        "data": end_event,
        "status": str(end_event.get("status") or ("error" if end_event.get("is_error") else "ok")),
        **_native_event_projection(end_event),
    }
    if end_event.get("duration_ms") is not None:
        row["duration_ms"] = end_event.get("duration_ms")
    timestamp = end_event.get("time") or end_event.get("timestamp") or start_event.get("time") or start_event.get("timestamp")
    if timestamp:
        row["timestamp"] = timestamp
    return row


def _tool_result_event(event: dict[str, Any], *, turn: int, sequence: int) -> dict[str, Any]:
    tool_name = str(event.get("tool_name") or "tool")
    result = _normalized_tool_result(event)
    tool_call_id = str(event.get("tool_call_id") or f"{tool_name}-{turn}")
    row = {
        "agent": OptimizationRunner.name,
        "kind": "tool_result",
        "turn": turn,
        "sequence": sequence,
        "tool": tool_name,
        "tool_call_id": tool_call_id,
        "tool_result": {**result, "data": event},
        "observation": str(result.get("observation") or tool_name),
        "ok": result.get("ok"),
        "metrics": result.get("metrics", {}),
        "artifacts": result.get("artifacts", []),
        "error": result.get("error"),
        "duration_ms": event.get("duration_ms"),
        "data": event,
        "status": str(event.get("status") or ("error" if event.get("is_error") else "ok")),
        **_native_event_projection(event),
    }
    summary = _decision_summary(event)
    if summary:
        row["thought"] = summary
    timestamp = event.get("time") or event.get("timestamp")
    if timestamp:
        row["timestamp"] = timestamp
    return row


def _normalized_tool_result(event: dict[str, Any]) -> dict[str, Any]:
    raw_result = event.get("result") if isinstance(event.get("result"), dict) else {}
    details = raw_result.get("details") if isinstance(raw_result.get("details"), dict) else {}
    ok = not bool(event.get("is_error"))
    if "ok" in details:
        ok = bool(details.get("ok"))
    observation = (
        details.get("observation")
        or raw_result.get("observation")
        or raw_result.get("message")
        or _content_text(raw_result.get("content"))
        or str(event.get("type") or "tool_execution_end")
    )
    result = {
        "ok": ok,
        "observation": str(observation),
    }
    for key in ("metrics", "artifacts", "error", "state_patch", "metadata"):
        if key in details:
            result[key] = details.get(key)
    return result


def _result_dir_from_tool_event(event: dict[str, Any]) -> str | None:
    raw_result = event.get("result") if isinstance(event.get("result"), dict) else {}
    details = raw_result.get("details") if isinstance(raw_result.get("details"), dict) else {}
    for payload in (details.get("state_patch"), raw_result.get("state_patch")):
        if isinstance(payload, dict) and payload.get("active_result_dir"):
            return str(payload["active_result_dir"])
    for payload in (details.get("data"), raw_result.get("data")):
        if isinstance(payload, dict) and payload.get("result_dir"):
            return str(payload["result_dir"])
    for payload in (details.get("artifacts"), raw_result.get("artifacts")):
        if not isinstance(payload, list):
            continue
        for artifact in payload:
            if not isinstance(artifact, dict):
                continue
            if artifact.get("role") == "run_result_dir" or artifact.get("kind") == "directory":
                path = artifact.get("path")
                if path:
                    return str(path)
    return None


def _tool_arguments(event: dict[str, Any]) -> dict[str, Any]:
    args = event.get("args") if isinstance(event.get("args"), dict) else {}
    return {key: value for key, value in args.items() if key != "decision_summary"}


def _native_event_projection(event: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in (
        "source_event_type",
        "assistant_event_type",
        "content_type",
        "content_index",
        "update_type",
        "delta_length",
        "stop_reason",
    ):
        if event.get(key) is not None:
            payload[key] = event.get(key)
    return payload


def _decision_summary(*events: dict[str, Any]) -> str:
    for event in events:
        if not isinstance(event, dict):
            continue
        for key in ("decision_summary", "thought"):
            value = event.get(key)
            if value:
                return str(value)
        args = event.get("args") if isinstance(event.get("args"), dict) else {}
        if args.get("decision_summary"):
            return str(args["decision_summary"])
        raw_result = event.get("result") if isinstance(event.get("result"), dict) else {}
        details = raw_result.get("details") if isinstance(raw_result.get("details"), dict) else {}
        metadata = details.get("metadata") if isinstance(details.get("metadata"), dict) else {}
        if metadata.get("decision_summary"):
            return str(metadata["decision_summary"])
    return ""


def _content_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
            parts.append(str(item.get("text")))
    return "\n".join(parts).strip()


__all__ = ["OptimizationRunner"]
