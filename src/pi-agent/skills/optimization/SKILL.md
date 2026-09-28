---
name: optimization
description: Choose a DeepLens starting structure, optimize it, and deliver an evidence-backed lens.
---

# Lens optimization

Own the optical decision loop. The outcome is a defensible chosen prescription,
not completion of a fixed curriculum/fine-tune recipe.

## Read the run contract

Use the supplied Intake/Seeding handoff directly:

- `design_contract` distinguishes optical targets, hard packaging constraints,
  starting geometry, tolerances, and provenance.
- `execution_params` is a runnable starting configuration. Stage-setting
  provenance says whether values are defaults, user-supplied, or adaptive; none
  is a hard limit unless the effort policy explicitly represents it as one.
- `initial_structures` contains the candidate structures and their reference
  information. Choose one to optimize; the others remain available if needed.
- `memory` is a prior, not a command or live state.
- `StateSnapshot` and structured tool results are live facts.

Use this handoff as the starting point for a brief optical design assessment,
not a requirement to launch curriculum immediately. Compare the supplied
candidates against the pressures that matter for this target: focal length and
image scale, field angle, aperture, and any packaging constraints. Consider how
lens family, stop placement, symmetry, group complexity, and aspheric freedom
could address those pressures. Discuss only relevant tradeoffs; anticipated
aberrations or feasibility risks are hypotheses until measured.

Keep the assessment proportional to the task. Check the first-order relationship
between focal length, field and image scale using the stated projection; identify
whether aperture, off-axis correction or packaging is the dominant difficulty.
Use that to justify the starting family and the minimum useful complexity,
including stop placement or aspheres when relevant. Preserve explicit targets
and distinguish starting geometry from final constraints. Summarize the design
basis and expected tradeoff in a few sentences; do not turn this into an
exhaustive optical checklist or claim unmeasured performance.

Before initialization, give a concise design rationale: why this candidate is a
promising start, its main optical risk or uncertainty, and what the first
optimization and analysis should establish. Choose initial effort accordingly.
If a specific uncertainty could change that choice or initialization settings,
read a relevant reference, inspect the supplied case at its known path, or use
an appropriate tool. There is no required number of preparatory calls. Start
`deeplens_curriculum` with the chosen `seed_candidate_id` once the evidence is
sufficient for a reasonable first experiment, without trying to resolve every
optical uncertainty in advance.

Reuse information already supplied instead of reconstructing the handoff from
archives. If a required input is missing or contradictory, name the specific
blocker. Do not substitute historical values for the current design contract.

Never relax a protected target. A missing tolerance is unknown acceptance
criteria, not zero tolerance. BFL/TTL are starting geometry unless the contract
explicitly classifies them as packaging constraints.

## Adaptive loop

Repeat this loop while the next action has decision value:

```text
observe comparable evidence
→ name the dominant uncertainty or defect
→ choose one informative intervention
→ verify what actually executed
→ analyze the resulting artifact
→ compare, continue, branch, or stop
```

Choose actions autonomously. Curriculum, refinement, strategy adjustment,
structure change, denser evaluation, and finish are options, not mandatory
stages. Prefer a small discriminating experiment when uncertainty is high;
extend a promising trajectory when metrics still improve; stop a line of inquiry
when comparable evidence shows no useful gain. Suggested iteration counts and
the review-point call count are orientation values, never targets to consume.

Before repeating an expensive call, state in `decision_summary`:

1. the hypothesis it tests;
2. why this source candidate and effort are appropriate;
3. the observable result that would justify continuing.

After every optimization call, require positive `iterations_executed` and check
the source artifact. Zero steps, stale artifacts, tool errors, and mismatched
evaluation definitions are software/evidence failures, not optical findings.

## Optical judgment

Read [references/optical-judgment.md](references/optical-judgment.md) before
diagnosing quality, drift, clipping, geometry, or a structure change. Use it as
a diagnostic vocabulary, not a table of universal thresholds.

Analyze the candidate that will be selected. If two or more credible optimization
variants exist, or a new attempt trades one metric for another, read and apply
[references/candidate-comparison.md](references/candidate-comparison.md).

Never infer a topology limit from one local plateau. Change structure only when
the current evidence supports a specific limitation or a deliberately different
starting basin is worth testing. Preserve prior candidates as controls.

Choose one of the supplied initial_structures as the primary starting point.
Pass its seed_candidate_id to deeplens_curriculum; the tool uses that candidate's
structure with the run's optical parameters. If results are unsatisfactory,
decide whether to refine the current design or switch to another supplied
candidate. Explain the choice from observed results. There is no requirement to
optimize all candidates; finish when the chosen design has sufficient evidence.

Each new session allocates fresh numbered directories under
`engines/deeplens/attempts/` within the run. Earlier attempts and exported
`candidates/candidate-NNN/` files remain available. Use the exact `session_id`
and artifact paths returned by tools; never assume attempt numbers or overwrite
an earlier attempt. To inspect or refine a previous candidate, pass its explicit
`lens_json` path. Its adjacent `session.json` records the associated parameters;
the run-level `engines/deeplens/session.json` describes only the latest session
update and must not be used as evidence for a different candidate.



## Evidence and tools

Use domain tools for optical work. File and PowerShell tools are for narrow,
known-path inspection inside the task's workspace root. Read a linked reference
when its stated condition applies, or a current artifact when its contents are
needed for the next optical decision. Before additional inspection, identify the
specific missing fact and how it changes that decision; stop reading once it is
resolved. Use evidence already in context without fetching it again.

Do not perform startup directory scans, source-code review, or historical-run
audits. Execution checks apply to the current tool result after a call; historical
bug notes do not trigger a preflight investigation. For a current failure, inspect
the returned error and directly relevant artifact or log at a known path. If it
cannot be resolved through supported domain tools, report the blocker and retain
the evidence rather than taking on software debugging.

Tool observations describe execution; they do not dictate strategy. Do not
repeat a tool because it recommended itself. `finish` validates artifact/evidence
completeness and promotes the selected candidate; it does not certify optical
quality.

## Finish

Finish when the best available candidate has matching analysis and one of these
is true:

- it satisfies the stated contract within known tolerances;
- further work lacks a supported, decision-changing hypothesis;
- an explicit external limit is reached.

Report `pass`, `fail`, or `uncertain` in `reason`, and state independently in
`stop_reason` why optimization stops now. When the user supplies no tolerance,
explain the engineering acceptance basis and its uncertainty; the runtime does
not invent an acceptance threshold. Use `uncertain` when evidence cannot support
a conclusion. A weak
but fully evidenced design may be finished as `fail` or `uncertain`; do not run
ceremonial retries merely to avoid that verdict.

Python owns finish validation: artifacts must exist, analysis must match the
chosen artifact, and evidence keys must resolve. A measured violation of an
explicit user constraint prevents a pass verdict. Unknown tolerances alone do
not override the agent's optical judgment.

The task ends only through `finish`. It terminates the Optimization session after
validating and promoting the selected artifact. A model or SDK run boundary is
not completion. The selected JSON/ZMX artifact and its matching analysis must be
present, the verdict must cite actual evidence keys, and no tool result may be
mistaken for optical proof.
