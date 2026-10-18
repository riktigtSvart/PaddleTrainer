"""Clock counterexamples; synthetic inputs are not athlete evidence."""

import json
import unittest
from copy import deepcopy

from app.services.api_hr_timebase_audit import (
    build_api_hr_timebase_audit, build_api_pause_clock_inventory, verify_api_hr_timebase_audit,
)


def source():
    return {"identifier": {"id": "synthetic-session"}, "timezoneOffsetMinutes": 120,
            "exercises": [{"identifier": {"id": "synthetic-exercise"},
                           "startTime": "2026-07-03T14:49:54", "stopTime": "2026-07-03T14:50:04",
                           "durationMillis": 10000,
                           "samples": {"samples": [
                               {"type": "HEART_RATE", "intervalMillis": 1000, "values": [120, 121, 122]},
                               {"type": "SPEED", "intervalMillis": 1000, "values": [8.0, 9.0, 10.0]},
                               {"type": "DISTANCE", "intervalMillis": 1000, "values": [1.0, 3.0, 5.0]}]},
                           "routes": {"route": {"startTime": "2026-07-03T14:49:54.580",
                                                "wayPoints": [{"elapsedMillis": 3100}, {"elapsedMillis": 4101}, {"elapsedMillis": 5100}]}}}]}


CONTEXT = {"expected_session_external_id": "synthetic-session", "sample_session_match_count": 1,
           "route_session_match_count": 1, "requested_features": ["samples", "routes", "pause-times"]}


