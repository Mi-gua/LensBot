# Optical judgment reference

Use this reference to classify evidence and choose a discriminating next action.
It adapts the supplied GeoLens design/API guidance to LensBot's actual tool
surface. Numeric examples in external documentation are not universal pass
criteria.

## Evaluation order

1. **Execution validity** — Did the requested optimizer steps execute? Is the
   analyzed artifact the output of that pass? Are values finite and units known?
2. **Physical feasibility** — When the current tools expose them, check ray-trace failures, self-intersection,
   center/edge thickness, air gaps, clear apertures, material validity, extreme
   surface shape, and invalid-ray fractions. A low loss cannot redeem invalid
   geometry.
3. **Contract fidelity** — Check EFL, full-field definition, working F-number,
   image/sensor scale, and any explicit BFL/TTL or other packaging requirement.
   Evaluate against stated tolerances only. Improvement elsewhere does not waive
   a hard constraint.
4. **Image quality** — Inspect the center, intermediate, and edge evidence the
   current evaluator actually reports. Across the
   stated wavelengths. Relate RMS/spot maps, sagittal/tangential MTF at relevant
   spatial frequencies, distortion, field curvature, vignetting, and valid-ray
   coverage. No single scalar substitutes for this set.
5. **Engineering complexity** — Only after nominal feasibility and quality,
   consider material matching, asphere count/order, slope and full-aperture
   thickness, sensitivity, and manufacturing implications. Nominal output is not
   proof of tolerance yield.

The current evaluator reports first-order values, center/mid/edge spot radius,
distortion, center/edge geometric MTF50, minimum loaded-surface vertex spacing,
and valid-ray fractions. It does not currently measure field curvature,
full-aperture thickness/slope, tolerance sensitivity, or manufacturing yield.
Treat those as unavailable evidence, not passed checks. A zero vertex spacing can
also be associated with an aperture plane, so inspect the prescription before
calling it an intersection.

## Comparable measurements

Before interpreting a difference, align prescription version, conjugate, focus,
wavelengths and weights, full/half/diagonal field convention, stop and F-number,
pupil sampling, valid-ray/vignetting treatment, centroid or chief-ray reference,
units, RMS radius versus diameter, and geometric versus diffraction MTF.

MTF50 (the frequency at 50% contrast) is not MTF measured at 50 lp/mm. Geometric,
FFT, and Huygens MTF are different analyses. Cross-engine disagreement is first
a definition/import question; historical percentages are observations, not
acceptance bands.

## Diagnose before intervening

| Evidence pattern | Investigate | Candidate actions |
| --- | --- | --- |
| NaN/Inf, zero valid rays, missing artifact, zero executed steps | Tool, state, sampling, numerical failure | Correct the execution/evaluation path; do not write an optical lesson |
| Self-intersection or thickness/gap violation | Geometry and regularization terms | Roll back, reduce destabilizing freedom/LR, or revise initialization |
| EFL/FOV/F-number drift | Target definition, constraint mechanism, material snap, focus/post-processing | Re-establish the target mechanism or refine from the exact artifact; do not hide drift with spot gains |
| Center good, edge poor | Off-axis aberration, field curvature, astigmatism, distortion, clipping | Inspect field-resolved evidence; compare a supported group-count or seed change when it tests a named hypothesis |
| Marginal rays clipped / low edge validity | Clear apertures, stop, pupil sampling, intentional vignetting | Separate throughput loss from aberration improvement; compare at consistent acceptance |
| Oscillating/worsening comparable loss | Step size, gradients, unstable geometry | Inspect checkpoint; reduce LR or roll back once, then reassess |
| Stable plateau with feasible geometry | Objective mismatch, inactive variables, local basin, structural limitation | Verify the first three, then test one targeted variable/seed/structure hypothesis |
| RMS improves but MTF/contract regresses | Metric mismatch or tradeoff | Compare at task-relevant frequency and contract; retain the Pareto alternative |

## Structure and aspheres

Double Gauss, retrofocus, telephoto, and simpler forms are conditional starting
families. Choose by conjugate, focal length, field, aperture, image scale,
back-focus/track requirements, spectral range, and complexity—not by surface
count alone. One failed member does not prove a family limit.

An asphere is a targeted degree of freedom. The current structure tool can alter
group surface count or convert an existing asphere to a sphere; it cannot move
the stop, convert a sphere to an asphere in place, or increase aspheric order.
Do not propose unsupported actions as the next tool call. Conversely, removing
an asphere to bypass a parser is a compatibility workaround, not evidence that
spherical optics is superior.

## Stage semantics in this repository

LensBot's curriculum and fine-tune stages both call geometric ray tracing.
Their differences include aperture/field progression, objectives, sampling,
material matching, target reset, and post-processing. Attribute phase-to-phase
changes only after isolating those factors; do not label the first as a surrogate
and the second as the first "real-ray" stage.
