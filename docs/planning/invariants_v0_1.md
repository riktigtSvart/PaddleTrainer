# Planning Core Invariants v0.1

1. UNKNOWN is distinct from NOT_APPLICABLE.
2. Missing values are not silently replaced by defaults.
3. Decision-relevant datetimes are timezone-aware.
4. Canonical serialization rejects NaN/infinity.
5. Snapshots carry schema version, information cutoff and content hash.
6. Future information cannot enter a decision-time context.
7. Snapshots are frozen rather than retroactively mutated.
8. Provenance remains explicit.
9. Semantic contract versions are distinct from package versions.
10. Open registries use registry keys rather than closed enums.
11. Identical canonical content yields identical hashes.
12. Changed cutoff changes snapshot hash.
13. Domain code does not depend on FastAPI/ORM/provider SDKs.
