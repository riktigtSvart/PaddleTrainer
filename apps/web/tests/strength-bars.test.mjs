import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/strength-bars.json", import.meta.url)),
);
const previous = JSON.parse(
  readFileSync(new URL("./fixtures/strength-machines.json", import.meta.url)),
);
const {
  matchingExercises,
  selectedEquipment,
  toggleEquipment,
  readStrengthCatalog,
} = load("src/lib/training-options/strength-catalog.ts");
const { readOptionsContext, readOptionsReceipt } = load(
  "src/lib/training-options/contracts.ts",
);
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const Picker = load(
  "src/components/training-options/strength-equipment.tsx",
).default;
const { equipmentIllustrationIds } = load(
  "src/components/training-options/equipment-illustration.tsx",
);
const catalog = fixture.context.strength_catalog;

test("real wall-bar/frame HTTP capture and exact durable receipt verify in the browser", async () => {
  await readOptionsContext(fixture.context);
  await readOptionsReceipt(
    fixture.receipt,
    fixture.context.athlete_id,
    JSON.stringify(fixture.request),
  );
  assert.deepEqual(fixture.context.strength_options[0].equipment_ids, [
    "pullup_frame",
  ]);
  assert(
    fixture.context.strength_options[1].exercise_ids.includes(
      "hanging_leg_raise",
    ),
  );
  assert(!fixture.context.strength_options[1].exercise_ids.includes("pullup"));
});

test("C20.3.1 snapshots and all existing equipment definitions remain readable and unchanged", async () => {
  await readOptionsContext(previous.context);
  for (const equipment of previous.context.strength_catalog.equipment) {
    assert.deepEqual(
      catalog.equipment.find((e) => e.id === equipment.id),
      equipment,
    );
  }
});

test("a declared frame extends pull-ups, a generic rack does not, and old bar names stay exact", () => {
  const exercises = (resources) =>
    matchingExercises(catalog, resources).map((e) => e.id);
  assert(exercises(["Nyújtó"]).includes("pullup"));
  assert(exercises(["Húzódzkodó rúd"]).includes("pullup"));
  assert(!exercises(["Erőkeret / guggolókeret"]).includes("pullup"));
  assert(!exercises(["Bordásfal"]).includes("pullup"));
  assert(exercises(["Bordásfal"]).includes("hanging_knee_raise"));
  assert(!exercises(["Bordásfal"]).includes("wall_bars_supported_squat"));
  assert(
    exercises(["Bordásfal", "Szabad padlófelület"]).includes(
      "wall_bars_supported_squat",
    ),
  );
  assert.deepEqual(
    selectedEquipment(catalog, ["Húzódzkodó rúd"]).map((e) => e.id),
    ["pullup_bar"],
  );
  const original = ["Húzódzkodó rúd", "Saját fogantyú, régi névvel"];
  assert.deepEqual(toggleEquipment(catalog, original, "pullup_frame", true), [
    ...original,
    "Nyújtó / húzódzkodó keret",
  ]);
  assert.deepEqual(original, ["Húzódzkodó rúd", "Saját fogantyú, régi névvel"]);
});

test("wall-bar context cannot acquire another location's frame or a lookalike manufacturer host", async () => {
  const value = structuredClone(fixture.context);
  value.strength_options[1].equipment_ids.push("pullup_frame");
  await assert.rejects(readOptionsContext(value));
  const changed = structuredClone(catalog);
  changed.sources.push({
    title: "Lookalike host",
    url: "https://www.nohrd.com.foreign.invalid/wallbars/",
  });
  const raw = { ...changed };
  delete raw.content_hash;
  changed.content_hash = await sha(raw);
  await assert.rejects(readStrengthCatalog(changed));
});

test("both new illustrated checkboxes are visible in the initial equipment view", () => {
  const html = renderToStaticMarkup(
    React.createElement(Picker, {
      catalog,
      resources: ["Húzódzkodó rúd"],
      onChange() {},
    }),
  );
  assert.match(html, /Bordásfal/);
  assert.match(html, /Nyújtó \/ húzódzkodó keret/);
  assert.equal(
    (html.match(/class="pt-equipment-card"/g) ?? []).length,
    catalog.equipment.length,
  );
  for (const id of ["wall_bars", "pullup_frame"]) {
    assert(
      equipmentIllustrationIds.includes(
        catalog.equipment.find((e) => e.id === id).illustration,
      ),
    );
  }
});
