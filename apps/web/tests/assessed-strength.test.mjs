import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const f = JSON.parse(
  readFileSync(new URL("./fixtures/assessed-strength.json", import.meta.url)),
);
const { readTrainingReview } = load("src/lib/planning-cycles/training-plan.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const { StrengthAssessmentPanel, AssessedStrengthDetails } = load(
  "src/components/planning-cycles/strength-assessment.tsx",
);
const { PrescriptionDetails } = load(
  "src/components/planning-cycles/plan-output.tsx",
);
const { strengthReasons, evaluateStrength } = load(
  "src/lib/planning-cycles/strength-assessment.ts",
);
const expected = {
  owner: f.dumbbells.athlete_id,
  reference: f.dumbbells.program_reference,
  zone: f.dumbbells.timezone_name,
};
const hash = async (v) => {
  const body = { ...v };
  delete body.content_hash;
  v.content_hash = await sha(body);
};
const candidates = (v) =>
  v.result.alternatives
    .flatMap((g) => g.candidates)
    .filter((c) => c.sport === "STRENGTH");
const render = (component, props) =>
  renderToStaticMarkup(React.createElement(component, props));

for (const name of [
  "missing",
  "dumbbells",
  "machines",
  "after_accept",
  "updated",
])
  test(`real owned Python ${name} review validates assessment, sources and exact dose`, async () => {
    await readTrainingReview(f[name], expected);
  });

test("own references can enable strength without inventing a recorded session", () => {
  const v = f.dumbbells,
    cs = candidates(v);
  assert(cs.length);
  assert.equal(v.inputs.recent_sessions.length, 0);
  for (const c of cs) {
    assert.equal(c.duration_reference_session_id, null);
    assert.equal(c.duration_sec, 1200);
    assert.equal(c.template_version, "v0.3");
    assert.equal(c.strength_prescription.movements.length, 2);
    assert(c.strength_prescription.movements.every((e) => e.sets.length === 1));
    assert.equal(
      v.result.prescription_context.by_candidate[c.candidate_key]
        .product_default_used,
      true,
    );
    assert.equal(c.strength_prescription.source_kind, "self_report");
  }
});

test("machines use their own declared level and identity, without needing dumbbells", () => {
  const v = f.machines,
    cs = candidates(v);
  assert(cs.length);
  assert(
    !v.inputs.strength_assessment.receipt.artifact.snapshot.locations[0].resources.includes(
      "Kézisúlyzó",
    ),
  );
  for (const c of cs)
    for (const e of c.strength_prescription.movements) {
      assert(["seated_row", "leg_press"].includes(e.exercise_id));
      assert.equal(e.sets[0].load_kind, "machine_level");
      assert.equal(e.sets[0].load_value, "4.000000");
      assert.equal(e.machine_note, "Saját gép <ülés 4> / fogantyú 2");
    }
});

test("the current saved assessment advances while cycle calibration remains frozen", () => {
  const v = f.updated;
  assert(v.calibration_review);
  assert.equal(
    v.calibration_review.inputs.strength_assessment.receipt.artifact.revision,
    1,
  );
  assert.equal(v.inputs.strength_assessment.receipt.artifact.revision, 2);
  assert.deepEqual(
    v.result.prescription_context.starting_budget,
    v.calibration_review.result.prescription_context.starting_budget,
  );
  assert(
    candidates(v).every(
      (c) =>
        c.strength_prescription.assessment_reference.content_hash ===
        f.updated_receipt.artifact.content_hash,
    ),
  );
});

