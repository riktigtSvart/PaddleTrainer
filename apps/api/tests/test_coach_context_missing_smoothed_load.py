"""Regression for a closed day with no smoothed training-load history."""

from copy import deepcopy
from datetime import date
import unittest

from app.services.athlete_state_scientific_view import (
    build_athlete_state_scientific_view,
)
from app.services.coach_context import (
    build_coach_assessment,
    build_coach_context,
    build_coach_inputs,
    build_coach_state,
    build_descriptive_flags,
    build_interpretation_facts,
    build_interpretation_signals,
    build_readiness_coach_view,
)
from app.services.scientific_assessment import build_scientific_assessment


AS_OF_DATE = date(2026, 7, 2)


def inputs_for(training_load):
    return {
        "as_of_date": AS_OF_DATE,
        "plan": {"today": {"planned_workouts": []}, "active_periods": []},
        "athlete": {"training_load": training_load, "readiness": None},
    }


class MissingSmoothedLoadTests(unittest.TestCase):
    def assert_smoothed_unknown(self, facts):
        self.assertIsNone(facts["athlete"]["load_method"])
        self.assertIsNone(facts["athlete"]["smoothed_acute_weekly_equivalent"])
        self.assertIsNone(facts["athlete"]["smoothed_chronic_weekly_equivalent"])
        flags = build_descriptive_flags(facts)
        self.assertIsNone(flags["load"]["smoothed_acute_vs_chronic"])

    def test_explicit_null_from_empty_history_preserves_raw_summary(self):
        inputs = inputs_for({
            "acute": {"weekly_load": 0.0, "session_count": 0},
            "chronic": {"weekly_load": 0.0, "session_count": 0},
            "smoothed": None,
        })
        original = deepcopy(inputs)
        facts = build_interpretation_facts(inputs)
        self.assert_smoothed_unknown(facts)
        self.assertTrue(facts["athlete"]["load_available"])
        self.assertEqual(facts["athlete"]["acute_weekly_load"], 0.0)
        self.assertEqual(facts["athlete"]["chronic_weekly_load"], 0.0)
        self.assertEqual(inputs, original)

    def test_missing_smoothed_key_remains_unknown(self):
        self.assert_smoothed_unknown(build_interpretation_facts(inputs_for({})))

    def test_empty_smoothed_mapping_remains_unknown(self):
        facts = build_interpretation_facts(inputs_for({"smoothed": {}}))
        self.assert_smoothed_unknown(facts)

    def test_missing_whole_load_remains_unavailable(self):
        for inputs in (inputs_for(None), {"athlete": {}}):
            with self.subTest(inputs=inputs):
                facts = build_interpretation_facts(inputs)
                self.assertFalse(facts["athlete"]["load_available"])
                self.assertIsNone(facts["athlete"]["acute_weekly_load"])
                self.assert_smoothed_unknown(facts)

    def test_measured_smoothed_zero_is_preserved(self):
        facts = build_interpretation_facts(inputs_for({"smoothed": {
            "method": "NORMALIZED_EWMA",
            "acute": {"weekly_equivalent": 0.0},
            "chronic": {"weekly_equivalent": 0.0},
        }}))
        self.assertEqual(facts["athlete"]["load_method"], "NORMALIZED_EWMA")
        self.assertEqual(facts["athlete"]["smoothed_acute_weekly_equivalent"], 0.0)
        self.assertEqual(facts["athlete"]["smoothed_chronic_weekly_equivalent"], 0.0)
        self.assertEqual(build_descriptive_flags(facts)["load"]["smoothed_acute_vs_chronic"],
                         "EQUAL")

    def test_populated_smoothed_load_preserves_values_and_input(self):
        inputs = inputs_for({
            "acute": {"weekly_load": 151.53},
            "chronic": {"weekly_load": 110.09},
            "smoothed": {
                "method": "NORMALIZED_EWMA",
                "acute": {"weekly_equivalent": 103.38},
                "chronic": {"weekly_equivalent": 221.69},
            },
        })
        original = deepcopy(inputs)
        athlete = build_interpretation_facts(inputs)["athlete"]
        self.assertEqual(athlete["load_method"], "NORMALIZED_EWMA")
        self.assertEqual(athlete["acute_weekly_load"], 151.53)
        self.assertEqual(athlete["chronic_weekly_load"], 110.09)
        self.assertEqual(athlete["smoothed_acute_weekly_equivalent"], 103.38)
        self.assertEqual(athlete["smoothed_chronic_weekly_equivalent"], 221.69)
        self.assertEqual(inputs, original)

    def test_entire_scientific_view_chain_accepts_null_without_load_inference(self):
        raw_state = {
            "as_of_date": AS_OF_DATE,
            "training_load": {
                "acute": {"weekly_load": 0.0},
                "chronic": {"weekly_load": 0.0},
                "smoothed": None,
            },
            "readiness": None,
            "plan_context": {"current_week": {"planned_workouts": []},
                             "active_periods": []},
        }
        original = deepcopy(raw_state)
        context = build_coach_context(raw_state, AS_OF_DATE)
        inputs = build_coach_inputs(context)
        facts = build_interpretation_facts(inputs)
        flags = build_descriptive_flags(facts)
        readiness = build_readiness_coach_view(facts)
        signals = build_interpretation_signals(facts, flags, readiness)
        assessment = build_coach_assessment(signals)
        state = build_coach_state(assessment, readiness, facts)
        scientific = build_scientific_assessment(state)
        view = build_athlete_state_scientific_view(scientific)
        self.assert_smoothed_unknown(facts)
        self.assertIsNone(state["load"]["pattern"])
        self.assertNotIn("LOAD_METHODS_DIVERGE", state["signal_codes"])
        self.assertEqual(view["as_of_date"], AS_OF_DATE)
        self.assertFalse(view["capacity"]["available"])
        self.assertEqual(raw_state, original)


if __name__ == "__main__":
    unittest.main()
