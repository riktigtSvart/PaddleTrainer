import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const contracts = load("src/lib/data-connections/contracts.ts");
const client = load("src/lib/data-connections/client.ts");
const { forwardConnections } = load("src/lib/data-connections/proxy.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const fixture = JSON.parse(
  readFileSync(
    new URL("./fixtures/data-sync-receipt.json", import.meta.url),
    "utf8",
  ),
);
const body = JSON.stringify(fixture.receipt.start.proposal);
const pending = {
  version: "data-sync-pending-v0.1",
  owner: fixture.receipt.athlete_id,
  body,
};
const clone = (value) => structuredClone(value);

test("optional pairing and skip reports retain zero, known reasons and forward-compatible reason codes", () => {
  const status = clone(fixture.status);
  const d = status.providers[0].last_run.datasets[0];
  d.skipped = 2;
  d.skip_reasons = { missing_start: 1, future_provider_reason: 1 };
  d.pairing = { linked: 3, already_linked: 0, unmatched: 1, missing_reference: 2, conflicts: 0, ambiguous: 0 };
  const parsed = contracts.readStatus(status).providers[0].last_run.datasets[0];
  assert.equal(parsed.pairing.already_linked, 0);
  const details = client.resultDetails(parsed).join("\n");
  assert.match(details, /Kezdési idő nélkül: 1/);
  assert.match(details, /future_provider_reason/);
  assert.match(details, /új tervkapcsolatai: 3/);
  assert.match(details, /hivatkozott terv még nincs meg: 1/);
});
for (const [name, change] of [
  ["negative pairing count", (d) => { d.pairing = { linked: -1, already_linked: 0, unmatched: 0, missing_reference: 0, conflicts: 0, ambiguous: 0 }; }],
  ["partial pairing census", (d) => { d.pairing = { linked: 1 }; }],
  ["boolean pairing count", (d) => { d.pairing = { linked: true, already_linked: 0, unmatched: 0, missing_reference: 0, conflicts: 0, ambiguous: 0 }; }],
  ["unreconciled skip total", (d) => { d.skipped = 1; d.skip_reasons = { missing_start: 2 }; }],
  ["boolean skip count", (d) => { d.skipped = 1; d.skip_reasons = { missing_start: true }; }],
]) test(`rejects ${name}`, () => {
  const status = clone(fixture.status);
  change(status.providers[0].last_run.datasets[0]);
  assert.throws(() => contracts.readStatus(status));
});
test("old receipts do not fabricate newly recorded linking or skip details", () => {
  const d = contracts.readStatus(fixture.status).providers[0].last_run.datasets[0];
  assert.equal(d.pairing, undefined);
  assert.equal(d.skip_reasons, undefined);
  assert.deepEqual(client.resultDetails(d), []);
});
test("skip and conflict remedies remain distinct", () => {
  assert.doesNotMatch(client.errorText("DATA_SYNC_SOURCE_RECORDS_SKIPPED"), /védett/);
  assert.match(client.errorText("DATA_SYNC_PROTECTED_PLANS_SKIPPED"), /védett vagy kézi/);
  assert.match(client.errorText("DATA_SYNC_PAIRING_REVIEW_REQUIRED"), /ellenőrzést igényel/);
});
test("a new durable receipt covers pairing metadata with the same original request", async () => {
  const receipt = clone(fixture.receipt);
  receipt.result.datasets[0].pairing = { linked: 2, already_linked: 1, unmatched: 0, missing_reference: 0, conflicts: 0, ambiguous: 0 };
  receipt.run.datasets = clone(receipt.result.datasets);
  const content = { ...receipt.result };
  delete content.content_hash;
  receipt.result.content_hash = await sha(content);
  assert.equal((await contracts.readReceipt(receipt, pending)).run.datasets[0].pairing.linked, 2);
  receipt.run.datasets[0].pairing.linked = 3;
  await assert.rejects(() => contracts.readReceipt(receipt, pending));
});

test("provider status keeps successful sync time separate from the latest stored activity", () => {
  const status = contracts.readStatus(fixture.status),
    polar = status.providers[0];
  assert.notEqual(polar.last_success_at, polar.latest_session_at);
  assert.equal(polar.last_run.state, "succeeded");
  assert.equal(status.providers[1].implemented, false);
  assert.equal(status.providers[2].manual_sync_supported, false);
});
test("unknown sync history remains unknown despite existing activities", () => {
  const status = clone(fixture.status),
    p = status.providers[0];
  p.last_success_at = null;
  p.last_success_datasets = [];
  p.last_run = null;
  assert.match(
    contracts.providerState(contracts.readStatus(status).providers[0]),
    /Még nincs rögzített/,
  );
  assert.equal(contracts.attention(p), false);
});
for (const mutate of [
  (s) => (s.has_more = true),
  (s) => (s.planning_authorized = true),
  (s) => s.providers.push(s.providers[0]),
  (s) => (s.providers[0].last_success_at = "2026-10-25T08:00:00"),
  (s) => (s.providers[1].manual_sync_supported = true),
  (s) => (s.providers[0].allowed_datasets = ["sleep"]),
])
  test("malformed or misleading provider status is refused", () => {
    const status = clone(fixture.status);
    mutate(status);
    assert.throws(() => contracts.readStatus(status));
  });
