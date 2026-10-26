"""Calendar structure and declared intent, without exercise-dose or adaptation claims.

The four entry modes share explicit macro/mesocycle structures. Dates are local
calendar dates; approximate competitions retain their full declared windows.
The 28-day / 12-calendar-month race limits are versioned product policy.
"""

from calendar import monthrange
from copy import deepcopy
from datetime import date, timedelta
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from . import cycle_program_context as context
from .common.serialization import compute_content_hash

RULES = "cycle-creation-rules-v0.1"
SCHEMA = "cycle-program-registration-v0.1"
EVENT_SCHEMA = "cycle-competition-revision-v0.1"
CALENDAR_VERSION = "ioc-games-calendar-2026-10-22"
CALENDAR_SOURCE = (
    "https://www.olympics.com/ioc/faq/sports-programme-and-results/"
    "where-will-the-next-olympic-games-be-held"
)
OLYMPICS = (
    {
        "key": "la-2028",
        "kind": "summer",
        "title": "Los Angeles 2028",
        "start_date": "2028-07-14",
        "end_date": "2028-07-30",
    },
    {
        "key": "alpes-2030",
        "kind": "winter",
        "title": "Francia-Alpok 2030",
        "start_date": "2030-02-01",
        "end_date": "2030-02-17",
    },
    {
        "key": "brisbane-2032",
        "kind": "summer",
        "title": "Brisbane 2032",
        "start_date": "2032-07-23",
        "end_date": "2032-08-08",
    },
    {
        "key": "utah-2034",
        "kind": "winter",
        "title": "Salt Lake City–Utah 2034",
        "start_date": "2034-02-10",
        "end_date": "2034-02-26",
    },
)
GOALS = {
    "performance": "Versenycél / sportteljesítmény",
    "aerobic_fitness": "Állóképesség javítása vagy fenntartása",
    "strength": "Erő és mindennapi terhelhetőség",
    "regular_activity": "Rendszeres mozgás kialakítása",
    "weight_loss": "Testsúlycsökkentés",
    "weight_maintenance": "Testsúly megtartása",
    "wellbeing": "Közérzet és élvezhető mozgás",
    "mobility": "Mozgékonyság",
}


class CycleRuleError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def reject(condition, code):
    if condition:
        raise CycleRuleError(code)


def plus_year(day):
    return day.replace(year=day.year + 1, day=min(day.day, monthrange(day.year + 1, day.month)[1]))


def slot(athlete_id, program_id, *, revision=None):
    return "pt-cycle:" + compute_content_hash(
        {
            "scope": "cycle-program" if revision is None else "cycle-competition-revision",
            "athlete_id": athlete_id,
            "program_id": program_id,
            "revision": revision,
        }
    )


def period_id(athlete_id, program_id, key):
    return str(uuid5(UUID(athlete_id), f"cycle-program-v0.1:{program_id}:{key}"))


def registration_slot(athlete_id, proposal):
    previous = proposal["continued_from"]
    if previous is None:
        return slot(athlete_id, proposal["program_id"])
    # A recreation block has one continuation slot, even across concurrent clients.
    return "pt-cycle:" + compute_content_hash(
        {
            "scope": "cycle-program-continuation",
            "athlete_id": athlete_id,
            "previous_artifact_id": previous["artifact_id"],
        }
    )


def _interval(node):
    start, end = date.fromisoformat(node["start_date"]), date.fromisoformat(node["end_date"])
    reject(start > end, "CYCLE_DATE_ORDER")
    return start, end


def _partition(nodes, start, end, code):
    ordered = sorted(nodes, key=lambda n: (n["start_date"], n["key"]))
    reject(not ordered, code)
    cursor = start
    for node in ordered:
        begin, finish = _interval(node)
        reject(begin != cursor or finish > end, code)
        cursor = finish + timedelta(days=1)
    reject(cursor != end + timedelta(days=1), code)


def validate_competitions(proposal, competitions, *, previous=None):
    reject(len({c["key"] for c in competitions}) != len(competitions), "CYCLE_EVENT_KEYS")
    start = date.fromisoformat(proposal["start_date"])
    end = max(date.fromisoformat(m["end_date"]) for m in proposal["macrocycles"])
    for item in competitions:
        first, last = _interval(item)
        reject(not start <= first <= last <= end, "CYCLE_EVENT_OUTSIDE_PROGRAM")
        reject((item["precision"] == "exact") != (first == last), "CYCLE_EVENT_PRECISION")
        if proposal["seasons"]:
            reject(
                not any(
                    s["start_date"] <= item["start_date"] <= item["end_date"] <= s["end_date"]
                    for s in proposal["seasons"]
                ),
                "CYCLE_EVENT_OUTSIDE_SEASON",
            )
    active_main = [c for c in competitions if c["priority"] == "main" and c["status"] == "planned"]
    if proposal["mode"] == "olympic":
        first = min(proposal["seasons"], key=lambda s: s["start_date"])
        reject(
            not any(
                first["start_date"] <= c["start_date"] <= c["end_date"] <= first["end_date"]
                for c in active_main
            ),
            "CYCLE_FIRST_SEASON_MAIN_EVENT_REQUIRED",
        )
    if proposal["mode"] == "race":
        reject(len(active_main) != 1, "CYCLE_ONE_TARGET_RACE_REQUIRED")
        if previous is None:
            reject(active_main[0]["end_date"] != proposal["end_date"], "CYCLE_RACE_END_DIFFERS")
    if previous is not None:
        old = {c["key"] for c in previous}
        reject(not old <= {c["key"] for c in competitions}, "CYCLE_EVENTS_CANNOT_DISAPPEAR")


