from app.services.response_observations import (
    build_response_trajectories,
)


def test_build_response_trajectories_groups_by_workout_and_keeps_unlinked():
    observations = [
        {
            "id": "response-1",
            "workout_session_id": "session-1",
            "response_timing": "IMMEDIATE",
            "fatigue_score": 6.0,
        },
        {
            "id": "response-2",
            "workout_session_id": "session-1",
            "response_timing": "SAME_DAY",
            "fatigue_score": 4.0,
        },
        {
            "id": "response-3",
            "workout_session_id": None,
            "response_timing": "FOLLOW_UP",
            "fatigue_score": 3.0,
        },
    ]

    trajectories = build_response_trajectories(
        observations
    )

    assert len(
        trajectories["by_workout_session"]
    ) == 1

    trajectory = trajectories[
        "by_workout_session"
    ][0]

    assert (
        trajectory["workout_session_id"]
        == "session-1"
    )

    assert [
        item["response_timing"]
        for item in trajectory["observations"]
    ] == [
        "IMMEDIATE",
        "SAME_DAY",
    ]

    assert trajectories[
        "unlinked_observations"
    ] == [
        observations[2]
    ]