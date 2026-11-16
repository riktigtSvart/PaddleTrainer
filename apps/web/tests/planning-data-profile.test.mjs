import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const { profileChanges, profileReadiness, retainProfileEdits, pendingDescription } = load("src/lib/planning-data/profile-state.ts");
const { emptyProfile, normalizeProfile, readQueue } = load("src/lib/athlete-setup/contracts.ts");
const ProfileForm = load("src/components/athlete-setup/profile-form.tsx").default;
const fixture = JSON.parse(readFileSync(new URL("./fixtures/training-options.json", import.meta.url)));
const base = fixture.review.inputs.profile.data;
const review = { global_entry_gate: "OPEN", reasons: [] };

test("personal completeness excludes sports-only gaps and does not require optional body measurements", () => {
  const value = { ...base, birth_date: "1982-05-30", constraint_status: "none_known", participation: "unrestricted", body_mass_kg: null, height_cm: null, target_sport: "", sport_history_status: "unknown" };
  assert.deepEqual(profileReadiness(value, { ...review, global_entry_gate: "REVIEW_REQUIRED", reasons: ["TARGET_SPORT_UNKNOWN", "SPORT_HISTORY_UNKNOWN"] }), { personal: true, sports: false });
  assert.deepEqual(profileReadiness({ ...value, target_sport: "Kajak", sport_history_status: "none" }, review), { personal: true, sports: true });
  assert.deepEqual(profileReadiness(undefined, null), { personal: false, sports: false });
});

for (const [reason, patch] of [
  ["AGE_UNKNOWN", { birth_date: null }], ["FUNCTIONAL_CONSTRAINTS_UNKNOWN", { constraint_status: "unknown" }],
  ["PARTICIPATION_UNKNOWN", { participation: "unknown" }], ["CONSTRAINT_REVIEW_DUE", {}],
  ["YOUTH_PLANNING_REVIEW", {}], ["USER_DECLARED_PAUSE", { participation: "paused" }], ["FUTURE_REVIEW_REASON", {}],
]) test(`closed heading assigns ${reason} to the block containing that question`, () => {
  const state = profileReadiness({ ...base, ...patch }, { ...review, reasons: [reason] });
  assert.equal(state.personal, reason !== "AGE_UNKNOWN");
  assert.equal(state.sports, reason === "AGE_UNKNOWN");
});

test("shared profile changes mark only the relevant chapter and retain unknowns and exact decimal digits", () => {
  const before = structuredClone(base), draft = structuredClone(base);
  assert.deepEqual(profileChanges(draft, before), { personal: false, sports: false, history: false });
  draft.body_mass_kg = "73,250";
  assert.deepEqual(profileChanges(draft, before), { personal: true, sports: false, history: false });
  draft.sport_history.push({ sport: "Alpesi síelés / lesiklás", discipline: "", role: "recreation", current_level: "unknown", level: "unknown", current: true, last_active_date: null, start_year: null, usual_sessions_per_week: null, notes: "" });
  draft.manual_observations = [...draft.manual_observations, { observation_id: crypto.randomUUID(), metric: "daily_steps", value: "0", start_date: fixture.context.local_today, end_date: fixture.context.local_today, method: "self_report", aggregation: "single", sport: "", protocol: "", conditions: "", supersedes_candidate_id: null }];
  assert.deepEqual(profileChanges(draft, before), { personal: true, sports: true, history: true });
  assert.equal(draft.sport_history.at(-1).current_level, "unknown");
  assert.equal(before.sport_history.length, base.sport_history.length);
});

test("confirming an older profile save retains later edits without changing the receipt or unrelated committed fields", () => {
  const before = structuredClone(base), committed = { ...structuredClone(base), height_cm: "181.0", body_measurements_recorded_on: fixture.context.local_today };
  const draft = { ...structuredClone(base), body_mass_kg: "73,250", body_measurements_recorded_on: fixture.context.local_today };
  draft.sport_history.push({ ...draft.sport_history[0], sport: "Lesiklás", discipline: "", role: "recreation", current_level: "unknown" });
  const committedBytes = JSON.stringify(committed), draftBytes = JSON.stringify(draft);
  const merged = retainProfileEdits(committed, draft, before);
  assert.equal(merged.body_mass_kg, "73,250");
  assert.equal(merged.height_cm, "181.0");
  assert.equal(merged.sport_history.at(-1).role, "recreation");
  assert.equal(normalizeProfile(merged, fixture.context.local_today).body_mass_kg, "73.250");
  assert.equal(JSON.stringify(committed), committedBytes);
  assert.equal(JSON.stringify(draft), draftBytes);
  assert.deepEqual(retainProfileEdits(committed, before, before), committed);
});

