import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/intake-continuation.json", import.meta.url)),
);
const { readContext, readReceipt } = load(
  "src/lib/guided-strength/contracts.ts",
);
const { readAssessmentReceipt } = load(
  "src/lib/initial-assessment/contracts.ts",
);
const { default: Preparation } = load(
  "src/components/guided-strength/preparation.tsx",
);

for (const name of ["blocked", "ready", "active"])
  test(`real HTTP ${name} context verifies across explicit intake continuation`, async () => {
    await readContext(fixture[name]);
  });

test("reviewed intake save retains exercises and zero references before explicit occasion start", async () => {
  await readAssessmentReceipt(
    fixture.saved,
    fixture.blocked.athlete_id,
    JSON.stringify(fixture.request),
  );
  await readReceipt(
    fixture.started,
    fixture.blocked.athlete_id,
    JSON.stringify(fixture.start_request),
  );
  assert.deepEqual(fixture.blocked.preparation.issues, [
    "GUIDED_SOURCES_CHANGED",
    "GUIDED_INTAKE_REVIEW_REQUIRED",
  ]);
  assert.deepEqual(fixture.ready.preparation.issues, []);
  assert.equal(fixture.ready.intake.summary.recorded_reference_count, 0);
  assert.equal(fixture.ready.intake.summary.form_complete, false);
  assert.equal(fixture.ready.latest, null);
  assert.deepEqual(
    fixture.ready.intake.data.exercises,
    fixture.blocked.intake.data.exercises,
  );
});

function props(context = fixture.blocked) {
  return {
    context,
    locked: false,
    place: context.intake.data.default_location_id,
    ids: context.intake.data.exercises.map((e) => e.id),
    mode: "manual",
    precheck: true,
    onPlace() {},
    onIds() {},
    onMode() {},
    onPrecheck() {},
    onBegin() {},
    onResolveIntake() {},
  };
}

test("blocked preparation offers an inline edit action while start remains blocked", () => {
  const html = renderToStaticMarkup(React.createElement(Preparation, props()));
  assert.match(html, /Kezdeti válaszok ellenőrzése és mentése itt/);
  assert.match(html, /A már kiválasztott gyakorlatok megmaradnak/);
  assert.match(html, /<button[^>]*disabled=""[^>]*>Felmérőalkalom indítása/);
});

test("open inline editor replaces its open action and allows reviewing a pending save even after server recovery", () => {
  const open = renderToStaticMarkup(
    React.createElement(Preparation, {
      ...props(),
      intakeEditor: React.createElement(
        "section",
        { "aria-label": "Kezdeti válaszok rendezése" },
        "Menthető válaszok",
      ),
    }),
  );
  assert.match(open, /Menthető válaszok/);
  assert(!open.includes("Kezdeti válaszok ellenőrzése és mentése itt"));
  const ready = renderToStaticMarkup(
    React.createElement(Preparation, props(fixture.ready)),
  );
  assert.match(ready, /Kezdeti válaszok ellenőrzése és mentése itt/);
  assert(!ready.match(/<button[^>]*disabled=""[^>]*>Felmérőalkalom indítása/));
  const readyOpen = renderToStaticMarkup(
    React.createElement(Preparation, {
      ...props(fixture.ready),
      intakeEditor: React.createElement("section", null, "Szerkesztés"),
    }),
  );
  assert.match(
    readyOpen,
    /<button[^>]*disabled=""[^>]*>Felmérőalkalom indítása/,
  );
  assert.match(readyOpen, /A kezdeti válaszok szerkesztője nyitva van/);
});
