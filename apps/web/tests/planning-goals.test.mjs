import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";
const nativeRequire = createRequire(import.meta.url);
const awaitImportReact = () => nativeRequire("react");
const awaitImportReactServer = () => nativeRequire("react-dom/server");
import { load } from "./load-goal-modules.mjs";

const {
  decimal,
  utcInput,
  lines,
  prepareRequest,
  readPending,
  readReceipt,
  readPage,
} = load("src/lib/planning-goals/contracts.ts");
const { macroProposal, protocolProposal, measurementProposal } = load(
  "src/lib/planning-goals/forms.ts",
);
const { forwardGoals } = load("src/lib/planning-goals/proxy.ts");
const { reasonLabel } = load("src/lib/planning-goals/labels.ts");
const { sendPending } = load("src/lib/planning-goals/client.ts");
const roles = [
  "primary_development",
  "secondary_development",
  "maintenance",
  "permitted_decline",
];
const ref = {
  artifact_id: "pt-goal:" + "a".repeat(64),
  content_hash: "b".repeat(64),
};
const period = { id: "33333333-3333-4333-8333-333333333333" };
const child = { id: "44444444-4444-4444-8444-444444444444" };
const catalog = {
  capabilities: ["VO2_CAPACITY"],
  goal_roles: roles,
  metrics: [
    {
      capability_key: "VO2_CAPACITY",
      metric_key: "VO2MAX_ABSOLUTE",
      unit: "L/min",
      scale: "ratio",
      evidence_kind: "physiological_measurement",
      primary_endpoint_eligible: true,
    },
  ],
};
function form(values) {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.append(key, value);
  return data;
}
function envelope() {
  return {
    identity_scope: "APPLICATION_DEMO_USER",
    committed: true,
    reused: false,
    measurement_schedule_preregistered: true,
    durable_available_at: "2026-10-22T10:00:00Z",
    physiological_adaptation_established: false,
    planning_utility_supported: false,
    planning_authorized: false,
    artifact: {
      ...ref,
      schema_version: "macrocycle-capability-plan-v0.1",
      proposal: {},
      authority: {
        shadow_only: true,
        physiological_adaptation_established: false,
        planning_utility_supported: false,
        planning_authorized: false,
      },
    },
  };
}
const endpoint = {
  endpoint_key: "aerobic-test",
  capability_key: "VO2_CAPACITY",
  metric_key: "VO2MAX_ABSOLUTE",
  role: "primary",
  procedure: { comparability_conditions: ["Same device", "Same task"] },
  baseline_window: {
    starts_at: "2030-01-02T09:00:00+00:00",
    ends_at: "2030-01-02T10:00:00+00:00",
  },
  followup_window: {
    starts_at: "2030-01-25T09:00:00+00:00",
    ends_at: "2030-01-25T10:00:00+00:00",
  },
};
const protocol = { artifact: { ...ref, proposal: { endpoints: [endpoint] } } };
const macro = {
  artifact: {
    ...ref,
    sources: { mesocycles: [{ period_id: child.id }] },
    proposal: {
      revision: 1,
      mesocycle_directives: [
        {
          mesocycle_period_id: child.id,
          capability_key: "VO2_CAPACITY",
          role: roles[0],
        },
      ],
    },
  },
};
function endpointForm() {
  return {
    "e.0.key": "aerobic-test",
    "e.0.metric": "VO2MAX_ABSOLUTE",
    "e.0.role": "primary",
    "e.0.origin": "explicit_custom",
    "e.0.protocolKey": "Exact test",
    "e.0.protocolVersion": "1",
    "e.0.source": "Explicit study protocol",
    "e.0.modality": "KAYAK",
    "e.0.task": "Fixed task",
    "e.0.procedure": "Fixed procedure",
    "e.0.equipment": "Same device and processing",
    "e.0.conditions": "Same device\nSame task",
    "e.0.baselineStart": "2030-01-02T09:00:00",
    "e.0.baselineEnd": "2030-01-02T10:00:00",
    "e.0.followupStart": "2030-01-25T09:00:00",
    "e.0.followupEnd": "2030-01-25T10:00:00",
    "e.0.basis": "favourable_percent_change",
    "e.0.minimum": "2",
    rationale: "Explicit mesocycle measurement intent",
  };
}
function observationForm() {
  return {
    value: "3,123456789012345",
    startedAt: "2030-01-02T09:00:00",
    endedAt: "2030-01-02T10:00:00",
    completion: "complete",
    resultLevel: "complete_protocol_result",
    executionEvidence: "Recorded test log",
    "condition.0.status": "unknown",
    "condition.0.observation": "Device calibration record unavailable",
    "condition.0.evidence": "Test log",
    "condition.1.status": "not_met",
    "condition.1.observation": "Task differed",
    "condition.1.evidence": "Task log",
  };
}

