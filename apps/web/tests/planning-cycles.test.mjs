import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";
import { load } from "./load-goal-modules.mjs";

const require = createRequire(import.meta.url);
const c = load("src/lib/planning-cycles/contracts.ts");
const client = load("src/lib/planning-cycles/client.ts");
const { forwardGoals } = load("src/lib/planning-goals/proxy.ts");
const modes = ["olympic", "season", "race", "recreation"];
const id = "pt-cycle:" + "a".repeat(64);

function draft(mode = "recreation") {
  return {
    program_id: "00000000-0000-4000-8000-000000000001",
    mode,
    title: "Teszt felkészülés",
    sport: "Kajak",
    start_date: "2026-10-22",
    end_date: mode === "recreation" ? null : "2027-10-21",
    olympic_key: mode === "olympic" ? "la-2028" : null,
    seasons: [],
    macrocycles: [],
    competitions: [],
    goals: [
      { key: "regular_activity", target_description: "Heti három alkalom" },
    ],
    continued_from: null,
  };
}
async function receipt(body) {
  const artifact = {
    artifact_id: id,
    schema_version: "cycle-program-registration-v0.1",
    rules_version: "cycle-creation-rules-v0.1",
    athlete_id: "11111111-1111-4111-8111-111111111111",
    timezone_name: "Europe/Budapest",
    proposal: body,
    periods: [
      {
        key: "macro-1",
        id: "33333333-3333-4333-8333-333333333333",
        parent_id: null,
        title: "Makrociklus",
        start_date: "2026-10-22",
        end_date: "2027-01-13",
        period_type: "MACROCYCLE",
      },
    ],
    calendar_snapshot: null,
    program_family_id: body.program_id,
    created_at: "2026-10-22T10:00:00+00:00",
    planning_authorized: false,
    workouts_created: false,
    capability_goals_preregistered: false,
  };
  artifact.content_hash = await c.sha(artifact);
  return {
    identity_scope: "APPLICATION_DEMO_USER",
    artifact,
    durable_available_at: "2026-10-22T10:00:01Z",
    reused: false,
    committed: true,
    planning_authorized: false,
    workouts_created: false,
  };
}
for (const mode of modes)
  test(`every entry mode yields explicit macrocycles and complete mesocycles: ${mode}`, () => {
    const end =
      mode === "olympic"
        ? "2028-07-30"
        : mode === "recreation"
          ? "2027-01-13"
          : "2027-10-21";
    const p = c.defaultStructure(draft(mode), end);
    assert(p.macrocycles.length >= 1);
    assert.equal(p.end_date, mode === "recreation" ? null : end);
    assert.equal(p.macrocycles[0].start_date, p.start_date);
    assert.equal(p.macrocycles.at(-1).end_date, end);
    for (const m of p.macrocycles) {
      assert(m.mesocycles.length >= 1);
      let cursor = m.start_date;
      for (const s of m.mesocycles) {
        assert.equal(s.start_date, cursor);
        cursor = c.addDays(s.end_date, 1);
      }
      assert.equal(cursor, c.addDays(m.end_date, 1));
      assert.equal(Boolean(m.season_key), ["olympic", "season"].includes(mode));
    }
  });
