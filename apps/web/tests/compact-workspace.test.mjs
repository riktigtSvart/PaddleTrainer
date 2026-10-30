import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const p = load("src/lib/data-connections/preferences.ts");
const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/data-sync-receipt.json", import.meta.url)),
);
const owner = fixture.status.athlete_id;
const selected = {
  mode: "provider",
  provider: "POLAR",
  pastDays: 7,
  datasets: ["sessions"],
};
const stored = (choice) => JSON.stringify({ version: 1, owner, choice });
test("last refresh choice roundtrips without starting or carrying a request", () => {
  assert.deepEqual(p.readChoice(stored(selected), owner), selected);
  assert.deepEqual(p.readChoice(stored(p.localChoice), owner), {
    mode: "local",
  });
  assert.equal(p.readChoice(stored(selected), owner).request_id, undefined);
});
for (const [name, change] of [
  ["empty dataset", (c) => (c.datasets = [])],
  ["duplicate dataset", (c) => (c.datasets = ["sessions", "sessions"])],
  ["unknown dataset", (c) => (c.datasets = ["sleep"])],
  ["unsupported range", (c) => (c.pastDays = 365)],
  ["boolean range", (c) => (c.pastDays = true)],
  ["bad provider", (c) => (c.provider = "../api")],
  ["wrong mode", (c) => (c.mode = "automatic")],
])
  test("unsafe saved preference is rejected: " + name, () => {
    const c = structuredClone(selected);
    change(c);
    assert.throws(() => p.readChoice(stored(c), owner));
  });
test("preferences are owner-bound and keys cannot share another athlete choice", () => {
  assert.notEqual(p.preferenceKey(owner), p.preferenceKey("other"));
  assert.throws(() => p.readChoice(stored(selected), "other"));
  assert.throws(() => p.readChoice("{}", owner));
});
test("only an implemented connected provider with current allowed datasets can run a stored choice", () => {
  const s = structuredClone(fixture.status),
    provider = s.providers.find((p) => p.key === "POLAR");
  provider.connection_state = "connected";
  provider.manual_sync_supported = true;
  provider.implemented = true;
  provider.allowed_datasets = ["sessions"];
  assert.equal(p.choiceProvider(selected, s).key, "POLAR");
  provider.allowed_datasets = [];
  assert.equal(p.choiceProvider(selected, s), null);
  provider.allowed_datasets = ["sessions"];
  provider.connection_state = "reconnect_required";
  assert.equal(p.choiceProvider(selected, s), null);
});
test("unimplemented Garmin or Suunto cannot be selected silently", () => {
  const s = structuredClone(fixture.status);
  assert.equal(p.choiceProvider({ ...selected, provider: "GARMIN" }, s), null);
  assert.equal(p.choiceProvider({ ...selected, provider: "SUUNTO" }, s), null);
  assert.equal(p.choiceProvider(p.localChoice, s), null);
});
test("global refresh has a named main action and separate settings, initially closed without a provider promise", () => {
  const Component = load(
    "src/components/ui/data-connections-control.tsx",
  ).default;
  const html = renderToStaticMarkup(React.createElement(Component));
  assert.match(html, /Frissítés<\/span>/);
  assert.match(html, /aria-label="Adatkapcsolatok"/);
  assert.match(html, /aria-expanded="false"/);
  assert.doesNotMatch(html, /role="dialog"/);
});
test("calendar keeps one date toolbar, optional view layers and explicit slot action", () => {
  const Workspace = load("src/components/calendar/workspace.tsx").default;
  const html = renderToStaticMarkup(React.createElement(Workspace));
  assert.match(html, /\+ Idősáv/);
  assert.match(html, /<summary[^>]*>.*Nézet/s);
  assert.doesNotMatch(
    html,
    /Nézet frissítése|Edzések, lehetőségek és elfoglaltságok/,
  );
  assert.match(html, /aria-pressed="true"[^>]*>1 hét/);
});
