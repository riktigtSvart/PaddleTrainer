from fastapi import APIRouter

from app.api.routes import (
    assessments,
    capacities,
    coach,
    health,
    polar,
    polar_hr_acquisition,
    polar_tcx,
    readiness,
    responses,
    sessions,
    training_periods,
    workouts,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(polar.router)
api_router.include_router(polar_hr_acquisition.router)
api_router.include_router(polar_tcx.router)
api_router.include_router(workouts.router)
api_router.include_router(sessions.router)
api_router.include_router(coach.router)
api_router.include_router(training_periods.router)
api_router.include_router(assessments.router)
api_router.include_router(capacities.router)
api_router.include_router(readiness.router)
api_router.include_router(responses.router)