for (const [name, mutate] of [
  [
    "missing assessment section",
    (v) => {
      delete v.inputs.strength_assessment;
    },
  ],
  [
    "missing readiness summary",
    (v) => {
      delete v.result.strength_assessment;
    },
  ],
  [
    "future rule version",
    (v) => {
      v.inputs.strength_assessment.rules_version = "future";
    },
  ],
  [
    "planning authority",
    (v) => {
      v.inputs.strength_assessment.planning_authorized = true;
    },
  ],
  [
    "automatic progression",
    (v) => {
      v.inputs.strength_assessment.automatic_progression_applied = true;
    },
  ],
  [
    "personal response claim",
    (v) => {
      v.inputs.strength_assessment.personal_response_model_applied = true;
    },
  ],
  [
    "uncommitted assessment",
    (v) => {
      v.inputs.strength_assessment.receipt.committed = false;
    },
  ],
  [
    "foreign assessment owner",
    (v) => {
      v.inputs.strength_assessment.receipt.artifact.athlete_id =
        crypto.randomUUID();
    },
  ],
  [
    "false eligible movement count",
    (v) => {
      v.result.strength_assessment.exercise_readiness[0].eligible = false;
    },
  ],
  [
    "edited source hash",
    (v) => {
      v.inputs.strength_assessment.source_hash = "f".repeat(64);
    },
  ],
  [
    "foreign current source profile",
    (v) => {
      v.inputs.strength_assessment.source_body.profile_reference.content_hash =
        "b".repeat(64);
    },
  ],
  [
    "future receipt timestamp",
    (v) => {
      v.inputs.strength_assessment.receipt.durable_available_at =
        "2027-01-01T00:00:00Z";
    },
  ],
  [
    "profile data changed behind its original reference",
    (v) => {
      v.inputs.profile.data.typical_minutes_per_week = 400;
    },
  ],
  [
    "opportunity borrows resources absent from its venue",
    (v) => {
      const candidate = candidates(v)[0];
      v.inputs.days
        .find((d) => d.date === candidate.date)
        .opportunities.find((g) => g.key === candidate.opportunity_key)
        .constraints.resources.push("Kölcsönzött gép másik helyszínről");
    },
  ],
])
  test(`reject ${name} after review rehash`, async () => {
    const v = structuredClone(f.dumbbells);
    mutate(v);
    await hash(v);
    await assert.rejects(() => readTrainingReview(v, expected));
  });

async function editedCandidate(change, view = f.dumbbells) {
  const v = structuredClone(view),
    first = candidates(v)[0],
    old = first.candidate_key;
  const next = structuredClone(first);
  change(next);
  const body = { ...next };
  delete body.candidate_key;
  next.candidate_key = await sha(body);
  const replace = (list) =>
    list.map((c) => (c.candidate_key === old ? structuredClone(next) : c));
  v.result.proposals = replace(v.result.proposals);
  v.result.create = replace(v.result.create);
  for (const g of v.result.alternatives) {
    g.candidates = replace(g.candidates);
    if (g.recommended_candidate_key === old)
      g.recommended_candidate_key = next.candidate_key;
    if (g.selected_candidate_key === old)
      g.selected_candidate_key = next.candidate_key;
  }
  const meta = v.result.prescription_context.by_candidate[old];
  delete v.result.prescription_context.by_candidate[old];
  v.result.prescription_context.by_candidate[next.candidate_key] = {
    ...meta,
    strength: structuredClone(next.strength_prescription),
    duration_sec: next.duration_sec,
  };
  await hash(v);
  return v;
}
for (const [name, change] of [
  [
    "invented extra set",
    (c) => {
      c.strength_prescription.movements[0].sets.push({
        ...c.strength_prescription.movements[0].sets[0],
        id: crypto.randomUUID(),
      });
    },
  ],
  [
    "changed exact load digits",
    (c) => {
      const s = c.strength_prescription.movements[0].sets[0];
      s.load_kind = "external_kg";
      s.load_basis = "total";
      s.load_value = "999.000001";
    },
  ],
  [
    "increased repetitions",
    (c) => {
      const s = c.strength_prescription.movements[0].sets[0];
      s.repetitions = 100;
      s.hold_seconds = null;
    },
  ],
  [
    "unknown invented weight basis",
    (c) => {
      c.strength_prescription.movements[0].sets[0].load_basis = "unknown";
    },
  ],
  [
    "foreign source set",
    (c) => {
      c.strength_prescription.movements[0].sets[0].id = crypto.randomUUID();
    },
  ],
  [
    "other venue",
    (c) => {
      c.location_id = crypto.randomUUID();
    },
  ],
  [
    "other execution side",
    (c) => {
      c.strength_prescription.movements[0].side = "left";
    },
  ],
  [
    "hidden unsafe RIR",
    (c) => {
      c.strength_prescription.movements[0].sets[0].rir = "0";
    },
  ],
  [
    "1RM claim",
    (c) => {
      c.strength_prescription.one_rm_estimated = true;
    },
  ],
  [
    "full development claim",
    (c) => {
      c.strength_prescription.full_development_claim = true;
    },
  ],
  [
    "different visible description",
    (c) => {
      c.description = "Feltételezett 100 kg";
    },
  ],
  [
    "invented hold time",
    (c) => {
      c.strength_prescription.movements[0].sets[0].hold_seconds = "59";
      c.strength_prescription.movements[0].sets[0].repetitions = null;
    },
  ],
])
  test(`reject ${name} even when candidate, metadata and review are all rehashed`, async () => {
    const v = await editedCandidate(change);
    await assert.rejects(() => readTrainingReview(v, expected));
  });

