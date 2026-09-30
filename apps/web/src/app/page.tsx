import Link from "next/link";

type Completion = {
  status: string;
  basis: "DISTANCE" | "DURATION" | "MIXED" | "NONE";
  unit: "m" | "sec" | null;
  planned: number | null;
  actual: number | null;
  delta: number | null;
  delta_percent: number | null;
  has_actual: boolean;
};

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
  sport: string;
  title: string;
  status: string;
  intensity_type: string | null;
  blocks: WorkoutBlock[];
};

type ActualSession = {
  id: string;
  started_at: string;
  ended_at: string | null;
  duration_sec: number | null;
  distance_m: number | null;
};

type CoachWorkout = {
  planned: PlannedWorkout;
  actual: ActualSession | null;
  completion: Completion;
};

type WorkoutSession = {
  id: string;
  sport: string;
  name: string | null;
  started_at: string;
  ended_at: string | null;
  duration_sec: number | null;
  distance_m: number | null;
  calories: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  cardio_load: number | null;
};

async function getWorkouts(): Promise<CoachWorkout[]> {
  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL ??
    "http://127.0.0.1:8000";

  const response = await fetch(
    `${apiUrl}/api/v1/coach/workouts`,
    {
      cache: "no-store",
    }
  );

  if (!response.ok) {
    throw new Error(
      `Coach API error: ${response.status}`
    );
  }

  return response.json();
}

async function getSessions(): Promise<WorkoutSession[]> {
  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL ??
    "http://127.0.0.1:8000";

  const response = await fetch(
    `${apiUrl}/api/v1/sessions`,
    {
      cache: "no-store",
    }
  );

  if (!response.ok) {
    throw new Error(
      `Sessions API error: ${response.status}`
    );
  }

  return response.json();
}

function formatCompletion(
  completion: Completion
): string {
  if (!completion.has_actual) {
    return "Még nincs teljesítve";
  }

  if (
    completion.basis === "DISTANCE" &&
    completion.actual !== null
  ) {
    return `${(
      completion.actual / 1000
    ).toFixed(2)} km`;
  }

  if (
    completion.basis === "DURATION" &&
    completion.actual !== null
  ) {
    const minutes = Math.round(
      completion.actual / 60
    );

    return `${minutes} perc`;
  }

  return "Teljesítve";
}

