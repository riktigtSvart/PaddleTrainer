import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { load } from "./load-goal-modules.mjs";

const c = load("src/lib/data-connections/contracts.ts");
const client = load("src/lib/data-connections/client.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const fixture = JSON.parse(readFileSync(new URL("./fixtures/data-sync-receipt.json", import.meta.url)));
const CODE = "DATA_SYNC_PROTECTED_PLANS_SKIPPED";
function status() {
  const s = structuredClone(fixture.status), p = s.providers[0], r = p.last_run;
  p.last_success_at = null;
  p.last_success_datasets = [];
  r.state = "partial";
  r.error_code = CODE;
  Object.assign(r.datasets[1], { skipped: 2, error_code: CODE, skip_reasons: { protected_plan: 2 } });
  return s;
}
function provider(s) { return c.readStatus(s).providers[0]; }

test("a fully reported preservation-only run is informational without rewriting its outcome or history", () => {
  const s = status(), before = structuredClone(s), p = provider(s);
  assert.equal(c.preservedPlansOnly(p.last_run), true);
  assert.equal(c.providerState(p), "Frissítés befejezve");
  assert.equal(c.attention(p), false);
  assert.equal(c.hasSuccessfulTransfer(p), true);
  assert.equal(p.last_run.state, "partial");
  assert.equal(p.last_success_at, null);
  assert.deepEqual(s, before);
});
test("a targets-only request may preserve plans and still finish its requested scope", () => {
  const s = status(), r = s.providers[0].last_run;
  r.requested_datasets = ["targets"];
  r.datasets = [r.datasets[1]];
  assert.equal(c.preservedPlansOnly(provider(s).last_run), true);
});
test("preserved counts are distinguished from omitted records while zero stays zero", () => {
  const d = provider(status()).last_run.datasets[1];
  assert.match(client.resultCounts(d), /megőrzött: 2/);
  assert.doesNotMatch(client.resultCounts(d), /kihagyott/);
  assert.match(client.resultDetails(d).join("\n"), /Védett vagy kézi terv megőrizve: 2/);
  assert.match(client.resultCounts({ ...d, imported: 0, updated: 0 }), /Új: 0 · frissített: 0/);
});
for (const [name, change] of [
  ["mixed omissions", (r) => { r.datasets[1].skip_reasons = { protected_plan: 1, missing_start: 1 }; }],
  ["unknown omission", (r) => { r.datasets[1].skip_reasons = { future_reason: 2 }; }],
  ["old missing reason census", (r) => { delete r.datasets[1].skip_reasons; }],
  ["missing dataset", (r) => { r.datasets = [r.datasets[1]]; }],
  ["duplicated dataset", (r) => { r.datasets[0] = structuredClone(r.datasets[1]); }],
  ["missing completion timestamp", (r) => { r.finished_at = null; }],
  ["unknown import count", (r) => { r.datasets[0].imported = null; }],
  ["another source record skipped", (r) => { Object.assign(r.datasets[0], { skipped: 1,
    skip_reasons: { missing_session_id: 1 }, error_code: "DATA_SYNC_SOURCE_RECORDS_SKIPPED" }); }],
  ["dataset not attempted", (r) => { Object.assign(r.datasets[0], { state: "not_attempted", imported: null,
    updated: null, skipped: null }); }],
  ["failed dataset", (r) => { Object.assign(r.datasets[0], { state: "failed", imported: null,
    updated: null, skipped: null, error_code: "DATA_SYNC_PROVIDER_HTTP_400" }); }],
  ["ambiguous plan", (r) => { r.datasets[1].pairing = { linked: 0, already_linked: 0, unmatched: 0,
    missing_reference: 0, conflicts: 0, ambiguous: 1 }; }],
  ["existing conflicting plan", (r) => { r.datasets[1].pairing = { linked: 0, already_linked: 0, unmatched: 0,
    missing_reference: 0, conflicts: 1, ambiguous: 0 }; }],
]) test(`preservation never masks ${name}`, () => {
  const s = status(); change(s.providers[0].last_run);
  const p = provider(s);
  assert.equal(c.preservedPlansOnly(p.last_run), false);
  assert.equal(c.attention(p), true);
  assert.equal(c.hasSuccessfulTransfer(p), false);
  assert.equal(c.providerState(p), "Részben sikerült");
});
for (const code of ["DATA_SYNC_PROVIDER_HTTP_400", "DATA_SYNC_RECONNECT_REQUIRED",
  "DATA_SYNC_PERMISSION_MISSING", "DATA_SYNC_TIMEOUT", "DATA_SYNC_PAIRING_FAILED", "FUTURE_FAILURE"])
  test(`another dataset error remains a warning: ${code}`, () => {
    const s = status();
    s.providers[0].last_run.datasets[0].error_code = code;
    const p = provider(s);
    assert.equal(c.preservedPlansOnly(p.last_run), false);
    assert.equal(c.attention(p), true);
  });
test("a generic old partial result is not silently reclassified", () => {
  const s = status();
  s.providers[0].last_run.error_code = "DATA_SYNC_SOURCE_RECORDS_SKIPPED";
  assert.equal(c.preservedPlansOnly(provider(s).last_run), false);
});
test("unmatched or absent provider references remain visible information without invented links", () => {
  const s = status();
  s.providers[0].last_run.datasets[1].pairing = { linked: 0, already_linked: 0, unmatched: 2,
    missing_reference: 3, conflicts: 0, ambiguous: 0 };
  const p = provider(s);
  assert.equal(c.preservedPlansOnly(p.last_run), true);
  assert.match(client.resultDetails(p.last_run.datasets[1]).join("\n"), /még nincs meg: 2/);
});
test("the latest run clock uses its completion time rather than an activity or historical success", () => {
  const s = status(), p = provider(s), zone = s.timezone_name;
  p.last_success_at = "2026-10-21T07:00:00Z";
  assert.equal(c.lastRunTime(p, zone), c.displayTime(p.last_run.finished_at, zone));
  assert.notEqual(c.lastRunTime(p, zone), c.displayTime(p.latest_session_at, zone));
  assert.notEqual(c.lastRunTime(p, zone), c.displayTime(p.last_success_at, zone));
});
test("an ended failed run gets an honest end timestamp without becoming successful", () => {
  const s = status(); s.providers[0].last_run.state = "failed";
  const p = provider(s);
  assert.equal(c.lastRunTime(p, s.timezone_name), c.displayTime(p.last_run.finished_at, s.timezone_name));
  assert.equal(c.hasSuccessfulTransfer(p), false);
  assert.equal(c.attention(p), true);
});
test("running, interrupted and unknown history have distinct clock labels", () => {
  const s = status(), p = s.providers[0];
  p.last_run.state = "running"; p.last_run.finished_at = null;
  assert.equal(c.lastRunTime(provider(s), s.timezone_name), "Folyamatban");
  p.last_run.state = "interrupted";
  assert.equal(c.lastRunTime(provider(s), s.timezone_name), "Nem igazolható");
  p.last_run = null;
  assert.equal(c.lastRunTime(provider(s), s.timezone_name), "Még nincs rögzítve");
  assert.equal(c.hasSuccessfulTransfer(p), false);
});
test("connection setup and missing permission warnings take precedence over preservation", () => {
  const s = status(), p = s.providers[0];
  p.connection_state = "reconnect_required";
  assert.equal(c.connectionAttention(provider(s)), true);
  assert.equal(c.providerState(p), "Újracsatlakozás szükséges");
  assert.equal(c.attention(p), true);
  p.connection_state = "connected"; p.allowed_datasets = ["sessions"];
  assert.equal(c.connectionAttention(provider(s)), true);
  assert.equal(c.providerState(p), "Hiányzó adathozzáférés");
});
test("ordinary record issues do not imply broken account authorization", () => {
  const s = status(), p = s.providers[0];
  p.last_run.error_code = "DATA_SYNC_SOURCE_RECORDS_SKIPPED";
  assert.equal(c.connectionAttention(provider(s)), false);
  assert.equal(c.attention(p), true);
  p.last_run.error_code = "DATA_SYNC_RECONNECT_REQUIRED";
  assert.equal(c.connectionAttention(provider(s)), true);
});
test("a verified partial receipt retains its exact hash and outcome after display classification", async () => {
  const receipt = structuredClone(fixture.receipt), run = status().providers[0].last_run;
  Object.assign(receipt.result, { datasets: structuredClone(run.datasets), outcome: "partial", error_code: CODE });
  receipt.run = structuredClone(run);
  const content = { ...receipt.result }; delete content.content_hash;
  receipt.result.content_hash = await sha(content);
  const before = structuredClone(receipt), body = JSON.stringify(receipt.start.proposal);
  const verified = await c.readReceipt(receipt, { version: "data-sync-pending-v0.1", owner: receipt.athlete_id, body });
  assert.equal(c.preservedPlansOnly(verified.run), true);
  assert.equal(verified.result.outcome, "partial");
  assert.deepEqual(receipt, before);
});
