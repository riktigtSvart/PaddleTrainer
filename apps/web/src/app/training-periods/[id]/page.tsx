import Link from "next/link";
import {notFound} from "next/navigation";

type Objective = {
    id: string;
    objective_type: string;
    weight: number;
};

type PeriodWorkout = {
    id: string;
    date: string;
    planned_start_time: string | null;
    sport: string;
    title: string;
    status: string;
    duration_sec: number | null;
    distance_m: number | null;
    intensity_type: string | null;
    execution: {
        has_actual: boolean;
        actual_session_count: number;
        session_id: string | null;
        link_source: string | null;
        actual_started_at: string | null;
        actual_duration_sec: number | null;
        actual_distance_m: number | null;
        actual_cardio_load: number | null;
        comparison_basis:
            | "DURATION"
            | "DISTANCE"
            | "MIXED"
            | "NONE";

        delta_percent: number | null;
        training_load_proxies: TrainingLoadProxies | null;
    };
};

type WeeklyPlanned = {
    workout_count: number;
    workout_count_by_sport: Record<
        string,
        number
    >;
    duration_sec: number;
    duration_known_count: number;
    distance_by_sport: Record<
        string,
        number
    >;
    distance_known_count: number;
};

type WeeklyActual = {
    session_count: number;
    plan_associated_count: number;
    provider_linked_count: number;
    manual_linked_count: number;
    auto_linked_count: number;
    unknown_link_source_count: number;
    unassociated_count: number;
    duration_sec: number;
    distance_by_sport: Record<string, number>;
    cardio_load: number;
    cardio_load_session_count: number;
    session_count_by_sport: Record<
        string,
        number
    >;
};

type WeeklyExecution = {
    planned_workout_count: number;
    completed_plan_count: number;
    uncompleted_plan_count: number;
    completion_rate_percent:
        | number
        | null;
    linked_session_count: number;
    provider_exact_link_count: number;
    manual_confirmed_link_count: number;
    auto_matched_link_count: number;
    unknown_link_source_count: number;
};

type WeeklySummary = {
    planned_duration_complete: boolean;
    notes: string[];
};

type PeriodWeek = {
    week_start: string;
    week_end: string;
    phase:
        | "PAST"
        | "CURRENT"
        | "FUTURE";
    planned: WeeklyPlanned;
    execution: WeeklyExecution;
    actual: WeeklyActual;
    summary: WeeklySummary;
    load_trend: WeeklyLoadTrend | null;
};

type PeriodSummary = {
    planned: {
        workout_count: number;
        duration_sec: number;
        duration_known_count: number;
        distance_by_sport: Record<string, number>;
        distance_known_count: number;
    };
    execution: {
        planned_workout_count: number;
        completed_plan_count: number;
        uncompleted_plan_count: number;
        completion_rate_percent: number | null;
        linked_session_count: number;
        provider_exact_link_count: number;
        manual_confirmed_link_count: number;
        auto_matched_link_count: number;
        unknown_link_source_count: number;
    };
    actual_in_period: {
        session_count: number;
        duration_sec: number;
        distance_by_sport: Record<string, number>;
        cardio_load: number;
        cardio_load_session_count: number;
    };
};

type TrainingPeriod = {
    id: string;
    parent_id: string | null;
    period_type: string;
    title: string;
    start_date: string;
    end_date: string;
    description: string | null;
    target_load: number | null;
    load_method: string | null;
    target_duration_sec: number | null;
    extra_data: Record<string, unknown>;
    objectives: Objective[];
    workouts: PeriodWorkout[];
    weeks: PeriodWeek[];
    summary: PeriodSummary;
    training_load_proxies: TrainingLoadProxies | null;
};

type WeeklyLoadTrend = {
    week_start: string;
    week_end: string;
    phase:
        | "PAST"
        | "CURRENT"
        | "FUTURE";
    cardio_load: number;
    session_count: number;
    cardio_load_session_count: number;
    previous_week_cardio_load: number;
    change_percent: number | null;
};

