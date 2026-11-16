import Link from "next/link";
import type { TrainingReview } from "@/lib/planning-cycles/training-plan";
import type { AssessedStrengthDose } from "@/lib/planning-cycles/strength-assessment";
import { strengthReasons } from "@/lib/planning-cycles/strength-assessment";
import {sourceChangeLabels} from "@/lib/planning-cycles/assessment-source-changes";
import ProfileChanges from "./profile-changes";
import type { SetRecord } from "@/lib/initial-assessment/contracts";
import { secondaryClass } from "@/components/planning-goals/fields";

const sides: Record<string, string> = {
  both: "Kétoldali",
  left: "Bal oldal",
  right: "Jobb oldal",
  alternating: "Váltott oldal",
  unknown: "Oldal pontosítandó",
};
const patterns: Record<string, string> = {
  pull: "Húzás",
  push: "Nyomás",
  knee: "Térddomináns",
  hip: "Csípődomináns",
  core: "Törzsstabilizálás",
};
const decimal = (v: string | null) => v?.replace(".", ",") ?? "Nem ismert";
function loadLabel(s: SetRecord) {
  if (s.load_kind === "bodyweight") return "Saját testsúly";
  if (s.load_kind === "band") return `Gumiszalag: ${s.load_note}`;
  const suffix = s.load_kind === "machine_level" ? "fokozat" : "kg";
  const basis: Record<string, string> = {
    total: "összsúly",
    per_hand: "kézenként",
    machine_display: "gép kijelzése",
    assistance: "rásegítés",
  };
  return `${decimal(s.load_value)} ${suffix} · ${basis[s.load_basis] ?? "jelentése pontosítandó"}`;
}
export function StrengthAssessmentPanel({
  review,
}: {
  review: TrainingReview;
}) {
  const value = review.result.strength_assessment,
    receipt = review.inputs?.strength_assessment?.receipt;
  if (!value) return null;
  const places = receipt?.artifact.snapshot.locations ?? [],
    eligible = value.exercise_readiness.filter((e) => e.eligible);
  return (
    <section
      className="pt-plan-strength-assessment pt-panel"
      aria-label="Az erőjavaslat kiinduló felmérése"
    >
      <p>
        <Link href="/strength-assessment">
          Kezdő felmérőalkalom indítása vagy folytatása
        </Link>
      </p>
      <h3>Erőjavaslat a mentett felmérésből</h3>
      <p>
        {receipt
          ? `${receipt.artifact.revision}. mentett felmérés · ${receipt.artifact.proposal.data.assessment_date} · ${eligible.length} használható gyakorlatreferencia a felülvizsgálat napján.`
          : "A tervező még nem kapott szerverre mentett kezdeti erőfelmérést."}
      </p>
      {!!value.issues.length && (
        <ul>
          {value.issues.map((code) => (
            <li key={code}>{strengthReasons[code] ?? code}</li>
          ))}
        </ul>
      )}
      {review.inputs?.strength_assessment?.source_comparison?.reusable===false&&<ul>{review.inputs.strength_assessment.source_comparison.changes.map(code=><li key={code}>{sourceChangeLabels[code]}</li>)}</ul>}
      <ProfileChanges value={review.inputs?.strength_assessment?.profile_comparison}/>
      {!!value.exercise_readiness.length && (
        <details>
          <summary>
            Gyakorlatonkénti források és pontosítandó adatok ·{" "}
            {value.exercise_readiness.length}
          </summary>
          <div className="pt-assessed-strength-grid">
            {value.exercise_readiness.map((e) => (
              <article key={e.entry_id}>
                <h4>{e.label}</h4>
                <p>
                  {patterns[e.pattern] ?? e.pattern} ·{" "}
                  {places.find((p) => p.id === e.location_id)?.name ??
                    "Helyszín pontosítandó"}{" "}
                  · {e.performed_on ?? "Dátum pontosítandó"}
                </p>
                <p>
                  <strong>
                    {e.eligible
                      ? "A mentett saját referencia használható"
                      : "Még pontosítandó"}
                  </strong>
                </p>
                {!!e.reasons.length && (
                  <ul>
                    {e.reasons.map((code) => (
                      <li key={code}>{strengthReasons[code] ?? code}</li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
          </div>
        </details>
      )}
      <p className="pt-options-meta">
        A kiválasztás naponta, az adott helyszín eszközeivel és a referencia
        dátumával újra ellenőrzött. A felmérés módosítását az új
        tervfelülvizsgálat veszi figyelembe.
      </p>
      <Link href="/initial-assessment" className={secondaryClass}>
        Kezdeti erőfelmérés megnyitása
      </Link>
    </section>
  );
}
export function AssessedStrengthDetails({
  review,
  dose,
  seconds,
  declaredMinutes,
  productDefault,
}: {
  review: TrainingReview;
  dose: AssessedStrengthDose;
  seconds: number;
  declaredMinutes: number | null;
  productDefault: boolean;
}) {
  const receipt = review.inputs?.strength_assessment?.receipt;
  return (
    <div className="pt-assessed-strength-details">
      <p>
        <strong>A mentett saját sorozatok alapján</strong>
        {receipt
          ? ` · ${receipt.artifact.revision}. felmérés, ${receipt.artifact.proposal.data.assessment_date}`
          : ""}
      </p>
      <p className="pt-options-meta">
        Időkeret: {seconds / 60} perc, bemelegítéssel, pihenőkkel és
        levezetéssel.
        {productDefault
          ? " A 20 perces kezdő helyfoglalás termékszabály; nem mért személyes edzésidő."
          : declaredMinutes !== null
            ? ` A felmérésben megadott ${declaredMinutes} perces szokásos időtartam is felső korlát.`
            : " A saját, rögzített erőedzések ideje is felső korlát."}
      </p>
      <div className="pt-assessed-strength-grid">
        {dose.movements.map((e) => (
          <article key={e.entry_id} className="pt-assessed-strength-movement">
            <h4>{e.label}</h4>
            <p className="pt-options-meta">
              {patterns[e.pattern] ?? e.pattern} · {sides[e.side]} · Saját
              referencia: {e.performed_on}
            </p>
            {receipt?.artifact.snapshot.locations
              .find((p) => p.id === e.location_id)
              ?.exercise_confirmations?.some(
                (c) => c.exercise_id === e.exercise_id,
              ) && (
              <p className="pt-options-meta">
                Helyszíni elérhetőség: saját megadás alapján.
              </p>
            )}
            {e.machine_note && <p>Gép és beállítás: {e.machine_note}</p>}
            {dose.calibration_derivations?.filter((d) => d.entry_id === e.entry_id).map((d) => <p key={d.observation_id} className="pt-options-meta">Mért teljesítés: {d.source_repetitions} ismétlés, jelzett tartalék: {d.source_rir === "5_plus" ? "legalább 5" : d.source_rir}. Kezdő edzéscél: {d.planned_repetitions} ismétlés azonos terheléssel. A két ismétléssel csökkentett, legfeljebb nyolcas cél kezdő alkalmazásszabály; a tervezett tartalék legalább 3 ismétlés.</p>)}
            <ol>
              {e.sets.map((s, i) => (
                <li key={s.id}>
                  <strong>{i + 1}. sorozat:</strong>{" "}
                  {s.repetitions !== null
                    ? `${s.repetitions} ismétlés`
                    : `${decimal(s.hold_seconds)} másodperc`}
                  {" · "}
                  {dose.calibration_derivations?.some((d) => d.entry_id === e.entry_id && d.load_kind === "machine_plate_components") ? `${s.load_value} kg felrakott tárcsa · a megadott gépen` : loadLabel(s)}
                  {s.repetitions !== null && !dose.calibration_derivations?.some((d) => d.entry_id === e.entry_id) && (
                    <span className="pt-options-meta">
                      {" "}
                      · A felmérésben jelzett tartalék:{" "}
                      {s.rir === "5_plus" ? "5 vagy több" : s.rir} ismétlés
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </article>
        ))}
      </div>
      <p>
        Sorozatok között legalább {dose.rest_seconds / 60} perc pihenő. Az ismétléses sorozatoknál
        legalább 3 szabályos ismétlés tartalék maradjon; a technika romlásakor
        vagy panasz esetén hagyd el a hátralévő részt.
      </p>
      <p className="pt-options-meta">
        Kezdő referenciaedzés: a mentett saját sorozatokból legfeljebb kettő
        szerepel gyakorlatonként. A tervező a súlyt, az ismétlésszámot és a
        sorozatszámot nem emeli automatikusan.
      </p>
    </div>
  );
}