for (const [input, output] of [
  ["52,500", "52.5"],
  ["-0.00", "0"],
  ["0.000000000000000123456789012345", "0.000000000000000123456789012345"],
  ["12345678901234567890", "12345678901234567890"],
])
  test(`decimal preserves digits: ${input}`, () =>
    assert.equal(decimal(input), output));
for (const value of [
  "1e4",
  "NaN",
  "Infinity",
  "01",
  "1,2,3",
  "1 000",
  "",
  "9".repeat(81),
])
  test(`invalid decimal: ${value.slice(0, 15)}`, () =>
    assert.throws(() => decimal(value)));
test("UTC input is independent of browser timezone and rejects rollover", () => {
  assert.equal(utcInput("2030-03-31T02:30"), "2030-03-31T02:30:00.000Z");
  assert.throws(() => utcInput("2030-02-30T01:00"));
  assert.throws(() => utcInput("2030-01-01T00:00+01:00"));
});
test("conditions require a nonempty, unique, bounded census", () => {
  assert.deepEqual(lines("same device\r\nsame task"), [
    "same device",
    "same task",
  ]);
  for (const value of [
    "",
    "x\nx",
    Array.from({ length: 33 }, (_, i) => String(i)).join("\n"),
  ])
    assert.throws(() => lines(value));
});
for (const role of roles)
  test(`explicit role roundtrip: ${role}`, () => {
    const data = form({
      capability: "VO2_CAPACITY",
      "VO2_CAPACITY.role": role,
      "VO2_CAPACITY.rationale": "Explicit career priority",
      [`${child.id}.VO2_CAPACITY.role`]: role,
      [`${child.id}.VO2_CAPACITY.rationale`]: "Explicit phase choice",
      rationale: "Explicit decomposition",
    });
    const result = macroProposal(data, catalog, period, [child]);
    assert.equal(result.revision, 1);
    assert.equal(result.supersedes, null);
    assert.equal(result.goals[0].role, role);
    assert.equal(result.mesocycle_directives[0].role, role);
    const revised = macroProposal(data, catalog, period, [child], macro);
    assert.equal(revised.revision, 2);
    assert.deepEqual(revised.supersedes, ref);
    assert.throws(() =>
      macroProposal(data, catalog, period, [child, { id: "another" }]),
    );
  });
