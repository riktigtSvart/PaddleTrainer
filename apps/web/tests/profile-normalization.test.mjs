import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { load } from "./load-goal-modules.mjs";

const contracts = load("src/lib/athlete-setup/contracts.ts");
const { recoverPending } = load("src/lib/athlete-setup/client.ts");
const { profileWireProposal } = load("src/lib/athlete-setup/profile-wire.ts");
const { sectionProfile, retainProfileEdits, profileChanges } = load("src/lib/planning-data/profile-state.ts");
const { canonical, sha } = load("src/lib/planning-cycles/contracts.ts");
const fixture = JSON.parse(readFileSync(new URL("./fixtures/profile-normalization.json", import.meta.url)));
const pendingFor = (f) => ({ schema_version: "athlete-pending-v0.1", operation: "profiles", body: JSON.stringify(f.request) });

for (const f of fixture) test(`actual API profile normalization confirms ${f.name} without rewriting a pending request`, async () => {
  const pending = pendingFor(f), raw = JSON.stringify(pending), original = canonical(f.receipt);
  assert.notEqual(await sha(f.request), await sha(f.receipt.artifact.proposal));
  assert.equal(canonical(profileWireProposal(f.request)), canonical(f.receipt.artifact.proposal));
  await contracts.readReceipt(f.receipt, pending);
  await contracts.readReceipt(f.retry, pending);
  assert.equal(JSON.stringify(pending), raw);
  assert.equal(canonical(f.receipt), original);
});

for (const [name, mutate] of [
  ["different request", (r) => r.artifact.proposal.request_id = crypto.randomUUID()],
  ["different parent", (r) => r.artifact.proposal.previous_reference = { artifact_id: "pt-athlete:" + "f".repeat(64), content_hash: "f".repeat(64) }],
  ["different birth date", (r) => r.artifact.proposal.data.birth_date = "1980-01-01"],
  ["different actual value", (r) => r.artifact.proposal.data.typical_days_per_week = 0],
  ["changed sport", (r) => r.artifact.proposal.data.sport_history[0].sport = "Úszás"],
  ["invented authority", (r) => r.artifact.planning_authorized = true],
]) test(`normalization does not accept a rehashed receipt with ${name}`, async () => {
  const f = fixture[0], receipt = structuredClone(f.receipt);
  mutate(receipt); delete receipt.artifact.content_hash; receipt.artifact.content_hash = await sha(receipt.artifact);
  await assert.rejects(contracts.readReceipt(receipt, pendingFor(f)));
});

test("unknown request fields are not stripped to make an unrelated receipt match", async () => {
  const f = fixture[0], request = structuredClone(f.request);
  request.data.future_authority = true;
  await assert.rejects(contracts.readReceipt(f.receipt, { ...pendingFor(f), body: JSON.stringify(request) }));
});

test("new profiles freeze API defaults and nested text before sending while preserving decimal precision", () => {
  const data = { ...fixture[1].request.data, body_mass_kg: "73,250", body_measurements_recorded_on: "2026-10-23" };
  const normalized = contracts.normalizeProfile(data, "2026-10-23");
  assert.equal(normalized.body_mass_kg, "73.250");
  assert.equal(normalized.duration_doubling_slowdown_pct, null);
  assert.equal(normalized.sport_history[0].notes, "Korábbi tapasztalat");
  assert.deepEqual(normalized.resources, ["Rúd"]);
  assert(!Object.hasOwn(normalized.sport_history[0], "role"));
});

test("section saves exclude incomplete edits in another block and keep those edits after confirmation", () => {
  const saved = fixture[0].receipt.artifact.proposal.data;
  const draft = { ...structuredClone(saved), body_mass_kg: "81.250", body_measurements_recorded_on: "2026-10-23" };
  draft.sport_history.push({ sport: "", current: true, level: "unknown", role: "secondary" });
  const request = contracts.normalizeProfile(sectionProfile(draft, saved, "personal"), "2026-10-23");
  assert.deepEqual(request.sport_history, saved.sport_history);
  assert.equal(request.body_mass_kg, "81.250");
  const retained = retainProfileEdits(request, sectionProfile(request, draft, "personal"), saved);
  assert.equal(retained.sport_history.at(-1).sport, "");
  assert.equal(retained.sport_history.at(-1).role, "secondary");
  assert.deepEqual(profileChanges(retained, request), { personal: false, sports: true, history: false });
  const sportsOnly = sectionProfile(draft, saved, "sports");
  assert.equal(sportsOnly.body_mass_kg, saved.body_mass_kg);
  assert.deepEqual(sportsOnly.sport_history, draft.sport_history);
});

test("already committed pending profiles resolve through the exact owned read without another POST", async () => {
  const f = fixture[0], pending = pendingFor(f), before = JSON.stringify(pending), old = globalThis.fetch, calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url, init }); return Response.json(f.receipt); };
  try {
    const receipt = await recoverPending(pending, f.receipt.artifact.athlete_id);
    assert.equal(receipt.artifact.artifact_id, f.receipt.artifact.artifact_id);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "/api/goal-workflow/athlete/profiles/" + f.receipt.artifact.artifact_id);
    assert.equal(calls[0].init?.method, undefined);
    assert.equal(JSON.stringify(pending), before);
  } finally { globalThis.fetch = old; }
});

test("a genuinely missing receipt retries original bytes, while a broken receipt cannot trigger a new write", async () => {
  const f = fixture[0], pending = pendingFor(f), old = globalThis.fetch, calls = [];
  let broken = false;
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    if (!init?.method) return broken ? Response.json({ ...f.receipt, committed: false }) : Response.json({ detail: "missing" }, { status: 404 });
    return Response.json(f.receipt);
  };
  try {
    await recoverPending(pending, f.receipt.artifact.athlete_id);
    assert.equal(calls.length, 2);
    assert.equal(calls[1].init.method, "POST");
    assert.equal(calls[1].init.body, pending.body);
    calls.length = 0; broken = true;
    await assert.rejects(recoverPending(pending, f.receipt.artifact.athlete_id));
    assert.equal(calls.length, 1);
  } finally { globalThis.fetch = old; }
});
