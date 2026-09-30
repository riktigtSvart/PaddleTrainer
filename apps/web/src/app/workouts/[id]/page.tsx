import Link from "next/link";
import { notFound } from "next/navigation";

type WorkoutBlock = {
  id: string;
  position: number;
  block_type:
    | "WORK"
    | "RECOVERY"
    | "WARMUP"
    | "COOLDOWN"
    | "REPEAT";
  name: string | null;
  duration_sec: number | null;
  distance_m: number | null;
  intensity_type: string | null;
  intensity_min: number | null;
  intensity_max: number | null;
  repeat_count: number | null;
  parent_block_id: string | null;
};

type PlannedWorkout = {
  id: string;
  date: string;
  planned_start_time: string | null;
  sport: string;
  title: string;
  description: string | null;
  duration_sec: number | null;
  distance_m: number | null;
  intensity_type: string | null;
  status: string;
  source: string;
  polar_target_id: string | null;
  blocks: WorkoutBlock[];
};

type ActualSession = {
  id: string;
  external_provider: string;
  external_id: string;
  sport: string;
  name: string | null;
  started_at: string;
  ended_at: string | null;
  duration_sec: number | null;
  distance_m: number | null;
  calories: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_speed: number | null;
  max_speed: number | null;
  cardio_load: number | null;
  perceived_load: number | null;
  rpe: number | null;
};

type Comparison = {
  basis:
    | "DISTANCE"
    | "DURATION"
    | "MIXED"
    | "NONE";
  duration_delta_sec: number | null;
  duration_delta_percent: number | null;
  distance_delta_m: number | null;
  distance_delta_percent: number | null;
};

type Completion = {
  status: string;
  basis:
    | "DISTANCE"
    | "DURATION"
    | "MIXED"
    | "NONE";
  unit: "m" | "sec" | null;
  planned: number | null;
  actual: number | null;
  delta: number | null;
  delta_percent: number | null;
  has_actual: boolean;
};

type CoachWorkout = {
  planned: PlannedWorkout;
  actual: ActualSession | null;
  comparison: Comparison;
  completion: Completion;
  actual_session_count: number;
};

async function getWorkout(
  id: string
): Promise<CoachWorkout | null> {
  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL ??
    "http://127.0.0.1:8000";

  const response = await fetch(
    `${apiUrl}/api/v1/coach/workouts/${id}`,
    {
      cache: "no-store",
    }
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(
      `Workout API error: ${response.status}`
    );
  }

  return response.json();
}

function formatDistance(
  meters: number | null
): string {
  if (meters === null) {
    return "—";
  }

  return `${(meters / 1000).toFixed(2)} km`;
}

function formatDuration(
  seconds: number | null
): string {
  if (seconds === null) {
    return "—";
  }

  const hours = Math.floor(
    seconds / 3600
  );

  const minutes = Math.floor(
    (seconds % 3600) / 60
  );

  const secs = seconds % 60;

  if (hours > 0) {
    return `${hours} óra ${minutes} perc`;
  }

  if (secs === 0) {
    return `${minutes} perc`;
  }

  return `${minutes}:${secs
    .toString()
    .padStart(2, "0")}`;
}

function formatBlockGoal(
  block: WorkoutBlock
): string | null {
  if (block.distance_m !== null) {
    if (block.distance_m >= 1000) {
      return `${(
        block.distance_m / 1000
      ).toFixed(
        block.distance_m % 1000 === 0
          ? 0
          : 1
      )} km`;
    }

    return `${block.distance_m} m`;
  }

  if (block.duration_sec !== null) {
    return formatDuration(
      block.duration_sec
    );
  }

  return null;
}

function formatIntensity(
  block: WorkoutBlock
): string | null {
  if (
    !block.intensity_type ||
    block.intensity_type === "NONE"
  ) {
    return null;
  }

  if (
    block.intensity_min === null ||
    block.intensity_max === null
  ) {
    return block.intensity_type;
  }

  const prefix =
    block.intensity_type ===
    "HEART_RATE_ZONES"
      ? "HR"
      : block.intensity_type ===
          "SPEED_ZONES"
        ? "Speed"
        : block.intensity_type;

  if (
    block.intensity_min ===
    block.intensity_max
  ) {
    return `${prefix} Z${block.intensity_min}`;
  }

  return `${prefix} Z${block.intensity_min}-${block.intensity_max}`;
}