test("a missing role never becomes permitted decline", () => {
  assert.throws(() =>
    macroProposal(form({ capability: "VO2_CAPACITY" }), catalog, period, [
      child,
    ]),
  );
});
test("prospective protocol pins exact parent and leaves unknown error null", () => {
  const proposal = protocolProposal(
    form(endpointForm()),
    catalog,
    macro,
    child.id,
    ["0"],
  );
  assert.deepEqual(proposal.macrocycle_plan, ref);
  assert.equal(proposal.endpoints[0].change_requirement.minimum, "2");
  assert.equal(
    proposal.endpoints[0].change_requirement.measurement_error_estimate,
    null,
  );
  assert.equal(
    proposal.endpoints[0].change_requirement.measurement_error_source,
    null,
  );
});
test("error estimate must have a source; explicit zero stays zero", () => {
  const values = { ...endpointForm(), "e.0.error": "0" };
  assert.throws(() =>
    protocolProposal(form(values), catalog, macro, child.id, ["0"]),
  );
  const result = protocolProposal(
    form({ ...values, "e.0.errorSource": "Synthetic zero-error assumption" }),
    catalog,
    macro,
    child.id,
    ["0"],
  );
  assert.equal(
    result.endpoints[0].change_requirement.measurement_error_estimate,
    "0",
  );
});
test("every assigned capability needs a primary; interval metrics cannot use percent", () => {
  assert.throws(() =>
    protocolProposal(
      form({ ...endpointForm(), "e.0.role": "supporting" }),
      catalog,
      macro,
      child.id,
      ["0"],
    ),
  );
  assert.throws(() =>
    protocolProposal(
      form(endpointForm()),
      { ...catalog, metrics: [{ ...catalog.metrics[0], scale: "interval" }] },
      macro,
      child.id,
      ["0"],
    ),
  );
});
test("measurement preserves exact digits, conditions, endpoint, and UUID at an offset window boundary", () => {
  const result = measurementProposal(
    form(observationForm()),
    protocol,
    endpoint,
    child.id,
  );
  assert.equal(result.value, "3.123456789012345");
  assert.deepEqual(result.protocol_reference, ref);
  assert.equal(result.client_request_id, child.id);
  assert.deepEqual(
    result.observation.conditions.map((c) => c.status),
    ["unknown", "not_met"],
  );
  assert.deepEqual(
    result.observation.conditions.map((c) => c.condition),
    endpoint.procedure.comparability_conditions,
  );
  assert.equal(result.observation.body_mass_kg, null);
  assert.equal("metric_key" in result, false);
  assert.equal("procedure" in result.observation, false);
});
test("out-of-window or incomplete observation cannot silently become a full result", () => {
  assert.throws(() =>
    measurementProposal(
      form({ ...observationForm(), endedAt: "2030-01-02T10:00:01" }),
      protocol,
      endpoint,
      child.id,
    ),
  );
  assert.throws(() =>
    measurementProposal(
      form({ ...observationForm(), completion: "" }),
      protocol,
      endpoint,
      child.id,
    ),
  );
});
test("pending body is byte-for-byte stable across persistence and retry", () => {
  const request = prepareRequest(
    "measurements",
    measurementProposal(form(observationForm()), protocol, endpoint, child.id),
  );
  assert.deepEqual(readPending(JSON.stringify(request)), request);
  assert.equal(JSON.parse(request.body).client_request_id, child.id);
  assert.throws(() =>
    readPending(JSON.stringify({ resource: "arbitrary-host", body: "{}" })),
  );
  assert.throws(() =>
    prepareRequest("measurements", { value: "x".repeat(1048576) }),
  );
});
test("durable receipt requires identity, commit, supported schema and false authority flags", () => {
  assert.equal(readReceipt(envelope(), "macrocycle-plans").committed, true);
  for (const mutate of [
    (v) => (v.committed = false),
    (v) => (v.identity_scope = "ANOTHER_OWNER"),
    (v) => (v.planning_authorized = true),
    (v) => (v.artifact.authority.planning_utility_supported = true),
    (v) => (v.artifact.schema_version = "unknown"),
    (v) => (v.artifact.content_hash = "bad"),
  ]) {
    const value = envelope();
    mutate(value);
    assert.throws(() => readReceipt(value, "macrocycle-plans"));
  }
});
test("pagination cannot silently return a truncated or mismatched page", () => {
  const page = {
    identity_scope: "APPLICATION_DEMO_USER",
    items: [envelope()],
    limit: 25,
    offset: 0,
    has_more: false,
  };
  assert.equal(readPage(page, "macrocycle-plans", 0).items.length, 1);
  assert.throws(() =>
    readPage({ ...page, has_more: true }, "macrocycle-plans", 0),
  );
  assert.throws(() => readPage(page, "macrocycle-plans", 25));
});
test("withheld reasons remain distinguishable and unknown codes remain visible", () => {
  assert.match(reasonLabel("BASELINE_RESULT_MISSING"), /hiányzik/);
  assert.match(reasonLabel("FOLLOWUP_RESULT_AMBIGUOUS"), /több/);
  assert.match(reasonLabel("CHANGE_UNCERTAINTY_UNQUANTIFIED"), /Nincs/);
  assert.match(reasonLabel("NEW_SERVER_REASON"), /NEW_SERVER_REASON/);
});
function request(path, options = {}) {
  return new Request(
    "http://localhost:3000/api/goal-workflow/" + path,
    options,
  );
}
function post(body = "{}", headers = {}) {
  return {
    method: "POST",
    body,
    headers: {
      "content-type": "application/json",
      origin: "http://localhost:3000",
      ...headers,
    },
  };
}
test("closed proxy forwards only allowed routes, unchanged bytes/query and no credentials", async () => {
  let seen;
  const send = async (url, options) => {
    seen = { url: String(url), options };
    return Response.json({ ok: true }, { status: 201 });
  };
  const body = '{"value":"0.123456789012345"}';
  const response = await forwardGoals(
    request(
      "measurements",
      post(body, { Cookie: "private", Authorization: "private" }),
    ),
    ["measurements"],
    "http://127.0.0.1:8000",
    send,
  );
  assert.equal(response.status, 201);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(seen.options.body, body);
  assert.equal(seen.options.cache, "no-store");
  assert.equal(seen.options.redirect, "error");
  assert.equal(seen.options.headers.Cookie, undefined);
  assert.equal(seen.options.headers.Authorization, undefined);
  assert.equal(
    seen.url,
    "http://127.0.0.1:8000/api/v1/planning/goals/measurements",
  );
  await forwardGoals(
    request("assessments?limit=25&offset=25"),
    ["assessments"],
    "http://127.0.0.1:8000",
    send,
  );
  assert.match(seen.url, /limit=25&offset=25$/);
});
for (const [path, route, options, status] of [
  ["evil", ["evil"], {}, 404],
  ["measurements/..", ["measurements", ".."], {}, 404],
  ["catalog", ["catalog"], post(), 405],
  ["periods", ["periods"], post(), 405],
  [
    "measurements",
    ["measurements"],
    post("{}", { origin: "https://another.invalid" }),
    403,
  ],
  [
    "measurements",
    ["measurements"],
    post("{}", { "content-type": "text/plain" }),
    415,
  ],
  ["measurements?offset=0&offset=25", ["measurements"], {}, 422],
  ["catalog?url=http://evil.invalid", ["catalog"], {}, 422],
])
  test(`proxy refuses ${path}: ${status}`, async () => {
    let sent = false;
    const result = await forwardGoals(
      request(path, options),
      route,
      "http://127.0.0.1:8000",
      async () => {
        sent = true;
        return Response.json({});
      },
    );
    assert.equal(result.status, status);
    assert.equal(sent, false);
  });
