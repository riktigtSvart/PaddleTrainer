import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { load } from "./load-goal-modules.mjs";
const a = load("src/lib/planning-data/automation.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const { forwardGoals } = load("src/lib/planning-goals/proxy.ts");
const f = JSON.parse(gunzipSync(readFileSync(new URL("./fixtures/automatic-planning.json.gz", import.meta.url))));
const owner = f.before.athlete_id;
async function rehash(v) { const { content_hash: ignored, ...body } = v; void ignored; v.content_hash = await sha(body); return v; }
test("real owned Python policy and run verify in the browser without a forged human approval", async () => {
  for (const value of [f.before, f.after_save, f.after_run, f.repeat.context]) await a.readAutomaticContext(value, owner);
  const policy = await a.readPolicy(f.saved.artifact, owner);
  assert.equal(policy.provider_writeback, false);
  assert.equal(policy.proposal.enabled, true);
  assert.equal(f.run.context.last_run.application_reference.artifact_id, f.run.run.application_reference.artifact_id);
  assert.equal(f.run.run.state, "applied");
});
for (const [name, mutate] of [
  ["foreign owner", (v) => { v.athlete_id = "other"; }],
  ["provider authority", (v) => { v.policy.provider_writeback = true; }],
  ["unsupported schema", (v) => { v.schema_version = "automatic-planning-v99"; }],
  ["foreign policy", (v) => { v.last_run.policy_reference.artifact_id = "pt-automatic:" + "a".repeat(64); }],
  ["invented nutrition", (v) => { v.nutrition_planning_available = true; }],
  ["boolean count", (v) => { v.last_run.created_count = true; }],
  ["missing application", (v) => { v.last_run.application_reference = null; }],
  ["unexplained blocker", (v) => { v.last_run.state = "blocked"; v.last_run.blockers = []; }],
]) test("automatic context rejects " + name + " after outer rehash", async () => {
  const value = structuredClone(f.after_run); mutate(value);
  if (value.policy) await rehash(value.policy);
  if (value.last_run) await rehash(value.last_run);
  await rehash(value);
  await assert.rejects(() => a.readAutomaticContext(value, owner));
});
test("pending setting stays owner-bound and byte stable, and restored state sends nothing", () => {
  const body = JSON.stringify(f.request), pending = { owner, body };
  assert.deepEqual(a.readAutomaticPending(JSON.stringify(pending), owner), pending);
  assert.notEqual(a.autoKey(owner), a.autoKey("other"));
  assert.throws(() => a.readAutomaticPending(JSON.stringify(pending), "other"));
  assert.throws(() => a.readSetting({ ...f.request, enabled: 1 }));
  assert.throws(() => a.readSetting({ ...f.request, onboarding_completed: false }));
});
test("exact durable receipt is required before resolving the settings write; run sends an empty bounded request", async () => {
  const original = globalThis.fetch, pending = { owner, body: JSON.stringify(f.request) }, requests = [];
  try {
    globalThis.fetch = async (url, init) => { requests.push([url, init]); return Response.json(url.endsWith("/run") ? f.run : f.saved); };
    await a.saveAutomatic(pending); await a.saveAutomatic(pending); await a.runAutomatic(owner);
    assert.equal(requests[0][1].body, pending.body); assert.equal(requests[1][1].body, pending.body);
    assert.equal(requests[2][0], "/api/goal-workflow/automation/run"); assert.equal(requests[2][1].body, "{}");
    const wrong = structuredClone(f.saved); wrong.committed = false;
    globalThis.fetch = async () => Response.json(wrong);
    await assert.rejects(() => a.saveAutomatic(pending));
  } finally { globalThis.fetch = original; }
});
for (const [method, path, status] of [["GET", ["automation"], 200], ["POST", ["automation"], 200], ["POST", ["automation", "run"], 200], ["GET", ["automation", "run"], 405], ["DELETE", ["automation"], 405], ["POST", ["automation", "other"], 404]]) test(`automatic proxy ${method} ${path.join("/")} ${status}`, async () => {
  const request = new Request("https://paddle.test/api/goal-workflow/" + path.join("/"), { method, ...(method === "POST" ? { headers: { Origin: "https://paddle.test", "Content-Type": "application/json" }, body: "{}" } : {}) });
  const sent = [];
  const response = await forwardGoals(request, path, "http://backend.test", async (url, init) => { sent.push([url, init]); return Response.json({}); });
  assert.equal(response.status, status);
  assert.equal(sent.length, status === 200 ? 1 : 0);
  if (sent.length) assert.equal(sent[0][0].pathname, "/api/v1/planning/" + path.join("/"));
});
test("automatic proxy rejects query and forged origin before forwarding", async () => {
  for (const request of [new Request("https://paddle.test/api/goal-workflow/automation?owner=other"), new Request("https://paddle.test/api/goal-workflow/automation", { method: "POST", headers: { Origin: "https://elsewhere.test", "Content-Type": "application/json" }, body: "{}" })]) {
    const response = await forwardGoals(request, ["automation"], "http://backend.test", async () => { throw Error("must not send"); });
    assert([403, 422].includes(response.status));
  }
});
