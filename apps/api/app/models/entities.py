import enum
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Sport(str, enum.Enum):
    KAYAK = "KAYAK"
    RUNNING = "RUNNING"
    SWIMMING = "SWIMMING"
    STRENGTH = "STRENGTH"
    CYCLING = "CYCLING"
    OTHER = "OTHER"


class WorkoutStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class BlockType(str, enum.Enum):
    WORK = "WORK"
    RECOVERY = "RECOVERY"
    WARMUP = "WARMUP"
    COOLDOWN = "COOLDOWN"
    REPEAT = "REPEAT"


class PeriodType(str, enum.Enum):
    OLYMPIC_CYCLE = "OLYMPIC_CYCLE"
    SEASON = "SEASON"
    MACROCYCLE = "MACROCYCLE"
    MESOCYCLE = "MESOCYCLE"


class ObjectiveType(str, enum.Enum):
    ENDURANCE = "ENDURANCE"
    SPEED = "SPEED"
    STRENGTH = "STRENGTH"
    TECHNIQUE = "TECHNIQUE"
    RECOVERY = "RECOVERY"
    MOBILITY = "MOBILITY"
    RACE_SPECIFIC = "RACE_SPECIFIC"


class WorkoutLinkSource(str, enum.Enum):
    PROVIDER_EXACT = "PROVIDER_EXACT"
    MANUAL_CONFIRMED = "MANUAL_CONFIRMED"
    AUTO_MATCHED = "AUTO_MATCHED"


class AssessmentType(str, enum.Enum):
    TRAINING_HISTORY = "TRAINING_HISTORY"
    VO2MAX_TEST = "VO2MAX_TEST"
    LACTATE_TEST = "LACTATE_TEST"
    PERFORMANCE_TEST = "PERFORMANCE_TEST"
    STRENGTH_TEST = "STRENGTH_TEST"
    BODY_COMPOSITION = "BODY_COMPOSITION"
    OTHER = "OTHER"


class CapacityType(str, enum.Enum):
    GENERAL_AEROBIC = "GENERAL_AEROBIC"
    SPORT_SPECIFIC_AEROBIC = "SPORT_SPECIFIC_AEROBIC"
    STRENGTH = "STRENGTH"
    MUSCULAR_ENDURANCE = "MUSCULAR_ENDURANCE"
    NEUROMUSCULAR = "NEUROMUSCULAR"
    TECHNIQUE = "TECHNIQUE"


class CapacitySource(str, enum.Enum):
    ASSESSMENT = "ASSESSMENT"
    TRAINING_INFERENCE = "TRAINING_INFERENCE"
    SELF_REPORTED = "SELF_REPORTED"
    MANUAL = "MANUAL"


class ResponseTiming(str, enum.Enum):
    IMMEDIATE = "IMMEDIATE"
    SAME_DAY = "SAME_DAY"
    NEXT_MORNING = "NEXT_MORNING"
    FOLLOW_UP = "FOLLOW_UP"


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Budapest")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ExternalConnection(Base):
    __tablename__ = "external_connections"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="POLAR")
    provider_user_id: Mapped[str | None] = mapped_column(String(128))
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TrainingPeriod(Base):
    __tablename__ = "training_periods"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "training_periods.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    period_type: Mapped[PeriodType] = mapped_column(
        Enum(
            PeriodType,
            name="period_type_enum",
        ),
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(200)
    )

    start_date: Mapped[date] = mapped_column(
        Date,
        index=True,
    )

    end_date: Mapped[date] = mapped_column(
        Date,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text
    )

    target_load: Mapped[float | None] = mapped_column(
        Float
    )

    load_method: Mapped[str | None] = mapped_column(
        String(32)
    )

    target_duration_sec: Mapped[int | None] = mapped_column(
        Integer
    )

    extra_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )

    parent: Mapped["TrainingPeriod | None"] = relationship(
        remote_side="TrainingPeriod.id",
        back_populates="children",
    )

    children: Mapped[list["TrainingPeriod"]] = relationship(
        back_populates="parent",
    )

    objectives: Mapped[list["TrainingPeriodObjective"]] = relationship(
        back_populates="period",
        cascade="all, delete-orphan",
    )

    planned_workouts: Mapped[list["PlannedWorkout"]] = relationship(
        back_populates="training_period",
    )


