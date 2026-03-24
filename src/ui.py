from __future__ import annotations

from html import escape
from pathlib import Path

import gradio as gr

from agent.context import build_agent_input
from agent.loop import LensResearchAgent
from settings import load_default_controls, load_default_params


PROJECT_ROOT = Path(__file__).resolve().parents[1]

HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Sora:wght@400;500;600;700&display=swap" rel="stylesheet">
"""

CSS = """
:root {
  --bg: #0c111b;
  --bg-elevated: #101827;
  --panel: rgba(16, 24, 39, 0.82);
  --panel-strong: rgba(12, 17, 27, 0.96);
  --panel-soft: rgba(17, 24, 39, 0.66);
  --text: #e8edf5;
  --text-muted: #94a3b8;
  --text-soft: #c8d2e1;
  --border: rgba(148, 163, 184, 0.16);
  --border-strong: rgba(148, 163, 184, 0.28);
  --accent: #22c55e;
  --accent-strong: #16a34a;
  --accent-soft: rgba(34, 197, 94, 0.14);
  --accent-blue: #38bdf8;
  --warn: #f59e0b;
  --danger: #fb7185;
  --shadow: 0 24px 80px rgba(0, 0, 0, 0.28);
  --radius-lg: 22px;
  --radius-md: 16px;
  --radius-sm: 12px;
  --hero: radial-gradient(circle at top left, rgba(56, 189, 248, 0.12), transparent 28%),
    radial-gradient(circle at 85% 10%, rgba(34, 197, 94, 0.16), transparent 22%),
    linear-gradient(180deg, #0b1020 0%, #0e1625 44%, #0c111b 100%);
}

html, body, .gradio-container {
  background: var(--hero) !important;
  color: var(--text) !important;
  font-family: "Sora", sans-serif !important;
}

.gradio-container {
  max-width: 1480px !important;
  margin: 0 auto !important;
  padding: 28px 20px 40px !important;
}

h1, h2, h3, h4, p, span, label, textarea, input, button {
  font-family: "Sora", sans-serif !important;
}

code, pre, .mono, .artifact-path, .metric-value {
  font-family: "JetBrains Mono", monospace !important;
}

.app-shell {
  position: relative;
}

.app-shell::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(148, 163, 184, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.05) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: linear-gradient(180deg, rgba(0,0,0,.18), transparent 70%);
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 20px;
  margin-bottom: 22px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel-soft);
  backdrop-filter: blur(18px);
  box-shadow: var(--shadow);
}

.brand {
  display: flex;
  align-items: center;
  gap: 16px;
}

.brand-mark {
  width: 48px;
  height: 48px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  color: white;
  font-weight: 700;
  letter-spacing: 0.08em;
  background: linear-gradient(135deg, var(--accent-blue), var(--accent));
  box-shadow: 0 16px 40px rgba(34, 197, 94, 0.16);
}

.brand-copy h1 {
  margin: 0;
  font-size: 1.08rem;
  font-weight: 700;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel-strong);
  color: var(--text-soft);
  font-size: 0.82rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--accent);
  box-shadow: 0 0 0 6px var(--accent-soft);
}

.artifact-card, .metric-card, .reference-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--panel);
  backdrop-filter: blur(18px);
  box-shadow: var(--shadow);
}

#mission-panel, #intel-panel, #result-panel, #metric-panel, #trace-panel {
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-lg) !important;
  background: var(--panel) !important;
  box-shadow: var(--shadow) !important;
}

#mission-panel, #intel-panel {
  padding: 8px !important;
}

.gr-group, .gr-box, .gr-panel {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}

.gradio-container .block-title {
  color: var(--text) !important;
}

.gradio-container .gr-button {
  border-radius: 16px !important;
  border: 1px solid transparent !important;
  min-height: 48px !important;
  font-weight: 600 !important;
}

.gradio-container .gr-button-primary {
  background: linear-gradient(135deg, var(--accent-blue), var(--accent)) !important;
  color: white !important;
  box-shadow: 0 16px 36px rgba(34, 197, 94, 0.18);
}