test("proxy enforces actual streamed bytes rather than Content-Length", async () => {
  const result = await forwardGoals(
    request(
      "measurements",
      post("x".repeat(1048577), { "content-length": "1" }),
    ),
    ["measurements"],
    "http://127.0.0.1:8000",
    async () => assert.fail("Oversized request reached backend"),
  );
  assert.equal(result.status, 413);
});
test("proxy preserves backend rejection, sanitizes unavailable/non-JSON upstream, and never follows redirects", async () => {
  const path = ["assessments"],
    req = request("assessments", post());
  const rejected = await forwardGoals(
    req,
    path,
    "http://127.0.0.1:8000",
    async () =>
      Response.json(
        { detail: { code: "GOAL_CONTRACT_REJECTED" } },
        { status: 409 },
      ),
  );
  assert.equal(rejected.status, 409);
  const bad = await forwardGoals(
    request("catalog"),
    ["catalog"],
    "http://127.0.0.1:8000",
    async () => new Response("secret diagnostic", { status: 500 }),
  );
  assert.equal(bad.status, 502);
  assert.doesNotMatch(await bad.text(), /secret/);
  const unavailable = await forwardGoals(
    request("catalog"),
    ["catalog"],
    "http://127.0.0.1:8000",
    async () => {
      throw new Error("secret URL");
    },
  );
  assert.equal(unavailable.status, 502);
  assert.doesNotMatch(await unavailable.text(), /secret/);
});
test("POST retry uses the identical body and only a valid receipt counts as success", async () => {
  const previous = globalThis.fetch,
    bodies = [],
    pending = prepareRequest("macrocycle-plans", { revision: 1 });
  try {
    globalThis.fetch = async (_url, options) => {
      bodies.push(options.body);
      return bodies.length === 1
        ? Response.json({}, { status: 502 })
        : Response.json(envelope());
    };
    await assert.rejects(sendPending(pending));
    assert.equal((await sendPending(pending)).committed, true);
    assert.deepEqual(bodies, [pending.body, pending.body]);
    globalThis.fetch = async () =>
      Response.json({ ...envelope(), committed: false });
    await assert.rejects(sendPending(pending));
  } finally {
    globalThis.fetch = previous;
  }
});

