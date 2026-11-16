import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/strength-machines.json", import.meta.url)),
);
const previous = JSON.parse(
  readFileSync(new URL("./fixtures/strength-catalog.json", import.meta.url)),
);
const { readStrengthCatalog, matchingExercises, selectedEquipment } = load(
  "src/lib/training-options/strength-catalog.ts",
);
const { readOptionsContext, readOptionsReceipt } = load(
  "src/lib/training-options/contracts.ts",
);
const Picker = load(
  "src/components/training-options/strength-equipment.tsx",
).default;
const { equipmentIllustrationIds } = load(
  "src/components/training-options/equipment-illustration.tsx",
);
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const catalog = fixture.context.strength_catalog;

test("extended real owned context and durable save verify without changing C20.3 declarations", async () => {
  await readOptionsContext(fixture.context);
  await readOptionsReceipt(
    fixture.receipt,
    fixture.context.athlete_id,
    JSON.stringify(fixture.request),
  );
  await readOptionsContext(previous.context);
  for (const equipment of previous.context.strength_catalog.equipment) {
    assert.deepEqual(
      catalog.equipment.find((e) => e.id === equipment.id),
      equipment,
    );
  }
  assert.deepEqual(
    fixture.context.data.locations[0].resources.at(-1),
    "Saját húzógép, külön fogantyúval",
  );
});

test("the default picker exposes machines even when only basic equipment was previously selected", () => {
  const html = renderToStaticMarkup(
    React.createElement(Picker, {
      catalog,
      resources: ["Tornaszőnyeg"],
      onChange() {},
    }),
  );
  assert.equal(
    (html.match(/class="pt-equipment-card"/g) ?? []).length,
    catalog.equipment.length,
  );
  assert.match(html, /aria-label="Eszközcsoportok"/);
  assert.match(html, /Erősítőgépek/);
  assert.match(html, /Mellhezhúzó pad/);
  assert.match(html, /Hack guggoló gép/);
  assert.match(html, /Megjelenítve:/);
  for (const e of catalog.equipment)
    assert(equipmentIllustrationIds.includes(e.illustration), e.id);
});

test("bench pull, pulldown and a generic flat bench remain distinct", () => {
  assert.deepEqual(
    selectedEquipment(catalog, ["Mellhez húzó pad"]).map((e) => e.id),
    ["seal_row_bench"],
  );
  assert(
    !matchingExercises(catalog, ["Vízszintes edzőpad", "Kézisúlyzó"]).some(
      (e) => e.id === "seal_row_dumbbell",
    ),
  );
  assert(
    matchingExercises(catalog, ["Mellhezhúzó pad", "Kézisúlyzó"]).some(
      (e) => e.id === "seal_row_dumbbell",
    ),
  );
  assert(
    !matchingExercises(catalog, ["Mellhezhúzó pad"]).some(
      (e) => e.id === "lat_pulldown",
    ),
  );
});

test("plate-loaded exercises need plates locally and do not replace selectorized declarations", () => {
  const machine = "Evezőgép (tárcsasúlyos)";
  assert(
    !matchingExercises(catalog, [machine]).some(
      (e) => e.id === "plate_loaded_row",
    ),
  );
  assert(
    matchingExercises(catalog, [machine, "Súlytárcsák"]).some(
      (e) => e.id === "plate_loaded_row",
    ),
  );
  assert(
    !matchingExercises(catalog, ["Ülő evezőgép", "Súlytárcsák"]).some(
      (e) => e.id === "plate_loaded_row",
    ),
  );
});

test("unchanged old saved resources never gain newly added machine declarations", () => {
  for (const location of previous.context.data.locations) {
    assert.deepEqual(
      selectedEquipment(catalog, location.resources).map((e) => e.id),
      selectedEquipment(
        previous.context.strength_catalog,
        location.resources,
      ).map((e) => e.id),
    );
  }
  assert.deepEqual(fixture.context.strength_options[1].exercise_ids, []);
});

test("manufacturer source host validation rejects lookalike domains after rehash", async () => {
  const edited = structuredClone(catalog);
  edited.sources.push({
    title: "Foreign host",
    url: "https://eleiko.com.foreign.invalid/catalog",
  });
  const raw = { ...edited };
  delete raw.content_hash;
  edited.content_hash = await sha(raw);
  await assert.rejects(readStrengthCatalog(edited));
});
