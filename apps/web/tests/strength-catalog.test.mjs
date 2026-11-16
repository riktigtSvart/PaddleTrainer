import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/strength-catalog.json", import.meta.url)),
);
const {
  readStrengthCatalog,
  selectedEquipment,
  toggleEquipment,
  matchingExercises,
} = load("src/lib/training-options/strength-catalog.ts");
const { readOptionsContext, readOptionsReceipt, readOptionsData } = load(
  "src/lib/training-options/contracts.ts",
);
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const Picker = load(
  "src/components/training-options/strength-equipment.tsx",
).default;
const { equipmentIllustrationIds } = load(
  "src/components/training-options/equipment-illustration.tsx",
);
const cat = fixture.context.strength_catalog;
const resources = (ids) =>
  ids.map((id) => cat.equipment.find((e) => e.id === id).resource);

test("actual owned context and 55-item durable request agree across Python and browser", async () => {
  await readStrengthCatalog(cat);
  await readOptionsContext(fixture.context);
  await readOptionsReceipt(
    fixture.receipt,
    fixture.context.athlete_id,
    JSON.stringify(fixture.request),
  );
  assert(cat.equipment.length >= 50 && cat.exercises.length >= 75);
  assert(
    fixture.context.strength_options.every(
      (v) => v.planning_authorized === false,
    ),
  );
  assert.equal(
    fixture.receipt.artifact.proposal.data.locations[0].resources.length,
    56,
  );
});
test("all catalog equipment has an authored diagram and guide links are local", () => {
  for (const equipment of cat.equipment)
    assert(
      equipmentIllustrationIds.includes(equipment.illustration),
      equipment.id,
    );
  assert.equal(cat.guides.length, 4);
  assert.deepEqual(
    cat.guides.map((g) => g.page),
    [1, 2, 3, 4],
  );
  for (const guide of cat.guides) {
    assert.equal(guide.src, `/strength-guides/${guide.id}.png`);
    assert(guide.width > 0 && guide.height > 0);
  }
});
test("equipment aliases are recognized without rewriting source strings", () => {
  const values = ["Dumbbell", "Kézisúlyzók", "Saját eszköz, tartozékkal"];
  const before = structuredClone(values);
  assert.deepEqual(
    selectedEquipment(cat, values).map((e) => e.id),
    ["dumbbells"],
  );
  assert.deepEqual(toggleEquipment(cat, values, "dumbbells", true), values);
  assert.deepEqual(toggleEquipment(cat, values, "dumbbells", false), [
    values[2],
  ]);
  assert.deepEqual(values, before);
});
test("all alternative requirements and all accessories must match within one place", () => {
  assert(
    matchingExercises(cat, resources(["kettlebell"])).some(
      (e) => e.id === "goblet_squat",
    ),
  );
  assert(
    matchingExercises(cat, resources(["dumbbells"])).some(
      (e) => e.id === "goblet_squat",
    ),
  );
  assert(
    !matchingExercises(cat, resources(["barbell"])).some(
      (e) => e.id === "barbell_row",
    ),
  );
  assert(
    !matchingExercises(cat, resources(["cable_station"])).some(
      (e) => e.id === "face_pull",
    ),
  );
  assert(
    matchingExercises(cat, resources(["cable_station", "rope"])).some(
      (e) => e.id === "face_pull",
    ),
  );
  assert(
    !matchingExercises(cat, resources(["band"])).some(
      (e) => e.id === "pallof_press",
    ),
  );
  assert(
    matchingExercises(cat, resources(["band", "anchor"])).some(
      (e) => e.id === "pallof_press",
    ),
  );
  assert.deepEqual(matchingExercises(cat, []), []);
});
test("kayak and rowing ergometers remain different equipment declarations", () => {
  assert.deepEqual(
    selectedEquipment(cat, ["Kajakergométer"]).map((e) => e.id),
    ["kayak_erg"],
  );
  assert.deepEqual(
    selectedEquipment(cat, ["RowErg"]).map((e) => e.id),
    ["row_erg"],
  );
  assert.deepEqual(
    selectedEquipment(cat, ["Evezőgép", "Labda"]).map((e) => e.id),
    [],
  );
});
const invalid = {
  "future schema": (c) => (c.schema_version = "future"),
  "prescription permission": (c) => (c.planning_authorized = true),
  "workout mutation claim": (c) => (c.workouts_changed = true),
  "duplicate equipment": (c) => c.equipment.push(c.equipment[0]),
  "ambiguous alias": (c) =>
    c.equipment[1].aliases.push(c.equipment[0].resource),
  "unknown equipment category": (c) => (c.equipment[0].category = "unknown"),
  "unknown exercise equipment": (c) =>
    (c.exercises[0].requirements = [["foreign"]]),
  "empty conjunction": (c) => (c.exercises[0].requirements = [[]]),
  "empty alternatives": (c) => (c.exercises[0].requirements = []),
  "duplicate exercise": (c) => c.exercises.push(c.exercises[0]),
  "foreign guide URL": (c) =>
    (c.guides[0].src = "https://foreign.invalid/image.png"),
  "invalid image geometry": (c) => (c.guides[0].width = 0),
  "unknown exercise guide": (c) => (c.exercises[0].guide_id = "foreign"),
};
for (const [name, edit] of Object.entries(invalid))
  test(`rejects ${name} even after catalog rehash`, async () => {
    const value = structuredClone(cat);
    edit(value);
    const raw = { ...value };
    delete raw.content_hash;
    value.content_hash = await sha(raw);
    await assert.rejects(readStrengthCatalog(value));
  });
