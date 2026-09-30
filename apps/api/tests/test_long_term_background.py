from app.services.long_term_background import (
    build_long_term_background_evidence,
)


def test_build_long_term_background_groups_by_sport():
    assessment = {
        "assessment_type": "TRAINING_HISTORY",
        "sport": "KAYAK",
        "source": "SELF_REPORTED",
        "measurements": [
            {
                "metric_key": "training_age_years",
                "value_float": 12.0,
                "value_text": None,
                "unit": "years",
            },
            {
                "metric_key": "competition_level",
                "value_float": None,
                "value_text": "INTERNATIONAL",
                "unit": None,
            },
            {
                "metric_key": "previous_weekly_hours",
                "value_float": 11.5,
                "value_text": None,
                "unit": "hours/week",
            },
        ],
    }

    evidence = (
        build_long_term_background_evidence(
            {
                "assessments": [
                    assessment
                ],
            }
        )
    )

    assert len(
        evidence["by_sport"]
    ) == 1

    kayak = evidence[
        "by_sport"
    ][0]

    assert kayak["sport"] == "KAYAK"
    assert kayak["assessments"] == [
        assessment
    ]

    assert (
        evidence["unscoped_assessments"]
        == []
    )