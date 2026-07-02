<div align="center">
  <img src="docs/assets/lensbot-title.png" width="100%" alt="LensBot">

  <p><strong>A vertical-domain AI agent for optical lens design.</strong></p>
  <p>by ZJU Yang Lab</p>

  <p>
    <a href="#what-lensbot-does">What it does</a> ·
    <a href="#quick-start">Quick Start</a> ·
    <a href="#how-it-works">How it works</a> ·
    <a href="#for-agents">For agents</a>
  </p>

  <p>
    <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
    <img alt="Agent" src="https://img.shields.io/badge/Agent-optical%20design-111827">
    <img alt="DeepLens" src="https://img.shields.io/badge/DeepLens-differentiable%20optics-2563EB">
    <img alt="Zemax" src="https://img.shields.io/badge/Zemax-optional%20verification-0F766E">
    <img alt="Status" src="https://img.shields.io/badge/status-research%20prototype-F59E0B">
  </p>
</div>

---

LensBot is an agentic optical design system. It turns a lens-design request into a staged engineering run: parse the target, choose reference cases, optimize with DeepLens, optionally verify with Zemax, show the process in a local dashboard, and write reusable design memory for later runs.

The project is not a general chat wrapper. It is built around a vertical optical workflow where the agent must use bounded tools, inspect artifacts, reason from measured metrics, and keep a trace of what happened.

## What LensBot Does

- Parses natural-language or structured optical requirements.
- Retrieves local Zemax reference cases from `cases/`.
- Builds a DeepLens-compatible starting point.
- Runs a pi-agent Optimization loop over project tools.
- Produces DeepLens artifacts under `engines/deeplens/` and stable final exports under `final/`.
- Optionally runs Zemax / OpticStudio verification when a licensed local environment is available.
- Streams workflow status, optimization trace, images, files, and metrics to a local dashboard.
- Records compact run memory and reusable engineering lessons.

## Current Status

The real Optimization path is wired through the pi sidecar:

```text
src/subagents/optimization.py
-> src/runtime/bridge.py
-> pi-agent/src/pi-sidecar.ts
-> src/tools/server.py
-> src/tools/deeplens/*
```

The Optimization agent now uses pi-coding-agent as the native decision loop. It sees a professional toolset and chooses the next action from trusted state facts and optical evidence:

```text
deeplens_curriculum / deeplens_finetune / deeplens_analysis
deeplens_inspect_checkpoint / deeplens_adjust_strategy / deeplens_adjust_structure_seed
read_file / write_file / edit_file
finish
```

`deeplens_analysis` is repeatable, and `finish` is the only successful exit. The final contract requires `final/final.json`, `final/final.zmx`, trusted final analysis evidence, and an honest natural-language caveat when quality is weak.

The repository is currently a research prototype. The next development plan is tracked in [`plan.md`](plan.md).

## Quick Start

Enter the project:

```powershell
cd LensBot
```

Install the basic Python dependencies:

```powershell
pip install openai pyyaml matplotlib pythonnet
```

Configure an OpenAI-compatible model endpoint:

```powershell
$env:LENSBOT_OPENAI_BASE_URL="https://your-api-base-url"
$env:LENSBOT_OPENAI_API_KEY="your-api-key"
$env:LENSBOT_OPENAI_MODEL="your-model-name"
```

Start the local dashboard:

```powershell
python main.py
```

Open the printed local URL, usually:

```text
http://127.0.0.1:8000
```

If port `8000` is busy, LensBot tries the next available port. You can also set one explicitly:

```powershell
$env:LENSBOT_PORT="8010"
python main.py
```

## Requirements

| Capability | Requirement |
| --- | --- |
| Agent runtime | Python 3.10+, OpenAI-compatible model endpoint |
| Optimization | DeepLens-compatible local environment, PyTorch / NumPy |
| Dashboard | Local browser |
| Zemax verification | Optional: Windows, Ansys Zemax OpticStudio, ZOS-API, `pythonnet` |

DeepLens is the core optical engine. Zemax is an optional independent verification backend and should not be treated as a hard dependency for the main workflow.

## How It Works

LensBot runs five workflow nodes:

| Node | Purpose | Main code |
| --- | --- | --- |
| `Intake` | Parse user intent into optical parameters. | `src/agent/workflow.py`, `src/tools/intake.py` |
| `Seeding` | Select and inspect reference Zemax cases. | `src/subagents/seeding.py`, `src/tools/seed_case.py` |
| `Optimization` | Delegate optimization to the pi sidecar and DeepLens tools. | `src/subagents/optimization.py`, `pi-agent/`, `src/tools/deeplens/` |
| `Analysis` | Merge DeepLens metrics and optional Zemax verification. | `src/subagents/analysis.py`, `src/tools/analysis.py` |
| `Reporting` | Archive output, summarize the run, and update memory. | `src/subagents/reporting.py`, `src/agent/memory.py` |

### Optimization Agent

The Optimization node is the most agentic part of the system. Python starts the pi sidecar, sends the target, seed candidates, memory, and allowed tools, then waits for a final state snapshot.

The pi sidecar follows the project skill at:

```text
pi-agent/skills/optimization/SKILL.md
```

It should call one tool per turn, treat tool observations as source of truth, and only finish after final artifacts and final analysis evidence are present.

