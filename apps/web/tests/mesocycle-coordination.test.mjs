import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(
  readFileSync(
    new URL("./fixtures/mesocycle-coordination.json", import.meta.url),
  ),
);
const { readTrainingReview, reviewTraining } = load(
  "src/lib/planning-cycles/training-plan.ts",
);
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const Summary = load(
  "src/components/planning-cycles/mesocycle-summary.tsx",
).default;
const { PrescriptionDetails } = load(
  "src/components/planning-cycles/plan-output.tsx",
);
const expected = {
  owner: fixture.first.athlete_id,
  reference: fixture.first.program_reference,
  zone: fixture.first.timezone_name,
};
async function rehash(value) {
  const body = { ...value };
  delete body.content_hash;
  value.content_hash = await sha(body);
  return value;
}

test("real owned reviews validate short, coordinated, frozen and advanced cycle contexts", async () => {
  for (const value of Object.values(fixture))
    await readTrainingReview(value, expected);
  assert.equal(fixture.short.coordinate_mesocycles, false);
  assert.equal(fixture.first.coordinate_mesocycles, true);
  assert.equal(
    fixture.frozen.calibration_review.artifact_id,
    fixture.first.artifact_id,
  );
  assert(
    fixture.first.result.mesocycle_coordination.blocks.some(
      (b) => b.kind === "consolidation",
    ),
  );
});
const invalid = {
  "future schema": (v) =>
    (v.result.mesocycle_coordination.schema_version = "future"),
  "missing coordination": (v) => delete v.result.mesocycle_coordination,
  "wrong rule version": (v) =>
    (v.result.mesocycle_coordination.rules_version = "future"),
  "authority claim": (v) =>
    (v.result.mesocycle_coordination.above_starting_budget_allowed = true),
  "personal response claim": (v) =>
    (v.result.mesocycle_coordination.personal_response_model_applied = true),
  "intensity progression claim": (v) =>
    (v.result.mesocycle_coordination.intensity_progression_applied = true),
  "omitted week": (v) => v.result.mesocycle_coordination.blocks.pop(),
  "changed saved boundary": (v) =>
    (v.result.mesocycle_coordination.blocks[0].start_date = "2026-10-25"),
  "duplicate week": (v) =>
    v.result.mesocycle_coordination.blocks.push(
      v.result.mesocycle_coordination.blocks[0],
    ),
  "invented larger block budget": (v) =>
    (v.result.mesocycle_coordination.blocks[0].max_minutes = 600),
  "invented larger block count": (v) =>
    (v.result.mesocycle_coordination.blocks[0].max_sessions = 7),
  "changed next-cycle horizon": (v) =>
    (v.result.mesocycle_coordination.recommended_end_date = "2027-12-31"),
  "calendar alignment substituted": (v) =>
    (v.result.mesocycle_coordination.date_basis = "monday"),
  "missing explicit scope mode": (v) => delete v.coordinate_mesocycles,
  "false short mode": (v) => (v.coordinate_mesocycles = false),
};
for (const [name, edit] of Object.entries(invalid))
  test(`rejects ${name} after outer rehash`, async () => {
    const value = structuredClone(fixture.first);
    edit(value);
    await assert.rejects(readTrainingReview(await rehash(value), expected));
  });
for (const problem of [
  "foreign owner",
  "future source",
  "nested base",
  "missing source",
  "edited source",
  "foreign current capture",
])
  test(`frozen reference rejects ${problem}`, async () => {
    const value = structuredClone(fixture.frozen),
      source = value.calibration_review;
    if (problem === "foreign owner") source.athlete_id = "foreign";
    else if (problem === "future source")
      source.created_at = "2099-01-01T00:00:00Z";
    else if (problem === "nested base")
      source.calibration_review = structuredClone(fixture.first);
    else if (problem === "missing source") delete value.calibration_review;
    else if (problem === "edited source")
      source.inputs.recent_sessions[0].duration_sec = 100;
    else value.inputs.athlete_id = "foreign";
    if (problem !== "edited source" && value.calibration_review)
      await rehash(source);
    await assert.rejects(readTrainingReview(await rehash(value), expected));
  });

test("a rehashed candidate still cannot exceed its cycle-specific duration ceiling", async () => {
  const value = structuredClone(fixture.first),
    old = value.result.proposals.find(
      (c) =>
        c.template_key === "KAYAK_EASY_TECHNICAL" && c.duration_sec === 2100,
    );
  assert(old);
  const body = structuredClone(old);
  delete body.candidate_key;
  body.duration_sec = 2700;
  body.end_at = new Date(Date.parse(body.start_at) + 2700000).toISOString();
  body.blocks[1].duration_sec += 600;
  const key = await sha(body),
    changed = { ...body, candidate_key: key };
  for (const field of ["proposals", "create"])
    value.result[field] = value.result[field].map((c) =>
      c.candidate_key === old.candidate_key ? changed : c,
    );
  for (const group of value.result.alternatives) {
    group.candidates = group.candidates.map((c) =>
      c.candidate_key === old.candidate_key ? changed : c,
    );
    for (const field of ["recommended_candidate_key", "selected_candidate_key"])
      if (group[field] === old.candidate_key) group[field] = key;
  }
  const meta = value.result.prescription_context.by_candidate;
  meta[key] = { ...meta[old.candidate_key], duration_sec: 2700 };
  delete meta[old.candidate_key];
  await assert.rejects(readTrainingReview(await rehash(value), expected));
});
test("summary exposes real weeks, caps, goals and the unchanged starting basis", () => {
  const value = structuredClone(fixture.frozen),
    period = value.inputs.periods.find((p) => p.period_type === "MESOCYCLE");
  period.title = "<script>unsafe</script>";
  const html = renderToStaticMarkup(
    React.createElement(Summary, { review: value }),
  );
  assert.match(html, /Rögzített ciklusalap/);
  assert.match(html, /Könnyebb szakasz/);
  assert.match(html, /125 perc/);
  assert.match(html, /140 perc/);
  assert.match(html, /Felső keret/);
  assert.match(html, /Következő szakasz/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  const candidate = value.result.proposals[0];
  const card = renderToStaticMarkup(
    React.createElement(PrescriptionDetails, {
      review: value,
      candidateKey: candidate.candidate_key,
    }),
  );
  assert.match(card, /ciklus kiindulópontján/);
  assert.match(card, /\/sessions\//);
});
test("short review clearly points to the explicit cycle coordination action", () => {
  const html = renderToStaticMarkup(
    React.createElement(Summary, { review: fixture.short }),
  );
  assert.match(html, /rövid dátumablak/);
  assert.match(html, /Ciklusok összehangolása/);
  assert.doesNotMatch(html, /<table/);
});
test("explicit coordination transport sends the exact range and mode without accepting workouts", async () => {
  const fetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ review: fixture.first }), {
      status: 200,
    });
  };
  try {
    await reviewTraining(
      expected,
      fixture.first.start_date,
      fixture.first.end_date,
      undefined,
      true,
    );
    assert.equal(calls.length, 1);
    assert.match(String(calls[0].url), /training-plan\/review$/);
    assert.deepEqual(JSON.parse(calls[0].options.body), {
      start_date: fixture.first.start_date,
      end_date: fixture.first.end_date,
      coordinate_mesocycles: true,
    });
  } finally {
    globalThis.fetch = fetch;
  }
});
