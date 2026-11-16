import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const f = JSON.parse(
  readFileSync(new URL("./fixtures/intake-continuation.json", import.meta.url)),
);
const { default: Preview, ExerciseInstructions } = load(
  "src/components/guided-strength/protocol-preview.tsx",
);
const { default: Preparation } = load(
  "src/components/guided-strength/preparation.tsx",
);
const c = f.blocked,
  catalog = c.intake.sources.catalog,
  locationId = c.intake.data.default_location_id;
const ids = c.intake.data.exercises.map((e) => e.id);
const render = (component, props) =>
  renderToStaticMarkup(React.createElement(component, props));
const preview = (selectedIds = ids) =>
  render(Preview, {
    preparation: c.preparation,
    locationId,
    selectedIds,
    catalog,
  });
const props = {
  context: c,
  locked: false,
  place: locationId,
  ids,
  mode: "manual",
  precheck: true,
  onPlace() {},
  onIds() {},
  onMode() {},
  onPrecheck() {},
  onBegin() {},
  onCloseIntake() {},
  intakeEditor: React.createElement("div", null, "Nyitott szerkesztő"),
};

test("current first-reference protocol is visible before start with selected exercises and exact stored ranges", () => {
  const html = preview();
  assert.match(html, /indítás előtt/);
  for (const label of [
    "Fekvenyomás rúddal",
    "Saját testsúlyos guggolás",
    "5–10",
    "3–5",
    "5–8",
    "10–20",
    "2 perc",
  ])
    assert(html.includes(label), label);
  assert.match(html, /1 könnyű sorozat/);
  assert.match(html, /testsúlyod adott/);
  assert.match(html, /külön súlyválasztás nélkül/);
});
test("preview follows explicit selection order and does not assign unselected exercises", () => {
  const html = preview([...ids].reverse());
  assert(
    html.indexOf("1. Saját testsúlyos guggolás") <
      html.indexOf("2. Fekvenyomás rúddal"),
  );
  assert(!html.includes("Csípőemelés rúddal"));
});
test("no selected exercise has an honest empty preview", () => {
  const html = preview([]);
  assert.match(html, /válassz gyakorlatot/);
  assert(!html.includes("1. Fekvenyomás"));
});
test("reference preview explicitly withholds endurance, multi-set tolerance and recovery claims", () => {
  const html = preview();
  assert.match(html, /erőállóképesség/);
  assert.match(html, /több egymást követő sorozat/);
  assert.match(html, /regeneráció ebből még nem állapítható meg/);
});
test("four reported exercises have technique reminders and primary-source links", () => {
  for (const exerciseId of [
    "barbell_benchpress",
    "seal_row_barbell",
    "squat",
    "hanging_leg_raise",
  ]) {
    const html = render(ExerciseInstructions, { exerciseId, catalog });
    assert.match(html, /Végrehajtási emlékeztető/);
    assert.match(html, /<ol>/);
    assert.match(html, /rel="noopener noreferrer"/);
    assert(!html.includes("még nincs külön részletes"));
  }
});
test("unwritten exercise instructions remain explicitly missing rather than receiving another exercise's technique", () => {
  const html = render(ExerciseInstructions, {
    exerciseId: "dumbbell_row",
    catalog,
  });
  assert.match(html, /még nincs külön részletes végrehajtási leírás/);
  assert(!html.includes("Barbell Bench Press"));
  assert.match(html, /Képes segítség/);
});
test("return control and actual missing saved prerequisites appear next to start outside its disabled fieldset", () => {
  const html = render(Preparation, props),
    end = html.lastIndexOf("</fieldset>");
  const tail = html.slice(end);
  assert.match(tail, /Vissza a gyakorlatválasztáshoz/);
  assert(!tail.match(/<button[^>]*disabled=""/));
  assert.match(tail, /A kezdeti felmérés átnézése még nincs mentve/);
  assert.match(tail, /korábbi profilhoz vagy helyszíni adatokhoz/);
});
test("open editor and unresolved prerequisites still prevent automatic start", () => {
  const html = render(Preparation, props);
  assert.match(html, /<button[^>]*disabled=""[^>]*>Felmérőalkalom indítása/);
  const locked = render(Preparation, { ...props, locked: true }).slice(
    html.lastIndexOf("</fieldset>"),
  );
  assert.match(
    locked,
    /<button[^>]*disabled=""[^>]*>Vissza a gyakorlatválasztáshoz/,
  );
});
