import Link from "next/link";
import { gateLabels, reasonLabels } from "@/lib/athlete-setup/contracts";
import { addDays } from "@/lib/planning-cycles/contracts";
import {
  eventLabels,
  trainingReasons,
} from "@/lib/planning-cycles/training-plan";
import type {
  EntryReview,
  TrainingEvent,
  TrainingReview,
} from "@/lib/planning-cycles/training-plan";
import { secondaryClass } from "@/components/planning-goals/fields";

const profileSteps: Record<string, string> = {
  AGE_UNKNOWN:
    "Alapadatok → Születési dátum: a jelenlegi kezdőtervező az életkori tervezési kerethez ezt használja.",
  TARGET_SPORT_UNKNOWN:
    "Alapadatok → Célsportág / szakág: add meg, melyik sporthoz készüljön a terv.",
  SPORT_HISTORY_UNKNOWN:
    "Sportmúlt: rögzítsd az előzményeket, vagy jelezd, ha még nincs sportmúltad.",
  FUNCTIONAL_CONSTRAINTS_UNKNOWN:
    "Korlátozások: jelezd az ismert korlátozásokat, vagy válaszd, hogy nincs ismert korlátozás.",
  PARTICIPATION_UNKNOWN:
    "Terhelhetőségi keret: válaszd ki a jelenlegi részvételi / terhelési keretedet.",
};

const selectionLabels: Record<string, string> = {
  OPPORTUNITY_NOT_KNOWN: "Az időablak pontos időpontja még nem tisztázott.",
  SPORT_SCOPE_UNKNOWN:
    "Egy korábbi időablaknál még nincs sportági beállítás. Általános lehetőség vagy konkrét sportág választható.",
  EFFORT_CAP_UNKNOWN: "Egy korábbi időablak terhelési kerete nincs tisztázva.",
  SPORT_NOT_ALLOWED:
    "A minta sportága nem szerepel az adott speciális időablakban.",
  EFFORT_NOT_ALLOWED:
    "A minta meghaladná az időablak megadott terhelési korlátját.",
  EQUIPMENT_NOT_DECLARED:
    "A mintához szükséges eszköz nincs megadva. A kajakmintákhoz kajak vagy kajakergométer, az erőmintához kézisúlyzó szükséges.",
  PERSONAL_DURATION_REFERENCE_MISSING:
    "A kéthetes előzményablakban a hosszabb kajakmintához legalább 60 perces rögzített kajakteljesítést, az erőmintához legalább 30 perces, erőedzésként azonosított teljesítést keres a jelenlegi tervező. Ez a könnyű technikai kezdőmintához nem szükséges.",
  OPPORTUNITY_OR_DAILY_MINUTE_CAP: "A minta nem fér a megadott időkeretbe.",
  INTERVAL_TOO_SHORT_OR_START_PASSED:
    "A még rendelkezésre álló időablak rövid, vagy a kezdés már elmúlt.",
  ROLLING_BUDGET_REVIEW:
    "A meglévő és új edzések együtt nem férnek a gördülő hétnapos keretbe, vagy egy meglévő időtartam még ismeretlen.",
  MINIMUM_SPACING:
    "A jelenlegi mintaválasztó által megkövetelt időköz nem tartható a meglévő edzések mellett.",
};

