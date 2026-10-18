# Public PFT fixture sanitization

This patch replaces the personally named, GPS-bearing PFT TCX test fixture with
`synthetic_pft_run_v01.TCX`.

Sanitization performed:
- all TCX `<Position>` GPS coordinates removed;
- altitude samples removed;
- all absolute timestamps shifted to a fixed synthetic date while preserving intervals;
- heart-rate, cadence, power and distance series retained so PFT processing regression values remain unchanged.

The original file is moved outside the repository to:
`..\PaddleTrainerPrivateData\2026-10-18\pft\`.

Apply from the extracted patch directory:

```powershell
.\apply_pft_fixture_sanitization.ps1
```

Then verify:

```powershell
.\.venv\Scripts\python.exe -m pytest apps\api\tests\test_pft_processing_integration.py -q
```
