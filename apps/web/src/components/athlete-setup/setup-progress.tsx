import Link from "next/link";
import { setupSteps } from "@/lib/athlete-setup/journey";
import type { Context } from "@/lib/athlete-setup/contracts";
import type { ScheduleContext } from "@/lib/calendar/constraints";

export default function SetupProgress({
  context,
  schedule,
  active,
  onSelect,
}: {
  context: Context;
  schedule: ScheduleContext | null;
  active: "profile" | "calendar" | "history";
  onSelect: (step: "profile" | "calendar" | "history") => void;
}) {
  const steps = setupSteps(context, schedule),
    ready = steps.filter((s) => s.state === "ready").length;
  return (
    <section
      className="space-y-4 rounded-2xl border border-teal-500/40 bg-teal-500/5 p-5"
      aria-label="Út az első edzéstervig"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-teal-400">
            Út az edzéstervedig
          </p>
          <h2 className="mt-1 text-xl font-semibold">
            Minden szükséges adat, egy követhető folyamatban
          </h2>
        </div>
        <span className="text-sm">{ready} / 3 lépéshez van mentett adat</span>
      </div>
      <p className="text-sm leading-6 text-zinc-400">
        A jelzések a mentett adatokra vonatkoznak. Válassz egy lépést; a korábbi
        válaszaid megmaradnak. A terv konkrét feltételeit a végső ellenőrzés
        mutatja meg.
      </p>
      <ol className="grid gap-3 md:grid-cols-3">
        {steps.map((step, i) => (
          <li key={step.key}>
            <button
              type="button"
              aria-current={active === step.key ? "step" : undefined}
              onClick={() => onSelect(step.key)}
              className={`h-full w-full rounded-xl border p-4 text-left ${active === step.key ? "border-teal-400 bg-teal-500/10" : "border-zinc-700"}`}
            >
              <span className="text-xs text-teal-400">
                {i + 1}. lépés ·{" "}
                {step.state === "ready"
                  ? "Mentett adat"
                  : step.state === "optional"
                    ? "Pontosításhoz"
                    : "Még szükséges"}
              </span>
              <strong className="mt-2 block">{step.title}</strong>
              <span className="mt-2 block text-sm leading-6 text-zinc-400">
                {step.detail}
              </span>
            </button>
          </li>
        ))}
      </ol>
      <p className="text-sm">
        4. lépés:{" "}
        <Link
          className="font-semibold text-teal-400 underline underline-offset-4"
          href="/planning-cycles"
        >
          Célok, edzésterv és közös áttekintés →
        </Link>
      </p>
    </section>
  );
}
