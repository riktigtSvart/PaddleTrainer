"""Versioned running starts: old experience is not current measured capacity.

Twenty minutes is an explicit starting product choice, including ten minutes
of walking. Unknown runners get four 1:00 jog / 1:30 walk intervals. This is
not a fitness test, a pace estimate or an automatic progression programme.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.models.entities import Sport, WorkoutSession
from app.planning.infrastructure.adapters.athlete_history import aware

POLICY = "running-start-v0.1"
FAMILY = "RUN_EASY_AEROBIC_FALLBACK"
BACKGROUND_LIMIT = 24


async def capture_background(session, owner, data):
    cutoff = datetime.fromisoformat(data["captured_at"])
    boundary = datetime.fromisoformat(data["recent_window"]["start_at"])
    rows = (await session.execute(select(WorkoutSession).where(
        WorkoutSession.user_id == UUID(owner), WorkoutSession.sport == Sport.RUNNING,
        WorkoutSession.started_at < boundary, WorkoutSession.created_at <= cutoff,
        WorkoutSession.ended_at.is_not(None), WorkoutSession.ended_at <= cutoff,
        WorkoutSession.duration_sec > 0,
    ).order_by(WorkoutSession.started_at.desc(), WorkoutSession.id.desc())
        .limit(BACKGROUND_LIMIT + 1).with_for_update())).scalars().all()
    return {"schema_version": "running-background-v0.1", "before_at": boundary.isoformat(),
            "sessions": [{"id": str(s.id), "sport": "RUNNING",
                "started_at": aware(s.started_at).isoformat(),
                "ended_at": aware(s.ended_at).isoformat(), "duration_sec": s.duration_sec}
                for s in rows[:BACKGROUND_LIMIT]],
            "has_more": len(rows) > BACKGROUND_LIMIT,
            "current_capacity_inferred": False}


def reference(data, completed, valid_completed, sport_code):
    cutoff = datetime.fromisoformat(data["captured_at"])
    recent = [s for s in completed if s["sport"] == "RUNNING" and not s.get("reference_occasion", False)]
    # A short test, warm-up or recovery run is not evidence against longer runs.
    eligible = [s for s in recent if s["duration_sec"] >= 1200][:3]
    cap = min((s["duration_sec"] for s in eligible), default=None)
    background = [s for s in data.get("running_background", {}).get("sessions", [])
                  if s["sport"] == "RUNNING" and valid_completed(s, cutoff) and s["duration_sec"] > 0]
    profile = (data.get("profile") or {}).get("data") or {}
    declarations, performances = [], []
    for index, row in enumerate(profile.get("sport_history", [])):
        if sport_code(row.get("sport")) != "RUNNING":
            continue
        if row.get("level") in {"recreational", "competitive", "professional"} or row.get("current_level") in {"recreational", "competitive", "professional"} or (row.get("planning") or {}).get("proficiency") in {"independent", "experienced"}:
            declarations.append(index)
        for result in row.get("performances") or []:
            if result.get("protocol", "distance_time") in {"distance_time", "cooper_12min"} and result.get("time") and result.get("distance_m"):
                performances.append({"sport_index": index, "result_id": result["result_id"]})
    mode = "recent_duration" if eligible else "experience_start" if recent or background or declarations or performances else "run_walk_start"
    return {"session_ids": [s["id"] for s in eligible], "cap_seconds": cap,
            "anchor_id": next((s["id"] for s in eligible if s["duration_sec"] == cap), None),
            "running": {"policy_version": POLICY, "mode": mode,
                "recent_session_ids": [s["id"] for s in recent],
                "historical_session_ids": [s["id"] for s in background],
                "declared_sport_indexes": declarations, "performance_references": performances,
                "current_capacity_inferred": False}}


def parameterize(template, available_seconds, reference, block, preferred_seconds=None):
    cap = min(available_seconds, reference["cap_seconds"] or 1200, 2700)
    seconds = int(cap // 300) * 300
    if type(preferred_seconds) is int and preferred_seconds % 300 == 0 and 1200 <= preferred_seconds <= cap:
        seconds = preferred_seconds
    if seconds < 1200:
        return None, "OPPORTUNITY_OR_DAILY_MINUTE_CAP"
    mode = reference["running"]["mode"]
    work = seconds - 600
    if mode == "run_walk_start":
        name = "4 × (1 perc könnyű kocogás + 90 másodperc séta)"
        title = "Kezdő futás–séta"
        description = "5 perc séta; 4 × (1 perc könnyű kocogás + 90 másodperc séta); 5 perc levezető séta. Ez egy 20 perces kezdő időkeret, nem maximális felmérés."
    elif mode == "experience_start":
        name = "10 perc könnyű futás, szükség szerint sétával"
        title = "Tájékozódó könnyű futás"
        description = "5 perc séta és könnyű bemelegítés; 10 perc könnyű futás, bármikor sétára váltva; 5 perc levezető séta. A korábbi futás vagy önbevallás tapasztalatot jelez, nem igazolja a mai terhelhetőséget. Ez 20 perces kezdő időkeret, nem kötelező folyamatosan végigfutni."
    else:
        name = "Könnyű, beszélgetős futás"
        title = "Könnyű aerob futás"
        description = f"5 perc könnyű bemelegítés; {work // 60} perc könnyű, beszélgetős futás; 5 perc levezetés. Az időkeret a legutóbbi legfeljebb három, legalább 20 perces saját futás legrövidebbikéhez és az elérhető időhöz igazodik. A rövid tesztek nem csökkentik ezt a keretet."
    description += " RPE 2–3/10, beszélgetős erőfeszítés, tempó- és pulzuskényszer nélkül. Ha ez nehéz, válts sétára vagy rövidíts; panasz esetén állj meg. Az edzés után rögzítsd a tényleges futás és séta idejét, az erőfeszítést és az esetleges panaszt. Általános aerob támogatás; a kajakspecifikus technikai edzést nem helyettesíti."
    result = {**template, "version": "v0.3", "minutes": seconds // 60,
              "title": f"{title} · {seconds // 60} perc", "description": description,
              "blocks": [block(1, "WARMUP", "Séta és könnyű bemelegítés", 300),
                         block(2, "WORK", name, work), block(3, "COOLDOWN", "Levezető séta", 300)]}
    metadata = {"schema_version": "training-prescription-v0.3", "family_key": FAMILY,
                "duration_sec": seconds, "minimum_seconds": 1200, "maximum_seconds": 2700,
                "reference_session_ids": reference["session_ids"], "reference_cap_seconds": reference["cap_seconds"],
                "product_default_used": reference["cap_seconds"] is None, "soft_duration_reduced": seconds < 1800,
                "progression_applied": False, "personal_response_model_applied": False,
                "intensity_basis": "product_default_not_personal_threshold", "rpe": {"min": 2, "max": 3},
                "running": reference["running"]}
    return (result, metadata), None
