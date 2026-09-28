# Candidate comparison

Compare candidates to select an artifact or decide which hypothesis deserves
another experiment. Do not automatically select the newest candidate.

## Build a comparable shortlist

Keep the incumbent plus candidates that add information: a distinct seed or
topology, a materially different strategy, or a credible Pareto tradeoff. Drop
exact re-exports and invalid/zero-step outputs. For each candidate retain:

- exact JSON/ZMX path and lineage/source artifact;
- actual optimizer steps, strategy and structure change;
- matching analysis definition and artifact path;
- feasibility, target/constraint values, image-quality values and caveats.

Analyze each shortlisted artifact explicitly under the same evaluation protocol.
If an older candidate is selected, analyze it again immediately before `finish`
so structured state refers to that exact prescription.

## Compare by gates, then tradeoffs

1. Exclude candidates with invalid execution evidence or physically invalid
   geometry unless all candidates fail, in which case report failure.
2. Apply explicit hard constraints and stated tolerances. Do not invent tolerance
   bands to force a winner.
3. Compare field-resolved image quality and throughput on aligned definitions.
4. Prefer a Pareto improvement. If metrics conflict, choose according to the
   user's stated priorities; otherwise preserve uncertainty and explain the main
   tradeoff.
5. Use lower complexity, better robustness evidence, or lower manufacturing cost
   only as tie-breakers when quality and contract evidence are comparable.

Relative improvement alone is insufficient: a 20% improvement may still fail a
requirement, while a small gain may be decisive near a specified boundary.

## Decide whether to continue

Continue only when the next run tests a named uncertainty and has a plausible
observable advantage over the shortlist. A plateau is supported by comparable
evaluations across real optimizer passes; repeated exports, altered sampling,
or different metric definitions do not count. If no candidate clearly dominates
and no discriminating experiment remains, finish the best evidenced candidate as
`uncertain` rather than manufacturing certainty through more retries.
