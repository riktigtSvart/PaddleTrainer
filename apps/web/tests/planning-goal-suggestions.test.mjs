import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const data = JSON.parse(
  readFileSync(
    new URL("./fixtures/planning-goal-suggestions.json", import.meta.url),
  ),
);
const { checkedSuggestion } = load(
  "src/lib/planning-cycles/goal-suggestions.ts",
);
const { readPlanningInputs } = load("src/lib/planning-cycles/inputs.ts");
const period = data.periods.find((p) => p.period_type === "MACROCYCLE"),
  children = data.periods.filter((p) => p.parent_id === period.id);
const stored = data.goal_versions.find(
  (v) => v.period_id === period.id,
).artifact;
const expected = {
  owner: data.athlete_id,
  reference: data.program_reference,
  zone: data.timezone_name,
  first: data.start_date,
  last: data.end_date,
};
const base = { reference: stored, revision: stored.proposal.revision };
const check = (v, b = base) =>
  checkedSuggestion(v, period, children, ["VO2_CAPACITY"], b);
test("real Python owned HTTP suggestion verifies hash and retains recorded roles", async () => {
  const v = await readPlanningInputs(data, expected);
  const m = check(v);
  assert.equal(m.rows[0].role, "primary_development");
  assert.equal(m.rows[0].mesocycle_directives[0].role, "maintenance");
  assert.ok(
    m.rows[0].family_links.every(
      (f) => !f.selected && !f.eligibility_evaluated,
    ),
  );
});
for (const [name, edit] of [
  [
    "source revision advanced",
    (v) => v.goal_suggestions.macrocycles[0].base_revision++,
  ],
  [
    "source hash changed",
    (v) =>
      (v.goal_suggestions.macrocycles[0].base_reference.content_hash =
        "f".repeat(64)),
  ],
  [
    "period moved",
    (v) => (v.periods.find((p) => p.id === period.id).end_date = "2030-01-01"),
  ],
  [
    "duplicate capability",
    (v) =>
      v.goal_suggestions.macrocycles[0].rows.push(
        v.goal_suggestions.macrocycles[0].rows[0],
      ),
  ],
  [
    "missing mesocycle",
    (v) => v.goal_suggestions.macrocycles[0].rows[0].mesocycle_directives.pop(),
  ],
  [
    "undeclared role",
    (v) => (v.goal_suggestions.macrocycles[0].rows[0].role = "auto"),
  ],
  ["dose escalation", (v) => (v.goal_suggestions.dose_selected = true)],
  [
    "family eligibility escalation",
    (v) =>
      (v.goal_suggestions.macrocycles[0].rows[0].family_links[0].eligibility_evaluated = true),
  ],
  ["unknown schema", (v) => (v.goal_suggestions.rules_version = "other")],
])
  test("reject suggestion: " + name, () => {
    const v = structuredClone(data);
    edit(v);
    assert.throws(() => check(v));
  });
test("must start a new version from the actual recorded parent", () =>
  assert.throws(() =>
    checkedSuggestion(data, period, children, ["VO2_CAPACITY"]),
  ));
test("macro form offers explicit suggestion request and retains existing durable submit", () => {
  const Macro = load("src/components/planning-goals/macro-form.tsx").default;
  const html = renderToStaticMarkup(
    React.createElement(Macro, {
      catalog: {
        capabilities: ["VO2_CAPACITY"],
        goal_roles: [
          "primary_development",
          "secondary_development",
          "maintenance",
          "permitted_decline",
        ],
      },
      period,
      periods: data.periods,
      locked: false,
      submit() {
        throw Error("Unexpected save");
      },
      invalid() {},
      cycle: {
        owner: data.athlete_id,
        reference: data.program_reference,
        zone: data.timezone_name,
        today: "2026-10-23",
      },
    }),
  );
  assert.match(html, /Céljavaslat a felkészülés adataiból/);
  assert.match(html, /Makrocikluscélok mentése/);
  assert.doesNotMatch(html, /kiválasztott edzés vagy dózis/);
});