### Tool Boundary

The agent does not call optical engines directly. It calls bounded tools:

| Tool area | Location | Notes |
| --- | --- | --- |
| Tool registry and schemas | `src/agent/tools.py` | Stable tool contracts and trace metadata. |
| Python tool server | `src/tools/server.py` | Dispatch bridge for pi-agent tool calls. |
| DeepLens tools | `src/tools/deeplens/` | Curriculum, fine-tune, analysis, fake mode. |
| Zemax analysis | `src/tools/analysis.py`, `src/engine/zemax/` | Optional verification backend. |
| File and PowerShell tools | `src/tools/read_file.py`, `src/tools/write_file.py`, `src/tools/edit_file.py`, `src/tools/bash.py` | Bounded local inspection, notes, edits, and PowerShell execution. |

### Dashboard

The dashboard lives in:

```text
src/ui/dashboard.html
src/ui/dashboard.css
src/ui/dashboard.js
```

It has four main pages:

- **Workbench**: task input and workflow-level timeline.
- **Optimization**: agent trace, current optimization snapshot, seed references, initial structure, final structure.
- **Results**: metrics, files, and generated analysis artifacts.
- **Config**: model endpoint and optimization budget controls.

The intended direction is to keep the workbench timeline concise and show detailed Optimization turns in the Optimization page as a unified think-act-observation trace.

## Outputs

Each run writes an isolated result directory under `results/`.

The run root keeps stable human-facing entry files and separates detailed evidence by responsibility:

```text
results/<run-id>/
├── manifest.json
├── summary.md
├── metrics.json
├── final/
│   ├── final.json
│   ├── final.png
│   └── final.zmx
├── workflow/
│   ├── timeline.json
│   └── <node>/
├── agents/
│   └── optimization/
│       ├── ledger/events.jsonl
│       ├── views/turns.json
│       └── workspace/turn-*.json
├── engines/
│   └── deeplens/
│       ├── session.json
│       ├── deeplens.log
│       ├── live/current.json
│       ├── live/current.png
│       └── attempts/
│           ├── attempt-001-curriculum/
│           └── attempt-002-finetune/
├── verification/
│   └── zemax/
└── events/
    ├── workflow.jsonl
    ├── agent.jsonl
    └── tools.jsonl
```

`final/` is the stable downstream export. `workflow/` stores workflow-node evidence, `agents/optimization/` stores the Optimization agent transcript and workspace, `engines/deeplens/` stores DeepLens session state and per-attempt artifacts, `verification/zemax/` stores optional independent Zemax evidence, and `events/` stores replayable JSONL event streams. For the Optimization agent, `active_result_dir` is this run root and `active_workspace_dir` is `active_result_dir/agents/optimization/workspace`.

## Memory

LensBot keeps memory in `src/memory/`:

| Memory | Purpose |
| --- | --- |
| `project.md` | Stable project role and design priorities. |
| `designrun/*.json` | Compact run records. |
| `lessons/seed_selection.md` | Reusable seed-choice experience. |
| `lessons/optimization.md` | Optimization behavior, drift, budget, and failure lessons. |
| `lessons/final_review.md` | Post-run acceptance and review lessons. |

Memory is meant to be concise engineering experience, not a run log.

## For Agents

If you are another Codex or coding agent continuing this project:

1. Read [`plan.md`](plan.md) first. It is the active four-part implementation handoff.
2. Keep the Optimization loop agent-native. Do not add separate UI branches for every DeepLens tool.
3. Do not make Zemax a hard dependency. Treat it as optional verification with explicit status.
4. Keep optimization judgment in the skill/tool-observation loop. The Analysis node should merge evidence, not run a second hardcoded optical evaluator.
5. Continue from the current `src/runtime/bridge.py` and `pi-agent/src/pi-sidecar.ts` path.
6. Preserve traceability: every meaningful tool call should be visible as a compact agent or workflow trace.

Useful entry points:

| Task | Start here |
| --- | --- |
| Run dashboard | `main.py` |
| Understand workflow | `src/agent/workflow.py` |
| Inspect Optimization adapter | `src/subagents/optimization.py` |
| Inspect pi sidecar | `pi-agent/src/pi-sidecar.ts` |
| Inspect tool dispatch | `src/tools/server.py` |
| Inspect dashboard rendering | `src/ui/dashboard.js` |
| Inspect memory rewriting | `src/agent/memory.py` |
| Continue planned work | `plan.md` |

## Repository Layout

```text
LensBot/
├── main.py
├── plan.md
├── cases/
├── docs/
├── pi-agent/
│   ├── SYSTEM.md
│   ├── package.json
│   ├── skills/optimization/SKILL.md
│   └── src/
├── src/
│   ├── agent/
│   ├── engine/
│   │   ├── deeplens/
│   │   └── zemax/
│   ├── memory/
│   ├── runtime/
│   ├── subagents/
│   ├── tools/
│   └── ui/
└── results/        # generated at runtime, ignored by git
```

## Acknowledgements

LensBot's optical optimization layer is built around [DeepLens](https://github.com/singer-yang/DeepLens), which provides the differentiable optics foundation for programmatic lens optimization.

LensBot focuses on the agent layer around optical engines: requirement interpretation, case retrieval, optimization orchestration, dashboard visualization, optional verification, reporting, and memory.
