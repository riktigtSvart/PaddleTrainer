import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/preparation.json", import.meta.url)),
);
const { readTrainingReview } = load("src/lib/planning-cycles/training-plan.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const { newWindow, normalizeProfile } = load(
  "src/lib/athlete-setup/contracts.ts",
);
const { setupSteps } = load("src/lib/athlete-setup/journey.ts");
const { readDurationEstimate } = load("src/lib/calendar/duration-estimate.ts");
const { defaultDetails } = load("src/lib/calendar/constraints.ts");
const { weeklyProposal, generalAgreementProposal } = load(
  "src/components/athlete-setup/weekly-agreement.tsx",
);
const { PreparationChecklist } = load(
  "src/components/planning-cycles/training-plan-feedback.tsx",
);
const SetupProgress = load(
  "src/components/athlete-setup/setup-progress.tsx",
).default;
const DurationDetails = load(
  "src/components/calendar/duration-details.tsx",
).default;
const expected = {
  owner: fixture.review.athlete_id,
  reference: fixture.review.program_reference,
  zone: fixture.review.timezone_name,
};
const render = (component, props) =>
  renderToStaticMarkup(React.createElement(component, props));
const e = Object.values(fixture.schedule.duration_estimates)[0];

test("new general windows and weekly agreements require no sport/intensity specialization", () => {
  assert.equal(newWindow().sport_scope, "any");
  assert.equal(newWindow().effort_cap, "any");
  assert.equal(defaultDetails("available").sport_scope, "any");
  assert.equal(defaultDetails("available").effort_cap, "any");
  const before = structuredClone(fixture.schedule);
  const proposal = weeklyProposal(fixture.schedule, {
    start: "2026-10-24",
    end: "",
    weekdays: [4, 0, 2],
    from: "18:00",
    to: "19:00",
    minutes: 60,
  });
  const rule = proposal.data.rules.at(-1);
  assert.deepEqual(rule.weekdays, [0, 2, 4]);
  assert.equal(rule.end_date, null);
  assert.equal(rule.details.sport_scope, "any");
  assert.equal(rule.details.effort_cap, "any");
  assert.deepEqual(proposal.data.exceptions, before.data.exceptions);
  assert.deepEqual(fixture.schedule, before);
});

test("a weekly time budget outside its window is rejected before preview", () => {
  assert.throws(() =>
    weeklyProposal(fixture.schedule, {
      start: "2026-10-24",
      end: "",
      weekdays: [0],
      from: "18:00",
      to: "19:00",
      minutes: 90,
    }),
  );
});

test("generalizing an old agreement preserves past dates, explicit limits and every daily exception", () => {
  const context = structuredClone(fixture.schedule),
    id = crypto.randomUUID();
  const details = {
    ...defaultDetails("available"),
    sport_scope: "unknown",
    effort_cap: "easy",
  };
  context.data.rules = [
    {
      id,
      start_date: "2026-10-19",
      end_date: null,
      repeat: "weekly",
      weekdays: [0, 2, 4],
      details,
    },
  ];
  context.data.exceptions = [
    { rule_id: id, date: "2026-10-21", replacement: null },
    { rule_id: id, date: "2026-10-26", replacement: null },
    {
      rule_id: id,
      date: "2026-10-28",
      replacement: { ...details, resources: ["kajak"] },
    },
  ];
  const before = structuredClone(context);
  const proposal = generalAgreementProposal(context, id, "2026-10-26");
  const past = proposal.data.rules.find((r) => r.id === id),
    future = proposal.data.rules.at(-1);
  assert.equal(past.end_date, "2026-10-25");
  assert.equal(past.details.sport_scope, "unknown");
  assert.equal(future.start_date, "2026-10-26");
  assert.equal(future.end_date, null);
  assert.equal(future.details.sport_scope, "any");
  assert.equal(future.details.effort_cap, "easy");
  assert.equal(proposal.data.exceptions[0].rule_id, id);
  assert.equal(proposal.data.exceptions[1].rule_id, future.id);
  assert.equal(proposal.data.exceptions[1].replacement, null);
  assert.deepEqual(
    proposal.data.exceptions[2].replacement,
    before.data.exceptions[2].replacement,
  );
  assert.deepEqual(context, before);
});

