import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const f = JSON.parse(
  readFileSync(new URL("./fixtures/guided-strength.json", import.meta.url)),
);
const { readContext, readReceipt, readPending, readCommand, key, readDraft } =
  load("src/lib/guided-strength/contracts.ts");
const { readTrainingReview } = load("src/lib/planning-cycles/training-plan.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const { default: Workspace } = load(
  "src/components/guided-strength/workspace.tsx",
);
const owner = f.ready.athlete_id,
  expected = {
    owner,
    reference: f.plan.program_reference,
    zone: f.plan.timezone_name,
  };
async function hash(v) {
  const { ...body } = v;
  delete body.content_hash;
  v.content_hash = await sha(body);
}
for (const name of ["ready", "active", "resumable", "complete"])
  test(`real owned HTTP ${name} context verifies`, async () => {
    await readContext(f[name]);
  });
for (const name of ["started", "checkpoint", "finished"])
  test(`committed ${name} receipt verifies exact actual command`, async () => {
    await readReceipt(
      f[name],
      owner,
      JSON.stringify(f[name].artifact.proposal),
    );
  });
for (const name of ["pending_review", "plan"])
  test(`planner ${name} verifies occasion proofs and actual workload`, async () => {
    await readTrainingReview(f[name], expected);
  });
test("zero prior references permit prepared baseline without fake weights", () => {
  assert.equal(f.ready.intake.summary.recorded_reference_count, 0);
  assert.equal(f.ready.preparation.fresh_reference_required_to_start, false);
  assert.equal(f.ready.preparation.protocol.numeric_load_prescribed, false);
  assert(
    f.ready.preparation.locations.some((p) => p.entries.some((e) => e.ready)),
  );
});
test("one real occasion becomes two references without changing declared history", () => {
  const a = f.finished.assessment_receipt.artifact;
  assert.equal(a.summary.recorded_reference_count, 2);
  assert.equal(a.proposal.data.experience, "none");
  assert.equal(a.proposal.data.exercises[0].sets[0].load_value, "12.500000");
  assert(
    f.plan.inputs.recent_sessions.some(
      (s) =>
        s.id === f.finished.artifact.result.workout_session_id &&
        s.reference_occasion,
    ),
  );
});
for (const [name, edit] of Object.entries({
  owner: (v) => {
    v.athlete_id = "22222222-2222-4222-8222-222222222222";
  },
  preparation: (v) => {
    v.preparation.protocol.numeric_load_prescribed = true;
  },
  readiness: (v) => {
    v.preparation.locations[0].entries[0].ready = false;
  },
  referenceGate: (v) => {
    v.preparation.fresh_reference_required_to_start = true;
  },
  clock: (v) => {
    v.server_now = "yesterday";
  },
  missingContext: (v) => {
    v.intake = null;
  },
}))
  test(`rejects rehashed ${name} context`, async () => {
    const v = structuredClone(f.ready);
    edit(v);
    await hash(v);
    await assert.rejects(() => readContext(v));
  });
for (const [name, edit] of Object.entries({
  uncommitted: (v) => (v.committed = false),
  request: (v) =>
    (v.artifact.proposal.request_id = "22222222-2222-4222-8222-222222222222"),
  progress: (v) =>
    (v.artifact.proposal.progress.results[0].observations[0].repetitions = 9),
  foreignWorkout: (v) =>
    (v.artifact.result.workout.athlete_id =
      "22222222-2222-4222-8222-222222222222"),
  duration: (v) => (v.artifact.result.workout.duration_sec = 9999),
  extraSet: (v) =>
    v.assessment_receipt.artifact.proposal.data.exercises[0].sets.push(
      v.assessment_receipt.artifact.proposal.data.exercises[0].sets[0],
    ),
  planning: (v) => (v.artifact.planning_authorized = true),
}))
  test(`rejects ${name} completion`, async () => {
    const v = structuredClone(f.finished);
    edit(v);
    await hash(v.artifact);
    await assert.rejects(() =>
      readReceipt(v, owner, JSON.stringify(f.finish_request)),
    );
  });
for (const [name, edit] of Object.entries({
  missingActivity: (v) => (v.inputs.strength_assessment.guided_activities = []),
  foreignProof: (v) =>
    (v.inputs.strength_assessment.guided_activities[0].artifact.athlete_id =
      "22222222-2222-4222-8222-222222222222"),
  unmarked: (v) =>
    delete v.inputs.recent_sessions.find((s) => s.reference_occasion)
      .reference_occasion,
  unknownWorkout: (v) =>
    (v.inputs.recent_sessions[0].id = "22222222-2222-4222-8222-222222222222"),
  missingEvidence: (v) => delete v.inputs.strength_assessment.guided_activities,
}))
  test(`rejects rehashed planner ${name}`, async () => {
    const v = structuredClone(f.plan);
    edit(v);
    await hash(v.inputs);
    await hash(v);
    await assert.rejects(() => readTrainingReview(v, expected));
  });