export function PreparationChecklist({ review }: { review: TrainingReview }) {
  const prep = review.result.preparation;
  if (!prep)
    return (
      <p className="text-sm text-zinc-400">
        A korábbi tervváltozat részletes előkészítési listája újraértékeléssel
        kérhető.
      </p>
    );
  const complete = !review.result.blockers.includes("PROFILE_REVIEW_REQUIRED");
  const steps = [
    {
      title: "Sportolói keret",
      ready: complete,
      text: complete
        ? "Mentett, értékelt kiindulópont."
        : "A lenti konkrét profilindokokat még rendezni kell.",
      href: "/athlete-setup#profile",
    },
    {
      title: "Mikor érsz rá?",
      ready: prep.available_day_count > 0,
      text: `${prep.available_day_count} naphoz ismert időlehetőség a kijelölt időszakban.`,
      href: "/athlete-setup#calendar",
    },
    {
      title: "Eszközök",
      ready: prep.equipment_declared,
      text: prep.equipment_declared
        ? "Van mentett eszközlista; a mintához való illeszkedést külön ellenőrizzük."
        : "Add meg az általában vagy az adott időablakban elérhető eszközöket.",
      href: "/athlete-setup#profile",
    },
    {
      title: "Edzések időigénye",
      ready: !prep.unknown_duration_workout_ids.length,
      text: prep.unknown_duration_workout_ids.length
        ? `${prep.unknown_duration_workout_ids.length} meglévő edzéshez még nincs használható időadat vagy becslés.`
        : "Az érintett meglévő edzések időadatai rendelkezésre állnak, vagy becsülhetők.",
      href: "/",
    },
    {
      title: "Célok és mezociklus",
      ready: prep.strategy_ready === true,
      text:
        prep.strategy_ready === true
          ? "A kijelölt napokhoz mezociklus és mentett képességszerepek tartoznak."
          : prep.strategy_ready === false
            ? "A kijelölt időszak minden napjához mezociklus és mentett képességszerepek szükségesek."
            : "A részletes célállapot friss újraértékeléssel ellenőrizhető.",
      href: "/planning-goals",
    },
  ];
  const title = (id: string) =>
    review.plan_snapshots.find((p) => p.workout.id === id)?.workout.title ??
    "Edzés";
  const grouped = new Map<string, string[]>();
  for (const issue of prep.selection_issues)
    for (const code of issue.codes)
      grouped.set(code, [...(grouped.get(code) ?? []), issue.date]);
  return (
    <section
      aria-label="Tervkészítés előrehaladása"
      className="space-y-4 rounded-xl border border-zinc-700 p-4"
    >
      <h4 className="font-semibold">
        Itt járunk az edzéstervedhez vezető úton
      </h4>
      <ol className="grid gap-3 sm:grid-cols-2">
        {steps.map((step, i) => (
          <li key={step.title} className="rounded-lg bg-zinc-500/5 p-3">
            <p className="text-xs text-teal-400">
              {i + 1}. ellenőrzés ·{" "}
              {step.ready ? "Rendelkezésre áll" : "Még szükséges"}
            </p>
            <p className="mt-1 font-medium">{step.title}</p>
            <p className="my-2 text-sm leading-6 text-zinc-400">{step.text}</p>
            <Link className="text-sm underline" href={step.href}>
              {step.ready ? "Megtekintés / módosítás" : "Adatok megadása"} →
            </Link>
          </li>
        ))}
      </ol>
      <div className="rounded-lg bg-teal-500/10 p-3 text-sm leading-6">
        <p>
          Megadott heti rendelkezésre állás:{" "}
          {prep.available_days_per_week ?? "ismeretlen"} nap /{" "}
          {prep.available_minutes_per_week ?? "ismeretlen"} perc.
        </p>
        <p>
          A jelenlegi kezdőminták kiválasztási kerete: legfeljebb{" "}
          {prep.max_sessions_per_7_days} alkalom / {prep.max_minutes_per_7_days}{" "}
          perc gördülő 7 napban, a meglévő edzésekkel együtt. Ez a tervező
          általános kezdőszabálya; az elérhető időből önmagában nem következik
          az előírandó terhelés. A kezdési időpontok között legalább 36 órát
          hagy a mintaválasztó.
        </p>
      </div>
      {!!prep.estimated_duration_workout_ids.length && (
        <div className="text-sm">
          <p className="font-medium">Becsléssel figyelembe vett edzések</p>
          <ul className="mt-2 space-y-2">
            {prep.estimated_duration_workout_ids.map((id) => {
              const e = review.plan_snapshots.find(
                (p) => p.workout.id === id,
              )?.duration_estimate;
              return (
                <li key={id}>
                  <Link
                    className="underline"
                    href={`/workouts/${encodeURIComponent(id)}`}
                  >
                    {title(id)}
                  </Link>
                  {e
                    ? ` · ~${Math.round(Number(e.duration_sec) / 60)} perc; a kerethez ${Math.ceil(Number(e.upper_sec) / 60)} perccel számolunk.`
                    : ""}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {!!prep.unknown_duration_workout_ids.length && (
        <div className="text-sm">
          <p className="font-medium">Időadatot igénylő edzések</p>
          <p className="mt-2 text-zinc-400">
            Ezeknél nincs megadott időtartam vagy használható távbecslés.
            Ellenőrizd a forrásterv időtartamát és strukturált távját, majd
            frissítsd az adatokat.
          </p>
          <ul className="mt-2 space-y-2">
            {prep.unknown_duration_workout_ids.map((id) => (
              <li key={id}>
                <Link
                  className="underline"
                  href={`/workouts/${encodeURIComponent(id)}`}
                >
                  {title(id)} → edzésadatok megtekintése
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      {!!grouped.size && (
        <details>
          <summary className="cursor-pointer font-medium">
            Mely ellenőrzéseknél estek ki az edzésminták?
          </summary>
          <p className="mt-2 text-xs text-zinc-400">
            A felsoroltak különböző mintákat vagy idősávokat érinthetnek.
            Egyetlen megfelelő lehetőség is elegendő lehet egy új javaslathoz.
          </p>
          <ul className="mt-3 space-y-3 text-sm">
            {[...grouped].map(([code, dates]) => (
              <li key={code}>
                <p className="font-medium">{compactDates(dates)}</p>
                <p>{selectionLabels[code] ?? code}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export function ProfileReviewNotice({
  entry,
}: {
  entry: EntryReview | null | undefined;
}) {
  const reasons = [...new Set(entry?.reasons ?? [])];
  return (
    <div
      className="space-y-3 rounded-lg border border-amber-500/40 p-3"
      role="status"
    >
      <p className="font-medium">Mi állítja meg a tervkészítést?</p>
      {entry === null ? (
        <p>Az értékeléshez nem volt elérhető mentett sportolói felmérés.</p>
      ) : entry === undefined ? (
        <p>
          Ez a korábbi értékelés nem tartalmaz részletes profilindokot. Kérj
          újraértékelést.
        </p>
      ) : (
        <>
          <p>
            {gateLabels[entry.global_entry_gate] ??
              "A sportolói keretek felülvizsgálata szükséges"}
          </p>
          {!!reasons.length && (
            <ul className="list-disc space-y-2 pl-5">
              {reasons.map((reason) => (
                <li key={reason}>
                  <span className="font-medium">
                    {reasonLabels[reason] ??
                      "További profilfelülvizsgálat szükséges"}
                  </span>
                  {profileSteps[reason] && (
                    <p className="mt-1 text-zinc-400">{profileSteps[reason]}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
          {entry.participation_status === "PROFESSIONAL_REVIEW_REQUIRED" && (
            <p>
              A rögzített terhelhetőségi keret vagy korlátozás szakmai
              felülvizsgálatot kér.
            </p>
          )}
          {entry.global_entry_gate === "OPEN_WITH_CONSTRAINTS" && (
            <p>
              Alkalmazkodást igénylő korlátozás van rögzítve. A jelenlegi
              mintatervező ehhez még nem választ egyéni terhelést.
            </p>
          )}
          {!!entry.constraints?.length && (
            <ul className="space-y-2">
              {entry.constraints.map((constraint) => (
                <li
                  key={constraint.key}
                  className="border-l-2 border-amber-500/40 pl-3"
                >
                  {constraint.affected_area && (
                    <p>{constraint.affected_area}</p>
                  )}
                  {!!constraint.restricted_activities.length && (
                    <p>
                      Korlátozott tevékenységek:{" "}
                      {constraint.restricted_activities.join(", ")}
                    </p>
                  )}
                  {constraint.adaptations && (
                    <p>Szükséges alkalmazkodás: {constraint.adaptations}</p>
                  )}
                  {constraint.professional_guidance && (
                    <p>
                      Rögzített szakmai keret:{" "}
                      {constraint.professional_guidance}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <Link href="/athlete-setup" className={secondaryClass}>
        Sportolói felmérés megnyitása
      </Link>
      <p className="text-xs text-zinc-400">
        A felmérés mentése után itt kérj újraértékelést. A felsoroltak az ehhez
        az értékeléshez használt adatokra vonatkoznak.
      </p>
    </div>
  );
}

const sportLabels: Record<string, string> = {
  KAYAK: "Kajak",
  RUNNING: "Futás",
  STRENGTH: "Erőedzés",
  SWIMMING: "Úszás",
  CYCLING: "Kerékpár",
  OTHER: "Edzés",
};

export function eventIdentity(event: TrainingEvent, review: TrainingReview) {
  const session = event.session_id
    ? review.inputs?.recent_sessions?.find((s) => s.id === event.session_id)
    : undefined;
  const plan = event.workout_id
    ? review.plan_snapshots.find((p) => p.workout.id === event.workout_id)
        ?.workout
    : undefined;
  const sport = event.sport ?? session?.sport ?? plan?.sport;
  return {
    title:
      event.title?.trim() ||
      session?.name?.trim() ||
      plan?.title?.trim() ||
      sportLabels[sport ?? ""] ||
      "Edzés",
    started_at:
      event.started_at ??
      session?.started_at ??
      plan?.planned_start_time ??
      null,
    date: event.date ?? session?.date ?? plan?.date ?? null,
    href: event.session_id
      ? `/sessions/${encodeURIComponent(event.session_id)}`
      : event.workout_id
        ? `/workouts/${encodeURIComponent(event.workout_id)}`
        : null,
  };
}

export function TrainingEvents({
  review,
  zone,
  disabled,
  onConfirmMissed,
}: {
  review: TrainingReview;
  zone: string;
  disabled: boolean;
  onConfirmMissed: (event: TrainingEvent) => void;
}) {
  const groups = new Map<string, TrainingEvent[]>();
  for (const event of review.result.events)
    groups.set(event.kind, [...(groups.get(event.kind) ?? []), event]);
  const time = new Intl.DateTimeFormat("hu-HU", {
    timeZone: zone,
    dateStyle: "short",
    timeStyle: "short",
  });
  return (
    <details>
      <summary className="cursor-pointer">
        Figyelembe vett teljesítések és tisztázandó edzések ·{" "}
        {review.result.events.length}
      </summary>
      <div className="mt-3 space-y-3">
        {[...groups].map(([kind, events]) => (
          <details key={kind} className="rounded border border-zinc-700 p-3">
            <summary className="cursor-pointer">
              {eventLabels[kind] ?? kind} · {events.length}
            </summary>
            <ul className="mt-3 space-y-2">
              {events.map((event) => {
                const identity = eventIdentity(event, review);
                const instant = identity.started_at
                  ? new Date(identity.started_at)
                  : null;
                const when =
                  instant && Number.isFinite(instant.getTime())
                    ? time.format(instant)
                    : (identity.date ?? "Időpont még nem ismert");
                return (
                  <li
                    key={
                      event.session_id ?? `${event.kind}:${event.workout_id}`
                    }
                    className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-zinc-700/50 pt-2"
                  >
                    <span className="text-zinc-400">{when}</span>
                    {identity.href ? (
                      <Link
                        href={identity.href}
                        className="underline underline-offset-4"
                      >
                        {identity.title}
                      </Link>
                    ) : (
                      <span>{identity.title}</span>
                    )}
                    {event.can_confirm_missed &&
                      event.workout_id &&
                      event.workout_hash && (
                        <button
                          className={secondaryClass}
                          disabled={disabled}
                          onClick={() => onConfirmMissed(event)}
                        >
                          Megerősítem, hogy kimaradt
                        </button>
                      )}
                  </li>
                );
              })}
            </ul>
          </details>
        ))}
      </div>
    </details>
  );
}

export function compactDates(values: string[]) {
  const dates = [...new Set(values)].sort(),
    ranges: { first: string; last: string }[] = [];
  for (const date of dates) {
    const current = ranges.at(-1);
    if (current && addDays(current.last, 1) === date) current.last = date;
    else ranges.push({ first: date, last: date });
  }
  return ranges
    .map((r) => (r.first === r.last ? r.first : `${r.first} – ${r.last}`))
    .join("; ");
}

export function DaysWithoutProposal({
  days,
}: {
  days: TrainingReview["result"]["days_without_proposal"];
}) {
  const groups = new Map<string, string[]>();
  for (const day of days)
    groups.set(day.reason, [...(groups.get(day.reason) ?? []), day.date]);
  return (
    <details>
      <summary className="cursor-pointer">
        Miért nem készült új edzésjavaslat egyes napokra? · {days.length}
      </summary>
      <ul className="mt-3 space-y-3">
        {[...groups].map(([reason, dates]) => (
          <li key={reason}>
            <p className="font-medium">{compactDates(dates)}</p>
            <p>
              {reason === "PROFILE_REVIEW_REQUIRED"
                ? "A fenti profilindokok az egész jelölt időszakot érintik."
                : (trainingReasons[reason] ?? reason)}
            </p>
          </li>
        ))}
      </ul>
    </details>
  );
}