test("progress uses actual saved gates and resources while history is optional", () => {
  let steps = setupSteps(fixture.context, fixture.schedule);
  assert.equal(steps[0].state, "ready");
  assert.equal(steps[1].state, "ready");
  const context = structuredClone(fixture.context);
  context.profile.artifact.proposal.data.resources = [];
  steps = setupSteps(context, null);
  assert.equal(steps[0].state, "needed");
  assert.match(steps[0].detail, /eszköz/);
  assert.equal(steps[1].state, "needed");
  context.profile.artifact.proposal.data.manual_observations = [];
  context.profile.artifact.imported_observations = [];
  assert.equal(setupSteps(context, null)[2].state, "optional");
});

test("the guide has a keyboard accessible current step, next destination and saved-state explanation", () => {
  const html = render(SetupProgress, {
    context: fixture.context,
    schedule: fixture.schedule,
    active: "calendar",
    onSelect() {},
  });
  assert.match(html, /aria-current="step"/);
  assert.match(html, /mentett adatokra/);
  assert.match(html, /href="\/planning-cycles"/);
  assert.match(html, /Előzmények és visszajelzések/);
});

test("real Python review shows exact remaining inputs and separates availability from the planning policy", async () => {
  const review = await readTrainingReview(fixture.review, expected);
  const html = render(PreparationChecklist, { review });
  assert.match(html, /6 nap \/ 450 perc/);
  assert.match(html, /3 alkalom \/ 180 perc/);
  assert.match(html, /Becsléssel figyelembe vett edzések/);
  assert.match(html, /Pontosítandó edzés/);
  assert.match(html, /href="\/athlete-setup#calendar"/);
  assert.match(html, /felsoroltak különböző mintákat/);
  assert.ok(review.result.preparation.estimated_duration_workout_ids.length);
  assert.ok(review.result.preparation.unknown_duration_workout_ids.length);
});

for (const [name, change] of [
  [
    "unknown workout",
    (p) => {
      p.unknown_duration_workout_ids = [crypto.randomUUID()];
    },
  ],
  [
    "negative limit",
    (p) => {
      p.max_minutes_per_7_days = -1;
    },
  ],
  [
    "invented availability",
    (p) => {
      p.available_day_count = 29;
    },
  ],
  [
    "invalid selection date",
    (p) => {
      p.selection_issues.push({ date: "2099-01-01", codes: ["x"] });
    },
  ],
])
  test("rejects malformed preparation metadata: " + name, async () => {
    const review = structuredClone(fixture.review);
    change(review.result.preparation);
    const { content_hash, ...body } = review;
    review.content_hash = await sha(body);
    await assert.rejects(() => readTrainingReview(review, expected));
  });

test("real extrapolation exposes its coefficient, wider range, source links and unverified conditions", () => {
  const estimate = readDurationEstimate(
    e,
    e.plan_id,
    fixture.review.athlete_id,
  );
  assert.equal(estimate.extrapolated, true);
  assert.equal(estimate.doubling_slowdown_pct, 5);
  const html = render(DurationDetails, {
    estimate,
    zone: fixture.review.timezone_name,
  });
  assert.match(html, /távokon túli becslés/);
  assert.match(html, /5%/);
  assert.match(html, /pontossága még nincs visszamérve/);
  assert.ok(html.includes("/sessions/" + estimate.samples[0].session_id));
});

for (const [name, change] of [
  [
    "wrong exponent",
    (x) => {
      x.exponent = 1;
    },
  ],
  [
    "unsupported ratio",
    (x) => {
      x.max_distance_ratio = 200;
    },
  ],
  [
    "claimed individual fit",
    (x) => {
      x.personal_coefficient_fitted = true;
    },
  ],
  [
    "claimed matched conditions",
    (x) => {
      x.conditions_verified = true;
    },
  ],
  [
    "wrong projection",
    (x) => {
      x.samples[0].projected_sec *= 1.05;
    },
  ],
  [
    "false interpolation",
    (x) => {
      x.extrapolated = false;
    },
  ],
])
  test("rejects invalid extrapolation metadata: " + name, () => {
    const estimate = structuredClone(e);
    change(estimate);
    assert.throws(() =>
      readDurationEstimate(estimate, e.plan_id, fixture.review.athlete_id),
    );
  });

test("profile slowdown setting remains an explicit bounded percentage", () => {
  const profile = structuredClone(
    fixture.context.profile.artifact.proposal.data,
  );
  profile.duration_doubling_slowdown_pct = 7;
  assert.equal(
    normalizeProfile(profile, fixture.context.local_today)
      .duration_doubling_slowdown_pct,
    7,
  );
  for (const value of [true, -1, 21, 2.5])
    assert.throws(() =>
      normalizeProfile(
        { ...profile, duration_doubling_slowdown_pct: value },
        fixture.context.local_today,
      ),
    );
});
