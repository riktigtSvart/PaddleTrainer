"""Explicitly reviewed changes to two adjoining provisional mesocycle windows."""

from copy import deepcopy
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .common.serialization import compute_content_hash
from .cycle_program import reference, reject

SCHEMA = "cycle-mesocycle-boundary-revision-v0.1"


def slot(owner, program_id, revision):
    return "pt-cycle:" + compute_content_hash(
        {
            "scope": "mesocycle-boundary-revision-v0.1",
            "athlete_id": owner,
            "program_id": program_id,
            "revision": revision,
        }
    )


def build(proposal, *, program, previous, competition, created_at, timezone_name):
    reject(proposal["program_reference"] != reference(program), "CYCLE_REFERENCE_DIFFERS")
    number = proposal["revision"]
    reject((number == 1) != (previous is None), "CYCLE_REVISION_CHAIN")
    reject((proposal["previous_reference"] is None) != (previous is None), "CYCLE_REVISION_CHAIN")
    if previous:
        reject(
            proposal["previous_reference"] != reference(previous)
            or previous["proposal"]["revision"] != number - 1
            or previous["proposal"]["program_reference"] != reference(program),
            "CYCLE_REVISION_CHAIN",
        )
    reject(proposal["competition_reference"] != reference(competition), "CYCLE_REFERENCE_DIFFERS")
    reject(
        competition != program
        and competition["proposal"]["program_reference"] != reference(program),
        "CYCLE_REFERENCE_DIFFERS",
    )
    periods = deepcopy(previous["periods"] if previous else program["periods"])
    by_id = {p["id"]: p for p in periods}
    left, right = by_id.get(proposal["left_period_id"]), by_id.get(proposal["right_period_id"])
    reject(left is None or right is None or left is right, "CYCLE_BOUNDARY_PAIR")
    reject(
        left["period_type"] != "MESOCYCLE"
        or right["period_type"] != "MESOCYCLE"
        or left["parent_id"] != right["parent_id"],
        "CYCLE_BOUNDARY_PAIR",
    )
    reject(
        (date.fromisoformat(left["end_date"]) + timedelta(days=1)).isoformat()
        != right["start_date"],
        "CYCLE_BOUNDARY_PAIR",
    )
    end = proposal["new_end_date"]
    reject(not left["start_date"] <= end < right["end_date"], "CYCLE_BOUNDARY_RANGE")
    reject(end == left["end_date"], "CYCLE_BOUNDARY_UNCHANGED")
    created = datetime.fromisoformat(created_at)
    reject(created.tzinfo is None, "CYCLE_BOUNDARY_TIMESTAMP")
    today = created.astimezone(ZoneInfo(timezone_name)).date().isoformat()
    reject(left["end_date"] < today or end < today, "CYCLE_BOUNDARY_PAST")
    before = [deepcopy(left), deepcopy(right)]
    left["end_date"] = end
    right["start_date"] = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    artifact = {
        "artifact_id": slot(program["athlete_id"], program["proposal"]["program_id"], number),
        "schema_version": SCHEMA,
        "athlete_id": program["athlete_id"],
        "proposal": deepcopy(proposal),
        "created_at": created_at,
        "timezone_name": timezone_name,
        "effective_local_day": today,
        "previous_periods": before,
        "periods": periods,
        "competition_snapshot": deepcopy(competition["proposal"]["competitions"]),
        "period_dates_changed": True,
        "planning_authorized": False,
        "workouts_created": False,
        "training_load_replanned": False,
        "goal_protocols_rewritten": False,
        "required_reviews": ["training_load", "mesocycle_capability_roles", "measurement_windows"],
    }
    artifact["content_hash"] = compute_content_hash(artifact, exclude_fields=frozenset())
    return artifact
