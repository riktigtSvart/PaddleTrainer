import Link from "next/link";
import { notFound } from "next/navigation";

type PlannedWorkoutSummary = {
  id: string;
  date: string;
  sport: string;
  title: string;
  status: string;
  duration_sec: number | null;
  distance_m: number | null;
  intensity_type: string | null;
};

type WorkoutSession = {
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

  avg_cadence: number | null;
  max_cadence: number | null;

  avg_power: number | null;
  max_power: number | null;

  cardio_load: number | null;
  perceived_load: number | null;

  planned_workout_id: string | null;
  planned_workout: PlannedWorkoutSummary | null;
};

async function getSession(
  id: string
): Promise<WorkoutSession | null> {
  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL ??
    "http://127.0.0.1:8000";

  const response = await fetch(
    `${apiUrl}/api/v1/sessions/${id}`,
    {
      cache: "no-store",
    }
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(
      `Session API error: ${response.status}`
    );
  }

  return response.json();
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

function formatDistance(
  meters: number | null
): string {
  if (meters === null) {
    return "—";
  }

  return `${(
    meters / 1000
  ).toFixed(2)} km`;
}

function formatSpeed(
  speed: number | null
): string {
  if (speed === null) {
    return "—";
  }

  return `${speed.toFixed(2)} km/h`;
}

function formatDate(
  value: string
): string {
  return new Date(
    value
  ).toLocaleDateString(
    "hu-HU",
    {
      timeZone: "Europe/Budapest",
    }
  );
}

function formatTime(
  value: string
): string {
  return new Date(
    value
  ).toLocaleTimeString(
    "hu-HU",
    {
      timeZone: "Europe/Budapest",
      hour: "2-digit",
      minute: "2-digit",
    }
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

export default async function SessionDetailPage({
  params,
}: {
  params: Promise<{
    id: string;
  }>;
}) {
  const { id } =
    await params;

  const session =
    await getSession(id);

  if (!session) {
    notFound();
  }

  const title =
    session.name?.trim() ||
    `${session.sport} edzés`;

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
            <span>
              {session.sport}
            </span>

            <span>·</span>

            <span>
              {formatDate(
                session.started_at
              )}
            </span>

            <span>·</span>

            <span>
              {formatTime(
                session.started_at
              )}
            </span>
          </div>

          <h1 className="mt-3 text-4xl font-semibold tracking-tight">
            {title}
          </h1>
        </header>

        <div className="space-y-12 py-10">
          <section>
            <h2 className="mb-5 text-2xl font-semibold">
              Edzés
            </h2>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Metric
                label="Táv"
                value={formatDistance(
                  session.distance_m
                )}
              />

              <Metric
                label="Idő"
                value={formatDuration(
                  session.duration_sec
                )}
              />

              <Metric
                label="Kalória"
                value={
                  session.calories ??
                  "—"
                }
              />

              <Metric
                label="Átlagpulzus"
                value={
                  session.avg_hr ??
                  "—"
                }
              />

              <Metric
                label="Max pulzus"
                value={
                  session.max_hr ??
                  "—"
                }
              />

              <Metric
                label="Cardio load"
                value={
                  session.cardio_load !==
                  null
                    ? session.cardio_load.toFixed(
                        1
                      )
                    : "—"
                }
              />
            </div>
          </section>

          <section>
            <h2 className="mb-5 text-2xl font-semibold">
              Tempó és teljesítmény
            </h2>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Metric
                label="Átlagsebesség"
                value={formatSpeed(
                  session.avg_speed
                )}
              />

              <Metric
                label="Max sebesség"
                value={formatSpeed(
                  session.max_speed
                )}
              />

              <Metric
                label="Átlag cadence"
                value={
                  session.avg_cadence ??
                  "—"
                }
              />

              <Metric
                label="Max cadence"
                value={
                  session.max_cadence ??
                  "—"
                }
              />

              <Metric
                label="Átlag power"
                value={
                  session.avg_power !==
                  null
                    ? `${session.avg_power} W`
                    : "—"
                }
              />

              <Metric
                label="Max power"
                value={
                  session.max_power !==
                  null
                    ? `${session.max_power} W`
                    : "—"
                }
              />
            </div>
          </section>

          <section>
            <h2 className="mb-5 text-2xl font-semibold">
              Terhelés
            </h2>

            <div className="grid gap-3 sm:grid-cols-2">
              <Metric
                label="Cardio load"
                value={
                  session.cardio_load !==
                  null
                    ? session.cardio_load.toFixed(
                        1
                      )
                    : "—"
                }
              />

              <Metric
                label="Perceived load"
                value={
                  session.perceived_load ??
                  "—"
                }
              />
            </div>
          </section>

          {session.planned_workout !== null ? (
  <section>
    <h2 className="mb-5 text-2xl font-semibold">
      Kapcsolódó edzésterv
    </h2>

    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
      <div className="flex flex-wrap items-center gap-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
        <span>
          {session.planned_workout.sport}
        </span>

        <span>·</span>

        <span>
          {session.planned_workout.date}
        </span>

        <span>·</span>

        <span>
          {session.planned_workout.status}
        </span>
      </div>

      <h3 className="mt-3 text-xl font-semibold">
        {session.planned_workout.title}
      </h3>

      <Link
        href={`/workouts/${session.planned_workout.id}`}
        className="mt-5 inline-flex rounded-xl border border-zinc-700 px-4 py-3 text-sm font-medium text-zinc-300 transition hover:border-zinc-500 hover:text-zinc-100"
      >
        Terv megnyitása →
      </Link>
    </div>
  </section>
) : (
  <section>
    <h2 className="mb-5 text-2xl font-semibold">
      Edzésterv
    </h2>

    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5 text-zinc-400">
      Ez az edzés spontán teljesítés volt, ezért nem tartozik hozzá előzetes edzésterv.
    </div>
  </section>
)}

          <section>
            <h2 className="mb-5 text-2xl font-semibold">
              Forrás
            </h2>

            <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
              <div className="text-sm text-zinc-400">
                {session.external_provider}
              </div>

              <div className="mt-2 break-all text-xs text-zinc-600">
                {session.external_id}
              </div>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}