test("proxy compares Origin to the incoming Host when Next uses its internal hostname", async () => {
  let sent = false;
  const req = new Request(
    "http://localhost:3000/api/goal-workflow/measurements",
    post("{}", { host: "127.0.0.1:3000", origin: "http://127.0.0.1:3000" }),
  );
  const result = await forwardGoals(
    req,
    ["measurements"],
    "http://127.0.0.1:8000",
    async () => {
      sent = true;
      return Response.json({});
    },
  );
  assert.equal(result.status, 200);
  assert.equal(sent, true);
});

test("assessment rendering distinguishes missing values, descriptive changes and a withheld criterion", () => {
  const { renderToStaticMarkup } = awaitImportReactServer();
  const Details = load(
    "src/components/planning-goals/artifact-details.tsx",
  ).default;
  const { createElement } = awaitImportReact();
  const receipt = envelope();
  receipt.artifact = {
    ...receipt.artifact,
    activity_cutoff_at: "2030-01-27T12:00:00Z",
    all_primary_criteria_status: "withheld",
    capability_assessments: [],
    unassigned_capability_keys: [],
    endpoint_assessments: [
      {
        endpoint_key: "test",
        metric_key: "VO2MAX_ABSOLUTE",
        metric_unit: "L/min",
        evidence_kind: "physiological_measurement",
        endpoint_role: "primary",
        baseline_value: null,
        followup_value: null,
        favourable_absolute_change: null,
        favourable_percent_change: null,
        declared_error_sensitivity_low: null,
        declared_error_sensitivity_high: null,
        criterion_status: "withheld",
        reason_codes: [
          "BASELINE_RESULT_MISSING",
          "CHANGE_UNCERTAINTY_UNQUANTIFIED",
        ],
        interpretation_limit: "Context-specific",
        candidates: [],
      },
    ],
  };
  const html = renderToStaticMarkup(
    createElement(Details, { receipt, resource: "assessments" }),
  );
  assert.match(html, /Hiányzik \/ nem egyértelmű/);
  assert.match(html, /Az értékelés visszatartva/);
  assert.match(html, /Nincs számszerűsített mérési hiba/);
  assert.doesNotMatch(html, />0 L\/min/);
  assert.match(html, /nem statisztikai konfidenciaintervallum/);
});

test("recorded rationale is escaped as text in the UI", () => {
  const { renderToStaticMarkup } = awaitImportReactServer(),
    { createElement } = awaitImportReact();
  const Details = load(
    "src/components/planning-goals/artifact-details.tsx",
  ).default;
  const receipt = envelope();
  receipt.artifact = {
    ...receipt.artifact,
    proposal: {
      revision: 1,
      rationale: "<script>alert(1)</script>",
      goals: [],
      mesocycle_directives: [],
    },
    sources: { mesocycles: [] },
    unassigned_capability_keys: [],
  };
  const html = renderToStaticMarkup(
    createElement(Details, { receipt, resource: "macrocycle-plans" }),
  );
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});
