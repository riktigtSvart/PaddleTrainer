import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/prescriptions.json", import.meta.url)),
);
const { readTrainingReview } = load("src/lib/planning-cycles/training-plan.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const { dayReason } = load("src/lib/planning-cycles/plan-view.ts");
const { PrescriptionDetails } = load(
  "src/components/planning-cycles/plan-output.tsx",
);
const { PreparationChecklist } = load(
  "src/components/planning-cycles/training-plan-feedback.tsx",
);
const expected = {
  owner: fixture.running.athlete_id,
  reference: fixture.running.program_reference,
  zone: fixture.running.timezone_name,
};

async function hash(value) {
  const body = { ...value };
  delete body.content_hash;
  value.content_hash = await sha(body);
  return value;
}
async function editCandidate(value, edit) {
  const original = value.result.proposals[0],
    oldKey = original.candidate_key;
  const body = structuredClone(original);
  delete body.candidate_key;
  edit(body);
  const key = await sha(body),
    changed = { ...body, candidate_key: key };
  for (const field of ["proposals", "create"])
    value.result[field] = value.result[field].map((c) =>
      c.candidate_key === oldKey ? changed : c,
    );
  for (const group of value.result.alternatives) {
    group.candidates = group.candidates.map((c) =>
      c.candidate_key === oldKey ? changed : c,
    );
    for (const field of ["recommended_candidate_key", "selected_candidate_key"])
      if (group[field] === oldKey) group[field] = key;
  }
  const meta = value.result.prescription_context.by_candidate;
  meta[key] = meta[oldKey];
  meta[key].duration_sec = body.duration_sec;
  delete meta[oldKey];
}

test("all real HTTP parameterized reviews retain owned sources, doses and starting budgets", async () => {
  for (const value of Object.values(fixture))
    await readTrainingReview(value, expected);
  assert.equal(fixture.personal.result.preparation.max_sessions_per_7_days, 4);
  assert.equal(fixture.personal.result.preparation.max_minutes_per_7_days, 240);
  assert(
    fixture.running.result.proposals.every(
      (c) => c.sport === "RUNNING" && c.duration_sec === 1500,
    ),
  );
});

const cases = {
  "foreign captured owner": (v) => (v.inputs.athlete_id = "foreign-owner"),
  "different captured timezone": (v) => (v.inputs.timezone_name = "UTC"),
  "unknown prescription schema": (v) =>
    (v.result.prescription_context.schema_version = "future"),
  "missing provenance for v2": (v) => delete v.result.prescription_context,
  "foreign duration reference": (v) =>
    (Object.values(
      v.result.prescription_context.by_candidate,
    )[0].reference_session_ids = ["foreign"]),
  "fabricated reference cap": (v) =>
    (Object.values(
      v.result.prescription_context.by_candidate,
    )[0].reference_cap_seconds = 9999),
  "personal intensity claim": (v) =>
    (Object.values(
      v.result.prescription_context.by_candidate,
    )[0].intensity_basis = "personal_threshold"),
  "hidden progression": (v) =>
    (Object.values(
      v.result.prescription_context.by_candidate,
    )[0].progression_applied = true),
  "missing candidate provenance": (v) =>
    delete v.result.prescription_context.by_candidate[
      v.result.proposals[0].candidate_key
    ],
  "unearned larger budget": (v) =>
    (v.result.preparation.max_sessions_per_7_days = 7),
  "omitted covered-week census": (v) =>
    v.result.prescription_context.starting_budget.weeks.pop(),
  "invented duration in an uncovered week": (v) =>
    (v.result.prescription_context.starting_budget.weeks[0].duration_sec = 0),
  "running borrows kayak history": (v) =>
    (v.inputs.recent_sessions[0].sport = "KAYAK"),
  "invalid completed reference": (v) =>
    (v.inputs.recent_sessions[0].duration_sec = 20000),
};
for (const [name, edit] of Object.entries(cases))
  test(`parameter validation rejects ${name} after outer rehash`, async () => {
    const value = structuredClone(fixture.running);
    edit(value);
    await assert.rejects(readTrainingReview(await hash(value), expected));
  });

for (const problem of [
  "absent source",
  "changed proof",
  "unknown week total",
  "false personal mode",
  "omitted empty week",
])
  test(`starting budget rejects ${problem}`, async () => {
    const value = structuredClone(fixture.personal),
      budget = value.result.prescription_context.starting_budget;
    if (problem === "absent source")
      value.result.execution_reconciliation.sync_windows = [];
    else if (problem === "changed proof")
      budget.weeks.find(
        (w) => w.status === "covered",
      ).source_reference.content_hash = "f".repeat(64);
    else if (problem === "unknown week total")
      budget.weeks.find((w) => w.status === "covered").duration_sec = null;
    else if (problem === "false personal mode")
      budget.mode = "declared_and_product_defaults";
    else budget.weeks.splice(0, 1);
    await assert.rejects(readTrainingReview(await hash(value), expected));
  });

test("rehashing a longer candidate and its metadata cannot bypass the own reference", async () => {
  const value = structuredClone(fixture.running);
  await editCandidate(value, (c) => {
    c.duration_sec = 2700;
    c.end_at = new Date(
      Date.parse(c.start_at) + c.duration_sec * 1000,
    ).toISOString();
    c.blocks[1].duration_sec = 2100;
  });
  await assert.rejects(readTrainingReview(await hash(value), expected));
});
test("a block sum different from the candidate duration is rejected with valid hashes", async () => {
  const value = structuredClone(fixture.running);
  await editCandidate(value, (c) => (c.blocks[1].duration_sec += 300));
  await assert.rejects(readTrainingReview(await hash(value), expected));
});
test("strength cannot acquire a fabricated weight", async () => {
  const value = structuredClone(fixture.strength);
  Object.values(value.result.prescription_context.by_candidate).find(
    (m) => m.strength,
  ).strength.load_kg = 15;
  await assert.rejects(readTrainingReview(await hash(value), expected));
});

test("duration and intensity explanations expose actual references as escaped links", () => {
  const value = structuredClone(fixture.running),
    candidate = value.result.proposals[0];
  value.inputs.recent_sessions[0].name = "<script>unsafe</script>";
  const html = renderToStaticMarkup(
    React.createElement(PrescriptionDetails, {
      review: value,
      candidateKey: candidate.candidate_key,
    }),
  );
  assert.match(html, /35 perc/);
  assert.match(html, /RPE 2–3/);
  assert.match(html, /\/sessions\//);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});
test("starting budget explains verified weeks and running does not request equipment", () => {
  const running = renderToStaticMarkup(
    React.createElement(PreparationChecklist, { review: fixture.running }),
  );
  assert.match(running, /futáshoz nem kérünk külön eszközlistát/);
  assert.match(running, /\/training-options\/locations/);
  assert.match(running, /\/training-options\/schedule/);
  const personal = renderToStaticMarkup(
    React.createElement(PreparationChecklist, { review: fixture.personal }),
  );
  assert.match(
    personal,
    /két közelmúltbeli, szinkronnal ellenőrzött teljes hét/,
  );
  assert.match(personal, /2026-10-05/);
  assert.match(personal, /240/);
});
test("usable running days excluded by budget or spacing are displayed as rest", () => {
  const day = fixture.running.result.days_without_proposal.find(
    (d) => d.reason === "PLANNED_RECOVERY_DAY",
  );
  assert(day);
  assert.equal(dayReason(fixture.running, day.date).label, "Pihenőnap");
  const missing = fixture.missing.result.preparation.selection_issues.flatMap(
    (i) => i.codes,
  );
  assert(missing.includes("PERSONAL_DURATION_REFERENCE_MISSING"));
  assert(!missing.includes("EQUIPMENT_NOT_DECLARED"));
});