class TrainingPeriodObjective(Base):
    __tablename__ = "training_period_objectives"

    __table_args__ = (
        UniqueConstraint(
            "period_id",
            "objective_type",
            name="uq_period_objective_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "training_periods.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    objective_type: Mapped[ObjectiveType] = mapped_column(
        Enum(
            ObjectiveType,
            name="objective_type_enum",
        )
    )

    weight: Mapped[float] = mapped_column(
        Float
    )

    period: Mapped[TrainingPeriod] = relationship(
        back_populates="objectives"
    )


class PlannedWorkout(Base):
    __tablename__ = "planned_workouts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    training_period_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "training_periods.id",
            ondelete="SET NULL",
        ),
        index=True,
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    planned_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sport: Mapped[Sport] = mapped_column(Enum(Sport, name="sport_enum"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[float | None] = mapped_column(Float)
    intensity_type: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[WorkoutStatus] = mapped_column(
        Enum(WorkoutStatus, name="workout_status_enum"), default=WorkoutStatus.PLANNED
    )
    source: Mapped[str] = mapped_column(String(32), default="MANUAL")
    polar_target_id: Mapped[str | None] = mapped_column(String(128), index=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    blocks: Mapped[list["WorkoutBlock"]] = relationship(
        back_populates="workout", cascade="all, delete-orphan", order_by="WorkoutBlock.position"
    )
    training_period: Mapped["TrainingPeriod | None"] = relationship(
        back_populates="planned_workouts"
    )


class WorkoutBlock(Base):
    __tablename__ = "workout_blocks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workout_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("planned_workouts.id", ondelete="CASCADE"), index=True
    )
    parent_block_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workout_blocks.id"))
    position: Mapped[int] = mapped_column(Integer)
    block_type: Mapped[BlockType] = mapped_column(Enum(BlockType, name="block_type_enum"))
    name: Mapped[str | None] = mapped_column(String(120))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[float | None] = mapped_column(Float)
    intensity_type: Mapped[str | None] = mapped_column(String(32))
    intensity_min: Mapped[float | None] = mapped_column(Float)
    intensity_max: Mapped[float | None] = mapped_column(Float)
    repeat_count: Mapped[int | None] = mapped_column(Integer)

    workout: Mapped[PlannedWorkout] = relationship(back_populates="blocks")


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"
    __table_args__ = (UniqueConstraint("external_provider", "external_id", name="uq_external_session"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    planned_workout_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("planned_workouts.id"))
    planned_workout_link_source: Mapped[
        WorkoutLinkSource | None
    ] = mapped_column(
        Enum(
            WorkoutLinkSource,
            name="workout_link_source_enum",
        ),
        nullable=True,
    )
    external_provider: Mapped[str] = mapped_column(String(32), default="POLAR")
    external_id: Mapped[str] = mapped_column(String(128))
    sport: Mapped[Sport] = mapped_column(Enum(Sport, name="session_sport_enum"), default=Sport.OTHER)
    name: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    max_hr: Mapped[float | None] = mapped_column(Float)
    avg_speed: Mapped[float | None] = mapped_column(Float)
    max_speed: Mapped[float | None] = mapped_column(Float)
    avg_cadence: Mapped[float | None] = mapped_column(Float)
    max_cadence: Mapped[float | None] = mapped_column(Float)
    avg_power: Mapped[float | None] = mapped_column(Float)
    max_power: Mapped[float | None] = mapped_column(Float)
    cardio_load: Mapped[float | None] = mapped_column(Float)
    perceived_load: Mapped[float | None] = mapped_column(Float)
    rpe: Mapped[float | None] = mapped_column(Float)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    responses: Mapped[
        list["AthleteResponse"]
    ] = relationship(
        back_populates="workout_session",
    )


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    assessment_type: Mapped[
        AssessmentType
    ] = mapped_column(
        Enum(
            AssessmentType,
            name="assessment_type_enum",
        ),
        index=True,
    )

    sport: Mapped[Sport | None] = mapped_column(
        Enum(
            Sport,
            name="assessment_sport_enum",
        ),
        nullable=True,
    )

    title: Mapped[str | None] = mapped_column(
        String(200)
    )

    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(32),
        default="MANUAL",
    )

    notes: Mapped[str | None] = mapped_column(
        Text
    )

    extra_data: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSON,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship()

    measurements: Mapped[
        list["Measurement"]
    ] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
    )

    capacities: Mapped[
        list["AthleteCapacity"]
    ] = relationship(
        back_populates="assessment",
    )


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "assessments.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    metric_key: Mapped[str] = mapped_column(
        String(64),
        index=True,
    )

    value_float: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    value_text: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    unit: Mapped[str | None] = mapped_column(
        String(32)
    )

    sport: Mapped[
        Sport | None
    ] = mapped_column(
        Enum(
            Sport,
            name="measurement_sport_enum",
        ),
        nullable=True,
    )

    extra_data: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSON,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    assessment: Mapped[
        "Assessment"
    ] = relationship(
        back_populates="measurements",
    )

    capacities: Mapped[
        list["AthleteCapacity"]
    ] = relationship(
        back_populates="measurement",
    )


class AthleteCapacity(Base):
    __tablename__ = "athlete_capacities"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    assessment_id: Mapped[
        uuid.UUID | None
    ] = mapped_column(
        ForeignKey(
            "assessments.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    measurement_id: Mapped[
        uuid.UUID | None
    ] = mapped_column(
        ForeignKey(
            "measurements.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    capacity_type: Mapped[
        CapacityType
    ] = mapped_column(
        Enum(
            CapacityType,
            name="capacity_type_enum",
        ),
        index=True,
    )

    sport: Mapped[
        Sport | None
    ] = mapped_column(
        Enum(
            Sport,
            name="capacity_sport_enum",
        ),
        nullable=True,
        index=True,
    )

    value: Mapped[float] = mapped_column(
        Float
    )

    unit: Mapped[str] = mapped_column(
        String(32)
    )

    source: Mapped[
        CapacitySource
    ] = mapped_column(
        Enum(
            CapacitySource,
            name="capacity_source_enum",
        ),
        index=True,
    )

    confidence: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    estimated_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    extra_data: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSON,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship()

    assessment: Mapped[
        "Assessment | None"
    ] = relationship(
        back_populates="capacities",
    )

    measurement: Mapped[
        "Measurement | None"
    ] = relationship(
        back_populates="capacities",
    )


class AthleteReadiness(Base):
    __tablename__ = "athlete_readiness"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "recorded_date",
            name="uq_readiness_user_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    recorded_date: Mapped[date] = mapped_column(
        Date,
        index=True,
    )

    hrv_rmssd_ms: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    resting_hr_bpm: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    sleep_duration_sec: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        nullable=True,
    )

    sleep_score: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    energy_score: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    fatigue_score: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    stress_score: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    soreness_score: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    readiness_score: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    illness: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    travel: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    source: Mapped[str] = mapped_column(
        String(32),
        default="MANUAL",
    )

    extra_data: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSON,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship()


class AthleteResponse(Base):
    __tablename__ = "athlete_responses"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    workout_session_id: Mapped[
        uuid.UUID | None
    ] = mapped_column(
        ForeignKey(
            "workout_sessions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    response_timing: Mapped[
        ResponseTiming
    ] = mapped_column(
        Enum(
            ResponseTiming,
            name="response_timing_enum",
        ),
        index=True,
    )

    recorded_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    fatigue_score: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    soreness_score: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    recovery_score: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    energy_score: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    performance_metric: Mapped[
        str | None
    ] = mapped_column(
        String(64),
        nullable=True,
    )

    performance_delta_percent: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    extra_data: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSON,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship()

    workout_session: Mapped[
        "WorkoutSession | None"
    ] = relationship(
        back_populates="responses",
    )


class PhysiologicalMeasurement(Base):
    __tablename__ = "physiological_measurements"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(32),
        index=True,
    )

    metric_key: Mapped[str] = mapped_column(
        String(64),
        index=True,
    )

    value_float: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    value_text: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    unit: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    period_start: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    period_end: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    device_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    device_model: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    quality: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    source_record_id: Mapped[
        str | None
    ] = mapped_column(
        String(256),
        nullable=True,
        index=True,
    )

    extra_data: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSON,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship()


class ProviderDataRecord(Base):
    __tablename__ = "provider_data_records"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(32),
        index=True,
    )

    data_type: Mapped[str] = mapped_column(
        String(64),
        index=True,
    )

    provider_record_id: Mapped[
        str | None
    ] = mapped_column(
        String(256),
        nullable=True,
        index=True,
    )

    occurred_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    period_start: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    period_end: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    raw_data: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSON,
    )

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship()
