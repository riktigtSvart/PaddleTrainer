from fastapi import APIRouter

from app.api.routes import (
    assessments,
    capacities,
    coach,
    executed_workouts,
    health,
    pft,
    phase_clarification_storage,
    phase_reconciliations,
    plan_contracts,
    plan_execution_comparisons,
    planning_adoption,
    planning_goals,
    polar,
    polar_environment_replay,
    polar_hr_acquisition,
    polar_hr_diagnostics,
    polar_response_cohort,
    polar_response_cohort_records,
    polar_response_dataset,
    polar_tcx,
    readiness,
    responses,
    sessions,
    training_periods,
    workouts,
)

api_router = APIRouter()
api_router.include_router(pft.router)
api_router.include_router(plan_contracts.router)
api_router.include_router(executed_workouts.router)
api_router.include_router(plan_execution_comparisons.router)
api_router.include_router(phase_reconciliations.router)
api_router.include_router(phase_clarification_storage.router)
api_router.include_router(planning_adoption.router)
api_router.include_router(planning_goals.router)

api_router.include_router(health.router)
api_router.include_router(polar.router)
api_router.include_router(polar_environment_replay.router)
api_router.include_router(polar_hr_acquisition.router)
api_router.include_router(polar_hr_diagnostics.router)
api_router.include_router(polar_response_cohort.router)
api_router.include_router(polar_response_cohort_records.router)
api_router.include_router(polar_response_dataset.router)
api_router.include_router(polar_tcx.router)
api_router.include_router(workouts.router)
api_router.include_router(sessions.router)
api_router.include_router(coach.router)
api_router.include_router(training_periods.router)
api_router.include_router(assessments.router)
api_router.include_router(capacities.router)
api_router.include_router(readiness.router)
api_router.include_router(responses.router)
