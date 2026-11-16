import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const f = JSON.parse(
  readFileSync(new URL("./fixtures/guided-preparation.json", import.meta.url)),
);
const { readContext, prepare } = load("src/lib/guided-strength/contracts.ts");
const {
  choiceState,
  startIssues,
  requestedStep,
  preparationLocation,
  retainedChoices,
} = load("src/lib/guided-strength/preparation.ts");
const { default: Preparation } = load(
  "src/components/guided-strength/preparation.tsx",
);
function props(context = f.blocked) {
  return {
    context,
    locked: false,
    place: context.intake.data.default_location_id,
    ids: [],
    mode: "manual",
    precheck: true,
    onPlace() {},
    onIds() {},
    onMode() {},
    onPrecheck() {},
    onBegin() {},
  };
}
const render = (p) => renderToStaticMarkup(React.createElement(Preparation, p));
for (const key of ["blocked", "restored"])
  test(`actual Python ${key} preparation remains a valid owned context`, async () => {
    await readContext(f[key]);
  });
test("a global start prerequisite does not prevent selecting individually suitable movements", () => {
  const p = props(),
    place = p.context.preparation.locations.find(
      (l) => l.location_id === p.place,
    ),
    e = place.entries[0];
  assert.equal(e.ready, false);
  assert.deepEqual(e.issues, []);
  assert.equal(choiceState(e, place.entries, []).selectable, true);
  const html = render(p),
    row = html.slice(html.indexOf("pt-guided-choice"));
  assert(!row.slice(0, row.indexOf("</label>")).includes('disabled=""'));
  assert.match(html, /<button[^>]+disabled=""[^>]*>Felmérőalkalom indítása/);
  assert.match(html, /Mi hiányzik még az indításhoz/);
  assert.match(html, /jelenlegi szerepe: szabadidős/);
  assert.match(html, /initial-assessment\?step=3/);
});
test("entry-specific equipment and familiarity problems still disable their own checkboxes", () => {
  const p = props(f.restored),
    place = p.context.preparation.locations.find(
      (l) => l.location_id === p.place,
    );
  for (const code of [
    "GUIDED_EQUIPMENT_MISSING",
    "GUIDED_INSTRUCTION_REQUIRED",
    "GUIDED_COMFORT_REVIEW",
  ]) {
    const entry = { ...place.entries[0], issues: [code], ready: false };
    assert.equal(choiceState(entry, [entry], []).selectable, false);
  }
});
test("duplicate movement pattern has an explicit reason", () => {
  const p = props(f.restored),
    es = p.context.preparation.locations.find(
      (l) => l.location_id === p.place,
    ).entries;
  const duplicate = { ...es[1], pattern: es[0].pattern };
  assert.equal(
    choiceState(duplicate, [es[0], duplicate], [es[0].entry_id]).samePattern,
    true,
  );
});
test("start becomes enabled only after current saved prerequisites and acknowledgement match", () => {
  const p = props(f.restored);
  p.ids = p.context.intake.data.exercises.slice(0, 2).map((e) => e.id);
  let html = render(p),
    button = html.match(/<button[^>]*>Felmérőalkalom indítása/)[0];
  assert(!button.includes('disabled=""'));
  p.precheck = false;
  html = render(p);
  assert(
    html
      .match(/<button[^>]*>Felmérőalkalom indítása/)[0]
      .includes('disabled=""'),
  );
});
for (const mode of ["manual", "device"])
  test(`${mode} explains manual set entry and one whole-workout record`, () => {
    const p = props(f.restored);
    p.mode = mode;
    const html = render(p);
    assert.match(html, /Gyakorlatadatok: mindkét esetben kézzel/);
    assert.match(
      html,
      /Nem várunk az órától gyakorlatfelismerést vagy ismétlésszámlálást/,
    );
    assert.match(html, /szokásos erősítő edzés elején/);
    assert.match(html, /az indítás után tudod beírni/);
    assert.match(html, /Az egész edzés naplózása/);
  });
test("supervision and missing history identify their real saved fields", () => {
  const c = structuredClone(f.restored);
  c.intake.data.experience = "unknown";
  c.intake.data.strength_frequency = "unknown";
  c.intake.data.supervision = "needed";
  c.preparation = prepare(c.intake);
  const issue = startIssues(c).find(
    (i) => i.code === "GUIDED_HISTORY_OR_SUPERVISION_REVIEW",
  );
  assert.equal(issue.href, "/initial-assessment?step=2");
  assert(issue.details.some((t) => t.includes("tapasztalat")));
  assert(issue.details.some((t) => t.includes("gyakoriság")));
  assert(issue.details.some((t) => t.includes("Betanuláshoz segítségre")));
});
test("profile constraints are reported as unsupported adaptations, not a missing consent checkbox", () => {
  const c = structuredClone(f.restored);
  c.intake.sources.profile_review.global_entry_gate = "OPEN_WITH_CONSTRAINTS";
  c.preparation = prepare(c.intake);
  const issue = startIssues(c).find((i) => i.code === "GUIDED_STATE_REVIEW");
  assert.equal(issue.href, "/athlete-setup");
  assert(issue.details.some((t) => t.includes("nem kezeli")));
});
test("source and review problems link to explicit existing save actions", () => {
  const c = structuredClone(f.restored);
  c.intake.sources_changed = true;
  c.intake.data.reviewed = false;
  c.preparation = prepare(c.intake);
  const issues = startIssues(c);
  assert(
    issues.some((i) =>
      i.details.some((d) =>
        d.includes("Friss források és mentési alap átvétele"),
      ),
    ),
  );
  assert(issues.every((i) => i.href === "/initial-assessment?step=6"));
});
test("step links select the actual 1–6 editor panel and reject arbitrary input", () => {
  for (let i = 1; i <= 6; i++) assert.equal(requestedStep("?step=" + i), i - 1);
  for (const q of ["", "?step=0", "?step=7", "?step=abc", "?step=1.5"])
    assert.equal(requestedStep(q), null);
});
test("refresh preserves only still available distinct choices and falls back to a real strength venue", () => {
  const c = structuredClone(f.restored),
    place = c.preparation.locations.find(
      (p) => p.location_id === c.intake.data.default_location_id,
    ),
    es = place.entries;
  assert.deepEqual(retainedChoices(es, [es[0].entry_id, es[1].entry_id]), [
    es[0].entry_id,
    es[1].entry_id,
  ]);
  es[0].issues = ["GUIDED_EQUIPMENT_MISSING"];
  assert.deepEqual(
    retainedChoices(es, [es[0].entry_id, es[1].entry_id, "missing"]),
    [es[1].entry_id],
  );
  c.intake.data.default_location_id = "not-a-strength-venue";
  assert.equal(preparationLocation(c), c.preparation.locations[0].location_id);
});
