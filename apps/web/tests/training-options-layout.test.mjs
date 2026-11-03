import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/training-options.json", import.meta.url)),
);
const Schedule = load(
  "src/components/training-options/schedule-editor.tsx",
).default;
const Current = load(
  "src/components/training-options/current-week.tsx",
).default;
const Locations = load(
  "src/components/training-options/location-editor.tsx",
).default;
const Profile = load("src/components/athlete-setup/profile-form.tsx").default;

test("both timetables show seven named day blocks without a horizontal data table", () => {
  const general = renderToStaticMarkup(
    React.createElement(Schedule, {
      data: fixture.context.data,
      today: fixture.context.local_today,
      disabled: false,
      save: async () => true,
    }),
  );
  const current = renderToStaticMarkup(
    React.createElement(Current, {
      context: fixture.context,
      schedule: fixture.schedule,
      disabled: false,
      save: async () => true,
    }),
  );
  for (const markup of [general, current]) {
    assert.equal(
      (markup.match(/class="pt-panel pt-schedule-day"/g) ?? []).length,
      7,
    );
    assert(!markup.includes("<table"));
    assert(markup.includes("Hétfő"));
    assert(markup.includes("Vasárnap"));
  }
  assert(general.includes('aria-label="Szerda"'));
  assert(current.includes(`data-date="${fixture.context.start_date}"`));
  assert(current.includes("Általános órarend"));
});

test("location deletion is available beside editing, with a recoverable deleted list", () => {
  const data = structuredClone(fixture.context.data);
  data.locations[1].archived = true;
  const markup = renderToStaticMarkup(
    React.createElement(Locations, {
      data,
      disabled: false,
      save: async () => true,
    }),
  );
  assert(markup.includes("+ Helyszín hozzáadása"));
  assert(markup.includes("Szerkesztés"));
  assert(markup.includes("Sirály csónakház törlése"));
  assert(markup.includes("Törölt helyszínek · visszaállíthatók"));
  assert(markup.includes("Visszaállítás"));
  assert(!markup.includes("Csillaghegyi uszoda törlése"));
});

test("planning profile separates venues and availability while keeping personal entry fields", () => {
  const profile = fixture.review.inputs.profile.data;
  const planning = renderToStaticMarkup(
    React.createElement(Profile, {
      value: profile,
      today: fixture.context.local_today,
      planning: true,
      onChange() {},
    }),
  );
  for (const name of [
    "birth_date",
    "sex_reference",
    "target_sport",
    "constraint_status",
    "participation",
  ]) {
    assert(planning.includes(`name="${name}"`));
  }
  assert(!planning.includes("Általában elérhető eszközök, helyszínek"));
  assert(!planning.includes("Általában hány napon tudsz edzeni"));
  assert(!planning.includes("1. Ismerjük meg"));
  assert(planning.includes("Hetente legfeljebb hány napon szeretnél edzeni"));
  assert(planning.includes('href="/training-options/locations"'));
  assert(planning.includes('href="/training-options/schedule"'));
  assert(planning.includes("Becslés és további személyes adatok"));
  assert(!planning.includes('<details class="pt-profile-extras" open=""'));
  const complete = renderToStaticMarkup(
    React.createElement(Profile, {
      value: profile,
      today: fixture.context.local_today,
      onChange() {},
    }),
  );
  assert(complete.includes("Általában elérhető eszközök, helyszínek"));
});