class ApiTimebaseAuditTests(unittest.TestCase):
    def audit(self, sample=None, route=None, **kwargs):
        sample = source() if sample is None else sample
        route = deepcopy(sample) if route is None else route
        return build_api_hr_timebase_audit(sample, route, **{**CONTEXT, **kwargs})

    def test_declared_route_clock_and_equal_counts_do_not_certify_hr_origin(self):
        audit = self.audit()
        exercise = audit["exercises"][0]
        self.assertEqual(exercise["gps_clock"]["first_point_utc"], "2026-07-03T12:49:57.680000+00:00")
        self.assertTrue(exercise["gps_clock"]["point_index_transfer_structurally_compatible"])
        self.assertEqual(len(exercise["candidate_hr_timebases"]), 3)
        self.assertIsNone(exercise["selected_hr_timebase"])
        self.assertFalse(audit["api_native_time_origin_verified"])
        self.assertFalse(audit["training_authorized"])
        self.assertFalse(exercise["absolute_hr_time_mapping_verified"])
        by_id = {c["candidate_id"]: c for c in exercise["candidate_hr_timebases"]}
        self.assertEqual(by_id["API_ROUTE_START_PLUS_ONE_INTERVAL"]["first_sample_offset_from_reported_exercise_start_us"], 1580000)
        self.assertEqual(by_id["API_ROUTE_FIRST_POINT_REGULAR_GRID"]["first_sample_offset_from_reported_exercise_start_us"], 3680000)

    def test_json_round_trip_and_original_source_reconstruction(self):
        s = source()
        audit = json.loads(json.dumps(self.audit(s)))
        self.assertTrue(verify_api_hr_timebase_audit(audit, s, s, **CONTEXT))

    def test_missing_or_duplicate_session_never_uses_list_position(self):
        for name in ("sample_session_match_count", "route_session_match_count"):
            for count in (0, 2, True):
                with self.subTest(name=name, count=count):
                    a = self.audit(**{name: count})
                    self.assertEqual(a["status"], "WITHHELD")
                    self.assertEqual(a["exercises"], [])

    def test_changed_route_exercise_identity_is_rejected(self):
        route = source()
        route["exercises"][0]["identifier"]["id"] = "another"
        self.assertEqual(self.audit(route=route)["status"], "WITHHELD")

    def test_duplicate_exercise_identity_is_rejected(self):
        s = source()
        s["exercises"].append(deepcopy(s["exercises"][0]))
        self.assertEqual(self.audit(s)["status"], "WITHHELD")

    def test_exercise_selector_is_identity_bound(self):
        self.assertEqual(self.audit(expected_exercise_external_id="another")["status"], "WITHHELD")
        self.assertEqual(self.audit(expected_exercise_external_id="synthetic-exercise")["exercise_count"], 1)

    def test_metadata_and_utc_offset_disagreement_stop_candidates(self):
        for key, value in [("startTime", "2026-07-03T14:49:55"), ("durationMillis", 9000), ("timezoneOffsetMinutes", 60)]:
            route = source()
            route["exercises"][0][key] = value
            a = self.audit(route=route)["exercises"][0]
            self.assertEqual(a["status"], "REVIEW_REQUIRED")
            self.assertEqual(a["candidate_hr_timebases"], [])

    def test_missing_timezone_is_not_assumed_local_machine_timezone(self):
        s = source()
        del s["timezoneOffsetMinutes"]
        a = self.audit(s)["exercises"][0]
        self.assertEqual(a["candidate_hr_timebases"], [])
        self.assertIsNone(a["exercise_start_utc"])

    def test_explicit_offset_needs_no_machine_timezone(self):
        s = source()
        del s["timezoneOffsetMinutes"]
        e = s["exercises"][0]
        for key in ("startTime", "stopTime"):
            e[key] += "+02:00"
        e["routes"]["route"]["startTime"] += "+02:00"
        self.assertEqual(self.audit(s)["exercises"][0]["exercise_start_utc"], "2026-07-03T12:49:54+00:00")

    def test_route_times_are_never_sorted_or_filled(self):
        for times in ([3100, 3100, 5100], [3100, 2100, 5100], [3100, None, 5100], [3100, True, 5100]):
            s = source()
            s["exercises"][0]["routes"]["route"]["wayPoints"] = [{"elapsedMillis": t} for t in times]
            a = self.audit(s)["exercises"][0]
            self.assertEqual(a["gps_clock"]["status"], "REVIEW_REQUIRED")
            self.assertEqual(a["candidate_hr_timebases"], [])

    def test_different_gps_count_does_not_allow_index_transfer(self):
        s = source()
        s["exercises"][0]["routes"]["route"]["wayPoints"].pop()
        a = self.audit(s)["exercises"][0]
        self.assertFalse(a["gps_clock"]["point_index_transfer_structurally_compatible"])
        self.assertNotIn("API_ROUTE_FIRST_POINT_REGULAR_GRID", [c["candidate_id"] for c in a["candidate_hr_timebases"]])

    def test_internal_gps_gap_defeats_equal_count_shortcut(self):
        s = source()
        s["exercises"][0]["routes"]["route"]["wayPoints"][2]["elapsedMillis"] = 6100
        a = self.audit(s)["exercises"][0]
        self.assertEqual(a["gps_clock"]["uniform_grid_max_deviation_ms"], 1000)
        self.assertFalse(a["gps_clock"]["point_index_transfer_structurally_compatible"])

    def test_speed_period_count_and_values_are_checked_independently(self):
        for key, value in [("intervalMillis", 2000), ("values", [1.0, 2.0]), ("values", [1.0, -2.0, 3.0])]:
            s = source()
            s["exercises"][0]["samples"]["samples"][1][key] = value
            a = self.audit(s)["exercises"][0]["relative_series_compatibility"][0]
            self.assertFalse(a["eligible_for_unmodified_relative_pairing"])
            if key == "values" and len(value) == 3:
                self.assertTrue(a["same_slot_count_and_interval_as_hr"])

    def test_invalid_hr_values_stop_clock_candidates(self):
        for bad in (None, True, 0, -1):
            s = source()
            s["exercises"][0]["samples"]["samples"][0]["values"][1] = bad
            a = self.audit(s)["exercises"][0]
            self.assertFalse(a["hr_values_technically_clean"])
            self.assertEqual(a["candidate_hr_timebases"], [])

    def test_unknown_hr_field_requires_review_instead_of_ignored_new_clock(self):
        s = source()
        s["exercises"][0]["samples"]["samples"][0]["firstSampleTime"] = "2026-07-03T14:49:55.580"
        self.assertEqual(self.audit(s)["exercises"][0]["candidate_hr_timebases"], [])

    def test_requested_missing_pause_field_does_not_establish_no_pauses(self):
        a = self.audit()["exercises"][0]
        self.assertTrue(a["pause_inventory"]["feature_requested"])
        self.assertEqual(a["pause_inventory"]["status"], "NOT_PROVIDED")
        self.assertFalse(a["pause_inventory"]["absence_is_proof_of_no_pause"])

    def test_nonempty_pause_metadata_is_preserved_without_proving_clock_semantics(self):
        s = source()
        s["exercises"][0]["pauseTimes"] = [{"startTime": "2026-07-03T14:49:57", "endTime": "2026-07-03T14:49:59"}]
        a = self.audit(s)["exercises"][0]
        self.assertEqual(a["pause_inventory"]["union_duration_ms"], 2000)
        self.assertFalse(a["pause_clock_semantics_verified"])

    def test_tampered_and_rehashed_authority_are_rejected_by_reconstruction(self):
        s = source()
        for key in ("training_authorized", "api_native_time_origin_verified", "export_timebase_verified"):
            a = self.audit(s)
            a[key] = True
            from app.services.api_hr_timebase_audit import _hash
            a["audit_hash"] = _hash({k: v for k, v in a.items() if k != "audit_hash"})
            self.assertFalse(verify_api_hr_timebase_audit(a, s, s, **CONTEXT))

    def test_source_values_changed_under_old_report_are_rejected(self):
        s = source()
        a = self.audit(s)
        s["exercises"][0]["samples"]["samples"][0]["values"][0] += 1
        self.assertFalse(verify_api_hr_timebase_audit(a, s, s, **CONTEXT))

    def test_source_nan_is_withheld_not_silently_removed(self):
        s = source()
        s["exercises"][0]["samples"]["samples"][0]["values"][0] = float("nan")
        self.assertEqual(self.audit(s)["status"], "WITHHELD")


