"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { addDays, canonical } from "@/lib/planning-cycles/contracts";
import type { Detail } from "@/lib/planning-cycles/contracts";
import { loadDetail, loadPage } from "@/lib/planning-cycles/client";
import { loadContext } from "@/lib/athlete-setup/client";
import type { Context } from "@/lib/athlete-setup/contracts";
import { loadConstraints } from "@/lib/calendar/constraint-client";
import type { ScheduleContext } from "@/lib/calendar/constraints";
import { loadOptions } from "@/lib/training-options/client";
import type { OptionsContext } from "@/lib/training-options/contracts";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import { loadPlanningInputs } from "@/lib/planning-cycles/inputs";
import { loadTrainingStatus } from "@/lib/planning-cycles/training-plan";
import { detailedPeriods } from "@/lib/planning-cycles/plan-view";
import {
  secondaryClass,
  buttonClass,
} from "@/components/planning-goals/fields";
import AthleteWorkspace from "@/components/athlete-setup/workspace";
import OptionsWorkspace from "@/components/training-options/workspace";
import CycleWorkspace from "@/components/planning-cycles/workspace";
import GoalWorkspace from "@/components/planning-goals/workspace";
import { TrainingPlanPanel } from "@/components/planning-cycles/training-plan";

const steps = [
  {
    key: "goal",
    title: "Cél és tervezési időtáv",
    expectation:
      "Válaszd ki vagy hozd létre a felkészülést, a fő célt és a tervezés legnagyobb időegységét.",
  },
  {
    key: "profile",
    title: "Személyes alapadatok és mozgáskeretek",
    expectation:
      "Személyes alapadatok, sporttapasztalat, heti összesített edzéskeret és a mozgást érintő korlátozások. A helyszínek és az időbeosztás külön lépésben szerepelnek.",
  },
  {
    key: "history",
    title: "Előzmények és kiindulópont",
    expectation:
      "Vedd át a rendelkezésre álló teljesítéseket és méréseket. Ez a lépés pontosítható; a hiányzó mérés nem lesz kitalált adat.",
  },
  {
    key: "locations",
    title: "Edzési helyszínek és lehetőségek",
    expectation:
      "Add meg egyszer az elérhető mozgásformákat és felszerelést minden saját helyszínhez.",
  },
  {
    key: "schedule",
    title: "Általános órarend",
    expectation:
      "Mikor és mely helyszíneken érsz rá? A lehetőségek módosításig érvényesek, egy időablak helyszínei egymás alternatívái.",
  },
  {
    key: "week",
    title: "Az aktuális 7 nap lehetőségei",
    expectation:
      "Tekintsd át az örökölt időbeosztást. Csak a napi eltéréseket vagy az időszaki helyszíni korlátozásokat kell megadnod.",
  },
  {
    key: "strategy",
    title: "Fejlesztési stratégia a teljes időszakra",
    expectation:
      "A célok alapján tekintsd át és mentsd el a képességek fejlesztési szerepeit a makro- és mezociklusokban.",
  },
  {
    key: "plan",
    title: "Edzésterv, naptár és edzésváltozatok",
    expectation:
      "Az aktuális és a következő mezociklus részletes terve. A gördülő 7 napban választhatsz változatot; a későbbi napok javaslata együtt frissül.",
  },
] as const;
type Step = (typeof steps)[number]["key"];
type Loaded = {
  athlete: Context;
  options: OptionsContext;
  schedule: ScheduleContext;
};

