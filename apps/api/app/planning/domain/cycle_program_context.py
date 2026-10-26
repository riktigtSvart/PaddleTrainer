"""Structured declared goals and event demands; no dose or individual response inference."""

from decimal import Decimal

from .goals.catalog import CapabilityKey

INTAKE_SCHEMA = "cycle-program-registration-v0.3"
INTAKE_RULES = "cycle-creation-rules-v0.3"
CONTEXT_SCHEMA = "cycle-program-registration-v0.2"
CONTEXT_EVENT_SCHEMA = "cycle-competition-revision-v0.2"
CONTEXT_RULES = "cycle-creation-rules-v0.2"
ICF_SOURCE = "https://www.canoeicf.com/sites/default/files/icf_canoe_sprint_coaching_manual_2-3.pdf"
# A deliberately qualitative app mapping of the ICF coaching manual, including chapter 26.
# No energy percentages, workout dose, individualized targets or mesocycle roles.
SPRINT_COMMON = (
    "TECHNICAL_SKILL",
    "TECHNICAL_STABILITY_UNDER_FATIGUE",
    "MAX_STRENGTH",
    "POWER_RFD",
    "SPRINT_SPEED_AND_START",
    "HIGH_INTENSITY_AND_ANAEROBIC_PROFILE",
    "VO2_CAPACITY",
)


def sprint_keys(profile):
    if profile["event_type"] != "sprint" or profile["distance_status"] != "specified":
        return None
    discipline = profile["discipline"].casefold()
    if not any(word in discipline for word in ("kajak", "kenu", "kayak", "canoe")):
        return None
    if any(
        word in discipline
        for word in (
            "slalom",
            "szlalom",
            "maraton",
            "marathon",
            "polo",
            "póló",
            "wildwater",
            "vadvíz",
        )
    ):
        return None
    distance = Decimal(profile["distance_value"]) * (
        1000 if profile["distance_unit"] == "km" else 1
    )
    if distance == 200:
        return list(SPRINT_COMMON)
    if distance in (500, 1000):
        return list(SPRINT_COMMON) + [
            "PERIPHERAL_OXIDATIVE_CAPACITY",
            "MUSCULAR_ENDURANCE",
            "PACING_COMPETENCE",
        ]
    return None


def validate_profile(profile):
    specified = profile["distance_status"] == "specified"
    if specified != (
        profile["distance_value"] is not None and profile["distance_unit"] is not None
    ):
        raise ValueError("A specified distance needs value and unit.")
    if not specified and (
        profile["distance_value"] is not None or profile["distance_unit"] is not None
    ):
        raise ValueError("An unknown or inapplicable distance must remain null.")
    keys = profile["capability_keys"]
    if len(set(keys)) != len(keys) or not set(keys) <= set(CapabilityKey):
        raise ValueError("Use unique supported capability keys.")
    if (profile["capability_basis"] == "unassessed") != (not keys):
        raise ValueError("An unassessed event must not claim a capability profile.")
    if profile["capability_basis"] == "icf_sprint_v0_1" and sprint_keys(profile) != keys:
        raise ValueError("The source-based suggestion differs from the declared event.")


def is_intake(proposal):
    return "athlete_context" in proposal or any("details" in g for g in proposal.get("goals", []))


def is_context(proposal):
    return (
        "planning_basis" in proposal
        or is_intake(proposal)
        or any("body_mass" in g for g in proposal.get("goals", []))
        or any("profile" in c for c in proposal.get("competitions", []))
    )


def validate_context(proposal, *, event_revision=False):
    if "planning_basis" not in proposal and not is_intake(proposal):
        return
    from .cycle_program import reject

    new_goals = any("details" in g for g in proposal["goals"])
    reject(
        new_goals
        and {"weight_loss", "weight_maintenance"} <= {g["key"] for g in proposal["goals"]},
        "CYCLE_WEIGHT_GOALS_CONFLICT",
    )
    for goal in proposal["goals"]:
        body = goal.get("body_mass")
        weight = goal["key"] in {"weight_loss", "weight_maintenance"}
        reject(weight != (body is not None), "CYCLE_BODY_MASS_REQUIRED")
        if body and goal["key"] == "weight_maintenance" and "target_kg" not in body:
            reject(not new_goals, "CYCLE_BODY_MASS_REQUIRED")
        if body and goal["key"] == "weight_loss":
            reject("target_kg" not in body, "CYCLE_BODY_MASS_REQUIRED")
            reject(
                Decimal(body["target_kg"]) >= Decimal(body["current_kg"]),
                "CYCLE_BODY_MASS_DIRECTION",
            )
        details = goal.get("details")
        if details:
            direction_goal = goal["key"] in {"aerobic_fitness", "strength", "mobility"}
            reject(
                direction_goal != (details["direction"] is not None),
                "CYCLE_GOAL_DIRECTION_REQUIRED",
            )
            reject(
                goal["key"] != "regular_activity" and details["weekly_sessions"] is not None,
                "CYCLE_GOAL_FIELD_DIFFERS",
            )
            reject(
                goal["key"] != "performance"
                and bool(details["event_keys"] or details["result_target"]),
                "CYCLE_GOAL_FIELD_DIFFERS",
            )
            active = {
                c["key"]
                for c in proposal["competitions"]
                if event_revision or c["status"] == "planned"
            }
            reject(
                len(set(details["event_keys"])) != len(details["event_keys"])
                or not set(details["event_keys"]) <= active,
                "CYCLE_GOAL_EVENTS_DIFFER",
            )
    for event in proposal["competitions"]:
        reject(
            event["status"] == "planned" and "profile" not in event, "CYCLE_EVENT_PROFILE_REQUIRED"
        )
