# PFT v0.1 handoff into PaddleTrainer — reviewed 2026-10-09

Inputs are the user-attached `Beillesztett szöveg(8).txt` and
`pft_v01_domain_impl(1).zip`. They describe a planned personalized physiological
response test and a standalone persistence reference. They are design inputs,
not observed PFT measurements or proof of calibrated fitness/fatigue estimates.

## Adopted design principles

- Original measurements, derived features, reference baselines and physiological
  interpretation have separate provenance and versioning.
- A feature may be usable for analysis while ineligible for baseline updates;
  quality and exclusions should remain per feature/stage/sequence.
- Future personal references are grouped by athlete, modality, protocol/version,
  feature/algorithm and stimulus context. Ergometer, water, running and cycling
  references are not automatically merged.
- Both historical measurement times and reference availability must precede the
  target comparison cutoff. The current measurement is compared first and only
  then considered for an eligible reference update. HR features computed from
  the target session are not independent inputs for predicting that same HR.
- Actual measured load histories remain separate from prescribed target loads.
  GPS ground speed, water level and discharge are not measured paddle power or
  validated local current velocity.

The V24.11-A contract captures these commitments without accepting PFT values
or declaring that a real personal baseline exists. It prevents target-derived
HR/PFT predictors from entering the present retrospective recorded-HR task.

## What the package actually implements

The reference includes enums, 19 feature definitions (11 labelled PRIMARY,
8 EXPERIMENTAL), SQLAlchemy models, an initial Alembic migration and a SQLite
schema/round-trip smoke test. Its README explicitly excludes processing, quality
thresholds, feature extraction, reference updates and readiness interpretation.
The supplied smoke test passes separately in the assistant's Python 3.12/SQLite
environment. It is not PostgreSQL integration or physiological validation.

## Integration work required before database adoption

1. Replace `pft.base.Base` with the project's existing declarative Base; import
   the models through the existing metadata registration mechanism.
2. Bind athlete UUIDs to the actual owner FK and verify owner-consistent links
   between protocol, load profile, session, measurements and baseline members.
   The standalone athlete columns currently have no owner FK.
3. Rebase migration `20261008_01`, whose `down_revision` is `None`, onto the
   actual project head at integration time. V24.11-A leaves the current head
   `e4f7a92c1836` unchanged and does not copy this initial migration into it.
4. Add processing/quality/eligibility services and constraints. The reference's
   `PftFeatureValue.usable_for_analysis=True` default is not an assessed quality
   decision. A smoke round-trip does not establish valid cross-owner/context
   relationships, immutable raw data or correct feature eligibility.
5. Specify UTC/as-of semantics and reference observation eligibility. A single
   `calculated_at` timestamp alone does not establish that all contributing
   measurements and the baseline were available before the target session.
6. Preserve finite-value validation, null/status semantics, signal and clock
   provenance, algorithm versions and coverage. Current Polar/TCX recorded-HR
   slots do not provide measured beat-to-beat RR merely by taking `60000/HR`.
   Derived intervals must never be labelled recorded RR or treated as native HRV.

## Scientific status of the handoff

The proposed 8–10-minute PRE/P0/P1/P2/recovery protocol, A/B/C/X grades,
5–7/8+ reference status thresholds and 0–100 readiness scale are engineering
design proposals. The attached package does not validate them. The PRIMARY
registry label is a selection label; it does not authenticate clinical or
physiological interpretation. Correlation, a fitted time constant and a model
residual are not automatically fatigue labels.

[Bellenger et al. (2020)](https://pubmed.ncbi.nlm.nih.gov/32884040/) studied rHRI
at relative workloads in eleven male runners, using treadmill and overground
running. This is relevant primary research for future method review. Applying
its findings to this kayak protocol or wrist-sensor processing requires further
validation; that transfer is an inference, not a result established by our data.

[Aubry et al. (2015)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0139754)
observed faster HR recovery with functional overreaching in a subgroup of trained
triathletes. This supports retaining HR recovery as a context-dependent measured
feature rather than assigning it an automatic positive fitness interpretation.
It does not validate our short PFT recovery protocol or a readiness percentage.

## Separate future workstreams

PFT: integrate the owned/versioned domain, then stage statistics and measured
load adherence, feature-specific quality, simple response/recovery features,
and temporally valid personal reference comparisons. Sigmoid/local rHRI and
other kinetics estimates need separate method and signal validation.

Retrospective HR model: materialize history/input/target arrays under the archived
cohort-bound experiment plan, expand the chronological TRAIN sessions and evaluate
a temporal baseline. This uses actual motion and environmental context; it does
not assume the historical workouts were standardized PFT sessions.

An integration between the workstreams will require a new explicit contract for
actual pre-session PFT measurements, modality/stimulus/algorithm compatibility,
owner binding and before-session temporal availability. Fitness, fatigue,
readiness interpretation and training recommendations remain separate decisions.