.gradio-container .gr-button-primary:hover {
  filter: brightness(1.04);
}

.gradio-container input,
.gradio-container textarea,
.gradio-container .wrap,
.gradio-container .gr-input,
.gradio-container .gr-textbox,
.gradio-container .gr-number,
.gradio-container .gr-dropdown,
.gradio-container .gradio-slider input {
  background: var(--panel-strong) !important;
  color: var(--text) !important;
  border-color: var(--border) !important;
}

.gradio-container label,
.gradio-container .gr-form label,
.gradio-container .gradio-checkbox label,
.gradio-container .gradio-radio label {
  color: var(--text-soft) !important;
}

.gradio-container .gradio-radio,
.gradio-container .gradio-checkbox,
.gradio-container .gradio-slider {
  background: transparent !important;
}

.gradio-container .tabs {
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-lg) !important;
  background: var(--panel) !important;
  box-shadow: var(--shadow) !important;
}

.gradio-container button[role="tab"] {
  font-weight: 600 !important;
  color: var(--text-muted) !important;
}

.gradio-container button[role="tab"][aria-selected="true"] {
  color: var(--text) !important;
}

.status-card {
  padding: 20px 22px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(56, 189, 248, 0.08), transparent 80%), var(--panel);
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.status-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
}

.status-copy {
  margin: 6px 0 0;
  color: var(--text-soft);
  line-height: 1.7;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 0.82rem;
  font-weight: 700;
}

.artifact-grid, .metric-grid, .reference-grid {
  display: grid;
  gap: 14px;
}

.artifact-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.metric-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.artifact-card, .metric-card, .reference-card {
  padding: 18px;
}

.artifact-label, .metric-label {
  margin: 0 0 8px;
  color: var(--text-muted);
  font-size: 0.8rem;
  text-transform: uppercase;
}

.artifact-path {
  word-break: break-all;
  color: var(--text);
  font-size: 0.84rem;
  line-height: 1.65;
}

.metric-value {
  margin: 0;
  font-size: 1.18rem;
  font-weight: 700;
  color: var(--text);
}

.metric-footnote, .reference-copy {
  margin: 8px 0 0;
  color: var(--text-soft);
  font-size: 0.88rem;
  line-height: 1.65;
}

.reference-meta {
  margin-top: 10px;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.empty-state {
  padding: 28px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-lg);
  color: var(--text-muted);
  text-align: center;
}