test("calendar-day operations are independent of browser timezone and reject rollover", () => {
  for (const zone of [
    "Pacific/Auckland",
    "Europe/Budapest",
    "America/Los_Angeles",
  ]) {
    const old = process.env.TZ;
    process.env.TZ = zone;
    assert.equal(c.addDays("2026-10-24", 2), "2026-10-26");
    assert.equal(c.addDays("2028-02-28", 1), "2028-02-29");
    if (old === undefined) delete process.env.TZ;
    else process.env.TZ = old;
  }
  for (const bad of ["2026-02-30", "2026-1-2", "2026-13-01", "9999-12-31", ""])
    assert.throws(() => c.day(bad));
});
test("anniversary handles leap-day season starts without a fabricated day", () => {
  assert.equal(c.anniversary("2028-02-29"), "2029-02-28");
  const p = c.defaultStructure(
    { ...draft("olympic"), start_date: "2028-02-29" },
    "2029-03-03",
  );
  assert.equal(p.seasons[0].end_date, "2029-02-27");
  assert.equal(p.seasons[1].start_date, "2029-02-28");
});
test("recreation remains open ended while its first macrocycle is finite", () => {
  const p = c.defaultStructure(draft(), "2027-01-13");
  assert.equal(p.end_date, null);
  assert.equal(p.macrocycles[0].mesocycles.length, 3);
});
test("last calendar block retains a shorter remainder without dropping dates", () => {
  const blocks = c.mesocycles("2026-10-22", "2027-01-14", "macro-1");
  assert.equal(blocks.length, 4);
  assert.equal(blocks.at(-1).start_date, "2027-01-14");
  assert.equal(blocks.at(-1).end_date, "2027-01-14");
});
test("explicit macro split retains season, full coverage and unique keys without mutating draft", () => {
  const p = c.defaultStructure(draft("season"), "2027-10-21");
  const before = JSON.stringify(p),
    split = c.splitMacro(p, 0, "2027-04-20");
  assert.equal(JSON.stringify(p), before);
  assert.equal(split.macrocycles.length, 2);
  assert.equal(split.macrocycles[0].end_date, "2027-04-20");
  assert.equal(split.macrocycles[1].start_date, "2027-04-21");
  const keys = split.macrocycles.flatMap((m) => [
    m.key,
    ...m.mesocycles.map((s) => s.key),
  ]);
  assert.equal(new Set(keys).size, keys.length);
  assert.throws(() => c.splitMacro(p, 0, "2027-10-21"));
  assert.throws(() =>
    c.splitMacro(c.defaultStructure(draft(), "2027-01-13"), 0, "2026-12-01"),
  );
});
test("canonical hashing agrees with the Python UTF-8 contract", async () => {
  assert.equal(
    await c.sha({
      név: "Árvíztűrő tükörfúrógép",
      a: [null, true, 12],
      z: { b: "x", a: "y" },
    }),
    "e4dd80ec29dcc2fb377a26a6a904bc83f186e36a4bad7770a88310e2b8bd80f1",
  );
});
test("text normalization is performed before the reviewed body is frozen", () => {
  const p = c.defaultStructure(draft(), "2027-01-13");
  p.title = "  Teszt  ";
  p.sport = " Kajak ";
  p.goals[0].target_description = " Három alkalom ";
  p.macrocycles[0].title = " Makro ";
  const n = c.normalizeProgram(p);
  assert.equal(n.title, "Teszt");
  assert.equal(n.sport, "Kajak");
  assert.equal(n.macrocycles[0].title, "Makro");
  assert.equal(n.goals[0].target_description, "Három alkalom");
  assert.equal(p.title, "  Teszt  ");
});
test("pending cycle body and program UUID survive persistence byte for byte", () => {
  const p = {
    schema_version: "cycle-pending-v0.1",
    operation: "programs",
    body: JSON.stringify(c.defaultStructure(draft(), "2027-01-13")),
  };
  assert.deepEqual(c.readPending(JSON.stringify(p)), p);
  assert.throws(() =>
    c.readPending(JSON.stringify({ ...p, operation: "workouts" })),
  );
  assert.throws(() => c.readPending("{"));
});
test("only committed matching receipts with a verified content hash resolve a pending write", async () => {
  const body = c.defaultStructure(draft(), "2027-01-13"),
    r = await receipt(body);
  const pending = {
    schema_version: "cycle-pending-v0.1",
    operation: "programs",
    body: JSON.stringify(body),
  };
  await c.readReceipt(r, pending);
  for (const key of ["committed", "planning_authorized", "workouts_created"]) {
    await assert.rejects(c.readReceipt({ ...r, [key]: !r[key] }, pending));
  }
  await assert.rejects(
    c.readReceipt(
      { ...r, artifact: { ...r.artifact, content_hash: "0".repeat(64) } },
      pending,
    ),
  );
  await assert.rejects(
    c.readReceipt(r, {
      ...pending,
      body: JSON.stringify({ ...body, program_id: crypto.randomUUID() }),
    }),
  );
});
test("POST retry sends identical bytes and validates the actual response before success", async () => {
  const body = c.defaultStructure(draft(), "2027-01-13"),
    r = await receipt(body),
    bodies = [];
  const pending = {
    schema_version: "cycle-pending-v0.1",
    operation: "programs",
    body: JSON.stringify(body),
  };
  const old = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    bodies.push(options.body);
    assert.equal(url, "/api/goal-workflow/cycles/programs");
    return Response.json({ ...r, reused: bodies.length > 1 });
  };
  try {
    await client.send(pending);
    await client.send(c.readPending(JSON.stringify(pending)));
  } finally {
    globalThis.fetch = old;
  }
  assert.deepEqual(bodies, [pending.body, pending.body]);
});
test("read errors describe loading and unknown write outcomes describe retry", () => {
  assert.match(new client.CycleHTTPError(503, "", false).message, /betöltése/);
  assert.match(new client.CycleHTTPError(503, "", true).message, /mentés/i);
});
for (const [path, method] of [
  ["catalog", "GET"],
  ["preview", "POST"],
  ["programs", "GET"],
  ["programs", "POST"],
  [`programs/${id}`, "GET"],
  ["competition-revisions", "POST"],
]) {
  test(`closed proxy forwards cycle operation: ${method} ${path}`, async () => {
    let called = false;
    const request = new Request(
      "http://localhost:3000/api/goal-workflow/cycles/" + path,
      {
        method,
        headers: {
          Origin: "http://localhost:3000",
          Host: "localhost:3000",
          "Content-Type": "application/json",
          Cookie: "private=do-not-forward",
        },
        ...(method === "POST" ? { body: '{"explicit":"unchanged"}' } : {}),
      },
    );
    const response = await forwardGoals(
      request,
      ["cycles", ...path.split("/")],
      "http://127.0.0.1:8000",
      async (url, options) => {
        called = true;
        assert.equal(
          url.href,
          "http://127.0.0.1:8000/api/v1/planning/cycles/" +
            path.replace(":", "%3A"),
        );
        assert.equal(options.headers.Cookie, undefined);
        assert.equal(options.redirect, "error");
        if (method === "POST")
          assert.equal(options.body, '{"explicit":"unchanged"}');
        return Response.json({ ok: true });
      },
    );
    assert(called);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("cache-control"), "no-store");
  });
}
for (const [path, method, status] of [
  ["preview", "GET", 405],
  ["catalog", "POST", 405],
  ["competition-revisions", "GET", 405],
  ["../workouts", "POST", 404],
  ["programs/evil", "GET", 404],
]) {
  test(`closed proxy rejects cycle escape or unsupported method: ${method} ${path}`, async () => {
    const r = await forwardGoals(
      new Request("http://localhost:3000/route", { method }),
      ["cycles", ...path.split("/")],
      "http://127.0.0.1:8000",
      async () => {
        throw Error("Must not send");
      },
    );
    assert.equal(r.status, status);
  });
}
test("cycle proxy refuses forged Origin and duplicate pagination fields", async () => {
  const bad = await forwardGoals(
    new Request("http://localhost:3000/api", {
      method: "POST",
      headers: {
        Origin: "http://evil.invalid",
        Host: "localhost:3000",
        "Content-Type": "application/json",
      },
      body: "{}",
    }),
    ["cycles", "programs"],
    "http://127.0.0.1:8000",
  );
  assert.equal(bad.status, 403);
  const duplicate = await forwardGoals(
    new Request("http://localhost:3000/api?offset=0&offset=25"),
    ["cycles", "programs"],
    "http://127.0.0.1:8000",
  );
  assert.equal(duplicate.status, 422);
});
test("approximate competitions and goals render as escaped declared intent", () => {
  const React = require("react"),
    { renderToStaticMarkup } = require("react-dom/server");
  const { ProgramSummary } = load(
    "src/components/planning-cycles/program-details.tsx",
  );
  const p = draft();
  p.goals[0].target_description = '<script>alert("x")</script>';
  p.competitions = [
    {
      key: "race",
      title: "Júliusi verseny",
      start_date: "2027-07-01",
      end_date: "2027-07-31",
      precision: "window",
      priority: "main",
      status: "planned",
    },
  ];
  const html = renderToStaticMarkup(
    React.createElement(ProgramSummary, {
      value: p,
      labels: { regular_activity: "Rendszeresség" },
    }),
  );
  assert.match(html, /Közelítő időablak/);
  assert.match(html, /2027-07-01/);
  assert.match(html, /2027-07-31/);
  assert(!html.includes("<script>"));
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /folyamatos program/);
});