function WorkoutPlan({
  blocks,
}: {
  blocks: WorkoutBlock[];
}) {
  if (blocks.length === 0) {
    return (
      <p className="text-zinc-500">
        Nincs részletes blokkstruktúra.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {blocks.map((block) => {
        const goal =
          formatBlockGoal(block);

        const intensity =
          formatIntensity(block);

        const isChild =
          block.parent_block_id !== null;

        if (
          block.block_type === "REPEAT"
        ) {
          return (
            <div
              key={block.id}
              className="mt-5 rounded-xl border border-zinc-800 px-4 py-3"
            >
              <span className="text-sm font-semibold">
                Ismétlés ×
                {block.repeat_count ?? 1}
              </span>
            </div>
          );
        }

        return (
          <div
            key={block.id}
            className={`flex items-center justify-between gap-6 rounded-xl px-4 py-3 ${
              isChild
                ? "ml-6 bg-zinc-800/40"
                : "bg-zinc-800"
            }`}
          >
            <div>
              <div className="font-medium">
                {block.name ||
                  block.block_type}
              </div>

              <div className="mt-1 text-xs text-zinc-500">
                {block.block_type}
              </div>
            </div>

            <div className="text-right">
              {goal && (
                <div className="text-sm">
                  {goal}
                </div>
              )}

              {intensity && (
                <div className="mt-1 text-xs text-zinc-400">
                  {intensity}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-xl bg-zinc-800/60 p-4">
      <div className="text-xs uppercase tracking-wide text-zinc-500">
        {label}
      </div>

      <div className="mt-2 text-lg font-semibold">
        {value}
      </div>
    </div>
  );
}

export default async function WorkoutDetailPage({
  params,
}: {
  params: Promise<{
    id: string;
  }>;
}) {
  const { id } = await params;

  const workout =
    await getWorkout(id);

  if (!workout) {
    notFound();
  }

  const planned =
    workout.planned;

  const actual =
    workout.actual;

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-100">
      <div className="mx-auto max-w-4xl">
        <Link
          href="/"
          className="text-sm text-zinc-400 transition hover:text-zinc-100"
        >
          ← Coach
        </Link>

        <header className="mt-8 border-b border-zinc-800 pb-8">
          <div className="flex flex-wrap items-center gap-2 text-sm uppercase tracking-wide text-zinc-500">
            <span>{planned.sport}</span>
            <span>·</span>
            <span>{planned.date}</span>
            <span>·</span>
            <span>{planned.status}</span>
          </div>

          <h1 className="mt-3 text-4xl font-semibold tracking-tight">
            {planned.title}
          </h1>

          {planned.description && (
            <p className="mt-4 text-zinc-400">
              {planned.description}
            </p>
          )}
        </header>

        <div className="space-y-12 py-10">
          <section>
            <h2 className="mb-5 text-2xl font-semibold">
              Terv
            </h2>

            <div className="mb-6 grid gap-3 sm:grid-cols-3">
              <Metric
                label="Tervezett táv"
                value={formatDistance(
                  planned.distance_m
                )}
              />

              <Metric
                label="Tervezett idő"
                value={formatDuration(
                  planned.duration_sec
                )}
              />

              <Metric
                label="Intenzitás"
                value={
                  planned.intensity_type ??
                  "—"
                }
              />
            </div>

            <WorkoutPlan
              blocks={planned.blocks}
            />
          </section>

          <section>
  <h2 className="mb-5 text-2xl font-semibold">
    Teljesítés
  </h2>

  {actual === null ? (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5 text-zinc-500">
      Ehhez az edzéshez még nincs teljesített session.
    </div>
  ) : (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Metric
          label="Táv"
          value={formatDistance(
            actual.distance_m
          )}
        />

        <Metric
          label="Idő"
          value={formatDuration(
            actual.duration_sec
          )}
        />

        <Metric
          label="Átlagpulzus"
          value={
            actual.avg_hr ?? "—"
          }
        />

        <Metric
          label="Max pulzus"
          value={
            actual.max_hr ?? "—"
          }
        />

        <Metric
          label="Kalória"
          value={
            actual.calories ?? "—"
          }
        />

        <Metric
          label="Cardio load"
          value={
            actual.cardio_load !== null
              ? actual.cardio_load.toFixed(1)
              : "—"
          }
        />
      </div>

      <Link
        href={`/sessions/${actual.id}`}
        className="inline-flex rounded-xl border border-zinc-700 px-4 py-3 text-sm font-medium text-zinc-300 transition hover:border-zinc-500 hover:text-zinc-100"
      >
        Teljes edzés megnyitása →
      </Link>
    </div>
  )}
</section>

          <section>
            <h2 className="mb-5 text-2xl font-semibold">
              Terv vs tény
            </h2>

            <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
              {!workout.completion
                  .has_actual ? (
                <p className="text-zinc-500">
                  Az összehasonlítás a
                  teljesítés után jelenik meg.
                </p>
              ) : workout.completion
                  .basis === "MIXED" ? (
                <div>
                  <div className="font-medium">
                    Összetett edzésterv
                  </div>

                  <p className="mt-2 text-sm leading-6 text-zinc-400">
                    A terv idő- és
                    távolságalapú blokkokat is
                    tartalmaz, ezért a teljes
                    sessionre nem számolunk
                    félrevezető egyetlen
                    százalékos eltérést.
                  </p>
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-3">
                  <Metric
                    label="Terv"
                    value={
                      workout.completion
                        .basis ===
                      "DISTANCE"
                        ? formatDistance(
                            workout
                              .completion
                              .planned
                          )
                        : formatDuration(
                            workout
                              .completion
                              .planned
                          )
                    }
                  />

                  <Metric
                    label="Tény"
                    value={
                      workout.completion
                        .basis ===
                      "DISTANCE"
                        ? formatDistance(
                            workout
                              .completion
                              .actual
                          )
                        : formatDuration(
                            workout
                              .completion
                              .actual
                          )
                    }
                  />

                  <Metric
                    label="Eltérés"
                    value={
                      workout.completion
                        .delta_percent !==
                      null
                        ? `${
                            workout
                              .completion
                              .delta_percent >
                            0
                              ? "+"
                              : ""
                          }${
                            workout
                              .completion
                              .delta_percent
                          }%`
                        : "—"
                    }
                  />
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}