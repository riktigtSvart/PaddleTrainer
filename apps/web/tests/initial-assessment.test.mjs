import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/initial-assessment.json", import.meta.url)),
);
const contracts = load("src/lib/initial-assessment/contracts.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const client = load("src/lib/initial-assessment/client.ts");
const { forwardGoals } = load("src/lib/planning-goals/proxy.ts");
const { default: Editor, titles } = load(
  "src/components/initial-assessment/editor.tsx",
);
const owner = fixture.empty.athlete_id;
const pending = {
  version: "initial-assessment-pending-v0.1",
  owner,
  body: JSON.stringify(fixture.request),
};
const hash = async (value) => {
  const body = { ...value };
  delete body.content_hash;
  value.content_hash = await sha(body);
};

test("real Python HTTP sources, complete and partial durable revisions verify independently", async () => {
  for (const name of ["empty", "after", "latest"])
    await contracts.readContext(fixture[name]);
  await contracts.readAssessmentReceipt(fixture.receipt, owner, pending.body);
  assert.equal(fixture.after.summary.form_complete, true);
  assert.equal(fixture.latest.summary.form_complete, false);
  assert.equal(fixture.receipt.artifact.summary.recorded_reference_count, 5);
});

test("zeros, unknowns and exact declared decimal digits survive freezing and pending restoration", () => {
  const data = contracts.readData(fixture.request.data);
  assert.equal(data.exercises[0].sets[0].load_value, "12.500000");
  assert.equal(data.sport_references[0].rpe, 0);
  assert.equal(data.sport_references[0].power_w, "0");
  assert.equal(data.sport_references[0].heart_rate_bpm, null);
  assert.deepEqual(
    contracts.readPending(JSON.stringify(pending), owner),
    pending,
  );
  const draft = structuredClone(data);
  draft.exercises[0].sets[0].load_value = "12.";
  assert.equal(
    contracts.normalizeData(draft).exercises[0].sets[0].load_value,
    "12",
  );
  assert.equal(draft.exercises[0].sets[0].load_value, "12.");
});

test("restored drafts retain their owner, source hash, parent and unfinished fields", () => {
  const saved = {
    version: "initial-assessment-draft-v0.1",
    owner,
    data: fixture.request.data,
    source_hash: fixture.request.source_hash,
    previous_reference: null,
    open: 3,
  };
  const restored = contracts.readDraft(JSON.stringify(saved), owner);
  assert.equal(restored.open, 3);
  assert.deepEqual(restored.data, saved.data);
  assert.throws(() =>
    contracts.readDraft(JSON.stringify(saved), crypto.randomUUID()),
  );
  assert.throws(() =>
    contracts.readPending(JSON.stringify(pending), crypto.randomUUID()),
  );
  saved.previous_reference = {
    artifact_id: `pt-initial-assessment:${"a".repeat(32)}:${"b".repeat(32)}`,
    content_hash: "c".repeat(64),
  };
  assert.throws(() => contracts.readDraft(JSON.stringify(saved), owner));
});

for (const [name, change] of [
  [
    "foreign owner",
    (v) => {
      v.artifact.athlete_id = crypto.randomUUID();
    },
  ],
  [
    "future schema",
    (v) => {
      v.artifact.schema_version = "initial-assessment-v9";
    },
  ],
  [
    "prescription authority",
    (v) => {
      v.artifact.planning_authorized = true;
    },
  ],
  [
    "workout mutation",
    (v) => {
      v.workouts_changed = true;
    },
  ],
  [
    "clinical clearance",
    (v) => {
      v.artifact.clinical_clearance = true;
    },
  ],
  [
    "false usable reference count",
    (v) => {
      v.artifact.summary.recorded_reference_count = 99;
    },
  ],
  [
    "foreign venue",
    (v) => {
      v.artifact.proposal.data.exercises[0].location_id = crypto.randomUUID();
    },
  ],
  [
    "unknown sport",
    (v) => {
      v.artifact.proposal.data.sports[0].sport_key = "FUTURE_SPORT";
    },
  ],
  [
    "wrong movement pattern",
    (v) => {
      v.artifact.proposal.data.exercises[0].exercise_id = "plank";
    },
  ],
  [
    "foreign programme",
    (v) => {
      v.artifact.proposal.data.program_reference.content_hash = "f".repeat(64);
    },
  ],
  [
    "profile gate escalation",
    (v) => {
      v.artifact.snapshot.profile_review.global_entry_gate = "HOLD";
    },
  ],
  [
    "changed saved constraint",
    (v) => {
      v.artifact.snapshot.profile_review.constraints.push({ area: "medical" });
    },
  ],
  [
    "borrowed equipment",
    (v) => {
      v.artifact.snapshot.locations[0].resources.push("Idegen gép");
    },
  ],
  [
    "uncommitted receipt",
    (v) => {
      v.committed = false;
    },
  ],
])
  test(`assessment rejects ${name} after outer rehash`, async () => {
    const v = structuredClone(fixture.receipt);
    change(v);
    await hash(v.artifact);
    await assert.rejects(() => contracts.readAssessmentReceipt(v, owner));
  });

test("validly hashed receipt must still match the exact retained request", async () => {
  const request = structuredClone(fixture.request);
  request.data.state_notes = "Másik kitöltés";
  await assert.rejects(() =>
    contracts.readAssessmentReceipt(
      fixture.receipt,
      owner,
      JSON.stringify(request),
    ),
  );
  const v = structuredClone(fixture.after);
  v.reference.content_hash = "f".repeat(64);
  await hash(v);
  await assert.rejects(() => contracts.readContext(v));
});

test("state changes, stale history, missing data and pain cannot create a usable exercise reference", () => {
  const data = structuredClone(fixture.request.data),
    source = fixture.empty.sources;
  data.exercises[0].sets[0].repetitions = 0;
  data.exercises[1].sets[0].repetitions = null;
  data.exercises[2].sets.push({
    ...data.exercises[2].sets[0],
    id: crypto.randomUUID(),
    symptoms: "pain",
  });
  data.exercises[3].location_id = fixture.empty.sources.locations[2].id;
  data.exercises[4].performed_on = "2026-01-01";
  const summary = contracts.summarize(data, source, fixture.empty.local_today);
  assert(summary.form_complete);
  assert.equal(summary.recorded_reference_count, 0);
  assert.equal(summary.exercise_states[2].state, "avoid");
  data.state_change = "changed";
  assert(
    contracts
      .summarize(data, source, fixture.empty.local_today)
      .exercise_states.every((s) => s.state === "review"),
  );
});

for (const [field, value] of [
  ["load_basis", "assistance"],
  ["repetitions", true],
  ["load_value", "1e3"],
  ["load_value", "-1"],
  ["rir", 0],
])
  test(`strict set input rejects ${field}: ${value}`, () => {
    const data = structuredClone(fixture.request.data);
    data.exercises[0].sets[0][field] = value;
    assert.throws(() => contracts.readData(data));
  });

test("transport retries identical stored bytes, checks completion and never sends on restore", async () => {
  const original = globalThis.fetch,
    sent = [];
  try {
    globalThis.fetch = async (url, init) => {
      sent.push([url, init]);
      if (sent.length === 1) throw Error("network outcome unknown");
      return Response.json(fixture.receipt);
    };
    const restored = contracts.readPending(JSON.stringify(pending), owner);
    assert.equal(sent.length, 0);
    await assert.rejects(() => client.sendAssessment(restored));
    const receipt = await client.sendAssessment(restored);
    assert(receipt.committed);
    assert.equal(sent.length, 2);
    assert(
      sent.every(
        ([url, init]) =>
          url === "/api/goal-workflow/initial-assessment" &&
          init.body === pending.body &&
          init.method === "POST" &&
          init.cache === "no-store",
      ),
    );
    globalThis.fetch = async () =>
      Response.json({ ...fixture.receipt, committed: false });
    await assert.rejects(() => client.sendAssessment(restored));
  } finally {
    globalThis.fetch = original;
  }
});

test("six guided panels expose imported sources, optional references and all fourteen sports", () => {
  const render = (open) =>
    renderToStaticMarkup(
      React.createElement(Editor, {
        context: fixture.empty,
        data: fixture.request.data,
        open,
        onOpen() {},
        onChange() {},
        disabled: false,
      }),
    );
  const all = titles.map((_, i) => render(i));
  assert.equal((all[0].match(/aria-expanded="true"/g) || []).length, 1);
  for (const title of titles) assert(all[0].includes(title));
  for (const sport of fixture.empty.sources.registry.sports)
    assert(all[2].includes(sport.label));
  assert(
    all[2].includes("Kerékpározás") &&
      all[2].includes("Sífutás") &&
      all[2].includes("Foci"),
  );
  assert(all[2].includes("még nincs bekötve"));
  assert(all[3].includes("Gyakorlat hozzáadása"));
  assert(all[4].includes("RPE") && all[4].includes("RIR"));
  assert(
    all[4].includes("&lt;nem új edzés&gt;") &&
      !all[4].includes("<nem új edzés>"),
  );
  assert(all[5].includes("nem ír elő súlyt"));
});

for (const [method, path, query, status] of [
  ["GET", ["initial-assessment"], "", 200],
  ["POST", ["initial-assessment"], "", 200],
  ["GET", ["initial-assessment"], "?owner=x", 422],
  ["POST", ["initial-assessment"], "?url=http://evil.invalid", 422],
  ["DELETE", ["initial-assessment"], "", 405],
  ["GET", ["initial-assessment", "other"], "", 404],
])
  test(`assessment proxy ${method} /${path.join("/")}${query} is scoped`, async () => {
    let calls = 0;
    const send = async (url, init) => {
      calls++;
      assert.equal(
        new URL(url).pathname,
        "/api/v1/planning/initial-assessment",
      );
      if (method === "POST") assert.equal(init.body, pending.body);
      return Response.json(fixture.empty);
    };
    const request = new Request(
      "https://paddle.test/api/goal-workflow/" + path.join("/") + query,
      {
        method,
        headers: {
          Host: "paddle.test",
          Origin: "https://paddle.test",
          "Content-Type": "application/json",
        },
        ...(method === "POST" ? { body: pending.body } : {}),
      },
    );
    const response = await forwardGoals(
      request,
      path,
      "http://127.0.0.1:8000",
      send,
    );
    assert.equal(response.status, status);
    assert.equal(calls, status === 200 ? 1 : 0);
  });

test("assessment proxy retains same-origin protection", async () => {
  let called = false;
  const result = await forwardGoals(
    new Request("https://paddle.test/api/goal-workflow/initial-assessment", {
      method: "POST",
      headers: {
        Host: "paddle.test",
        Origin: "https://foreign.test",
        "Content-Type": "application/json",
      },
      body: pending.body,
    }),
    ["initial-assessment"],
    "http://127.0.0.1:8000",
    async () => {
      called = true;
      return Response.json({});
    },
  );
  assert.equal(result.status, 403);
  assert.equal(called, false);
});
