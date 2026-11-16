import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const f = JSON.parse(
  readFileSync(
    new URL("./fixtures/exercise-availability.json", import.meta.url),
  ),
);
const { readOptionsContext, readOptionsReceipt, readOptionsData } = load(
  "src/lib/training-options/contracts.ts",
);
const { readContext, readReceipt } = load(
  "src/lib/guided-strength/contracts.ts",
);
const { readTrainingReview } = load("src/lib/planning-cycles/training-plan.ts");
const {
  matchingExercises,
  availableExercises,
  equipmentGaps,
  selectedEquipment,
} = load("src/lib/training-options/strength-catalog.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const { default: Confirmations } = load(
  "src/components/training-options/exercise-confirmations.tsx",
);
const { default: Preparation } = load(
  "src/components/guided-strength/preparation.tsx",
);
const { AssessedStrengthDetails } = load(
  "src/components/planning-cycles/strength-assessment.tsx",
);
const { default: StrengthEquipment } = load(
  "src/components/training-options/strength-equipment.tsx",
);
const owner = f.ready.athlete_id,
  catalog = f.options.strength_catalog,
  place = f.options.data.locations[0];
const expected = {
  owner,
  reference: f.plan.program_reference,
  zone: f.plan.timezone_name,
};
const render = (component, props) =>
  renderToStaticMarkup(React.createElement(component, props));
async function hash(v) {
  const raw = { ...v };
  delete raw.content_hash;
  v.content_hash = await sha(raw);
}
test("real Python location receipt retains declarations and old missing fields byte for byte", async () => {
  await readOptionsReceipt(
    f.options_receipt,
    owner,
    JSON.stringify(f.options_request),
  );
  await readOptionsReceipt(f.legacy_receipt, owner);
  assert(
    !(
      "exercise_confirmations" in
      f.legacy_receipt.artifact.proposal.data.locations[0]
    ),
  );
});
test("real Python inventory, guided start, finish and plan all verify the same owned declarations", async () => {
  await readOptionsContext(f.options);
  await readContext(f.ready);
  await readReceipt(f.started, owner, JSON.stringify(f.start_request));
  await readReceipt(f.finished, owner, JSON.stringify(f.finish_request));
  await readTrainingReview(f.plan, expected);
});
test("self report supplies availability without a single invented equipment identity", () => {
  assert.deepEqual(place.resources, []);
  assert.deepEqual(selectedEquipment(catalog, place.resources), []);
  assert(
    !matchingExercises(catalog, []).some((e) => e.id === "barbell_benchpress"),
  );
  assert(
    availableExercises(catalog, place).some(
      (e) => e.id === "barbell_benchpress",
    ),
  );
  assert.equal(f.ready.intake.summary.recorded_reference_count, 0);
});
test("dedicated bench station and adjustable bench alternatives are independently recognized", () => {
  for (const resources of [
    ["Fekvenyomó pad", "Súlyzórúd", "Súlytárcsák"],
    [
      "Állítható edzőpad",
      "Erőkeret / guggolókeret",
      "Súlyzórúd",
      "Súlytárcsák",
      "Tárcsarögzítők",
    ],
  ])
    assert(
      matchingExercises(catalog, resources).some(
        (e) => e.id === "barbell_benchpress",
      ),
    );
  assert(
    !matchingExercises(catalog, [
      "Vízszintes edzőpad",
      "Súlyzórúd",
      "Súlytárcsák",
    ]).some((e) => e.id === "barbell_benchpress"),
  );
});
test("missing equipment names describe every alternative rather than an unexplained refusal", () => {
  const gaps = equipmentGaps(catalog, "barbell_benchpress", [
    "Vízszintes edzőpad",
    "Súlyzórúd",
    "Súlytárcsák",
  ]);
  assert(gaps[0].includes("Tárcsarögzítők"));
  assert(gaps[0].includes("Erőkeret / guggolókeret"));
  assert(gaps.some((g) => g.includes("Fekvenyomó pad rúdtartóval")));
});
for (const [name, edit] of Object.entries({
  inventedEquipment: (v) => v.strength_options[0].equipment_ids.push("rack"),
  omittedDeclaration: (v) => delete v.data.locations[0].exercise_confirmations,
  extraExercise: (v) =>
    v.strength_options[0].declared_exercise_ids.push("pushup"),
  otherPlace: (v) => {
    v.data.locations[2].exercise_confirmations =
      v.data.locations[0].exercise_confirmations;
    v.data.locations[0].exercise_confirmations = [];
  },
}))
  test(`rejects ${name} location availability`, async () => {
    const v = structuredClone(f.options);
    edit(v);
    await assert.rejects(() => readOptionsContext(v));
  });
