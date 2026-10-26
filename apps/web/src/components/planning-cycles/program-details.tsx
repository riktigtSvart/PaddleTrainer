import Link from "next/link";
import { gateLabels, reasonLabels } from "@/lib/athlete-setup/contracts";
import { capabilityLabels } from "@/lib/planning-goals/labels";
import { ICF_SOURCE } from "@/lib/planning-cycles/contracts";
import { modeLabels, periodLabels } from "@/lib/planning-cycles/contracts";
import type {
  AthleteSnapshot,
  Competition,
  Period,
  Program,
  Registration,
} from "@/lib/planning-cycles/contracts";
import { secondaryClass } from "@/components/planning-goals/fields";

export function Competitions({ value }: { value: Competition[] }) {
  return value.length ? (
    <ul className="space-y-3">
      {value.map((c) => (
        <li
          key={c.key}
          className="rounded-lg border border-zinc-700 p-3 text-sm leading-6"
        >
          <span className="font-semibold">{c.title}</span> ·{" "}
          {c.priority === "main" ? "Főverseny" : "Köztes verseny"}
          {c.status === "cancelled" && " · Lemondott / elmaradt"}
          <br />
          {c.start_date}
          {c.start_date !== c.end_date && ` – ${c.end_date}`} ·{" "}
          {c.precision === "window" ? "Közelítő időablak" : "Pontos versenynap"}
          {c.profile && (
            <div className="mt-3 space-y-1 border-t border-zinc-700 pt-2">
              <p>
                {c.profile.discipline} ·{" "}
                {
                  {
                    sprint: "Sprint",
                    endurance: "Állóképességi",
                    technical: "Technikai",
                    strength: "Erőverseny",
                    mixed: "Összetett",
                    other: "Egyéb",
                  }[c.profile.event_type]
                }
              </p>
              <p>
                Táv:{" "}
                {c.profile.distance_status === "specified"
                  ? `${c.profile.distance_value} ${c.profile.distance_unit}`
                  : c.profile.distance_status === "unknown"
                    ? "még nem ismert"
                    : "nem értelmezhető"}
                {c.profile.expected_duration_minutes &&
                  ` · Várható idő: ${c.profile.expected_duration_minutes} perc`}
              </p>
              {c.profile.course_description && (
                <p>{c.profile.course_description}</p>
              )}
              <p>
                {c.profile.capability_basis === "unassessed"
                  ? "Képességigény: még nincs értékelve."
                  : `Előzetes képességigény: ${c.profile.capability_keys.map((k) => capabilityLabels[k] ?? k).join(", ")}`}
              </p>
              {c.profile.capability_basis === "icf_sprint_v0_1" && (
                <a
                  className="underline"
                  href={ICF_SOURCE}
                  target="_blank"
                  rel="noreferrer"
                >
                  ICF-alapú minőségi alkalmazásjavaslat
                </a>
              )}
            </div>
          )}
        </li>
      ))}
    </ul>
  ) : (
    <p className="text-sm text-zinc-400">
      Ehhez a programhoz nincs verseny megadva.
    </p>
  );
}
export function ProgramSummary({
  value,
  labels,
}: {
  value: Program;
  labels: Record<string, string>;
}) {
  return (
    <div className="space-y-4 text-sm leading-6">
      <p>
        <strong>{value.title}</strong> · {modeLabels[value.mode]} ·{" "}
        {value.sport}
        <br />
        {value.start_date} –{" "}
        {value.end_date ??
          "folyamatos program; az aktuális makrociklus végén felülvizsgáljuk"}
      </p>
      <ul className="space-y-2">
        {value.goals.map((g) => (
          <li key={g.key}>
            <strong>{labels[g.key] ?? g.key}:</strong>{" "}
            {g.body_mass
              ? g.key === "weight_maintenance" && g.details
                ? `Megtartandó testsúly: ${g.body_mass.current_kg} kg`
                : `Jelenlegi testsúly: ${g.body_mass.current_kg} kg · céltestsúly: ${g.body_mass.target_kg} kg`
              : g.target_description}
            {g.details?.event_keys.length ? (
              <p className="text-zinc-300">
                Célversenyek:{" "}
                {g.details.event_keys
                  .map((key) => {
                    const event = value.competitions.find((c) => c.key === key);
                    return `${event?.title ?? key}${event?.status === "cancelled" ? " (lemondott; célfelülvizsgálat szükséges)" : ""}`;
                  })
                  .join(", ")}
              </p>
            ) : null}
            {g.details?.notes && (
              <p className="text-zinc-300">{g.details.notes}</p>
            )}
          </li>
        ))}
      </ul>
      {value.planning_basis && (
        <p className="text-zinc-400">
          A mezociklusok dátumai tervezett iránymutatók. A pontos
          főversenynapokhoz igazítva, felülvizsgálat után módosíthatók.
        </p>
      )}
      <Competitions value={value.competitions} />
    </div>
  );
}
export function Structure({
  periods,
  saved = false,
  cycleId,
}: {
  periods: Period[];
  saved?: boolean;
  cycleId?: string;
}) {
  return (
    <div className="space-y-4">
      {periods
        .filter((p) => p.period_type !== "MESOCYCLE")
        .map((p) => (
          <div key={p.id} className="rounded-xl border border-zinc-700 p-4">
            <p className="font-medium">
              {periodLabels[p.period_type] ?? p.period_type} · {p.title}
            </p>
            <p className="mt-1 text-sm text-zinc-300">
              {p.start_date} – {p.end_date}
            </p>
            {saved && p.period_type === "MACROCYCLE" && (
              <Link
                className={`${secondaryClass} mt-3 inline-block`}
                href={`/planning-goals?period=${p.id}${cycleId ? `&cycle=${encodeURIComponent(cycleId)}` : ""}`}
              >
                Képességcélok felosztása ehhez a makrociklushoz
              </Link>
            )}
            {!!periods.filter(
              (n) => n.parent_id === p.id && n.period_type === "MESOCYCLE",
            ).length && (
              <details className="mt-4">
                <summary className="cursor-pointer text-sm text-teal-200">
                  Hozzá tartozó mezociklusok
                </summary>
                <ul className="mt-3 space-y-3">
                  {periods
                    .filter(
                      (n) =>
                        n.parent_id === p.id && n.period_type === "MESOCYCLE",
                    )
                    .map((n) => (
                      <li
                        key={n.id}
                        className="border-l-2 border-zinc-600 pl-3 text-sm leading-6"
                      >
                        {n.title} · tervezett időkeret: {n.start_date} –{" "}
                        {n.end_date}
                        {saved && (
                          <>
                            <br />
                            <Link
                              className="text-teal-200 underline underline-offset-4"
                              href={`/planning-goals?period=${n.id}${cycleId ? `&cycle=${encodeURIComponent(cycleId)}` : ""}`}
                            >
                              Mérési protokollok ehhez a mezociklushoz
                            </Link>
                          </>
                        )}
                      </li>
                    ))}
                </ul>
              </details>
            )}
          </div>
        ))}
    </div>
  );
}
export function Provenance({ value }: { value: Registration }) {
  return (
    <details className="text-xs leading-6 text-zinc-400">
      <summary className="cursor-pointer">
        Rögzített változat és hivatkozások
      </summary>
      <p className="mt-2 break-all">
        Azonosító: {value.artifact_id}
        <br />
        Tartalomlenyomat: {value.content_hash}
        <br />
        Időzóna: {value.timezone_name}
      </p>
      {value.calendar_snapshot && (
        <p>
          Olimpiai naptár: {value.calendar_snapshot.version} ·{" "}
          <a
            className="underline"
            href={value.calendar_snapshot.source}
            target="_blank"
            rel="noreferrer"
          >
            Hivatalos forrás
          </a>
        </p>
      )}
      <p>
        A szerkezet a létrehozáskor rögzített állapotot mutatja. A későbbi
        versenypontosítások külön változatokban láthatók.
      </p>
    </details>
  );
}