for (const days of [7, 35, 89])
  test(`bounded sync request accepts ${days} days`, () => {
    assert.equal(
      contracts.readBody({ ...JSON.parse(body), past_days: days }).past_days,
      days,
    );
  });
for (const changes of [
  { past_days: 90 },
  { past_days: true },
  { future_days: -1 },
  { datasets: [] },
  { datasets: ["sessions", "sessions"] },
  { arbitrary_url: "http://elsewhere.invalid" },
  { provider: "UNKNOWN" },
])
  test("invalid sync requests cannot be frozen", () => {
    assert.throws(() =>
      contracts.readBody({ ...JSON.parse(body), ...changes }),
    );
  });
test("pending owner and the exact request bytes survive a storage roundtrip", () => {
  const value = { ...pending, body: JSON.stringify(JSON.parse(body), null, 2) };
  assert.deepEqual(contracts.readPending(JSON.stringify(value)), value);
});
test("Python durable receipt verifies identity, nested references and original request", async () => {
  const receipt = await contracts.readReceipt(fixture.receipt, pending);
  assert.equal(receipt.committed, true);
  assert.equal(receipt.run.state, "succeeded");
  assert.equal(receipt.run.datasets[0].imported, 1);
});
for (const mutate of [
  (r) => (r.committed = false),
  (r) => (r.athlete_id = "00000000-0000-0000-0000-000000000999"),
  (r) => (r.schema_version = "unsupported"),
  (r) => (r.run.state = "running"),
  (r) => (r.result = null),
])
  test("invalid completion cannot resolve a pending request", async () => {
    const receipt = clone(fixture.receipt);
    mutate(receipt);
    await assert.rejects(() => contracts.readReceipt(receipt, pending));
  });
test("tampered nested parent hash is rejected even after rehashing the result", async () => {
  const receipt = clone(fixture.receipt);
  receipt.result.start_reference.content_hash = "0".repeat(64);
  const { content_hash: ignored, ...content } = receipt.result;
  assert(ignored);
  receipt.result.content_hash = await sha(content);
  await assert.rejects(() => contracts.readReceipt(receipt, pending));
});
test("retry sends identical body bytes and completion is verified before success", async () => {
  const previous = globalThis.fetch,
    sent = [];
  globalThis.fetch = async (_url, init) => {
    sent.push(init.body);
    return Response.json(fixture.receipt);
  };
  try {
    await client.sendSync(pending);
    await client.sendSync(pending);
    assert.deepEqual(sent, [body, body]);
  } finally {
    globalThis.fetch = previous;
  }
});
test("unknown backend error codes stay visible", () => {
  assert.match(
    client.errorText("FUTURE_PROVIDER_CODE"),
    /FUTURE_PROVIDER_CODE/,
  );
});
const backend = "http://api.invalid:8000";
function request(path, method = "GET", extra = {}) {
  return new Request("https://app.invalid/api/data-connections/" + path, {
    method,
    ...(method === "POST"
      ? {
          body,
          headers: {
            Origin: "https://app.invalid",
            "Content-Type": "application/json",
            Cookie: "not-forwarded",
            Authorization: "not-forwarded",
          },
        }
      : {}),
    ...extra,
  });
}
for (const path of ["status", "sync", "runs/" + JSON.parse(body).request_id])
  test(`closed proxy forwards only the known operation: ${path}`, async () => {
    const method = path === "sync" ? "POST" : "GET";
    const r = await forwardConnections(
      request(path, method),
      path.split("/"),
      backend,
      async (url, init) => {
        assert.equal(url.href, backend + "/api/v1/data-connections/" + path);
        assert.equal(init.method, method);
        assert.equal(init.redirect, "error");
        assert.equal(init.cache, "no-store");
        assert.equal(new Headers(init.headers).get("cookie"), null);
        assert.equal(new Headers(init.headers).get("authorization"), null);
        if (method === "POST") assert.equal(init.body, body);
        return Response.json({ ok: true });
      },
    );
    assert.equal(r.status, 200);
    assert.equal(r.headers.get("Cache-Control"), "no-store");
  });
