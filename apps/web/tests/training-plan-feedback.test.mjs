import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const {
  ProfileReviewNotice,
  TrainingEvents,
  DaysWithoutProposal,
  eventIdentity,
  compactDates,
} = load("src/components/planning-cycles/training-plan-feedback.tsx");
const { readTrainingReview } = load("src/lib/planning-cycles/training-plan.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/training-plan.json", import.meta.url)),
);
const render = (component, props) =>
  renderToStaticMarkup(React.createElement(component, props));

for (const [reason, label] of [
  ["AGE_UNKNOWN", "Születési dátum"],
  ["TARGET_SPORT_UNKNOWN", "Célsportág"],
  ["SPORT_HISTORY_UNKNOWN", "Sportmúlt"],
  ["FUNCTIONAL_CONSTRAINTS_UNKNOWN", "Korlátozások"],
  ["PARTICIPATION_UNKNOWN", "Terhelhetőségi keret"],
])
  test("blocked profile identifies the actual field: " + reason, () => {
    const html = render(ProfileReviewNotice, {
      entry: {
        global_entry_gate: "REVIEW_REQUIRED",
        participation_status: "UNKNOWN",
        reasons: [reason],
      },
    });
    assert.ok(html.includes(label));
    assert.match(html, /href="\/athlete-setup"/);
    assert.match(html, /mentése után itt kérj újraértékelést/);
  });

test("an absent profile is distinct from an older review without diagnostics", () => {
  assert.match(
    render(ProfileReviewNotice, { entry: null }),
    /nem volt elérhető mentett sportolói felmérés/,
  );
  const old = render(ProfileReviewNotice, { entry: undefined });
  assert.match(old, /korábbi értékelés/);
  assert.doesNotMatch(old, /nem volt elérhető mentett/);
});

test("adaptations are explained even when the intake reason list is empty", () => {
  const html = render(ProfileReviewNotice, {
    entry: {
      global_entry_gate: "OPEN_WITH_CONSTRAINTS",
      participation_status: "READY_WITH_CONSTRAINTS",
      reasons: [],
      constraints: [
        {
          key: "shoulder",
          affected_area: "Váll",
          restricted_activities: ["Fej fölötti nyomás"],
          adaptations: "Kisebb mozgástartomány",
          professional_guidance: "Rögzített szakmai keret",
        },
      ],
    },
  });
  assert.match(html, /Alkalmazkodást igénylő korlátozás/);
  assert.match(html, /Fej fölötti nyomás/);
  assert.match(html, /Kisebb mozgástartomány/);
});

test("an explicitly requested professional review has a specific explanation", () => {
  assert.match(
    render(ProfileReviewNotice, {
      entry: {
        global_entry_gate: "REVIEW_REQUIRED",
        participation_status: "PROFESSIONAL_REVIEW_REQUIRED",
        reasons: [],
      },
    }),
    /szakmai felülvizsgálatot kér/,
  );
});

test("profile notes and workout names render as escaped text", () => {
  const html = render(ProfileReviewNotice, {
    entry: {
      global_entry_gate: "OPEN_WITH_CONSTRAINTS",
      participation_status: "READY_WITH_CONSTRAINTS",
      reasons: [],
      constraints: [
        {
          key: "x",
          affected_area: "<script>alert(1)</script>",
          restricted_activities: [],
          adaptations: "",
          professional_guidance: "",
        },
      ],
    },
  });
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(!html.includes("<script>"));
});

test("an older stored event recovers date and plan title from its frozen sources", () => {
  const review = structuredClone(fixture.review);
  review.inputs.recent_sessions = [
    { id: "old-session", sport: "KAYAK", started_at: "2026-10-21T06:00:00Z" },
  ];
  review.plan_snapshots = [
    {
      workout: {
        id: "old-plan",
        title: "Korábbi 8 km kajak",
        date: "2026-10-21",
        sport: "KAYAK",
      },
    },
  ];
  const identity = eventIdentity(
    {
      kind: "planned_completed",
      session_id: "old-session",
      workout_id: "old-plan",
    },
    review,
  );
  assert.equal(identity.title, "Korábbi 8 km kajak");
  assert.equal(identity.started_at, "2026-10-21T06:00:00Z");
  assert.equal(identity.href, "/sessions/old-session");
});

test("an unnamed unplanned session has a sport label and retains its measured date", () => {
  const review = structuredClone(fixture.review);
  review.inputs.recent_sessions = [
    { id: "run", sport: "RUNNING", started_at: "2026-10-21T06:00:00Z" },
  ];
  const identity = eventIdentity(
    { kind: "unplanned_completed", session_id: "run", workout_id: null },
    review,
  );
  assert.equal(identity.title, "Futás");
  assert.equal(identity.started_at, "2026-10-21T06:00:00Z");
});

test("event groups show counts and identifiable names with local dates", () => {
  const review = structuredClone(fixture.review);
  review.result.events = [
    {
      kind: "planned_completed",
      session_id: "one",
      workout_id: null,
      title: "Evezés",
      sport: "KAYAK",
      started_at: "2026-10-21T06:00:00Z",
    },
    {
      kind: "planned_completed",
      session_id: "two",
      workout_id: null,
      title: "Második evezés",
      sport: "KAYAK",
      started_at: "2026-10-22T06:00:00Z",
    },
    {
      kind: "execution_unknown",
      workout_id: "three",
      title: "PFT",
      date: "2026-10-23",
      can_confirm_missed: false,
    },
  ];
  const html = render(TrainingEvents, {
    review,
    zone: "Europe/Budapest",
    disabled: false,
    onConfirmMissed: () => {
      throw Error("render must not confirm");
    },
  });
  assert.match(html, /Tervezett és teljesített edzés · 2/);
  assert.match(html, /2026\. 10\. 21\./);
  assert.match(html, /Evezés/);
  assert.match(html, /PFT/);
  assert.doesNotMatch(html, /Megerősítem, hogy kimaradt/);
});

test("the seven repeated profile exclusions render as a single date range", () => {
  const days = Array.from({ length: 7 }, (_, i) => ({
    date: new Date(Date.UTC(2026, 9, 31 + i)).toISOString().slice(0, 10),
    reason: "PROFILE_REVIEW_REQUIRED",
  }));
  const html = render(DaysWithoutProposal, { days });
  assert.match(html, /2026-10-31 – 2026-11-06/);
  assert.equal((html.match(/A fenti profilindokok/g) ?? []).length, 1);
});

test("compact ranges never hide nonconsecutive dates", () => {
  assert.equal(
    compactDates(["2026-11-03", "2026-10-31", "2026-11-02"]),
    "2026-10-31; 2026-11-02 – 2026-11-03",
  );
});

test("malformed specific profile reasons are rejected before rendering", async () => {
  const v = structuredClone(fixture.review);
  v.result.entry_review.reasons = "AGE_UNKNOWN";
  const { content_hash, ...body } = v;
  await assert.rejects(
    readTrainingReview(
      { ...body, content_hash: await sha(body) },
      {
        owner: v.athlete_id,
        reference: v.program_reference,
        zone: v.timezone_name,
      },
    ),
  );
});
