from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _css() -> str:
    return (PROJECT_ROOT / "src" / "ui" / "dashboard.css").read_text(encoding="utf-8")


def _css_rule(selector: str, *, occurrence: int = -1) -> str:
    pattern = re.compile(rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\}}", re.DOTALL)
    matches = pattern.findall(_css())
    if not matches:
        raise AssertionError(f"Missing CSS rule for {selector}")
    return matches[occurrence]


def _js_function_body(name: str) -> str:
    pattern = re.compile(rf"function {re.escape(name)}\([^)]*\)\s*\{{(?P<body>[\s\S]*?)\n  \}}")
    match = pattern.search(_js())
    if not match:
        raise AssertionError(f"Missing JS function {name}")
    return match.group("body")


def _js() -> str:
    return (PROJECT_ROOT / "src" / "ui" / "dashboard.js").read_text(encoding="utf-8")


class DashboardProcessLayoutTest(unittest.TestCase):
    def test_current_turn_number_is_deep_blue(self) -> None:
        number_rule = _css_rule(".optimization-progress-number")

        self.assertRegex(number_rule, r"color\s*:\s*#1d4ed8\s*;")

    def test_transcript_spans_current_snapshot_and_initial_structure_height(self) -> None:
        layout_rule = _css_rule(".process-layout", occurrence=1)
        side_rule = _css_rule(".process-side-rail", occurrence=1)
        transcript_rule = _css_rule(".process-transcript-card", occurrence=1)
        seed_rule = _css_rule(".seed-evidence-card", occurrence=0)

        self.assertRegex(layout_rule, r"--process-final-card-height\s*:\s*460px\s*;")
        self.assertRegex(layout_rule, r"--process-reference-card-height\s*:\s*var\(--process-final-card-height\)\s*;")
        self.assertRegex(layout_rule, r"grid-template-rows\s*:\s*max-content\s+minmax\(var\(--process-reference-card-height\),\s*max-content\)\s+var\(--process-final-card-height\)\s*;")
        self.assertRegex(layout_rule, r"align-items\s*:\s*start\s*;")
        self.assertRegex(side_rule, r"display\s*:\s*contents\s*;")
        self.assertRegex(transcript_rule, r"grid-row\s*:\s*1\s*/\s*3\s*;")
        self.assertRegex(transcript_rule, r"align-self\s*:\s*stretch\s*;")
        self.assertRegex(transcript_rule, r"height\s*:\s*100%\s*;")
        self.assertRegex(transcript_rule, r"max-height\s*:\s*none\s*;")
        self.assertNotRegex(transcript_rule, r"min-height\s*:\s*720px\s*;")
        self.assertRegex(seed_rule, r"grid-row\s*:\s*2\s*;")
        self.assertRegex(seed_rule, r"height\s*:\s*auto\s*;")
        self.assertRegex(seed_rule, r"min-height\s*:\s*var\(--process-reference-card-height\)\s*;")

    def test_transcript_inner_frame_owns_scroll_and_turn_jumps(self) -> None:
        transcript_rule = _css_rule(".process-transcript-card", occurrence=1)
        stages_rule = _css_rule(".process-transcript-card #optimization-stages")
        render_body = _js_function_body("renderOptimizationStages")
        jump_body = _js_function_body("scrollTranscriptTurnIntoView")

        self.assertRegex(transcript_rule, r"overflow\s*:\s*hidden\s*;")
        self.assertRegex(stages_rule, r"flex\s*:\s*1\s+1\s+0\s*;")
        self.assertRegex(stages_rule, r"height\s*:\s*100%\s*;")
        self.assertRegex(stages_rule, r"overflow-y\s*:\s*auto\s*;")
        self.assertRegex(stages_rule, r"scrollbar-gutter\s*:\s*stable\s*;")
        self.assertRegex(stages_rule, r"display\s*:\s*grid\s*;")
        self.assertRegex(stages_rule, r"padding\s*:\s*18px\s*;")
        self.assertIn("optimizationProgressPanel.innerHTML = renderOptimizationProgress(progressEvents, turnCount)", render_body)
        self.assertNotRegex(render_body, r"optimizationStages\.innerHTML\s*=\s*renderOptimizationProgress\(progressEvents,\s*turnCount\)")
        self.assertIn("optimizationStages.scrollTo", jump_body)
        self.assertNotIn("window.scrollTo", jump_body)
        self.assertNotIn("scrollIntoView", jump_body)

    def test_transcript_scroll_container_keeps_frame_and_inner_wrapper_is_unframed(self) -> None:
        stages_rule = _css_rule(".process-transcript-card #optimization-stages")
        transcript_card_rule = _css_rule(".transcript-card")
        last_entry_rule = _css_rule(".transcript-stream .transcript-entry:last-child")

        self.assertRegex(stages_rule, r"border\s*:\s*1px\s+solid\s+var\(--enterprise-line\)\s*;")
        self.assertRegex(stages_rule, r"border-radius\s*:\s*4px\s*;")
        self.assertRegex(stages_rule, r"background\s*:\s*#fff\s*;")
        self.assertRegex(transcript_card_rule, r"padding\s*:\s*0\s*;")
        self.assertRegex(transcript_card_rule, r"border\s*:\s*0\s*;")
        self.assertRegex(transcript_card_rule, r"background\s*:\s*transparent\s*;")
        self.assertRegex(last_entry_rule, r"margin-bottom\s*:\s*8px\s*;")

    def test_transcript_scroll_does_not_trap_page_wheel_scrolling(self) -> None:
        stages_rule = _css_rule(".process-transcript-card #optimization-stages")

        self.assertRegex(stages_rule, r"overflow-y\s*:\s*auto\s*;")
        self.assertNotRegex(stages_rule, r"overscroll-behavior\s*:\s*contain\s*;")
        self.assertRegex(stages_rule, r"overscroll-behavior-y\s*:\s*auto\s*;")

    def test_transcript_empty_state_matches_the_right_side_pending_panel(self) -> None:
        empty_container_rule = _css_rule(".process-transcript-card #optimization-stages:has(> .empty-state:only-child)")
        empty_rule = _css_rule(".process-transcript-card #optimization-stages > .empty-state")

        self.assertRegex(empty_container_rule, r"grid-template-rows\s*:\s*minmax\(0,\s*1fr\)\s*;")
        self.assertRegex(empty_container_rule, r"padding\s*:\s*0\s*;")
        self.assertRegex(empty_container_rule, r"scrollbar-gutter\s*:\s*auto\s*;")
        self.assertRegex(empty_rule, r"align-self\s*:\s*stretch\s*;")
        self.assertRegex(empty_rule, r"height\s*:\s*100%\s*;")
        self.assertRegex(empty_rule, r"min-height\s*:\s*100%\s*;")
        self.assertRegex(empty_rule, r"border\s*:\s*0\s*;")
        self.assertRegex(empty_rule, r"background\s*:\s*transparent\s*;")

    def test_initial_structure_list_expands_above_fixed_preview(self) -> None:
        grid_rule = _css_rule(".seed-evidence-grid")
        placeholder_grid_rule = _css_rule(".seed-evidence-grid:has(#initial-structure > .empty-state:only-child)")
        references_rule = _css_rule(".seed-evidence-grid #references")
        initial_rule = _css_rule(".seed-evidence-grid #initial-structure")
        image_rule = _css_rule(
            ".process-card.current-snapshot-card .result-panel.no-head .result-image,\n"
            "    .process-card .seed-evidence-grid .result-panel.no-head .result-image"
        )

        self.assertRegex(grid_rule, r"grid-template-rows\s*:\s*max-content\s+var\(--process-preview-height\)\s*;")
        self.assertRegex(placeholder_grid_rule, r"grid-template-rows\s*:\s*max-content\s+minmax\(var\(--process-preview-height\),\s*1fr\)\s*;")
        self.assertNotIn("--process-reference-list-height", _css())
        self.assertRegex(references_rule, r"overflow-y\s*:\s*visible\s*;")
        self.assertRegex(initial_rule, r"height\s*:\s*var\(--process-preview-height\)\s*;")
        self.assertRegex(initial_rule, r"overflow\s*:\s*hidden\s*;")
        self.assertRegex(image_rule, r"height\s*:\s*var\(--process-preview-height\)\s*;")
        self.assertRegex(image_rule, r"max-height\s*:\s*var\(--process-preview-height\)\s*;")

    def test_final_design_image_margins_are_plain_white(self) -> None:
        wrap_rule = _css_rule(".final-stage-panel.no-head > .result-image-wrap")
        image_rule = _css_rule(".final-stage-panel.no-head > .result-image-wrap > .result-image")

        self.assertRegex(wrap_rule, r"background\s*:\s*#fff\s*;")
        self.assertRegex(image_rule, r"background\s*:\s*#fff\s*;")
        self.assertNotRegex(wrap_rule, r"linear-gradient")
        self.assertNotRegex(image_rule, r"linear-gradient")

    def test_completion_thumbnail_image_margins_are_plain_white(self) -> None:
        thumb_rule = _css_rule(".completion-thumb", occurrence=0)
        thumb_image_rule = _css_rule(".completion-thumb .result-image", occurrence=0)

        self.assertRegex(thumb_rule, r"background\s*:\s*#fff\s*;")
        self.assertRegex(thumb_image_rule, r"background\s*:\s*#fff\s*;")
        self.assertNotRegex(thumb_image_rule, r"repeating-linear-gradient")

    def test_current_snapshot_inner_panel_fills_card_body(self) -> None:
        current_rule = _css_rule(".current-snapshot-card #current-snapshot")
        child_rule = _css_rule(
            ".current-snapshot-card #current-snapshot > .empty-state,\n"
            "    .current-snapshot-card #current-snapshot > .empty,\n"
            "    .current-snapshot-card #current-snapshot > .result-panel"
        )
        image_rule = _css_rule(".current-snapshot-card .result-panel.no-head .result-image")

        self.assertRegex(current_rule, r"display\s*:\s*grid\s*;")
        self.assertRegex(current_rule, r"height\s*:\s*100%\s*;")
        self.assertRegex(child_rule, r"height\s*:\s*100%\s*;")
        self.assertRegex(child_rule, r"min-height\s*:\s*100%\s*;")
        self.assertRegex(image_rule, r"object-fit\s*:\s*cover\s*;")

    def test_result_metrics_card_aligns_with_file_index_and_uses_tighter_row_gaps(self) -> None:
        card_rule = _css_rule("#view-results .result-layout > .stage-card")
        metrics_rule = _css_rule("#view-results .metrics")
        metric_rule = _css_rule("#view-results .metric")

        self.assertRegex(card_rule, r"align-self\s*:\s*stretch\s*;")
        self.assertRegex(metrics_rule, r"column-gap\s*:\s*36px\s*;")
        self.assertRegex(metric_rule, r"column-gap\s*:\s*6px\s*;")

    def test_completion_summary_uses_available_text_space_without_character_truncation(self) -> None:
        js = _js()
        narrative_rule = _css_rule(".completion-narrative")
        paragraph_rule = _css_rule(".completion-narrative p")

        self.assertNotIn("compactSummaryText", js)
        self.assertRegex(narrative_rule, r"display\s*:\s*flex\s*;")
        self.assertRegex(narrative_rule, r"flex-direction\s*:\s*column\s*;")
        self.assertRegex(narrative_rule, r"min-height\s*:\s*0\s*;")
        self.assertRegex(paragraph_rule, r"flex\s*:\s*1\s+1\s+auto\s*;")
        self.assertRegex(paragraph_rule, r"display\s*:\s*block\s*;")
        self.assertNotIn("-webkit-line-clamp", paragraph_rule)

    def test_narrow_layout_returns_to_single_column_flow(self) -> None:
        css = _css()

        self.assertRegex(css, r"@media \(max-width: 1180px\)[\s\S]*?\.process-side-rail\s*\{[\s\S]*?display\s*:\s*grid\s*;")
        self.assertRegex(css, r"@media \(max-width: 1180px\)[\s\S]*?\.process-transcript-card\s*\{[\s\S]*?grid-row\s*:\s*auto\s*;")
        self.assertRegex(css, r"@media \(max-width: 1180px\)[\s\S]*?\.seed-evidence-card\s*\{[\s\S]*?grid-row\s*:\s*auto\s*;")

    def test_turn_anchor_is_consumed_only_for_rendered_events(self) -> None:
        js = _js()
        event_body = re.search(
            r"function renderTranscriptEvent\(event,\s*anchorTurns,\s*completedToolStatuses,\s*liveProgress\)\s*\{(?P<body>[\s\S]*?)\n  \}\n\n  function renderTranscriptEvents",
            js,
        )

        self.assertIsNotNone(event_body)
        self.assertIn("function turnAnchorAttrs", js)
        self.assertNotIn("const anchor = anchorTurns.has(turn)", event_body.group("body"))
        self.assertRegex(js, r"if \(!text\) return \"\";[\s\S]*?turnAnchorAttrs\(turn,\s*anchorTurns\)")

    def test_completed_agent_event_does_not_add_an_extra_progress_turn(self) -> None:
        node_script = f"""
const fs = require("fs");
const vm = require("vm");

const elements = new Map();
function classList() {{
  return {{
    add() {{}},
    remove() {{}},
    toggle() {{}},
    contains() {{ return false; }},
  }};
}}
function makeElement(id = "") {{
  return {{
    id,
    dataset: {{}},
    style: {{}},
    classList: classList(),
    value: "",
    disabled: false,
    textContent: "",
    innerHTML: "",
    scrollTop: 0,
    scrollHeight: 0,
    listeners: {{}},
    appendChild(child) {{ this.lastChild = child; }},
    addEventListener(type, handler) {{ this.listeners[type] = handler; }},
    querySelectorAll() {{ return []; }},
    querySelector() {{ return null; }},
    closest() {{ return null; }},
    getBoundingClientRect() {{ return {{ top: 0 }}; }},
    scrollTo(args) {{ this.scrollTop = args.top || 0; }},
  }};
}}
function element(id) {{
  if (!elements.has(id)) elements.set(id, makeElement(id));
  return elements.get(id);
}}

const modeButton = makeElement("mode-natural");
modeButton.dataset.mode = "natural";

global.window = {{
  LENSBOT_DEFAULTS: {{}},
  location: {{ hash: "" }},
  history: {{ replaceState() {{}} }},
  scrollX: 0,
  scrollY: 0,
  setInterval() {{ return 1; }},
  clearInterval() {{}},
  addEventListener() {{}},
  scrollTo() {{}},
  getComputedStyle() {{ return {{ scrollMarginTop: "0" }}; }},
}};
global.history = window.history;
global.document = {{
  querySelectorAll(selector) {{
    if (selector === "#mode-toggle button") return [modeButton];
    return [];
  }},
  querySelector() {{ return null; }},
  getElementById(id) {{ return element(id); }},
  addEventListener() {{}},
  createElement() {{ return makeElement(); }},
}};
global.fetch = async () => ({{
  ok: true,
  json: async () => ({{ run_id: "unit-run" }}),
}});
let source;
global.EventSource = class {{
  constructor() {{ source = this; this.listeners = {{}}; }}
  addEventListener(type, handler) {{ this.listeners[type] = handler; }}
  close() {{}}
}};

async function main() {{
vm.runInThisContext(fs.readFileSync({str(PROJECT_ROOT / "src" / "ui" / "dashboard.js")!r}, "utf8"));
await element("run-btn").listeners.click();
source.listeners.result({{
  lastEventId: "result-1",
  data: JSON.stringify({{
    ok: true,
    metrics: {{}},
    references: [],
    preview: {{
      optimization_stages: [{{
        data: {{
          turn_count: 14,
          transcript_events: [
            {{ kind: "assistant_message", turn: 12, text: "final reasoning" }},
            {{ kind: "tool_call", turn: 12, tool: "finish", tool_call: {{ name: "finish", arguments: {{}} }} }},
            {{ kind: "tool_result", turn: 12, tool: "finish", tool_result: {{ ok: true, observation: "Optimization finish validated." }}, ok: true }},
            {{ kind: "agent_end", turn: 13, text: "Optimization agent finished.", done: true }}
          ]
        }}
      }}]
    }}
  }})
}});

const progressHtml = element("optimization-progress-panel").innerHTML;
if (!progressHtml.includes("optimization-progress-number\\">13<")) {{
  throw new Error("Expected current progress turn 13, got: " + progressHtml);
}}
if (progressHtml.includes("data-turn-anchor=\\"13\\"")) {{
  throw new Error("Completion event generated a 14th jump button: " + progressHtml);
}}
}}
main().catch((error) => {{
  console.error(error.stack || error);
  process.exit(1);
}});
"""
        result = subprocess.run(
            ["node", "--eval", node_script],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