class PauseBoundaryTests(unittest.TestCase):
    def source(self):
        s = source()
        s.update(startTime="2026-07-03T14:49:54", stopTime="2026-07-03T14:50:10")
        e = s["exercises"][0]
        e["pauseTimes"] = [{"startTime":"2026-07-03T14:50:04.580", "endTime":"2026-07-03T14:50:10.333"}]
        return s,e

    def test_duration_end_marker_is_valid_interval_not_legacy_stop_error(self):
        s,e=self.source()
        p=build_api_pause_clock_inventory(e,s,feature_requested=True)
        self.assertEqual(p["status"],"CHECKED_WITH_LIMITATIONS")
        self.assertEqual(p["at_duration_end_record_count"],1)
        self.assertEqual(p["invalid_record_count"],0)
        self.assertEqual(p["pause_duration_sum_ms"],5753)
        self.assertFalse(p["pause_clock_semantics_verified"])
        self.assertIsNone(build_api_hr_timebase_audit(s,s,**CONTEXT)["exercises"][0]["selected_hr_timebase"])

    def test_internal_pause_and_end_marker_are_separate_roles(self):
        s,e=self.source()
        e["pauseTimes"].insert(0,{"startTime":"2026-07-03T14:49:57", "endTime":"2026-07-03T14:49:59"})
        s["stopTime"]="2026-07-03T14:50:12"
        p=build_api_pause_clock_inventory(e,s)
        self.assertEqual(p["before_duration_end_record_count"],1)
        self.assertEqual(p["at_duration_end_record_count"],1)
        self.assertEqual(p["session_clock_hypothesis"]["candidate_minus_reported_session_stop_ms"],333)
        self.assertFalse(p["session_clock_hypothesis"]["applied_to_hr_or_gps_samples"])

    def test_outside_session_interval_is_not_accepted_as_end_marker(self):
        s,e=self.source()
        e["pauseTimes"][0]["endTime"]="2026-07-03T15:00:00"
        self.assertEqual(build_api_pause_clock_inventory(e,s)["status"],"INVALID")

    def test_reversed_time_is_invalid(self):
        s,e=self.source()
        e["pauseTimes"][0]["endTime"]="2026-07-03T14:49:00"
        self.assertEqual(build_api_pause_clock_inventory(e,s)["invalid_record_count"],1)

    def test_crossing_duration_anchor_requires_explicit_role(self):
        s,e=self.source()
        e["pauseTimes"]=[{"startTime":"2026-07-03T14:50:03", "endTime":"2026-07-03T14:50:05"}]
        p=build_api_pause_clock_inventory(e,s)
        self.assertEqual(p["events"][0]["role"],"CROSSES_DURATION_END_ANCHOR")
        self.assertEqual(p["at_duration_end_record_count"],0)

    def test_overlapping_intervals_are_not_silently_certified(self):
        s,e=self.source()
        e["pauseTimes"]=[{"startTime":"2026-07-03T14:49:55", "endTime":"2026-07-03T14:49:58"},
                         {"startTime":"2026-07-03T14:49:57", "endTime":"2026-07-03T14:50:00"}]
        p=build_api_pause_clock_inventory(e,s)
        self.assertEqual(p["status"],"REVIEW_REQUIRED")
        self.assertEqual(p["pause_duration_sum_ms"],6000)
        self.assertEqual(p["union_duration_ms"],5000)

    def test_missing_pause_field_has_no_invented_endpoint(self):
        s,e=self.source();del e["pauseTimes"]
        p=build_api_pause_clock_inventory(e,s)
        self.assertEqual(p["status"],"NOT_PROVIDED")
        self.assertIsNone(p["session_clock_hypothesis"]["candidate_session_end_utc"])

    def test_finer_stop_metadata_does_not_rewrite_raw_pause_times(self):
        s,e=self.source()
        expected=deepcopy(e["pauseTimes"])
        e["stopTime"]="2026-07-03T14:50:04.580"
        p=build_api_pause_clock_inventory(e,s)
        self.assertEqual(e["pauseTimes"],expected)
        self.assertEqual(p["at_duration_end_record_count"],1)


if __name__ == "__main__":
    unittest.main()