test("unchanged catalog hash cannot hide edited labels", async () => {
  const value = structuredClone(cat);
  value.equipment[0].label = "edited";
  await assert.rejects(readStrengthCatalog(value));
});
test("location result cannot borrow equipment or exercises from another place", async () => {
  const value = structuredClone(fixture.context);
  value.strength_options[1].exercise_ids.push("dumbbell_row");
  await assert.rejects(readOptionsContext(value));
});
test("location result cannot silently omit available exercises", async () => {
  const value = structuredClone(fixture.context);
  value.strength_options[0].exercise_ids.pop();
  await assert.rejects(readOptionsContext(value));
});
test("a capability list without its matching catalog is rejected", async () => {
  const value = structuredClone(fixture.context);
  delete value.strength_catalog;
  await assert.rejects(readOptionsContext(value));
});
test("old contexts remain readable without newly invented catalog declarations", async () => {
  const value = structuredClone(fixture.context);
  delete value.strength_catalog;
  delete value.strength_options;
  await readOptionsContext(value);
});
test("resource capacity remains explicitly bounded at 128", () => {
  const value = structuredClone(fixture.context.data);
  value.locations[0].resources = Array.from(
    { length: 128 },
    (_, i) => `Saját eszköz ${i}`,
  );
  readOptionsData(value);
  value.locations[0].resources.push("129. eszköz");
  assert.throws(() => readOptionsData(value));
});
test("picker renders labelled illustrated checkboxes, search and exercise help", () => {
  const html = renderToStaticMarkup(
    React.createElement(Picker, {
      catalog: cat,
      resources: resources(["dumbbells"]),
      onChange() {},
    }),
  );
  assert.match(html, /Erősítéshez elérhető felszerelés/);
  assert.match(html, /Eszköz keresése/);
  assert.match(html, /Eszközcsoport/);
  assert.match(html, /Kézisúlyzó/);
  assert.match(html, /type="checkbox"/);
  assert.match(html, /pt-equipment-illustration/);
  assert.match(html, /Kapcsolódó gyakorlatok/);
  assert.match(html, /ismerete külön adat/);
  assert.match(html, /feltöltött szemléltető lapok/);
});