test("pending exact body is owner-bound and remains byte stable", () => {
  const body = JSON.stringify(f.finish_request),
    p = { version: "guided-strength-pending-v0.1", owner, body };
  assert.deepEqual(readPending(JSON.stringify(p), owner), p);
  assert.throws(() =>
    readPending(JSON.stringify(p), "22222222-2222-4222-8222-222222222222"),
  );
  assert.notEqual(key(owner, "pending"), key("other", "pending"));
});
test("actual zero and unknown stay explicit and booleans are rejected", () => {
  const v = structuredClone(f.finish_request);
  v.progress.results[0].observations[0].repetitions = 0;
  v.progress.results[0].observations[0].rir = "unknown";
  assert.equal(
    readCommand(v).progress.results[0].observations[0].repetitions,
    0,
  );
  v.progress.results[0].observations[0].repetitions = true;
  assert.throws(() => readCommand(v));
});
test("draft is bound to its exact parent revision", () => {
  const command = f.checkpoint_request,
    parent = command.previous_reference;
  const raw = JSON.stringify({
    version: "guided-strength-draft-v0.1",
    owner,
    parent,
    command,
  });
  assert.deepEqual(readDraft(raw, owner, parent), command);
  assert.throws(() =>
    readDraft(raw, owner, {
      artifact_id: "other",
      content_hash: "a".repeat(64),
    }),
  );
});
test("initial render names the live assessment region", () => {
  const html = renderToStaticMarkup(React.createElement(Workspace));
  assert.match(html, /Vezetett kezdő erőfelmérés/);
  assert.match(html, /betöltése/);
});
test("closed proxy allows exact scoped operations and refuses injection", async () => {
  const { forwardGoals } = load("src/lib/planning-goals/proxy.ts");
  const original = globalThis.fetch;
  let called = 0;
  globalThis.fetch = async (url) => {
    called++;
    assert.equal(String(url), "http://backend/api/v1/planning/guided-strength");
    return Response.json({ ok: true });
  };
  try {
    for (const method of ["GET", "POST"]) {
      const request = new Request(
        "https://paddle.test/api/goal-workflow/guided-strength",
        {
          method,
          headers:
            method === "POST"
              ? {
                  Origin: "https://paddle.test",
                  "Content-Type": "application/json",
                }
              : {},
          ...(method === "POST" ? { body: "{}" } : {}),
        },
      );
      assert.equal(
        (await forwardGoals(request, ["guided-strength"], "http://backend"))
          .status,
        200,
      );
    }
    for (const [method, path, url, origin, status] of [
      ["GET", ["guided-strength", "extra"], "", "", 404],
      ["GET", ["guided-strength"], "?x=1", "", 422],
      ["DELETE", ["guided-strength"], "", "", 405],
      ["POST", ["guided-strength"], "", "https://evil.test", 403],
    ]) {
      const request = new Request(
        "https://paddle.test/api/goal-workflow/guided-strength" + url,
        {
          method,
          headers: { Origin: origin, "Content-Type": "application/json" },
          ...(method === "POST" ? { body: "{}" } : {}),
        },
      );
      assert.equal(
        (await forwardGoals(request, path, "http://backend")).status,
        status,
      );
    }
    assert.equal(called, 2);
  } finally {
    globalThis.fetch = original;
  }
});

test("partial numeric fields normalize to unknown without fabricating zero or kilograms", () => {
  const { normalizeCommand } = load("src/lib/guided-strength/contracts.ts");
  const c = structuredClone(f.finish_request),
    s = c.progress.results[0].observations[0];
  s.hold_seconds = "";
  s.repetitions = null;
  s.load_value = "";
  const result = normalizeCommand(c);
  assert.equal(result.progress.results[0].observations[0].hold_seconds, null);
  assert.equal(result.progress.results[0].observations[0].load_value, null);
  assert.equal(s.load_value, "");
});
test("manual civil clocks use the profile zone and reject DST ambiguity", () => {
  const { clockInput, clockInstant } = load(
    "src/components/guided-strength/workspace.tsx",
  );
  assert.equal(
    clockInput("2026-11-06T10:00:00Z", "Europe/Budapest"),
    "2026-11-06T11:00:00",
  );
  assert.equal(
    clockInstant("2026-11-06T11:00:00", "Europe/Budapest"),
    "2026-11-06T10:00:00.000Z",
  );
  assert.throws(() => clockInstant("2026-10-25T02:30:00", "Europe/Budapest"));
  assert.throws(() => clockInstant("2026-03-29T02:30:00", "Europe/Budapest"));
});
