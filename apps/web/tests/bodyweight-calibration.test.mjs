import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const f = JSON.parse(gunzipSync(readFileSync(new URL("./fixtures/calibration-bodyweight.json.gz", import.meta.url))));
const { readContext, readReceipt } = load("src/lib/guided-strength/contracts.ts");
const { protocolFor, newMeasurement, selectedProtocols, forMeasurementMode } = load("src/lib/guided-strength/calibration.ts");
const { default: Movement, CalibrationInstructions } = load("src/components/guided-strength/calibration-movement.tsx");
const { default: Preparation } = load("src/components/guided-strength/preparation.tsx");
const owner = f.ready.athlete_id;

test("current Python contexts and saved bodyweight results verify alongside the released C20.7 fixtures", async () => {
  await readContext(f.ready);
  await readContext(f.complete);
  for (const receipt of [f.started, f.finished]) {
    await readReceipt(receipt, owner, JSON.stringify(receipt.artifact.proposal));
  }
});

test("nineteen bodyweight cards measure the selected movement without a ten-repetition load target", () => {
  const cards = f.ready.calibration_protocols.entries.filter((p) => p.family === "bodyweight_repetitions");
  assert.equal(cards.length, 19);
  for (const p of cards) {
    assert.equal(p.planned_measurement.target_repetitions, null);
    assert.equal(p.planned_measurement.repetition_cap, 12);
    assert(p.steps.join(" ").includes("nincs elérendő célismétlésszám"));
    assert(!p.steps.join(" ").includes("körülbelül 10"));
  }
});

test("bodyweight result form defaults to no external weight and keeps actual zero distinct from unknown mass", () => {
  const protocol = protocolFor("squat");
  const observation = newMeasurement(protocol, f.ready.local_today);
  assert.equal(observation.load_kind, "bodyweight");
  assert.equal(observation.load_value, null);
  const row = { entry_id: "test", state: "pending", side: "both", machine_note: "", note: "", observations: [] };
  const html = renderToStaticMarkup(React.createElement(Movement, { row, protocol, today: f.ready.local_today, mode: "calibration", onChange() {}, onSave() {} }));
  assert(html.includes("Saját testsúly · külső súly nélkül"));
  assert(html.includes("Nem kell terhelést vagy kg-értéket választanod."));
  assert(!html.includes("Tényleges terhelés (kg)"));
  assert.match(html, /<details><summary>Eltérő terheléssel elvégzett próba adatai<\/summary>[\s\S]*A használt terhelés típusa[\s\S]*<\/details>/);
});

test("a cap-terminated bodyweight record keeps twelve and its reserve without claiming a maximum", () => {
  const row = f.finished.artifact.proposal.progress.results[1];
  const protocol = f.started.artifact.measurement_protocols.entries.find((v) => v.entry_id === row.entry_id).protocol;
  const html = renderToStaticMarkup(React.createElement(Movement, { row, protocol, today: f.ready.local_today, mode: "calibration", onChange() {}, onSave() {} }));
  assert(html.includes("12 ismétlés"));
  assert(html.includes("legalább 5"));
  assert(html.includes("A maximális ismétlésszámod ebből még nem derül ki."));
  assert.equal(row.observations[0].load_value, null);
});

test("bodyweight repeatability uses the same fixed variation and matches the frozen Python snapshot", async () => {
  const ids = f.started.artifact.proposal.selected_entry_ids;
  const snapshot = await selectedProtocols(f.ready.intake.data, ids, "repeatability", f.ready.calibration_protocols.content_hash);
  assert.deepEqual(snapshot, f.repeated_snapshot);
  const bodyweight = snapshot.entries.find((v) => v.protocol.family === "bodyweight_repetitions").protocol;
  assert(bodyweight.steps[0].includes("saját testsúlyos"));
  const weighted = forMeasurementMode(protocolFor("dumbbell_row"), "repeatability");
  assert(weighted.steps[0].includes("ismert terhelést"));
});

test("rendering an active occasion uses its frozen instructions rather than rewriting its bank", () => {
  const protocol = structuredClone(f.repeated_snapshot.entries[0].protocol);
  protocol.steps[0] = "Az alkalomhoz rögzített eredeti utasítás.";
  const html = renderToStaticMarkup(React.createElement(CalibrationInstructions, { protocol, mode: "repeatability" }));
  assert(html.includes(protocol.steps[0]));
});

test("the preparation preview uses the exact bank supplied with its context", () => {
  const ids = f.started.artifact.proposal.selected_entry_ids;
  const html = renderToStaticMarkup(React.createElement(Preparation, { context: f.ready, locked: false, place: f.started.artifact.proposal.location_id, ids, mode: "manual", checked: true, measurementMode: "calibration", onMeasurementMode() {}, onPlace() {}, onIds() {}, onMode() {}, onChecked() {}, onStart() {}, onResolveIntake() {} }));
  assert(html.includes("nincs elérendő célismétlésszám"));
  assert(html.includes("a maximális ismétlésszámod még nem ismert"));
});

test("an already active old-bank bodyweight occasion displays corrected instructions without changing its stored snapshot", () => {
  const legacy = JSON.parse(gunzipSync(readFileSync(new URL("./fixtures/calibration-strength.json.gz", import.meta.url))));
  const protocol = legacy.started.artifact.measurement_protocols.entries.find((e) => e.protocol.family === "bodyweight_repetitions").protocol;
  const before = JSON.stringify(protocol);
  assert(protocol.steps.join(" ").includes("körülbelül 10"));
  const html = renderToStaticMarkup(React.createElement(CalibrationInstructions, { protocol, mode: "calibration" }));
  assert(!html.includes("körülbelül 10"));
  assert(html.includes("A saját testsúlyod adott."));
  assert(html.includes("nincs elérendő célismétlésszám"));
  assert.equal(JSON.stringify(protocol), before);
});