test("a frozen calibration cannot substitute its older assessment for the latest one", async () => {
  const v = await editedCandidate((c) => {
    c.strength_prescription.assessment_reference =
      f.dumbbells.result.strength_assessment.reference;
  }, f.updated);
  await assert.rejects(() => readTrainingReview(v, expected));
});

test("reference age is checked against the proposed civil day", () => {
  const v = f.dumbbells,
    e = evaluateStrength(v.inputs.strength_assessment, v.inputs, "2026-12-19");
  assert(
    e.entries.every(
      (x) => !x.eligible && x.reasons.includes("RECENT_REFERENCE_MISSING"),
    ),
  );
});

test("the readiness panel names the missing assessment and links directly to its form", () => {
  const html = render(StrengthAssessmentPanel, { review: f.missing });
  assert(html.includes("Még nincs szerverre mentett kezdeti erőfelmérés"));
  assert(html.includes('href="/initial-assessment"'));
});

test("the plan displays exact source sets, load meanings, dates and the starting time basis", () => {
  const v = f.dumbbells,
    c = candidates(v).find((c) =>
      c.strength_prescription.movements.some((e) =>
        e.sets.some((s) => s.load_basis === "per_hand"),
      ),
    );
  assert(c);
  const html = render(PrescriptionDetails, {
    review: v,
    candidateKey: c.candidate_key,
  });
  assert(html.includes("12,500000 kg · kézenként"));
  assert(html.includes("8 ismétlés"));
  assert(html.includes("20 perces kezdő helyfoglalás"));
  assert(!html.includes("2 gyakorlat × 2 × 6"));
  for (const e of c.strength_prescription.movements)
    assert(html.includes(e.label));
});

test("machine names and settings remain escaped, with levels never relabelled as kilograms", () => {
  const v = f.machines,
    c = candidates(v)[0],
    meta = v.result.prescription_context.by_candidate[c.candidate_key];
  const html = render(AssessedStrengthDetails, {
    review: v,
    dose: meta.strength,
    seconds: c.duration_sec,
    declaredMinutes: null,
    productDefault: true,
  });
  assert(html.includes("4,000000 fokozat"));
  assert(html.includes("&lt;ülés 4&gt;"));
  assert(!html.includes("<ülés 4>") && !html.includes("4,000000 kg"));
});

test("precise new gate reasons include a repair destination and preserve unknown codes as text", () => {
  const v = structuredClone(f.dumbbells);
  v.result.strength_assessment.issues = [
    "STRENGTH_ASSESSMENT_SPORT_ROLE_REQUIRED",
    "<future reason>",
  ];
  const html = render(StrengthAssessmentPanel, { review: v });
  assert(
    html.includes(strengthReasons.STRENGTH_ASSESSMENT_SPORT_ROLE_REQUIRED),
  );
  assert(
    html.includes("&lt;future reason&gt;") && !html.includes("<future reason>"),
  );
});