for (const [name, edit] of Object.entries({
  duplicate: (v) =>
    v.locations[0].exercise_confirmations.push(
      v.locations[0].exercise_confirmations[0],
    ),
  authority: (v) =>
    (v.locations[0].exercise_confirmations[0].planning_authorized = true),
  source: (v) =>
    (v.locations[0].exercise_confirmations[0].source_kind =
      "clinically_verified"),
}))
  test(`strict declaration rejects ${name}`, () => {
    const v = structuredClone(f.options.data);
    edit(v);
    assert.throws(() => readOptionsData(v));
  });
test("unknown catalogue exercise never becomes available silently", () => {
  const p = structuredClone(place);
  p.exercise_confirmations[0].exercise_id = "not_in_catalog";
  assert.throws(() => availableExercises(catalog, p));
});
test("archived, non-strength and other venues never inherit the local declaration", () => {
  for (const p of [
    { ...place, archived: true },
    { ...place, sports: ["RUNNING"] },
    f.options.data.locations[2],
  ])
    assert(
      !availableExercises(catalog, p).some(
        (e) => e.id === "barbell_benchpress",
      ),
    );
});
test("guided preparation displays declaration provenance and the real alternative equipment gaps", () => {
  const p = {
    context: f.ready,
    locked: false,
    place: place.id,
    ids: [],
    mode: "manual",
    precheck: false,
    onPlace() {},
    onIds() {},
    onMode() {},
    onPrecheck() {},
    onBegin() {},
  };
  const html = render(Preparation, p);
  assert.match(html, /Helyszíni elérhetőség: saját megadás alapján/);
  const v = structuredClone(f.ready);
  v.intake.sources.locations[0].exercise_confirmations = [];
  v.preparation.locations[0].entries[0].issues = ["GUIDED_EQUIPMENT_MISSING"];
  const blocked = render(Preparation, { ...p, context: v });
  assert.match(blocked, /Tárcsarögzítők/);
  assert.match(blocked, /Erőkeret/);
  assert.match(blocked, /Fekvenyomó pad rúdtartóval/);
});
test("location editor confirmation section and station illustration are visible and labelled", () => {
  const html = render(Confirmations, {
    catalog,
    value: place.exercise_confirmations,
    onChange() {},
    resources: [],
  });
  assert.match(html, /Gyakorlat megadása ezen a helyszínen/);
  assert.match(html, /Fekvenyomás rúddal/);
  assert.match(html, /Megadás törlése/);
  const inventory = render(StrengthEquipment, {
    catalog,
    resources: [],
    onChange() {},
  });
  assert.match(inventory, /Fekvenyomó pad rúdtartóval/);
});
test("the accepted own-source strength recipe exposes the declaration without changing its load", () => {
  const candidate = f.plan.result.alternatives
    .flatMap((g) => g.candidates)
    .find((c) => c.sport === "STRENGTH");
  assert(candidate);
  const meta =
    f.plan.result.prescription_context.by_candidate[candidate.candidate_key];
  const html = render(AssessedStrengthDetails, {
    review: f.plan,
    dose: candidate.strength_prescription,
    seconds: candidate.duration_sec,
    declaredMinutes: meta.assessment_duration_minutes,
    productDefault: meta.product_default_used,
  });
  assert.match(html, /Helyszíni elérhetőség: saját megadás alapján/);
  assert.match(html, /25/);
  assert.equal(
    candidate.strength_prescription.movements.find(
      (e) => e.exercise_id === "barbell_benchpress",
    ).sets[0].load_value,
    "25.000000",
  );
});
test("editing a declaration note cannot keep an unchanged durable receipt hash", async () => {
  const v = structuredClone(f.options_receipt);
  v.artifact.proposal.data.locations[0].exercise_confirmations[0].note =
    "Más gép";
  await assert.rejects(() => readOptionsReceipt(v, owner));
});
test("rehashing a missing declaration cannot hide the matching options snapshot", async () => {
  const v = structuredClone(f.ready);
  v.intake.sources.locations[0].exercise_confirmations = [];
  await hash(v.intake);
  await hash(v);
  await assert.rejects(() => readContext(v));
});