type TrainingLoadProxies = {
    as_of_date: string;
    acute: {
        days: number;
        start_date: string;
        end_date: string;
        weekly_load: number;
        session_count: number;
    };
    chronic: {
        days: number;
        start_date: string;
        end_date: string;
        total_load: number;
        weekly_load: number;
        session_count: number;
    };
    comparison: {
        absolute_difference: number;
        difference_percent: number | null;
    };
};

async function getTrainingPeriod(
    id: string
): Promise<TrainingPeriod | null> {
    const apiUrl =
        process.env.NEXT_PUBLIC_API_URL ??
        "http://127.0.0.1:8000";

    const response = await fetch(
        `${apiUrl}/api/v1/training-periods/${id}`,
        {
            cache: "no-store",
        }
    );

    if (response.status === 404) {
        return null;
    }

    if (!response.ok) {
        throw new Error(
            `Training period API error: ${response.status}`
        );
    }

    return response.json();
}

function loadTrendText(
    trend: WeeklyLoadTrend | null
): string | null {
    if (!trend) {
        return null;
    }

    if (trend.phase === "CURRENT") {
        return `Előző hét: ${trend.previous_week_cardio_load}`;
    }

    if (trend.phase === "FUTURE") {
        return null;
    }

    if (trend.change_percent === null) {
        return "Nincs összehasonlítható előző hét";
    }

    const prefix =
        trend.change_percent > 0
            ? "+"
            : "";

    return `${prefix}${trend.change_percent}% az előző héthez képest`;
}

function formatDuration(
    seconds: number | null
): string {
    if (seconds === null) {
        return "—";
    }

    const hours = Math.floor(seconds / 3600);

    const minutes = Math.floor(
        (seconds % 3600) / 60
    );

    if (hours > 0) {
        return `${hours} óra ${minutes} perc`;
    }

    return `${minutes} perc`;
}

function formatDurationClock(
    seconds: number
): string {
    const hours = Math.floor(
        seconds / 3600
    );

    const minutes = Math.floor(
        (seconds % 3600) / 60
    );

    const secs = seconds % 60;

    if (hours > 0) {
        return `${hours}:${minutes
            .toString()
            .padStart(2, "0")}:${secs
            .toString()
            .padStart(2, "0")}`;
    }

    return `${minutes}:${secs
        .toString()
        .padStart(2, "0")}`;
}

function actualSummary(
    workout: PeriodWorkout
): string {
    const parts: string[] = [];

    if (
        workout.execution
            .actual_duration_sec !== null
    ) {
        parts.push(
            formatDurationClock(
                workout.execution
                    .actual_duration_sec
            )
        );
    }

    if (
        workout.execution
            .actual_distance_m !== null
    ) {
        parts.push(
            formatDistance(
                workout.execution
                    .actual_distance_m
            )
        );
    }

    return parts.join(" · ");
}

function formatDistance(
    meters: number | null
): string {
    if (meters === null) {
        return "—";
    }

    return `${(meters / 1000).toFixed(2)} km`;
}

function objectiveLabel(
    objectiveType: string
): string {
    const labels: Record<string, string> = {
        ENDURANCE: "Állóképesség",
        SPEED: "Sebesség",
        STRENGTH: "Erő",
        TECHNIQUE: "Technika",
        RECOVERY: "Regeneráció",
        MOBILITY: "Mobilitás",
        RACE_SPECIFIC: "Versenyspecifikus",
    };

    return labels[objectiveType] ?? objectiveType;
}

function sportLabel(
    sport: string
): string {
    const labels: Record<string, string> = {
        KAYAK: "Kajak",
        RUNNING: "Futás",
        SWIMMING: "Úszás",
        STRENGTH: "Erősítés",
        CYCLING: "Kerékpár",
        OTHER: "Egyéb",
    };

    return labels[sport] ?? sport;
}

function linkSourceLabel(
    source: string | null
): string | null {
    if (source === "MANUAL_CONFIRMED") {
        return "Kézzel megerősített";
    }

    if (source === "PROVIDER_EXACT") {
        return "Polar által kapcsolt";
    }

    if (source === "AUTO_MATCHED") {
        return "Automatikusan párosított";
    }

    return null;
}

function dateFromIsoDate(value: string): Date {
    const [year, month, day] = value
        .split("-")
        .map(Number);

    return new Date(
        Date.UTC(year, month - 1, day)
    );
}

