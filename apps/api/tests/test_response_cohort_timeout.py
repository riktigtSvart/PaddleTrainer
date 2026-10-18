"""Deadline orchestration tests; member source verification is mocked here.

The existing SQLite assembly/API suites exercise the actual source verifiers.
Virtual elapsed time avoids multi-minute sleeps in the budget regression cases.
"""

import asyncio
import importlib.util
import io
import json
import tempfile
from contextlib import ExitStack
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch
from urllib.error import HTTPError
from uuid import UUID

from app.schemas.response_cohort import ResponseCohortManifest
from app.services import response_cohort_assembly as module

OWNER = UUID(int=11)


def manifest_for(count):
    return ResponseCohortManifest.model_validate({
        "schema_version": "0.1",
        "manifest_id": "synthetic-deadline-regression",
        "members": [{
            "provider": "POLAR",
            "athlete_id": str(OWNER),
            "session_external_id": f"synthetic-{i:02d}",
            "route_date": "2026-09-01",
            "replay_snapshot_id": str(UUID(int=500 + i)),
            "expected_snapshot_hash": "a" * 64,
            "expected_evidence_set_id": str(UUID(int=700 + i)),
            "expected_evidence_hash": "b" * 64,
            "expected_unassigned_replay_package_hash": "c" * 64,
        } for i in range(count)],
    })


class CohortDeadlineTests(TestCase):
    def run_batch(self, count, step, *, waiting=False, fail_at=None):
        clock = SimpleNamespace(elapsed=0.0)
        connection = SimpleNamespace(scopes=["training_sessions:read"])
        db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
            scalar_one_or_none=lambda: connection,
        )))
        metadata = AsyncMock()
        seen = []

        async def member_index(db, owner, member, split, client, token, start, **kwargs):
            position = len(seen)
            seen.append(member.session_external_id)
            if "assembly_seconds" in kwargs:
                self.assertEqual(kwargs["assembly_seconds"], module._assembly_seconds(count))
            if waiting:
                await asyncio.Event().wait()
            if position == fail_at:
                raise module.CohortVerificationError("COHORT_REPLAY_PACKAGE_PIN_MISMATCH")
            clock.elapsed += step
            return {
                "session_external_id": member.session_external_id,
                "counts": {"observation_count": 1, "hr_slot_count": 1},
                "requested_split": {"split": None},
            }

        verified = AsyncMock(side_effect=member_index)
        with ExitStack() as stack:
            for name, value in (
                ("monotonic", lambda: clock.elapsed),
                ("_selected_metadata", metadata),
                ("_member_index", verified),
                ("get_valid_access_token", AsyncMock(return_value="synthetic-token")),
                ("PolarClient", lambda: object()),
            ):
                stack.enter_context(patch.object(module, name, value))
            result = asyncio.run(module.assemble_response_cohort(
                db, manifest_for(count), user_id=OWNER,
            ))
        return result, verified, metadata

    def assert_no_prefix(self, result, code):
        self.assertEqual(result["blocking_reasons"], [code])
        self.assertEqual(result["verified_member_count"], 0)
        self.assertEqual(result["members"], [])
        self.assertIsNone(result["totals"])
        self.assertIsNone(result["cohort_index_hash"])
        self.assertFalse(result["source_evidence_verified"])
        self.assertFalse(result["training_authorized"])
        self.assertFalse(result["numeric_output_authorized"])
        self.assertEqual(result["science_storage_writes"], 0)
        self.assertEqual(result["environmental_provider_calls"], 0)

    def test_three_session_control_keeps_original_budget(self):
        self.assertEqual(
            module._base(manifest_for(3))["execution_limits"]["max_assembly_seconds"], 120
        )
        result, _, _ = self.run_batch(3, 45)
        self.assert_no_prefix(result, "COHORT_EXECUTION_TIME_LIMIT")
        self.assertEqual(result["failed_member_canonical_index"], 2)

    def test_four_sessions_can_complete_after_original_120_seconds(self):
        result, verified, metadata = self.run_batch(4, 45)
        self.assertTrue(result["source_evidence_verified"])
        self.assertEqual(result["verified_member_count"], 4)
        self.assertEqual(result["execution_limits"]["max_assembly_seconds"], 360)
        self.assertEqual(verified.await_count, 4)
        self.assertEqual(metadata.await_count, 4)
        self.assertTrue(module.verify_cohort_index_integrity(result))
        self.assertFalse(result["training_authorized"])
        self.assertFalse(result["numeric_output_authorized"])

    def test_extended_budget_remains_finite_for_twenty_members(self):
        result, verified, _ = self.run_batch(20, 5)
        self.assertTrue(result["source_evidence_verified"])
        self.assertEqual(result["execution_limits"]["max_assembly_seconds"], 360)
        self.assertEqual(verified.await_count, 20)

    def test_four_sessions_can_complete_just_before_extended_deadline(self):
        result, verified, _ = self.run_batch(4, 89.999)
        self.assertTrue(result["source_evidence_verified"])
        self.assertEqual(verified.await_count, 4)

    def test_extended_deadline_discards_completed_prefix(self):
        result, verified, _ = self.run_batch(4, 90)
        self.assert_no_prefix(result, "COHORT_EXECUTION_TIME_LIMIT")
        self.assertEqual(verified.await_count, 4)
        self.assertEqual(result["failed_member_canonical_index"], 3)

    def test_waiting_member_is_cancelled_by_async_timeout(self):
        with patch.object(module, "MAX_EXTENDED_ASSEMBLY_SECONDS", 0.02):
            result, verified, _ = self.run_batch(4, 0, waiting=True)
        self.assert_no_prefix(result, "COHORT_EXECUTION_TIME_LIMIT")
        self.assertEqual(verified.await_count, 1)

    def test_extended_budget_does_not_hide_member_evidence_failure(self):
        result, verified, _ = self.run_batch(4, 45, fail_at=3)
        self.assert_no_prefix(result, "COHORT_REPLAY_PACKAGE_PIN_MISMATCH")
        self.assertEqual(verified.await_count, 4)
        self.assertEqual(result["failed_member_canonical_index"], 3)


