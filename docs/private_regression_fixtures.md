# Private regression fixtures

Some regression checks were built from real Polar/source replay material. Those payloads can
contain location, timestamps, user/session identifiers, and other personal training data.

They are intentionally **not versioned in Git**.

Local private paths are ignored:

- `apps/api/tests/fixtures/phase_reconciliation/`
- `apps/api/tests/fixtures/flow_phase_time_evidence/`
- `apps/api/app/phase_evidence/flow_display_catalog_v01.json`

On the primary development machine these paths may be NTFS junctions/hard-links to
`PaddleTrainerPrivateData`. When the private replay bundle is absent, tests that specifically
require real-derived replay evidence are skipped with an explicit reason. Synthetic/unit/API
coverage continues to run.

Never use `git add -f` on these paths.

The private replay bundle is development evidence, not a production database migration and
not a source of planner authority by itself.
