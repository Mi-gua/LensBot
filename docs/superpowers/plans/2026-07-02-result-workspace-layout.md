# Result Workspace Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure generated `results/<run-id>/` directories so workflow state, agent traces, DeepLens engine artifacts, final deliverables, verification output, and event logs have clear homes.

**Architecture:** Keep `results/<run-id>/` as the stable run root and add a path helper in `runtime.result` that defines canonical subdirectories. Dashboard and pi-agent code should consume the canonical paths exposed through manifest records and tool state.

**Tech Stack:** Python runtime and tests, TypeScript pi-agent state tests, JSON/JSONL result artifacts.

---

### Task 1: Add Result Workspace Path Contract

**Files:**
- Modify: `test/test_optimization_turn_count.py`
- Modify: `src/runtime/result.py`

- [ ] **Step 1: Write the failing test**

Add assertions that a `ResultWorkspace` exposes canonical folders:

```python
def test_result_workspace_exposes_layered_paths(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = ResultWorkspace.from_result_dir(Path(tmp) / "run")

        self.assertEqual(workspace.final_dir, workspace.root / "final")
        self.assertEqual(workspace.events_dir, workspace.root / "events")
        self.assertEqual(workspace.agents_dir, workspace.root / "agents")
        self.assertEqual(workspace.optimization_agent_dir, workspace.root / "agents" / "optimization")
        self.assertEqual(workspace.deeplens_dir, workspace.root / "engines" / "deeplens")
        self.assertEqual(workspace.deeplens_live_dir, workspace.root / "engines" / "deeplens" / "live")
        self.assertEqual(workspace.deeplens_attempt_dir("curriculum"), workspace.root / "engines" / "deeplens" / "attempts" / "attempt-001-curriculum")
        self.assertTrue((workspace.root / "final").is_dir())
        self.assertTrue((workspace.root / "events").is_dir())
        self.assertTrue((workspace.root / "agents" / "optimization" / "workspace").is_dir())
        self.assertTrue((workspace.root / "engines" / "deeplens" / "attempts").is_dir())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test.test_optimization_turn_count.OptimizationTurnCountTest.test_result_workspace_exposes_layered_paths`

Expected: FAIL because `ResultWorkspace` has no layered path properties yet.

- [ ] **Step 3: Implement minimal path helpers**

Add properties and `deeplens_attempt_dir()` to `ResultWorkspace`, and update `ensure()` to create the canonical folders.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test.test_optimization_turn_count.OptimizationTurnCountTest.test_result_workspace_exposes_layered_paths`

Expected: PASS.

### Task 2: Move Agent and Event Paths

**Files:**
- Modify: `test/test_optimization_turn_count.py`
- Modify: `src/runtime/result.py`
- Modify: `src/runtime/traces.py`
- Modify: `src/runtime/artifacts.py`
- Modify: `pi-agent/src/state.ts`
- Modify: `pi-agent/test/pi-session.test.ts`

- [ ] **Step 1: Write failing tests**

Update tests so optimization turns are written under `agents/optimization`, state derives `active_workspace_dir` as `agents/optimization/workspace`, and trace append writes to `events/agent.jsonl` or `events/workflow.jsonl`.

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m unittest test.test_optimization_turn_count
Push-Location pi-agent
npm test
Pop-Location
```

Expected: FAIL while code still writes agent turns or events outside the canonical layout.

- [ ] **Step 3: Implement minimal path changes**

Change `ResultWorkspace.record_optimization_agent_turn()` and `layered_workspace_index()` to use `agents/optimization`. Change `runtime.traces` to write `events/agent.jsonl` and `events/workflow.jsonl`. Update pi-agent state default workspace path.

- [ ] **Step 4: Run tests to verify they pass**

Run the same Python and npm commands.

Expected: PASS.

### Task 3: Move DeepLens Engine Artifacts

**Files:**
- Modify: `test/test_pi_tool_registration.py`
- Modify: `src/engine/deeplens/session.py`
- Modify: `src/tools/deeplens/curriculum.py`
- Modify: `src/tools/deeplens/analysis.py`
- Modify: `src/tools/deeplens/fake.py`
- Modify: `src/tools/server.py`
- Modify: `src/subagents/reporting.py`
- Modify: `src/runtime/artifacts.py`

- [ ] **Step 1: Write failing tests**

Change tests to expect:

```text
engines/deeplens/session.json
engines/deeplens/deeplens.log
engines/deeplens/live/current.json
engines/deeplens/attempts/attempt-001-curriculum/curriculum.json
final/final.json
final/final.png
final/final.zmx
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m unittest test.test_pi_tool_registration`

Expected: FAIL because current code writes DeepLens artifacts at run root.

- [ ] **Step 3: Implement canonical path methods**

Give `DeepLensOptimizationSession` explicit paths for session state, log, live preview, curriculum attempt, fine-tune attempt, and final output. Return canonical artifact paths in tool data and state patches.

- [ ] **Step 4: Remove flat-layout reads**

Update analysis, preview, and reporting code to read the canonical paths directly.

- [ ] **Step 5: Run tests to verify pass**

Run: `python -m unittest test.test_pi_tool_registration`

Expected: PASS.

### Task 4: Move Zemax Verification Output

**Files:**
- Modify: `src/engine/zemax/analysis.py`
- Modify: `src/runtime/artifacts.py`
- Modify: tests only if an existing test asserts the verification directory.

- [ ] **Step 1: Write or update focused test**

Assert manifest discovers `verification/zemax/zemax_report.json` and figures.

- [ ] **Step 2: Run test to verify failure**

Run the focused manifest test.

Expected: FAIL while discovery still expects the old verification location.

- [ ] **Step 3: Implement output path change**

Write Zemax analysis into `verification/zemax`, and discover that location in the manifest.

- [ ] **Step 4: Run test to verify pass**

Run the focused test again.

Expected: PASS.

### Task 5: Update Documentation and Focused Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update outputs section**

Replace the flat file table with the layered layout tree and short descriptions.

- [ ] **Step 2: Run focused verification**

Run:

```powershell
python -m unittest test.test_optimization_turn_count test.test_pi_tool_registration
Push-Location pi-agent
npm test
Pop-Location
```

Expected: PASS.

- [ ] **Step 3: Inspect git diff**

Run: `git -C LensBot diff --stat`

Expected: Only result layout, tests, pi-agent state, and README/docs changes are present.
