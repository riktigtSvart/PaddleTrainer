import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/training-plan.json", import.meta.url)),
);
const { readTrainingReview, readTrainingPending, sendTraining } = load(
  "src/lib/planning-cycles/training-plan.ts",
);
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const expected = {
  owner: fixture.review.athlete_id,
  reference: fixture.review.program_reference,
  zone: fixture.review.timezone_name,
};
async function sign(value) {
  const { content_hash, ...body } = value;
  return { ...body, content_hash: await sha(body) };
}

test("real Python review verifies its ownership, capture, candidates and explicit acceptance scope", async () => {
  const v = await readTrainingReview(fixture.review, expected);
  assert.equal(v.result.create.length, 3);
  assert.equal(v.result.automatic_plan_mutation, false);
  assert.equal(v.result.personal_model_applied, false);
  const after = await readTrainingReview(fixture.after_review, expected);
  assert.equal(after.result.create.length, 0);
  assert.equal(after.result.keep.length, 3);
});
for (const [name, change] of [
  ["foreign owner", (v) => (v.athlete_id = "other")],
  ["foreign programme", (v) => (v.program_id = "pt-cycle:" + "f".repeat(64))],
  ["timezone drift", (v) => (v.timezone_name = "UTC")],
  [
    "unexpected automatic mutation",
    (v) => (v.result.automatic_plan_mutation = true),
  ],
  [
    "unexpected personal response claim",
    (v) => (v.result.personal_model_applied = true),
  ],
  ["bypassed approval", (v) => (v.requires_explicit_acceptance = false)],
  [
    "unknown cancellation",
    (v) => v.result.cancel.push("00000000-0000-0000-0000-000000000001"),
  ],
  ["changed dose", (v) => (v.result.proposals[0].duration_sec = 99999)],
  ["missing candidate", (v) => v.result.proposals.pop()],
  [
    "blocker with a prescription",
    (v) => v.result.blockers.push("PROFILE_REVIEW_REQUIRED"),
  ],
])
  test(
    "reject " + name + " even when the outer response is rehashed",
    async () => {
      const v = structuredClone(fixture.review);
      change(v);
      await assert.rejects(readTrainingReview(await sign(v), expected));
    },
  );
test("an unacknowledged changed response cannot pass its original hash", async () => {
  const v = structuredClone(fixture.review);
  v.created_at = "2026-10-23T13:00:00Z";
  await assert.rejects(readTrainingReview(v, expected));
});
test("pending request restores the exact body but never sends on restore", () => {
  const pending = {
    owner: expected.owner,
    program: expected.reference.artifact_id,
    operation: "accept",
    body: JSON.stringify({
      request_id: "00000000-0000-0000-0000-000000180401",
      review_reference: {
        artifact_id: fixture.review.artifact_id,
        content_hash: fixture.review.content_hash,
      },
      acknowledge_reviewed_plan: true,
    }),
  };
  assert.deepEqual(
    readTrainingPending(
      JSON.stringify(pending),
      expected.owner,
      pending.program,
    ),
    pending,
  );
  assert.throws(() =>
    readTrainingPending(JSON.stringify(pending), "other", pending.program),
  );
});
test("acceptance receipt must match the exact retained request", async () => {
  const p = fixture.receipt.artifact.proposal;
  const { program_id, ...body } = p;
  const pending = {
    owner: expected.owner,
    program: program_id,
    operation: "accept",
    body: JSON.stringify(body),
  };
  const previous = globalThis.fetch;
  try {
    globalThis.fetch = async () => Response.json(fixture.receipt);
    assert.equal(
      (await sendTraining(pending)).artifact_id,
      fixture.receipt.artifact.artifact_id,
    );
    await assert.rejects(
      sendTraining({
        ...pending,
        body: JSON.stringify({
          ...body,
          request_id: "00000000-0000-0000-0000-000000999999",
        }),
      }),
    );
  } finally {
    globalThis.fetch = previous;
  }
});
test("panel offers an explicit first proposal without automatically writing a plan", () => {
  const { TrainingPlanPanel } = load(
    "src/components/planning-cycles/training-plan.tsx",
  );
  const html = renderToStaticMarkup(
    React.createElement(TrainingPlanPanel, {
      owner: expected.owner,
      reference: expected.reference,
      zone: expected.zone,
      today: "2026-10-23",
    }),
  );
  assert.match(html, /Edzésterv és újraértékelés/);
  assert.match(html, /Tervjavaslat készítése/);
  assert.doesNotMatch(html, /Változtatások elfogadása/);
});
test("proxy permits only the scoped training plan methods and rejects query or origin injection", async () => {
  const { forwardGoals } = load("src/lib/planning-goals/proxy.ts");
  const base = [
    "cycles",
    "programs",
    expected.reference.artifact_id,
    "training-plan",
  ];
  for (const operation of ["review", "accept", "missed"]) {
    let sent;
    const path = [...base, operation];
    const response = await forwardGoals(
      new Request("http://localhost:3000/api/x", {
        method: "POST",
        body: "{}",
        headers: {
          Origin: "http://localhost:3000",
          "Content-Type": "application/json",
        },
      }),
      path,
      "http://api.invalid",
      async (url, init) => {
        sent = { url: String(url), init };
        return Response.json({});
      },
    );
    assert.equal(response.status, 200);
    assert.ok(sent.url.endsWith("/" + operation));
    assert.equal(sent.init.body, "{}");
    assert.equal(sent.init.headers.Authorization, undefined);
  }
  for (const [path, method, query, origin, status] of [
    [base, "POST", "", "http://localhost:3000", 405],
    [[...base, "accept"], "GET", "", "http://localhost:3000", 405],
    [[...base, "accept"], "POST", "?owner=other", "http://localhost:3000", 422],
    [[...base, "accept"], "POST", "", "http://foreign.invalid", 403],
    [[...base, "delete"], "POST", "", "http://localhost:3000", 404],
  ]) {
    const response = await forwardGoals(
      new Request("http://localhost:3000/api/x" + query, {
        method,
        headers: { Origin: origin, "Content-Type": "application/json" },
      }),
      path,
      "http://api.invalid",
      async () => {
        throw Error("must not forward");
      },
    );
    assert.equal(response.status, status);
  }
});