class CohortProbeTests(TestCase):
    def setUp(self):
        tool_path = Path(__file__).resolve().parents[3] / "tools/probe_response_cohort_assembly.py"
        spec = importlib.util.spec_from_file_location("cohort_probe_cli_test", tool_path)
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def test_non_200_json_is_saved_without_promoting_a_member_prefix(self):
        raw = json.dumps({
            "status": "WITHHELD", "blocking_reasons": ["COHORT_EXECUTION_TIME_LIMIT"],
            "source_evidence_verified": False, "verified_member_count": 3,
        }).encode()
        error = HTTPError(self.tool.API_URL, 504, "synthetic", None, io.BytesIO(raw))
        opener = SimpleNamespace(open=Mock(side_effect=error))
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            request = parent / "request.json"
            request.write_text(json.dumps(manifest_for(4).canonical_payload()), encoding="utf-8")
            original = request.read_bytes()
            output = parent / "new-output"
            with patch.object(self.tool, "build_opener", return_value=opener):
                with redirect_stdout(io.StringIO()):
                    status = self.tool.run(request, output)
            self.assertEqual(status, 2)
            self.assertEqual((output / "cohort_assemble_response.json").read_bytes(), raw)
            summary = json.loads((output / "cohort_probe_summary.json").read_bytes())
            self.assertEqual(summary["HttpStatus"], 504)
            self.assertEqual(summary["VerifiedMemberCount"], 0)
            self.assertFalse(summary["SourceEvidenceVerified"])
            self.assertEqual(request.read_bytes(), original)
            self.assertEqual(opener.open.call_args.kwargs["timeout"], 420)

    def test_existing_output_is_preserved_without_an_http_request(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            request = parent / "request.json"
            request.write_text(json.dumps(manifest_for(4).canonical_payload()), encoding="utf-8")
            output = parent / "existing-output"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_bytes(b"previous-results")
            with patch.object(self.tool, "build_opener") as build:
                with self.assertRaises(FileExistsError):
                    self.tool.run(request, output)
            build.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b"previous-results")