for (const [path, method, status, extra] of [
  ["evil", "GET", 404],
  ["../workouts", "GET", 404],
  ["status", "POST", 405],
  ["sync", "GET", 405],
  ["runs/bad-id", "GET", 404],
  [
    "sync",
    "POST",
    403,
    {
      headers: {
        Origin: "https://evil.invalid",
        "Content-Type": "application/json",
      },
    },
  ],
  [
    "sync",
    "POST",
    415,
    {
      headers: { Origin: "https://app.invalid", "Content-Type": "text/plain" },
    },
  ],
  ["status?url=http://evil.invalid", "GET", 422],
])
  test(`closed proxy refuses ${method} ${path}`, async () => {
    const r = await forwardConnections(
      request(path, method, extra),
      path.split("?")[0].split("/"),
      backend,
      () => {
        throw Error("Must not call upstream");
      },
    );
    assert.equal(r.status, status);
  });
test("actual streamed byte limit applies even with a forged Content-Length", async () => {
  const r = await forwardConnections(
    request("sync", "POST", {
      body: "x".repeat(16385),
      headers: {
        Origin: "https://app.invalid",
        "Content-Type": "application/json",
        "Content-Length": "1",
      },
    }),
    ["sync"],
    backend,
  );
  assert.equal(r.status, 413);
});
test("explicit OAuth navigation has one fixed backend entry point", async () => {
  const r = await forwardConnections(
    request("polar/connect"),
    ["polar", "connect"],
    backend,
  );
  assert.equal(r.status, 303);
  assert.equal(
    r.headers.get("location"),
    backend + "/api/v1/integrations/polar/connect",
  );
});
test("proxy preserves backend rejection and sanitizes unavailable or non-JSON upstreams", async () => {
  const rejected = await forwardConnections(
    request("status"),
    ["status"],
    backend,
    async () =>
      Response.json({ detail: { code: "EXPECTED" } }, { status: 409 }),
  );
  assert.equal(rejected.status, 409);
  assert.equal((await rejected.json()).detail.code, "EXPECTED");
  const bad = await forwardConnections(
    request("status"),
    ["status"],
    backend,
    async () => new Response("private traceback"),
  );
  assert.equal(bad.status, 502);
  assert.doesNotMatch(await bad.text(), /private traceback/);
});
test("proxy compares Origin with the incoming Host behind Next's internal host", async () => {
  const r = await forwardConnections(
    new Request("http://internal:3000/api/data-connections/sync", {
      method: "POST",
      body,
      headers: {
        Host: "app.invalid",
        Origin: "http://app.invalid",
        "Content-Type": "application/json",
      },
    }),
    ["sync"],
    backend,
    async () => Response.json({ ok: true }),
  );
  assert.equal(r.status, 200);
});
test("initial rendering contains one accessible control without claiming a connection", () => {
  const Control = load(
    "src/components/ui/data-connections-control.tsx",
  ).default;
  const html = renderToStaticMarkup(React.createElement(Control));
  assert.match(html, /aria-label="Adatkapcsolatok"/);
  assert.match(html, /aria-expanded="false"/);
  assert.doesNotMatch(
    html,
    /Frissítés befejezve|Szinkronizálás<|role="dialog"/,
  );
});
test("state labels and warning shapes express failures independently of training colors", () => {
  const p = clone(fixture.status.providers[0]);
  p.last_run.state = "partial";
  assert.equal(contracts.attention(p), true);
  assert.match(contracts.providerState(p), /Részben/);
  p.connection_state = "reconnect_required";
  assert.match(contracts.providerState(p), /Újracsatlakozás/);
});

for (const [status, explanation] of [
  [400, /hibás kérésként/],
  [404, /nem található/],
  [422, /hibás kérésként/],
  [500, /szerverhibát/],
  [502, /szerverhibát/],
  [503, /szerverhibát/],
  [599, /szerverhibát/],
])
  test(`provider rejection retains HTTP ${status} with an actionable category`, () => {
    const text = client.errorText(`DATA_SYNC_PROVIDER_HTTP_${status}`);
    assert.match(text, new RegExp(`HTTP ${status}`));
    assert.match(text, explanation);
    assert.doesNotMatch(text, /újra engedélyezni/);
  });

for (const code of [
  "DATA_SYNC_PROVIDER_HTTP_0400",
  "DATA_SYNC_PROVIDER_HTTP_600",
  "DATA_SYNC_PROVIDER_HTTP_400_suffix",
])
  test(`unrecognized provider code remains visible: ${code}`, () => {
    assert.ok(client.errorText(code).includes(code));
  });

test("authentication, permissions and rate limits retain their separate remedies", () => {
  assert.match(client.errorText("DATA_SYNC_RECONNECT_REQUIRED"), /újra engedélyezni/);
  assert.match(client.errorText("DATA_SYNC_PERMISSION_MISSING"), /hozzáférés szükséges/);
  assert.match(client.errorText("DATA_SYNC_RATE_LIMITED"), /Később próbáld újra/);
});