function isoDate(value: Date): string {
    return value.toISOString().slice(0, 10);
}

function addDays(
    date: Date,
    days: number
): Date {
    const result = new Date(date);

    result.setUTCDate(
        result.getUTCDate() + days
    );

    return result;
}

function dayName(
    value: string
): string {
    const date = dateFromIsoDate(value);

    return new Intl.DateTimeFormat(
        "hu-HU",
        {
            weekday: "short",
            timeZone: "UTC",
        }
    ).format(date);
}

function dayNumber(
    value: string
): string {
    const date = dateFromIsoDate(value);

    return String(date.getUTCDate());
}

function monthLabel(
    start: string,
    end: string
): string {
    const startDate = dateFromIsoDate(start);
    const endDate = dateFromIsoDate(end);

    const formatter =
        new Intl.DateTimeFormat(
            "hu-HU",
            {
                month: "long",
                timeZone: "UTC",
            }
        );

    const startMonth =
        formatter.format(startDate);

    const endMonth =
        formatter.format(endDate);

    if (startMonth === endMonth) {
        return startMonth;
    }

    return `${startMonth}–${endMonth}`;
}

function isoWeekNumber(
    value: string
): number {
    const date = dateFromIsoDate(value);

    const target = new Date(date);

    const day =
        target.getUTCDay() || 7;

    target.setUTCDate(
        target.getUTCDate() + 4 - day
    );

    const yearStart = new Date(
        Date.UTC(
            target.getUTCFullYear(),
            0,
            1
        )
    );

    return Math.ceil(
        (
            (
                target.getTime() -
                yearStart.getTime()
            ) /
            86400000 +
            1
        ) / 7
    );
}

function DistanceBySport({
                             distances,
                         }: {
    distances: Record<string, number>;
}) {
    const entries = Object.entries(distances);

    if (entries.length === 0) {
        return (
            <span className="text-zinc-500">
        —
      </span>
        );
    }

    return (
        <div className="space-y-1">
            {entries.map(([sport, meters]) => (
                <div
                    key={sport}
                    className="flex justify-between gap-4 text-sm"
                >
          <span className="text-zinc-400">
            {sportLabel(sport)}
          </span>

                    <span>
            {formatDistance(meters)}
          </span>
                </div>
            ))}
        </div>
    );
}

function Metric({
                    label,
                    value,
                    hint,
                }: {
    label: string;
    value: string | number;
    hint?: string;
}) {
    return (
        <div className="rounded-xl bg-zinc-800/60 p-4">
            <div className="text-xs uppercase tracking-wide text-zinc-500">
                {label}
            </div>

            <div className="mt-2 text-lg font-semibold">
                {value}
            </div>

            {hint && (
                <div className="mt-1 text-xs text-zinc-500">
                    {hint}
                </div>
            )}
        </div>
    );
}

