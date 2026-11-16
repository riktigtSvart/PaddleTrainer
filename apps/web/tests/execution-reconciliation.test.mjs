import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(
  readFileSync(
    new URL("./fixtures/execution-reconciliation.json", import.meta.url),
  ),
);
const { readTrainingReview } = load("src/lib/planning-cycles/training-plan.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const { TrainingEvents } = load(
  "src/components/planning-cycles/training-plan-feedback.tsx",
);
const expected = {
  owner: fixture.absent.athlete_id,
  reference: fixture.absent.program_reference,
  zone: fixture.absent.timezone_name,
};

test("real HTTP reviews validate unknown, sync-checked absence and late completion", async () => {
  for (const value of Object.values(fixture))
    await readTrainingReview(value, expected);
  assert(
    fixture.before.result.events.some(
      (event) => event.kind === "execution_unknown",
    ),
  );
  assert.equal(
    fixture.absent.result.events.filter(
      (event) => event.kind === "not_recorded_after_sync",
    ).length,
    2,
  );
  assert(
    fixture.late.result.events.some(
      (event) => event.kind === "planned_completed",
    ),
  );
  assert.equal(
    fixture.resolved.result.execution_reconciliation.resolved_links.length,
    1,
  );
  const unknownDuration = fixture.absent.plan_snapshots.find(
    (snapshot) => snapshot.workout.duration_sec === null,
  );
  assert(unknownDuration);
  assert(
    fixture.absent.result.events.some(
      (event) =>
        event.kind === "not_recorded_after_sync" &&
        event.workout_id === unknownDuration.workout.id,
    ),
  );
});

const cases = {
  "foreign reconciliation owner": (value) => {
    value.result.execution_reconciliation.athlete_id =
      "00000000-0000-0000-0000-000000000001";
  },
  "sessions omitted from sync": (value) => {
    value.result.execution_reconciliation.sync_windows[0].sessions.skipped = 1;
  },
  "unknown import count": (value) => {
    value.result.execution_reconciliation.sync_windows[0].sessions.imported =
      null;
  },
  "missing sync source": (value) => {
    value.result.execution_reconciliation.sync_windows = [];
  },
  "missing reconciliation section": (value) => {
    delete value.result.execution_reconciliation;
  },
  "foreign sync identity": (value) => {
    value.result.execution_reconciliation.sync_windows[0].result_reference.artifact_id =
      "pt-data-sync:foreign:POLAR:bad";
  },
  "import started before workout ended": (value) => {
    value.result.execution_reconciliation.sync_windows[0].started_at =
      "2026-10-22T05:00:00+00:00";
  },
  "source arrived after capture": (value) => {
    value.result.execution_reconciliation.sync_windows[0].finished_at =
      "2099-01-01T00:00:00+00:00";
  },
  "changed checked-through time": (value) => {
    value.result.events.find(
      (event) => event.kind === "not_recorded_after_sync",
    ).checked_through = "2026-10-23T09:00:00+00:00";
  },
  "invented manual confirmation": (value) => {
    value.result.events.find(
      (event) => event.kind === "not_recorded_after_sync",
    ).can_confirm_missed = true;
  },
  "absence attached to unknown workout": (value) => {
    value.result.events.find(
      (event) => event.kind === "not_recorded_after_sync",
    ).workout_id = "unknown";
  },
  "a full day was not covered for an unknown clock": (value) => {
    const id = value.plan_snapshots.find(
      (snapshot) => snapshot.workout.duration_sec === null,
    ).workout.id;
    value.result.events.find(
      (event) => event.workout_id === id,
    ).absence_window.to_exclusive_at = "2026-10-22T12:00:00+00:00";
  },
};
for (const [name, change] of Object.entries(cases)) {
  test(`reject rehashed execution evidence: ${name}`, async () => {
    const value = structuredClone(fixture.absent);
    change(value);
    const { content_hash, ...body } = value;
    value.content_hash = await sha(body);
    await assert.rejects(() => readTrainingReview(value, expected));
  });
}

test("sync-checked absence is explained separately and does not ask for manual confirmation", () => {
  const markup = renderToStaticMarkup(
    React.createElement(TrainingEvents, {
      review: fixture.absent,
      zone: fixture.absent.timezone_name,
      disabled: false,
      onConfirmMissed() {},
    }),
  );
  assert(markup.includes("Nincs rögzített teljesítés · szinkronellenőrizve"));
  assert(markup.includes("később beérkező teljesítésnél újraértékeli"));
  assert(!markup.includes("Megerősítem, hogy kimaradt"));
});

for (const kind of ["foreign session", "guessed relationship"]) {
  test(`reject a rehashed resolved link: ${kind}`, async () => {
    const value = structuredClone(fixture.resolved);
    const link = value.result.execution_reconciliation.resolved_links[0];
    if (kind === "foreign session")
      link.session_id = "00000000-0000-0000-0000-000000000001";
    else link.basis = "same_name_and_time";
    const { content_hash, ...body } = value;
    value.content_hash = await sha(body);
    await assert.rejects(() => readTrainingReview(value, expected));
  });
}