export function ContextSnapshot({
  value,
}: {
  value: AthleteSnapshot | undefined;
}) {
  if (!value) return null;
  const review = value.review,
    calendar = value.first_mesocycle_availability;
  return (
    <section className="space-y-3 rounded-xl border border-amber-500/40 p-4 text-sm leading-6">
      <h3 className="font-semibold">A tervhez rögzített sportolói keretek</h3>
      <p>
        {gateLabels[review.global_entry_gate] ?? review.global_entry_gate} ·
        életkor: {review.age_years ?? "ismeretlen"}
      </p>
      {!!review.reasons.length && (
        <ul className="list-disc pl-5">
          {review.reasons.map((r) => (
            <li key={r}>{reasonLabels[r] ?? r}</li>
          ))}
        </ul>
      )}
      {review.constraints.map((c) => (
        <div key={c.key}>
          <p>
            {c.restricted_activities.length
              ? `Korlátozott tevékenységek: ${c.restricted_activities.join(", ")}`
              : ""}
          </p>
          {c.adaptations && <p>Szükséges alkalmazkodás: {c.adaptations}</p>}
          {c.professional_guidance && (
            <p>Megadott szakmai keret: {c.professional_guidance}</p>
          )}
        </div>
      ))}
      <p>
        Az első mezociklusban {calendar.available_days} naphoz van
        edzéslehetőség megadva.{" "}
        {calendar.missing_days === null
          ? "Nincs kitöltött naptár."
          : `Még nincs megadva: ${calendar.missing_days.length} nap.`}
      </p>
      <p>
        Kézi megfigyelések: {value.manual_observation_count} · Átvett órás /
        tárolt megfigyelések: {value.imported_observation_count}.
      </p>
      {review.weight_change_requires_review && (
        <p>
          Testsúlyváltoztatási cél előtt a személyes keretek felülvizsgálata
          szükséges.
        </p>
      )}
      <p className="text-zinc-400">
        A felmérés és a naptár ezen változatát megőrizzük a terv mellett. A
        későbbi módosítások külön változatként jelennek meg.
      </p>
      <Link className="underline" href="/athlete-setup">
        Aktuális felmérés és naptár
      </Link>
    </section>
  );
}