test("editing from an empty profile preserves a manually declared zero and leaves other values unknown", () => {
  const empty = emptyProfile(), draft = { ...empty, typical_minutes_per_week: 0, recovery_notes: "Pihenés" };
  const result = retainProfileEdits({ ...empty, target_sport: "Futás" }, draft, empty);
  assert.equal(result.typical_minutes_per_week, 0);
  assert.equal(result.typical_days_per_week, null);
  assert.equal(result.target_sport, "Futás");
});

test("pending descriptions identify a profile save or the concrete watch dataset without changing retained bytes", () => {
  const body = JSON.stringify({ request_id: crypto.randomUUID(), previous_reference: null, data: base });
  const queue = readQueue(JSON.stringify({ schema_version: "athlete-queue-v0.1", athlete_id: fixture.context.athlete_id, items: [{ schema_version: "athlete-pending-v0.1", operation: "profiles", body }] }));
  assert.match(pendingDescription(queue).title, /személyes adatok és sportelőélet/);
  assert.match(pendingDescription(queue).action, /Mentés ellenőrzése/);
  assert.equal(queue.items[0].body, body);
  const watch = { ...queue, items: [{ schema_version: "athlete-pending-v0.1", operation: "polar-imports", body: JSON.stringify({ request_id: crypto.randomUUID(), day: "2026-10-22", domain: "sleep" }) }] };
  const restored = readQueue(JSON.stringify(watch));
  assert.match(pendingDescription(restored).detail, /Alvás · 2026-10-22/);
  assert.equal(pendingDescription(restored).action, "Adatátvétel folytatása");
  assert.match(pendingDescription(restored, true).title, /folyamatban/);
  assert.deepEqual(restored, watch);
});

test("sport form offers free text, secondary and leisure additions, and explicitly retains skiing", () => {
  const html = renderToStaticMarkup(React.createElement(ProfileForm, { value: base, today: fixture.context.local_today, section: "sports", planning: true, onChange() {} }));
  assert.match(html, /Kiegészítő sport hozzáadása/);
  assert.match(html, /Szabadidős sport hozzáadása/);
  assert.match(html, /Alpesi síelés \/ lesiklás/);
  assert.match(html, /A sport nevét szabadon is beírhatod/);
  assert.match(html, /<input[^>]*list="pt-sport-history-choices"/);
  assert.doesNotMatch(html, /Születési dátum/);
});

test("personal fields stay compact and training questions precede the sport history", () => {
  const value = { ...base, body_mass_kg: "81.250", height_cm: "181.0", body_measurements_recorded_on: fixture.context.local_today };
  const render = (section) => renderToStaticMarkup(React.createElement(ProfileForm, { value, today: fixture.context.local_today, section, planning: true, onChange() {} }));
  const personal = render("personal"), sports = render("sports");
  for (const label of ["Születési dátum", "Biológiai nem", "Testsúly (kg)", "Magasság (cm)"]) assert(personal.includes(label));
  for (const label of ["Korlátozások és alkalmazkodás", "Heti edzési keret és visszatérés", "Kihagyás / visszatérés", "További sportolási beállítások", "Sportmúlt, sportáganként"]) {
    assert(!personal.includes(label), label);
    assert(sports.includes(label), label);
  }
  assert(sports.indexOf("Korlátozások és alkalmazkodás") < sports.indexOf("Sportmúlt, sportáganként"));
  assert(sports.indexOf("Heti edzési keret és visszatérés") < sports.indexOf("Sportmúlt, sportáganként"));
  assert.match(personal, /<details class="pt-measurement-date[^>]*><summary>Mért adatok dátuma/);
  assert(!sports.includes("Biológiai nem"));
});

test("restriction, weekly budget and return edits save with sports and retain unsubmitted physical measurements", () => {
  const { sectionProfile } = load("src/lib/planning-data/profile-state.ts");
  const draft = { ...structuredClone(base), constraint_status: "unknown", participation: "unknown", typical_days_per_week: 6,
    typical_minutes_per_week: 450, interruption: "returning", recovery_notes: "Változó heti terhelés" };
  assert.deepEqual(profileChanges(draft, base), { personal: false, sports: true, history: false });
  const personal = sectionProfile(draft, base, "personal");
  for (const key of ["constraint_status", "participation", "typical_days_per_week", "typical_minutes_per_week", "interruption", "recovery_notes"]) assert.deepEqual(personal[key], base[key]);
  draft.body_mass_kg = "81.250"; draft.body_measurements_recorded_on = fixture.context.local_today;
  const sports = sectionProfile(draft, base, "sports");
  for (const key of ["constraint_status", "participation", "typical_days_per_week", "typical_minutes_per_week", "interruption", "recovery_notes"]) assert.deepEqual(sports[key], draft[key]);
  assert.equal(sports.body_mass_kg, base.body_mass_kg);
  const retained = retainProfileEdits(sports, draft, base);
  assert.equal(retained.body_mass_kg, "81.250");
  assert.deepEqual(profileChanges(retained, sports), { personal: true, sports: false, history: false });
});
