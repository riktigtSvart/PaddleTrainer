from enum import StrEnum


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"
    UNKNOWN = "unknown"


class Freshness(StrEnum):
    CURRENT = "current"
    AGING = "aging"
    STALE = "stale"
    UNKNOWN = "unknown"


class PlanningScope(StrEnum):
    LONG_TERM = "long_term"
    SEASON = "season"
    MACROCYCLE = "macrocycle"
    MESOCYCLE = "mesocycle"
    MICROCYCLE = "microcycle"
    SESSION = "session"
    SESSION_ADAPTATION = "session_adaptation"


class DecisionPurpose(StrEnum):
    CREATE_PLAN = "create_plan"
    CREATE_MICROCYCLE = "create_microcycle"
    CREATE_WORKOUT = "create_workout"
    REVISE_PLAN = "revise_plan"
    ADAPT_SESSION = "adapt_session"
    HANDLE_MISSED_SESSION = "handle_missed_session"
    SELECT_MEASUREMENT = "select_measurement"
    REVIEW_MESOCYCLE = "review_mesocycle"
    REVIEW_SEASON = "review_season"
    HANDOVER_DECISION = "handover_decision"
    GOAL_FORECAST = "goal_forecast"


class ProvenanceKind(StrEnum):
    SOURCE = "source"
    DERIVED = "derived"
    POLICY_RESOLVED = "policy_resolved"
    INFERRED = "inferred"


class KnowledgeStatus(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    NOT_MEASURED = "not_measured"
    NOT_ASKED = "not_asked"


class SnapshotStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    FROZEN = "frozen"
    INVALID = "invalid"


class DecisionRelevance(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    BLOCKING = "blocking"