function WorkoutRow({
                        workout,
                    }: {
    workout: PeriodWorkout;
}) {
    return (
        <Link
            href={`/workouts/${workout.id}`}
            className="block"
        >
            <div className="rounded-xl bg-zinc-800/50 px-4 py-3 transition hover:bg-zinc-800">
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <div className="text-xs uppercase tracking-wide text-zinc-500">
                            {sportLabel(workout.sport)}
                            {" · "}
                            {workout.date}
                        </div>

                        <div className="mt-1 font-medium">
                            {workout.title}
                        </div>

                        <div className="mt-1 text-sm text-zinc-400">
                            {workout.intensity_type ??
                                "Nincs intenzitási cél"}
                        </div>
                    </div>

                    <div className="text-right text-sm text-zinc-400">
                        {workout.duration_sec !== null && (
                            <div>
                                {formatDuration(
                                    workout.duration_sec
                                )}
                            </div>
                        )}

                        {workout.distance_m !== null && (
                            <div>
                                {formatDistance(
                                    workout.distance_m
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </Link>
    );
}

export default async function TrainingPeriodPage({
                                                     params,
                                                 }: {
    params: Promise<{
        id: string;
    }>;
}) {
    const {id} = await params;

    const period =
        await getTrainingPeriod(id);

    if (!period) {
        notFound();
    }

    return (
        <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-100">
            <div className="w-full">
                <Link
                    href="/"
                    className="text-sm text-zinc-400 transition hover:text-zinc-100"
                >
                    ← Coach
                </Link>

                <header className="mt-8 border-b border-zinc-800 pb-8">
                    <div className="flex flex-wrap items-center gap-2 text-sm uppercase tracking-wide text-zinc-500">
                        <span>{period.period_type}</span>
                        <span>·</span>
                        <span>
              {period.start_date}
                            {" – "}
                            {period.end_date}
            </span>
                    </div>

                    <div className="mt-3 flex flex-wrap items-start justify-between gap-8">
                        <div className="min-w-0">
                            <h1 className="text-4xl font-semibold tracking-tight">
                                {period.title}
                            </h1>

                            {period.description && (
                                <p className="mt-4 max-w-3xl leading-7 text-zinc-400">
                                </p>
                            )}
                        </div>

                        {period.training_load_proxies && (
                            <div className="flex shrink-0 gap-8 text-right">
                                <div>
                                    <div className="text-xs uppercase tracking-wide text-zinc-500">
                                        7 nap
                                    </div>
                                    <div className="mt-1 text-xl font-semibold text-zinc-100">
                                        {period.training_load_proxies.acute.weekly_load}
                                    </div>
                                    <div className="text-xs text-zinc-500">
                                        cardio load
                                    </div>
                                </div>

                                <div>
                                    <div className="text-xs uppercase tracking-wide text-zinc-500">
                                        42 nap
                                    </div>
                                    <div className="mt-1 text-xl font-semibold text-zinc-100">
                                        {period.training_load_proxies.chronic.weekly_load}
                                    </div>
                                    <div className="text-xs text-zinc-500">
                                        heti átlag
                                    </div>
                                </div>

                                <div>
                                    <div className="text-xs uppercase tracking-wide text-zinc-500">
                                        Eltérés
                                    </div>
                                    <div className="mt-1 text-xl font-semibold text-zinc-100">
                                        {period.training_load_proxies.comparison.difference_percent !== null
                                            ? `${
                                                period.training_load_proxies.comparison.difference_percent > 0
                                                    ? "+"
                                                    : ""
                                            }${period.training_load_proxies.comparison.difference_percent}%`
                                            : "—"}
                                    </div>
                                    <div className="text-xs text-zinc-500">
                                        7 vs. 42 nap
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {period.description && (
                        <p className="mt-4 max-w-3xl leading-7 text-zinc-400">
                            {period.description}
                        </p>
                    )}
                </header>

                <div className="space-y-12 py-10">

                    <section>
                        <h2 className="mb-5 text-2xl font-semibold">
                            Célok
                        </h2>

                        <div className="grid gap-3 sm:grid-cols-3">
                            {period.objectives.map(
                                (objective) => (
                                    <Metric
                                        key={objective.id}
                                        label={objectiveLabel(
                                            objective.objective_type
                                        )}
                                        value={`${Math.round(
                                            objective.weight * 100
                                        )}%`}
                                    />
                                )
                            )}
                        </div>
                    </section>

                    <section>
                        <h2 className="mb-5 text-2xl font-semibold">
                            Ciklus összegzés
                        </h2>

                        <div className="grid gap-4 lg:grid-cols-3">
                            <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
                                <div className="text-sm font-semibold">
                                    Terv
                                </div>

                                <div className="mt-4 grid gap-3">
                                    <Metric
                                        label="Edzések"
                                        value={
                                            period.summary.planned
                                                .workout_count
                                        }
                                    />

                                    <Metric
                                        label="Ismert tervezett idő"
                                        value={formatDuration(
                                            period.summary.planned
                                                .duration_sec
                                        )}
                                        hint={`${
                                            period.summary.planned
                                                .duration_known_count
                                        } / ${
                                            period.summary.planned
                                                .workout_count
                                        } edzésnél ismert`}
                                    />

                                    <div className="rounded-xl bg-zinc-800/60 p-4">
                                        <div className="mb-3 text-xs uppercase tracking-wide text-zinc-500">
                                            Tervezett táv
                                        </div>

                                        <DistanceBySport
                                            distances={
                                                period.summary.planned
                                                    .distance_by_sport
                                            }
                                        />

                                        <div className="mt-3 text-xs text-zinc-500">
                                            {
                                                period.summary.planned
                                                    .distance_known_count
                                            }{" "}
                                            /{" "}
                                            {
                                                period.summary.planned
                                                    .workout_count
                                            }{" "}
                                            edzésnél ismert
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
                                <div className="text-sm font-semibold">
                                    Végrehajtás
                                </div>

                                <div className="mt-4 grid gap-3">
                                    <Metric
                                        label="Teljesített tervek"
                                        value={`${
                                            period.summary.execution
                                                .completed_plan_count
                                        } / ${
                                            period.summary.execution
                                                .planned_workout_count
                                        }`}
                                    />

                                    <Metric
                                        label="Teljesítési arány"
                                        value={
                                            period.summary.execution
                                                .completion_rate_percent !==
                                            null
                                                ? `${
                                                    period.summary
                                                        .execution
                                                        .completion_rate_percent
                                                }%`
                                                : "—"
                                        }
                                    />

                                    <Metric
                                        label="Kézzel megerősített"
                                        value={
                                            period.summary.execution
                                                .manual_confirmed_link_count
                                        }
                                    />
                                </div>
                            </div>

                            <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
                                <div className="text-sm font-semibold">
                                    Tényleges terhelés
                                </div>

                                <div className="mt-4 grid gap-3">
                                    <Metric
                                        label="Sessionök a ciklusban"
                                        value={
                                            period.summary
                                                .actual_in_period
                                                .session_count
                                        }
                                    />

                                    <Metric
                                        label="Összes idő"
                                        value={formatDuration(
                                            period.summary
                                                .actual_in_period
                                                .duration_sec
                                        )}
                                    />

                                    <Metric
                                        label="Cardio load"
                                        value={
                                            period.summary
                                                .actual_in_period
                                                .cardio_load
                                        }
                                        hint={`${
                                            period.summary
                                                .actual_in_period
                                                .cardio_load_session_count
                                        } session alapján`}
                                    />

                                    <div className="rounded-xl bg-zinc-800/60 p-4">
                                        <div className="mb-3 text-xs uppercase tracking-wide text-zinc-500">
                                            Tényleges táv
                                        </div>

                                        <DistanceBySport
                                            distances={
                                                period.summary
                                                    .actual_in_period
                                                    .distance_by_sport
                                            }
                                        />
                                    </div>
                                </div>
                            </div>
                        </div>
                    </section>

                    <section>
                        <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
                            <div>
                                <h2 className="text-2xl font-semibold">
                                    Ciklusnaptár
                                </h2>

                                <p className="mt-2 text-sm text-zinc-500">
                                    {period.weeks.length} hét ·{" "}
                                    {period.start_date} –{" "}
                                    {period.end_date}
                                </p>
                            </div>
                        </div>

                        <div className="space-y-6">
                            {period.weeks.map(
                                (week, weekIndex) => {
                                    const calendarWeek =
                                        isoWeekNumber(
                                            week.week_start
                                        );

                                    const days = Array.from(
                                        {length: 7},
                                        (_, dayIndex) => {
                                            const date = isoDate(
                                                addDays(
                                                    dateFromIsoDate(
                                                        week.week_start
                                                    ),
                                                    dayIndex
                                                )
                                            );

                                            const workouts =
                                                period.workouts.filter(
                                                    (workout) =>
                                                        workout.date === date
                                                );

                                            return {
                                                date,
                                                workouts,
                                            };
                                        }
                                    );

                                    return (
                                        <article
                                            key={week.week_start}
                                            className="overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900"
                                        >
                                            <header
                                                className="flex flex-wrap items-center justify-between gap-5 border-b border-zinc-800 px-5 py-4">
                                                <div>
                                                    <div className="text-xs uppercase tracking-wide text-zinc-500">
                                                        Ciklus {weekIndex + 1}. hete
                                                    </div>

                                                    <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                                                        <h3 className="text-xl font-semibold">
                                                            {monthLabel(
                                                                week.week_start,
                                                                week.week_end
                                                            )}
                                                        </h3>

                                                        <span className="text-sm text-zinc-500">
                                                            {calendarWeek}. naptári hét
                                                        </span>

                                                        <span className="text-sm text-zinc-600">
                                                            {week.week_start}
                                                            {" – "}
                                                            {week.week_end}
                                                        </span>
                                                    </div>
                                                </div>
                                            </header>

                                            <div className="overflow-x-auto">
                                                <div
                                                    className="grid w-full min-w-[1860px] grid-cols-[repeat(7,minmax(220px,1fr))_360px]">
                                                    {days.map(
                                                        ({date, workouts}) => {
                                                            const outsidePeriod =
                                                                date <
                                                                period.start_date ||
                                                                date >
                                                                period.end_date;

                                                            const isToday =
                                                                date ===
                                                                period.training_load_proxies?.as_of_date;

                                                            return (
                                                                <div
                                                                    key={date}
                                                                    className={`min-h-44 border-r border-zinc-800 p-3 ${
                                                                        outsidePeriod
                                                                            ? "bg-zinc-950/60 text-zinc-600"
                                                                            : isToday
                                                                                ? "bg-zinc-800/70 ring-1 ring-inset ring-zinc-500"
                                                                                : "bg-zinc-900"
                                                                    }`}
                                                                >
                                                                    <div
                                                                        className="mb-4 flex items-baseline justify-between">
                                                                        <span
                                                                            className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                                                                            {dayName(date)}
                                                                        </span>

                                                                        <span className="text-lg font-semibold">
                                                                            {dayNumber(date)}
                                                                        </span>
                                                                    </div>

                                                                    <div className="space-y-2">
                                                                        {workouts.map(
                                                                            (workout) => (
                                                                                <Link
                                                                                    key={workout.id}
                                                                                    href={`/workouts/${workout.id}`}
                                                                                    className="block rounded-lg border border-zinc-700 bg-zinc-800/70 p-3 transition hover:border-zinc-500 hover:bg-zinc-800"
                                                                                >
                                                                                    <div
                                                                                        className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                                                                                        {sportLabel(workout.sport)}
                                                                                    </div>

                                                                                    <div
                                                                                        className="mt-1 text-sm font-medium leading-5">
                                                                                        {workout.title}
                                                                                    </div>

                                                                                    {(workout.duration_sec !== null ||
                                                                                        workout.distance_m !== null) && (
                                                                                        <div
                                                                                            className="mt-2 text-xs text-zinc-400">
                                                                                            {workout.duration_sec !== null &&
                                                                                                formatDuration(
                                                                                                    workout.duration_sec
                                                                                                )}

                                                                                            {workout.duration_sec !== null &&
                                                                                                workout.distance_m !== null &&
                                                                                                " · "}

                                                                                            {workout.distance_m !== null &&
                                                                                                formatDistance(
                                                                                                    workout.distance_m
                                                                                                )}
                                                                                        </div>
                                                                                    )}

                                                                                    <div
                                                                                        className="mt-3 border-t border-zinc-700/70 pt-3">
                                                                                        {workout.execution.has_actual ? (
                                                                                            <div>
                                                                                                <div
                                                                                                    className="text-xs font-medium text-emerald-400">
                                                                                                    ✓ Teljesítve
                                                                                                </div>

                                                                                                <div
                                                                                                    className="mt-1 text-xs text-zinc-300">
                                                                                                    {actualSummary(workout)}
                                                                                                </div>

                                                                                                {workout.execution
                                                                                                    .delta_percent !== null && (
                                                                                                    <div
                                                                                                        className="mt-1 text-xs font-medium text-zinc-400">
                                                                                                        {workout.execution
                                                                                                            .delta_percent > 0
                                                                                                            ? "+"
                                                                                                            : ""}
                                                                                                        {
                                                                                                            workout.execution
                                                                                                                .delta_percent
                                                                                                        }
                                                                                                        %
                                                                                                    </div>
                                                                                                )}
                                                                                            </div>
                                                                                        ) : (
                                                                                            <div
                                                                                                className="text-xs text-zinc-500">
                                                                                                Tervezett
                                                                                            </div>
                                                                                        )}
                                                                                    </div>
                                                                                </Link>
                                                                            )
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            );
                                                        }
                                                    )}
                                                    <aside className="bg-zinc-950/30 p-4">
                                                        <div className="text-xs uppercase tracking-wide text-zinc-500">
                                                            Heti összegzés
                                                        </div>

                                                        <div className="mt-4 space-y-3 text-sm">
                                                            <div className="flex justify-between gap-4">
      <span className="text-zinc-500">
        Terv
      </span>
                                                                <span className="font-medium">
        {week.planned.workout_count}
      </span>
                                                            </div>

                                                            <div className="flex justify-between gap-4">
      <span className="text-zinc-500">
        Tény
      </span>
                                                                <span className="font-medium">
        {week.actual.session_count}
      </span>
                                                            </div>

                                                            <div className="flex justify-between gap-4">
      <span className="text-zinc-500">
        Idő
      </span>
                                                                <span className="font-medium">
        {formatDuration(
            week.actual.duration_sec
        )}
      </span>
                                                            </div>

                                                            <div className="border-t border-zinc-800 pt-3">
                                                                <div className="flex justify-between gap-4">
        <span className="text-zinc-500">
          Cardio load
        </span>
                                                                    <span className="font-medium">
          {week.load_trend
              ? week.load_trend.cardio_load
              : week.actual.cardio_load}
        </span>
                                                                </div>

                                                                {loadTrendText(
                                                                    week.load_trend
                                                                ) && (
                                                                    <div className="mt-1 text-xs text-zinc-500">
                                                                        {loadTrendText(
                                                                            week.load_trend
                                                                        )}
                                                                    </div>
                                                                )}
                                                            </div>

                                                            <div className="border-t border-zinc-800 pt-3">
                                                                <div
                                                                    className="mb-2 text-xs uppercase tracking-wide text-zinc-500">
                                                                    Tervezett táv
                                                                </div>

                                                                <DistanceBySport
                                                                    distances={
                                                                        week.planned.distance_by_sport
                                                                    }
                                                                />
                                                            </div>

                                                            <div className="border-t border-zinc-800 pt-3">
                                                                <div
                                                                    className="mb-2 text-xs uppercase tracking-wide text-zinc-500">
                                                                    Tényleges táv
                                                                </div>

                                                                <DistanceBySport
                                                                    distances={
                                                                        week.actual.distance_by_sport
                                                                    }
                                                                />
                                                            </div>

                                                            <div className="border-t border-zinc-800 pt-3">
                                                                <div
                                                                    className="mb-2 text-xs uppercase tracking-wide text-zinc-500">
                                                                    Teljesítés
                                                                </div>

                                                                <div className="font-medium">
                                                                    {week.execution.completed_plan_count}
                                                                    {" / "}
                                                                    {week.execution.planned_workout_count}

                                                                    {week.execution.completion_rate_percent !== null && (
                                                                        <span className="text-zinc-500">
            {" · "}
                                                                            {week.execution.completion_rate_percent}%
          </span>
                                                                    )}
                                                                </div>
                                                            </div>

                                                            {week.summary.notes.length > 0 && (
                                                                <div className="border-t border-zinc-800 pt-3">
                                                                    <div
                                                                        className="mb-2 text-xs uppercase tracking-wide text-zinc-500">
                                                                        Heti jellemzés
                                                                    </div>

                                                                    <ul className="space-y-1.5 text-xs leading-5 text-zinc-400">
                                                                        {week.summary.notes.map(
                                                                            (note, noteIndex) => (
                                                                                <li
                                                                                    key={noteIndex}
                                                                                    className="flex gap-2"
                                                                                >
                                                                                    <span className="text-zinc-600">
                                                                                        ·
                                                                                    </span>
                                                                                    <span>{note}</span>
                                                                                </li>
                                                                            )
                                                                        )}
                                                                    </ul>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </aside>
                                                </div>
                                            </div>
                                        </article>
                                    );
                                }
                            )}
                        </div>
                    </section>
                </div>
            </div>
        </main>
    );
}