function formatBlockGoal(
  block: WorkoutBlock
): string | null {
  if (block.distance_m !== null) {
    if (block.distance_m >= 1000) {
      return `${(
        block.distance_m / 1000
      ).toFixed(
        block.distance_m % 1000 === 0 ? 0 : 1
      )} km`;
    }

    return `${block.distance_m} m`;
  }

  if (block.duration_sec !== null) {
    const minutes = Math.floor(
      block.duration_sec / 60
    );

    const seconds =
      block.duration_sec % 60;

    if (seconds === 0) {
      return `${minutes} perc`;
    }

    return `${minutes}:${seconds
      .toString()
      .padStart(2, "0")}`;
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
    block.intensity_type === "HEART_RATE_ZONES"
      ? "HR"
      : block.intensity_type === "SPEED_ZONES"
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

function formatDuration(
  seconds: number | null
): string | null {
  if (seconds === null) {
    return null;
  }

  const minutes = Math.round(seconds / 60);

  return `${minutes} perc`;
}

function formatDistance(
  meters: number | null
): string | null {
  if (meters === null) {
    return null;
  }

  return `${(meters / 1000).toFixed(2)} km`;
}

function localDate(
  value: string
): string {
  return new Date(value).toLocaleDateString(
    "en-CA",
    {
      timeZone: "Europe/Budapest",
    }
  );
}

function WorkoutPlan({
  blocks,
}: {
  blocks: WorkoutBlock[];
}) {
  if (blocks.length === 0) {
    return null;
  }

  return (
    <div className="mt-5 border-t border-zinc-800 pt-4">
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
                className="mt-3 text-sm font-semibold text-zinc-300"
              >
                Ismétlés ×
                {block.repeat_count ?? 1}
              </div>
            );
          }

          return (
            <div
              key={block.id}
              className={`flex items-center justify-between gap-4 rounded-lg px-3 py-2 ${
                isChild
                  ? "ml-5 bg-zinc-800/50"
                  : "bg-zinc-800"
              }`}
            >
              <div>
                <div className="text-sm font-medium">
                  {block.name ||
                    block.block_type}
                </div>

                <div className="mt-1 text-xs text-zinc-500">
                  {block.block_type}
                </div>
              </div>

              <div className="text-right text-sm">
                {goal && (
                  <div>{goal}</div>
                )}

                {intensity && (
                  <div className="text-xs text-zinc-400">
                    {intensity}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function WorkoutCard({
  workout,
  showPlan = false,
}: {
  workout: CoachWorkout;
  showPlan?: boolean;
}) {
  return (
    <Link
      href={`/workouts/${workout.planned.id}`}
      className="block"
    >
      <article className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5 transition hover:border-zinc-700 hover:bg-zinc-900/80">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex gap-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
              <span>
                {workout.planned.sport}
              </span>

              <span>·</span>

              <span>
                {workout.planned.date}
              </span>
            </div>

            <h3 className="text-xl font-semibold">
              {workout.planned.title}
            </h3>

            <p className="mt-2 text-sm text-zinc-400">
              {workout.planned.intensity_type ??
                "Nincs intenzitási cél"}
            </p>
          </div>

          <div className="text-right">
            <div className="text-sm font-medium">
              {formatCompletion(
                workout.completion
              )}
            </div>

            {workout.completion
              .delta_percent !== null && (
              <div className="mt-1 text-sm text-zinc-400">
                {workout.completion
                  .delta_percent > 0
                  ? "+"
                  : ""}
                {workout.completion.delta_percent}%
              </div>
            )}
          </div>
        </div>

        {showPlan && (
          <WorkoutPlan
            blocks={workout.planned.blocks}
          />
        )}
      </article>
    </Link>
  );
}

function SessionCard({
  session,
}: {
  session: WorkoutSession;
}) {
  const duration =
    formatDuration(session.duration_sec);

  const distance =
    formatDistance(session.distance_m);

  const title =
    session.name?.trim() ||
    `${session.sport} edzés`;

return (
  <Link
    href={`/sessions/${session.id}`}
    className="block"
  >
    <article className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5 transition hover:border-zinc-700 hover:bg-zinc-900/80">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex gap-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
            <span>{session.sport}</span>

            <span>·</span>

            <span>
              {localDate(
                session.started_at
              )}
            </span>
          </div>

          <h3 className="text-xl font-semibold">
            {title}
          </h3>

          <div className="mt-2 flex flex-wrap gap-3 text-sm text-zinc-400">
            {duration && (
              <span>{duration}</span>
            )}

            {distance && (
              <span>{distance}</span>
            )}

            {session.avg_hr !== null && (
              <span>
                Átlag HR: {session.avg_hr}
              </span>
            )}

            {session.max_hr !== null && (
              <span>
                Max HR: {session.max_hr}
              </span>
            )}
          </div>
        </div>

        {session.cardio_load !== null && (
          <div className="text-right">
            <div className="text-xs text-zinc-500">
              Cardio load
            </div>

            <div className="mt-1 text-sm font-medium">
              {session.cardio_load.toFixed(1)}
            </div>
          </div>
        )}
      </div>
    </article>
  </Link>
  );
}

export default async function Home() {
  const [workouts, sessions] =
    await Promise.all([
      getWorkouts(),
      getSessions(),
    ]);

  const today =
    new Date().toLocaleDateString(
      "en-CA",
      {
        timeZone: "Europe/Budapest",
      }
    );

  const todayWorkouts = workouts.filter(
    (workout) =>
      workout.planned.date === today
  );

  const upcomingWorkouts = workouts
    .filter(
      (workout) =>
        workout.planned.date > today &&
        !workout.completion.has_actual
    )
    .sort((a, b) =>
      a.planned.date.localeCompare(
        b.planned.date
      )
    );

  const recentSessions = [...sessions]
    .sort(
      (a, b) =>
        new Date(
          b.started_at
        ).getTime() -
        new Date(
          a.started_at
        ).getTime()
    )
    .slice(0, 5);

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-100">
      <div className="mx-auto max-w-4xl">
        <header className="mb-10">
          <p className="text-sm font-medium text-zinc-400">
            PaddleTrainer4ME
          </p>

          <h1 className="mt-2 text-4xl font-semibold tracking-tight">
            Coach
          </h1>

          <p className="mt-3 text-zinc-400">
            Tervezett és teljesített edzések
          </p>
        </header>

        <div className="space-y-10">
          <section>
            <h2 className="mb-4 text-2xl font-semibold">
              Mai edzés
            </h2>

            <div className="space-y-4">
              {todayWorkouts.length === 0 ? (
                <p className="text-zinc-500">
                  Ma nincs tervezett edzés.
                </p>
              ) : (
                todayWorkouts.map(
                  (workout) => (
                    <WorkoutCard
                      key={
                        workout.planned.id
                      }
                      workout={workout}
                      showPlan
                    />
                  )
                )
              )}
            </div>
          </section>

          <section>
            <h2 className="mb-4 text-2xl font-semibold">
              Közelgő edzések
            </h2>

            <div className="space-y-4">
              {upcomingWorkouts.length ===
              0 ? (
                <p className="text-zinc-500">
                  Nincs közelgő edzés.
                </p>
              ) : (
                upcomingWorkouts.map(
                  (workout) => (
                    <WorkoutCard
                      key={
                        workout.planned.id
                      }
                      workout={workout}
                    />
                  )
                )
              )}
            </div>
          </section>

          <section>
            <h2 className="mb-4 text-2xl font-semibold">
              Legutóbbi teljesítések
            </h2>

            <div className="space-y-4">
              {recentSessions.length ===
              0 ? (
                <p className="text-zinc-500">
                  Még nincs teljesített edzés.
                </p>
              ) : (
                recentSessions.map(
                  (session) => (
                    <SessionCard
                      key={session.id}
                      session={session}
                    />
                  )
                )
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
