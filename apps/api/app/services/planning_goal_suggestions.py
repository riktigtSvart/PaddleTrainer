"""Review scaffolding from declared intent, never a physiological periodization policy."""
from copy import deepcopy
from app.planning.domain.goals.catalog import CapabilityKey
from app.planning.domain.workout_family.builtins import builtin_workout_family_registry_v0_1

RULES = "declared-goal-review-v0.1"
ROLES = {"primary_development", "secondary_development", "maintenance", "permitted_decline"}
# Product vocabulary mapping, not evidence of an individual adaptation or a dose.
GOAL_KEYS = {"aerobic_fitness": ("VO2_CAPACITY", "PERIPHERAL_OXIDATIVE_CAPACITY"),
             "strength": ("MAX_STRENGTH",)}

def _declared(data):
    registry = builtin_workout_family_registry_v0_1()
    result = []
    for macro in (p for p in data["periods"] if p["period_type"] == "MACROCYCLE"):
        children = [p for p in data["periods"] if p["parent_id"] == macro["id"] and p["period_type"] == "MESOCYCLE"]
        current = next((v["artifact"] for v in data["goal_versions"] if v["period_id"] == macro["id"] and "macrocycle_period_id" in v["artifact"]["proposal"]), None)
        sources = {}
        def add(key, source):
            if key in set(CapabilityKey):
                sources.setdefault(key, []).append(source)
        future_main = sorted([e for e in data["competitions"] if e["status"] == "planned" and e.get("priority") == "main" and e["end_date"] >= macro["start_date"]],key=lambda e:(e["start_date"],e["key"]))
        next_key = future_main[0]["key"] if future_main else None
        events = [e for e in data["competitions"] if e["status"] == "planned" and ((e["start_date"] <= macro["end_date"] and e["end_date"] >= macro["start_date"]) or e["key"] == next_key)]
        for event in events:
            profile = event.get("profile") or {}
            if profile.get("capability_basis") != "unassessed":
                for key in profile.get("capability_keys", []):
                    add(key, {"kind": "declared_event_profile", "key": event["key"], "basis": profile["capability_basis"]})
        for goal in data["declared_goals"]:
            for key in GOAL_KEYS.get(goal["key"], ()):
                add(key, {"kind": "declared_goal", "key": goal["key"], "direction": (goal.get("details") or {}).get("direction")})
        if current:
            for goal in current["proposal"]["goals"]:
                add(goal["capability_key"], {"kind": "recorded_goal", "artifact_id": current["artifact_id"]})
        rows = []
        for key, evidence in sorted(sources.items()):
            old = next((g for g in current["proposal"]["goals"] if g["capability_key"] == key), None) if current else None
            explicit = [s for s in evidence if s["kind"] == "declared_goal"]
            # Directions are not guessed from a weight goal or a race name.
            directions = {s["direction"] for s in explicit}
            suggested = "maintenance" if directions == {"maintain"} else "primary_development" if directions == {"improve"} else None
            role = old["role"] if old else suggested
            reason = old["rationale"] if old else "A megadott célból származó kiinduló javaslat; a mezociklusonkénti szerepet felül kell vizsgálni." if suggested else "A verseny megadott képességprofilja alapján releváns; a szerep még kiválasztandó."
            directives = []
            for child in children:
                previous = next((d for d in current["proposal"]["mesocycle_directives"] if d["capability_key"] == key and d["mesocycle_period_id"] == child["id"]), None) if current else None
                directives.append({"mesocycle_period_id": child["id"], "role": previous["role"] if previous else None,
                    "rationale": previous["rationale"] if previous else "A mezociklus célja a makrociklus és az aktuális állapot alapján még felülvizsgálandó.",
                    "origin": "recorded" if previous else "review_required"})
            # Registry links are descriptive coverage only. In particular a RUN fallback is never selected for kayak.
            links = [{"family_key": f.family_ref.family_key, "family_version": f.family_ref.family_version,
                      "modality_key": f.modality_key.key, "match": "primary" if key in f.primary_capability_keys else "secondary",
                      "eligibility_evaluated": False, "selected": False}
                     for f in registry.families if key in f.primary_capability_keys or key in f.secondary_capability_keys]
            rows.append({"capability_key": key, "role": role, "rationale": reason,
                         "origin": "recorded" if old else "declared_goal_mapping" if suggested else "review_required",
                         "sources": evidence, "mesocycle_directives": directives, "family_links": links,
                         "family_coverage": "linked_not_evaluated" if links else "missing"})
        result.append({"macrocycle_period_id": macro["id"], "base_reference": {"artifact_id": current["artifact_id"], "content_hash": current["content_hash"]} if current else None,
                       "base_revision": current["proposal"]["revision"] if current else 0, "rows": rows,
                       "unprofiled_event_keys": [e["key"] for e in events if not (e.get("profile") or {}).get("capability_keys")],
                       "unmapped_goal_keys": [g["key"] for g in data["declared_goals"] if g["key"] not in GOAL_KEYS]})
    return {"schema_version": "planning-goal-suggestions-v0.1", "rules_version": RULES,
            "registry_reference": {"version": registry.registry_version, "content_hash": registry.content_hash},
            "macrocycles": deepcopy(result), "review_required": True, "periodization_inferred": False,
            "dose_selected": False, "family_selection_authorized": False, "committed": False}


def build(data):
    from app.services.planning_strategy import enrich
    return enrich(data, _declared(data))