@media (max-width: 1100px) {
  .artifact-grid,
  .metric-grid {
    grid-template-columns: 1fr;
  }
}
"""


def build_agent() -> LensResearchAgent:
    return LensResearchAgent(load_default_params(PROJECT_ROOT), PROJECT_ROOT)


def _build_param_input(
    mode: str,
    nl_prompt: str,
    foclen: float,
    fov: float,
    fnum: float,
    bfl: float,
    thickness: float,
    iterations: int,
    spp: int,
    test_per_iter: int,
    enable_patent_search: bool,
) -> object:
    return build_agent_input(
        PROJECT_ROOT,
        mode=mode,
        nl_prompt=nl_prompt,
        foclen=foclen,
        fov=fov,
        fnum=fnum,
        bfl=bfl,
        thickness=thickness,
        iterations=iterations,
        spp=spp,
        test_per_iter=test_per_iter,
        enable_patent_search=enable_patent_search,
    )


def _status_html(summary: str, ok: bool) -> str:
    badge = "完成" if ok else "失败"
    return f"""
    <div class="status-card">
      <div class="status-row">
        <div>
          <p class="status-title">运行状态</p>
          <p class="status-copy">{escape(summary)}</p>
        </div>
        <div class="status-badge"><span class="status-dot"></span>{badge}</div>
      </div>
    </div>
    """


def _artifacts_html(result_dir: str, curriculum_json: str, final_json: str, log_file: str) -> str:
    items = [
        ("结果目录", result_dir or "-"),
        ("课程学习结果", curriculum_json or "-"),
        ("最终结果", final_json or "-"),
        ("运行日志", log_file or "-"),
    ]
    cards = "".join(
        f"""
        <div class="artifact-card">
          <p class="artifact-label">{label}</p>
          <div class="artifact-path">{escape(value)}</div>
        </div>
        """
        for label, value in items
    )
    return f'<div class="artifact-grid">{cards}</div>'


def _metrics_html(metrics: dict) -> str:
    if not metrics:
        return '<div class="empty-state">运行后显示指标。</div>'

    display_items = [
        ("完成度", metrics.get("artifact_score"), "综合完成度"),
        ("边缘 Spot RMS", metrics.get("spot_rms_um_edge"), "um"),
        ("中心 Spot RMS", metrics.get("spot_rms_um_center"), "um"),
        ("边缘畸变", metrics.get("distortion_pct_edge"), "%"),
        ("中心 MTF50", metrics.get("mtf50_center_tan_cy_mm"), "cy/mm"),
        ("RFOV", metrics.get("rfov"), "rad"),
    ]
    cards = "".join(
        f"""
        <div class="metric-card">
          <p class="metric-label">{label}</p>
          <p class="metric-value">{escape(str(value))}</p>
          <p class="metric-footnote">{note}</p>
        </div>
        """
        for label, value, note in display_items
    )
    return f'<div class="metric-grid">{cards}</div>'


def _references_html(references: list[dict]) -> str:
    if not references:
        return '<div class="empty-state">没有参考结果。</div>'

    cards = []
    for item in references[:6]:
        title = escape(str(item.get("title", "未命名")))
        snippet = escape(str(item.get("snippet", "")))
        meta = " · ".join(
            part for part in [str(item.get("source", "")), str(item.get("published", "")), str(item.get("patent_id", ""))] if part
        )
        cards.append(
            f"""
            <div class="reference-card">
              <p class="metric-label">参考</p>
              <p class="metric-value">{title}</p>
              <p class="reference-copy">{snippet or "无摘要。"}</p>
              <div class="reference-meta">{escape(meta) if meta else "无元数据"}</div>
            </div>
            """
        )
    return f'<div class="reference-grid">{"".join(cards)}</div>'


def _memory_md(memory_snapshot: dict, agent: LensResearchAgent) -> str:
    recent = agent.memory.load_recent_episodes(limit=3)
    semantic = agent.memory.load_semantic_notes(limit=6)
    lines = ["### 运行记录"]
    lines.append(f"- 本次轨迹步数: {len(memory_snapshot.get('timeline', []))}")
    lines.append(f"- 最近运行次数: {len(recent)}")
    lines.append(f"- 经验笔记数: {len(semantic)}")
    if semantic:
        lines.append("")
        lines.append("最近笔记:")
        lines.extend(f"- {item}" for item in semantic[-3:])
    return "\n".join(lines)


def _timeline_md(timeline: list[str]) -> str:
    if not timeline:
        return "### 执行轨迹\n- 暂无记录"
    return "### 执行轨迹\n" + "\n".join(f"- {escape(item)}" for item in timeline)


def run_agent(
    mode: str,
    nl_prompt: str,
    foclen: float,
    fov: float,
    fnum: float,
    bfl: float,
    thickness: float,
    iterations: int,
    spp: int,
    test_per_iter: int,
    enable_patent_search: bool,
):
    agent = build_agent()
    agent_input = _build_param_input(
        mode,
        nl_prompt,
        foclen,
        fov,
        fnum,
        bfl,
        thickness,
        iterations,
        spp,
        test_per_iter,
        enable_patent_search,
    )
    result = agent.run(agent_input)

    return (
        _status_html(result.summary, result.ok),
        result.summary,
        _artifacts_html(
            result.result_dir or "",
            result.curriculum_json or "",
            result.final_json or "",
            result.log_file or "",
        ),
        _metrics_html(result.metrics),
        _timeline_md(result.timeline),
        _references_html(result.references),
        _memory_md(result.memory_snapshot, agent),
    )


def toggle_input_mode(mode: str):
    is_nl = mode == "自然语言输入"
    return gr.update(visible=is_nl), gr.update(visible=not is_nl)


def build_ui() -> gr.Blocks:
    defaults = load_default_params(PROJECT_ROOT)
    controls = load_default_controls(PROJECT_ROOT)
    theme = gr.themes.Base(
        font=["Sora", "ui-sans-serif", "sans-serif"],
        font_mono=["JetBrains Mono", "ui-monospace", "monospace"],
        radius_size=gr.themes.sizes.radius_lg,
    )

    with gr.Blocks(
        title="LensBot",
        theme=theme,
        css=CSS,
        head=HEAD,
        fill_height=True,
    ) as demo:
        gr.HTML(
            """
            <div class="app-shell">
                <div class="topbar">
                <div class="brand">
                  <div class="brand-mark">LB</div>
                  <div class="brand-copy">
                    <h1>LensBot</h1>
                  </div>
                </div>
                <div class="topbar-actions">
                  <div class="pill"><span class="status-dot"></span>就绪</div>
                </div>
              </div>
            </div>
            """
        )

        with gr.Row():
            with gr.Column(scale=5, elem_id="mission-panel"):
                gr.Markdown("### 任务")

                with gr.Row():
                    mode = gr.Radio(
                        choices=["自然语言输入", "目标参数输入"],
                        value="自然语言输入",
                        label="输入方式",
                    )
                    enable_patent_search = gr.Checkbox(value=True, label="启用专利检索")

                nl_group = gr.Group(visible=True)
                with nl_group:
                    nl_prompt = gr.Textbox(
                        label="任务描述",
                        value="我需要一个 50mm 焦距、F/2.8、40 度视场的镜头，优化 20 轮，spp 128。",
                        lines=7,
                    )

                param_group = gr.Group(visible=False)
                with param_group:
                    with gr.Row():
                        foclen = gr.Number(label="焦距 (mm)", value=defaults.foclen)
                        fov = gr.Number(label="视场 (deg)", value=defaults.fov)
                        fnum = gr.Number(label="F 数", value=defaults.fnum)
                    with gr.Row():
                        bfl = gr.Number(label="后焦距 (mm)", value=defaults.bfl)
                        thickness = gr.Number(label="总厚度 (mm)", value=defaults.thickness)

                mode.change(fn=toggle_input_mode, inputs=[mode], outputs=[nl_group, param_group])

                gr.Markdown("### 优化预算")
                with gr.Row():
                    iterations = gr.Slider(5, 200, value=controls.iterations, step=1, label="迭代轮数")
                    spp = gr.Slider(16, 512, value=controls.spp, step=16, label="采样数")
                    test_per_iter = gr.Slider(1, 20, value=controls.test_per_iter, step=1, label="测试间隔")

                run_btn = gr.Button("开始运行", variant="primary")

            with gr.Column(scale=7, elem_id="intel-panel"):
                gr.Markdown("### 结果")
                status_html = gr.HTML(
                    _status_html(
                        "等待运行。",
                        True,
                    )
                )
                with gr.Tabs():
                    with gr.Tab("输出", elem_id="result-panel"):
                        summary = gr.Markdown("尚未运行。")
                        artifacts_html = gr.HTML(
                            '<div class="empty-state">运行后显示结果文件。</div>'
                        )
                    with gr.Tab("指标", elem_id="metric-panel"):
                        metrics_html = gr.HTML(
                            '<div class="empty-state">运行后显示指标。</div>'
                        )
                    with gr.Tab("记录", elem_id="trace-panel"):
                        workflow_text = gr.Markdown("### 执行轨迹\n- 暂无记录")
                        references_html = gr.HTML(
                            '<div class="empty-state">运行后显示参考结果。</div>'
                        )
                        memory_md = gr.Markdown("### 运行记录\n- waiting")

        run_btn.click(
            fn=run_agent,
            inputs=[
                mode,
                nl_prompt,
                foclen,
                fov,
                fnum,
                bfl,
                thickness,
                iterations,
                spp,
                test_per_iter,
                enable_patent_search,
            ],
            outputs=[
                status_html,
                summary,
                artifacts_html,
                metrics_html,
                workflow_text,
                references_html,
                memory_md,
            ],
        )

    return demo