def build_structure(proposal, *, athlete_id, timezone_name, calendar_snapshot=None):
    """Validate a complete explicit graph and assign owner-scoped stable UUIDs."""
    ZoneInfo(timezone_name)
    context.validate_context(proposal)
    start = date.fromisoformat(proposal["start_date"])
    macros, seasons, mode = proposal["macrocycles"], proposal["seasons"], proposal["mode"]
    reject(len({g["key"] for g in proposal["goals"]}) != len(proposal["goals"]), "CYCLE_GOAL_KEYS")
    end = max(date.fromisoformat(m["end_date"]) for m in macros)
    reject(start > end, "CYCLE_DATE_ORDER")
    reject((mode == "recreation") != (proposal["end_date"] is None), "CYCLE_PROGRAM_END_REQUIRED")
    if mode != "recreation":
        reject(proposal["end_date"] != end.isoformat(), "CYCLE_PROGRAM_END_DIFFERS")
    reject((mode in {"olympic", "season"}) != bool(seasons), "CYCLE_SEASON_STRUCTURE")
    reject(mode == "season" and len(seasons) != 1, "CYCLE_ONE_SEASON_REQUIRED")
    reject(mode in {"race", "recreation"} and len(macros) != 1, "CYCLE_ONE_MACRO_REQUIRED")
    reject(
        mode != "recreation" and proposal["continued_from"] is not None, "CYCLE_CONTINUATION_MODE"
    )
    if mode == "race":
        reject((end - start).days + 1 < 28, "CYCLE_RACE_TOO_CLOSE")
        reject(end >= plus_year(start), "CYCLE_RACE_TOO_FAR")
    reject(mode == "recreation" and (end - start).days + 1 > 366, "CYCLE_RECREATION_BLOCK_TOO_LONG")
    reject(mode == "season" and (end - start).days + 1 > 550, "CYCLE_SEASON_TOO_LONG")
    calendar = None
    if mode == "olympic":
        calendar = (
            deepcopy(calendar_snapshot)
            if calendar_snapshot is not None
            else next(
                (
                    dict(e, version=CALENDAR_VERSION, source=CALENDAR_SOURCE)
                    for e in OLYMPICS
                    if e["key"] == proposal["olympic_key"]
                ),
                None,
            )
        )
        reject(
            calendar is None or calendar["key"] != proposal["olympic_key"],
            "CYCLE_OLYMPICS_UNAVAILABLE",
        )
        reject(end.isoformat() != calendar["end_date"], "CYCLE_OLYMPIC_END_DIFFERS")
        reject((end - start).days > 1461, "CYCLE_OLYMPIC_HORIZON_TOO_LONG")
    else:
        reject(
            proposal["olympic_key"] is not None or calendar_snapshot is not None,
            "CYCLE_UNEXPECTED_OLYMPIC_REFERENCE",
        )
    all_nodes = seasons + macros + [n for m in macros for n in m["mesocycles"]]
    reject(len(all_nodes) + (mode == "olympic") > 256, "CYCLE_STRUCTURE_SIZE_LIMIT")
    keys = [n["key"] for n in all_nodes]
    reject(len(keys) != len(set(keys)) or "olympic-root" in keys, "CYCLE_PERIOD_KEYS")
    season_keys = {s["key"] for s in seasons}
    if seasons:
        _partition(seasons, start, end, "CYCLE_SEASON_COVERAGE")
        reject(any(m["season_key"] not in season_keys for m in macros), "CYCLE_MACRO_PARENT")
        for season in seasons:
            _partition(
                [m for m in macros if m["season_key"] == season["key"]],
                *_interval(season),
                "CYCLE_MACRO_COVERAGE",
            )
    else:
        reject(any(m["season_key"] is not None for m in macros), "CYCLE_MACRO_PARENT")
        _partition(macros, start, end, "CYCLE_MACRO_COVERAGE")
    for macro in macros:
        _partition(macro["mesocycles"], *_interval(macro), "CYCLE_MESO_COVERAGE")
    validate_competitions(proposal, proposal["competitions"])
    result = []

    def node(source, kind, parent):
        result.append(
            {
                "id": period_id(athlete_id, proposal["program_id"], source["key"]),
                "key": source["key"],
                "parent_id": parent,
                "period_type": kind,
                "title": source["title"],
                "start_date": source["start_date"],
                "end_date": source["end_date"],
            }
        )

    root_id = None
    if mode == "olympic":
        root = {
            "key": "olympic-root",
            "title": proposal["title"],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        node(root, "OLYMPIC_CYCLE", None)
        root_id = result[-1]["id"]
    for season in sorted(seasons, key=lambda n: n["start_date"]):
        node(season, "SEASON", root_id)
    for macro in sorted(macros, key=lambda n: n["start_date"]):
        parent = (
            period_id(athlete_id, proposal["program_id"], macro["season_key"])
            if macro["season_key"]
            else None
        )
        node(macro, "MACROCYCLE", parent)
        macro_id = result[-1]["id"]
        for meso in sorted(macro["mesocycles"], key=lambda n: n["start_date"]):
            node(meso, "MESOCYCLE", macro_id)
    return result, calendar


def build_registration(
    proposal,
    *,
    athlete_id,
    timezone_name,
    created_at,
    calendar_snapshot=None,
    continuation=None,
    athlete_snapshot=None,
):
    periods, calendar = build_structure(
        proposal,
        athlete_id=athlete_id,
        timezone_name=timezone_name,
        calendar_snapshot=calendar_snapshot,
    )
    reject(
        (proposal["continued_from"] is None) != (continuation is None),
        "CYCLE_CONTINUATION_REQUIRED",
    )
    family = proposal["program_id"]
    if continuation is not None:
        reject(continuation["proposal"]["mode"] != "recreation", "CYCLE_CONTINUATION_MODE")
        reject(
            proposal["start_date"] <= max(p["end_date"] for p in continuation["periods"]),
            "CYCLE_CONTINUATION_OVERLAP",
        )
        reject(proposal["sport"] != continuation["proposal"]["sport"], "CYCLE_CONTINUATION_SPORT")
        family = continuation["program_family_id"]
    artifact = {
        "artifact_id": registration_slot(athlete_id, proposal),
        "schema_version": context.INTAKE_SCHEMA
        if context.is_intake(proposal)
        else context.CONTEXT_SCHEMA
        if context.is_context(proposal)
        else SCHEMA,
        "rules_version": context.INTAKE_RULES
        if context.is_intake(proposal)
        else context.CONTEXT_RULES
        if context.is_context(proposal)
        else RULES,
        "athlete_id": athlete_id,
        "timezone_name": timezone_name,
        "proposal": deepcopy(proposal),
        "periods": periods,
        "calendar_snapshot": calendar,
        "program_family_id": family,
        "created_at": created_at,
        "planning_authorized": False,
        "workouts_created": False,
        "capability_goals_preregistered": False,
        "content_hash": "",
    }
    if "athlete_context" in proposal:
        reject(
            athlete_snapshot is None
            or athlete_snapshot["references"] != proposal["athlete_context"],
            "CYCLE_ATHLETE_CONTEXT_REQUIRED",
        )
        artifact["athlete_context_snapshot"] = deepcopy(athlete_snapshot)
    artifact["content_hash"] = compute_content_hash(
        {k: v for k, v in artifact.items() if k != "content_hash"}, exclude_fields=frozenset()
    )
    return artifact


def build_competition_revision(proposal, *, program, previous, created_at):
    reject(proposal["program_reference"] != reference(program), "CYCLE_PROGRAM_REFERENCE_DIFFERS")
    number = proposal["revision"]
    reject((number == 1) != (previous is None), "CYCLE_REVISION_CHAIN")
    reject((proposal["previous_reference"] is None) != (previous is None), "CYCLE_REVISION_CHAIN")
    if previous is not None:
        reject(
            proposal["previous_reference"] != reference(previous)
            or previous["proposal"]["revision"] != number - 1
            or previous["proposal"]["program_reference"] != reference(program),
            "CYCLE_REVISION_CHAIN",
        )
    old = previous["proposal"]["competitions"] if previous else program["proposal"]["competitions"]
    context.validate_context(
        {**program["proposal"], "competitions": proposal["competitions"]}, event_revision=True
    )
    validate_competitions(program["proposal"], proposal["competitions"], previous=old)
    artifact = {
        "artifact_id": slot(
            program["athlete_id"], program["proposal"]["program_id"], revision=number
        ),
        "schema_version": context.CONTEXT_EVENT_SCHEMA
        if context.is_context(proposal)
        else EVENT_SCHEMA,
        "rules_version": context.CONTEXT_RULES if context.is_context(proposal) else RULES,
        "athlete_id": program["athlete_id"],
        "proposal": deepcopy(proposal),
        "created_at": created_at,
        "period_dates_changed": False,
        "planning_authorized": False,
        "content_hash": "",
    }
    artifact["content_hash"] = compute_content_hash(
        {k: v for k, v in artifact.items() if k != "content_hash"}, exclude_fields=frozenset()
    )
    return artifact


def reference(artifact):
    return {"artifact_id": artifact["artifact_id"], "content_hash": artifact["content_hash"]}