export default function PlanningJourney() {
  const [loaded, setLoaded] = useState<Loaded | null>(null),
    [selected, setSelected] = useState<Detail | null>(null),
    [open, setOpen] = useState<Step | null>(null),
    [reload, setReload] = useState(0),
    [failure, setFailure] = useState(""),
    [planningError, setPlanningError] = useState(""),
    [strategyReady, setStrategyReady] = useState(false),
    [planReady, setPlanReady] = useState(false),
    [weekReviewed, setWeekReviewed] = useState("");
  const initialized = useRef(false),
    selectedIdentity = useRef<string | null>(null);
  const selectProgram = useCallback((value: Detail) => {
    selectedIdentity.current = value.program.artifact.artifact_id;
    setSelected(value);
    try {
      sessionStorage.setItem(
        `paddletrainer.journey.program.v1:${value.program.artifact.athlete_id}`,
        value.program.artifact.artifact_id,
      );
    } catch {
      /* This is a navigation preference, not a pending data write. */
    }
    setReload((n) => n + 1);
  }, []);
  useEffect(() => {
    const refresh = () => setReload((n) => n + 1);
    window.addEventListener(LOCAL_REFRESH_EVENT, refresh);
    return () => window.removeEventListener(LOCAL_REFRESH_EVENT, refresh);
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    void Promise.all([
      loadContext(abort.signal),
      loadOptions(undefined, abort.signal),
      loadConstraints(null, abort.signal),
      loadPage(0, abort.signal),
    ])
      .then(async ([athlete, options, schedule, history]) => {
        if (abort.signal.aborted) return;
        if (
          athlete.athlete_id !== options.athlete_id ||
          athlete.athlete_id !== schedule.athlete_id
        )
          throw Error(
            "A felmérés és az órarend különböző sportolóhoz tartozik.",
          );
        let id = selectedIdentity.current;
        try {
          id ??= sessionStorage.getItem(
            `paddletrainer.journey.program.v1:${athlete.athlete_id}`,
          );
        } catch {
          /* Optional navigation preference. */
        }
        id ??=
          history.items.find(
            (item) =>
              !item.artifact.proposal.end_date ||
              item.artifact.proposal.end_date >= athlete.local_today,
          )?.artifact.artifact_id ?? null;
        const detail = id ? await loadDetail(id, abort.signal) : null;
        if (abort.signal.aborted) return;
        selectedIdentity.current = detail?.program.artifact.artifact_id ?? null;
        setSelected(detail);
        setLoaded({ athlete, options, schedule });
        setFailure("");
        if (!initialized.current) {
          initialized.current = true;
          const hash = window.location.hash.slice(1),
            explicit = steps.find((step) => step.key === hash);
          setOpen(
            explicit?.key ??
              (!athlete.profile
                ? "profile"
                : !detail
                  ? "goal"
                  : !options.data.locations.some((l) => !l.archived)
                    ? "locations"
                    : !options.data.schedule_start_date
                      ? "schedule"
                      : "week"),
          );
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted)
          setFailure(
            e instanceof Error
              ? e.message
              : "A tervezési folyamat nem tölthető be.",
          );
      });
    return () => abort.abort();
  }, [reload]);
  useEffect(() => {
    if (!loaded || !selected) return;
    const abort = new AbortController(),
      program = selected.program.artifact,
      first =
        program.proposal.start_date > loaded.athlete.local_today
          ? program.proposal.start_date
          : loaded.athlete.local_today,
      periods =
        selected.boundary_revisions.at(-1)?.artifact.periods ?? program.periods,
      scopes = detailedPeriods(periods, first),
      expected = {
        owner: program.athlete_id,
        reference: {
          artifact_id: program.artifact_id,
          content_hash: program.content_hash,
        },
        zone: loaded.athlete.timezone_name,
      };
    void Promise.all([
      Promise.all(
        scopes.map((period) => {
          const begin = period.start_date > first ? period.start_date : first;
          return loadPlanningInputs(
            {
              ...expected,
              first: begin,
              last:
                period.end_date < addDays(begin, 6)
                  ? period.end_date
                  : addDays(begin, 6),
            },
            abort.signal,
          );
        }),
      ),
      loadTrainingStatus(expected, abort.signal),
    ])
      .then(([inputs, state]) => {
        if (abort.signal.aborted) return;
        setStrategyReady(
          inputs.length > 0 &&
            inputs.every(
              (input) =>
                input.days.length > 0 &&
                input.days.every(
                  (day) => day.mesocycle_id && day.capability_roles.length > 0,
                ),
            ),
        );
        setPlanReady(
          !!state.acceptance &&
            !!state.review &&
            !state.review.result.blockers.length &&
            !state.review.result.create.length &&
            !state.review.result.cancel.length,
        );
        setPlanningError("");
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setStrategyReady(false);
          setPlanReady(false);
          setPlanningError(
            e instanceof Error
              ? e.message
              : "A stratégia és a terv állapota még nem olvasható.",
          );
        }
      });
    return () => abort.abort();
  }, [selected, loaded]);
  const weekKey = loaded
    ? canonical([
        loaded.options.reference,
        loaded.schedule.reference,
        loaded.schedule.availability?.artifact.content_hash ?? null,
        loaded.schedule.opportunities,
      ])
    : "";
  const ready: Record<Step, boolean> = {
    goal: !!selected,
    profile: loaded?.athlete.current_review?.global_entry_gate === "OPEN",
    history: !!loaded?.athlete.profile?.artifact.imported_observations?.length,
    locations: !!loaded?.options.data.locations.some((l) => !l.archived),
    schedule: !!loaded?.options.data.schedule_start_date,
    week: !!weekKey && weekReviewed === weekKey,
    strategy: strategyReady,
    plan: planReady,
  };
  const done = steps.filter(
    (step) => step.key !== "history" && ready[step.key],
  ).length;
  function continueFrom(index: number) {
    setReload((n) => n + 1);
    setOpen(steps[index + 1]?.key ?? "plan");
  }
  const program = selected?.program.artifact,
    periods =
      selected?.boundary_revisions.at(-1)?.artifact.periods ??
      program?.periods ??
      [],
    macro = periods.find(
      (period) =>
        period.period_type === "MACROCYCLE" &&
        period.end_date >= (loaded?.athlete.local_today ?? ""),
    );
  return (
    <div className="pt-planning-journey">
      <div className="pt-journey-progress">
        <p>
          {done} / 7 szükséges lépéshez van ellenőrzött mentett adat vagy
          áttekintés · az előzmények opcionálisan pontosíthatók
        </p>
        <progress value={done} max={7} aria-label="Tervezés előrehaladása" />
      </div>
      {failure && (
        <div role="alert" className="pt-options-message">
          <p>{failure}</p>
          <button
            type="button"
            className={secondaryClass}
            onClick={() => setReload((n) => n + 1)}
          >
            Adatok újraolvasása
          </button>
        </div>
      )}
      {!loaded && !failure && (
        <p role="status">
          A mentett profil, helyszínek és felkészülések betöltése…
        </p>
      )}
      {loaded &&
        steps.map((step, index) => (
          <details
            className="pt-journey-step"
            key={step.key}
            open={open === step.key}
            id={step.key}
            data-ready={ready[step.key]}
          >
            <summary
              onClick={(event) => {
                event.preventDefault();
                setOpen((current) => (current === step.key ? null : step.key));
              }}
            >
              <span className="pt-journey-number">{index + 1}</span>
              <span>
                <strong>{step.title}</strong>
                <small>
                  {step.key === "goal" && selected
                    ? selected.program.artifact.proposal.title
                    : step.key === "locations"
                      ? `${loaded.options.data.locations.filter((l) => !l.archived).length} mentett helyszín`
                      : step.key === "history"
                        ? "Pontosításhoz; nem minden kezdőmintához kötelező"
                        : ready[step.key]
                          ? "A mentett állapot alapján rendelkezésre áll"
                          : step.expectation}
                </small>
              </span>
              <span className="pt-journey-state">
                {ready[step.key]
                  ? "Rögzítve"
                  : step.key === "history"
                    ? "Pontosítható"
                    : open === step.key
                      ? "Most következik"
                      : "Még szükséges"}
              </span>
            </summary>
            {open === step.key && (
              <div className="pt-journey-body">
                <p className="pt-options-meta">{step.expectation}</p>
                {step.key === "goal" && (
                  <CycleWorkspace creationOnly onSelected={selectProgram} />
                )}
                {step.key === "profile" && (
                  <AthleteWorkspace initialTab="profile" embedded />
                )}
                {step.key === "history" && (
                  <AthleteWorkspace initialTab="history" embedded />
                )}
                {step.key === "locations" && (
                  <OptionsWorkspace mode="locations" />
                )}
                {step.key === "schedule" && (
                  <OptionsWorkspace mode="schedule" />
                )}
                {step.key === "week" && (
                  <OptionsWorkspace
                    mode="week"
                    onContinue={() => {
                      setWeekReviewed(weekKey);
                      setOpen("strategy");
                    }}
                  />
                )}
                {step.key === "strategy" &&
                  (program && macro ? (
                    <>
                      <GoalWorkspace
                        key={program.artifact_id}
                        initialCycle={program.artifact_id}
                        initialPeriod={macro.id}
                      />
                      {planningError && <p role="status">{planningError}</p>}
                    </>
                  ) : (
                    <p>
                      Előbb a Cél és tervezési időtáv lépésben válassz
                      felkészülést.
                    </p>
                  ))}
                {step.key === "plan" &&
                  (program ? (
                    <TrainingPlanPanel
                      key={`${program.artifact_id}:${selected?.boundary_revisions.at(-1)?.artifact.content_hash ?? "base"}`}
                      owner={program.athlete_id}
                      reference={{
                        artifact_id: program.artifact_id,
                        content_hash: program.content_hash,
                      }}
                      zone={loaded.athlete.timezone_name}
                      today={loaded.athlete.local_today}
                      initialDate={
                        program.proposal.start_date > loaded.athlete.local_today
                          ? program.proposal.start_date
                          : loaded.athlete.local_today
                      }
                      periods={periods}
                    />
                  ) : (
                    <p>
                      A részletes tervhez előbb válassz vagy hozz létre
                      felkészülést.
                    </p>
                  ))}
                {step.key !== "week" && step.key !== "plan" && (
                  <div className="pt-options-actions">
                    <button
                      type="button"
                      className={buttonClass}
                      disabled={step.key !== "history" && !ready[step.key]}
                      onClick={() => continueFrom(index)}
                    >
                      Tovább
                    </button>
                    <button
                      type="button"
                      className={secondaryClass}
                      onClick={() => setReload((n) => n + 1)}
                    >
                      Mentett állapot frissítése
                    </button>
                  </div>
                )}
              </div>
            )}
          </details>
        ))}
    </div>
  );
}
