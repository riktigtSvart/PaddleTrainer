"use client";
import { useState } from "react";
import { measurementProposal, text } from "@/lib/planning-goals/forms";
import { reference, utcInput } from "@/lib/planning-goals/contracts";
import {
  dateLabel,
  evidenceLabels,
  metricLabels,
} from "@/lib/planning-goals/labels";
import type {
  Catalog,
  ProtocolArtifact,
  Receipt,
} from "@/lib/planning-goals/types";
import { Area, buttonClass, Card, Field, Select } from "./fields";

export function MeasurementForm({
  protocol,
  catalog,
  locked,
  submit,
  invalid,
}: {
  protocol: Receipt<ProtocolArtifact>;
  catalog: Catalog;
  locked: boolean;
  submit: (proposal: unknown) => void;
  invalid: (message: string) => void;
}) {
  const [endpointKey, setEndpointKey] = useState("");
  const endpoint = protocol.artifact.proposal.endpoints.find(
    (e) => e.endpoint_key === endpointKey,
  );
  const metric = catalog.metrics.find(
    (m) => m.metric_key === endpoint?.metric_key,
  );
  return (
    <Card title="Mérési eredmény rögzítése">
      <p className="mb-5 text-sm leading-6 text-zinc-300">
        Az eredményt a kiválasztott protokoll pontos mérési céljához rögzítjük.
        Az egységet és az eljárást a protokoll határozza meg. Egy időablakban
        több megfelelő teljes eredmény esetén a rendszer visszatartja az
        összehasonlítást.
      </p>
      <fieldset disabled={locked}>
        <Select
          label="Mérési cél kiválasztása"
          value={endpointKey}
          onChange={(event) => setEndpointKey(event.target.value)}
        >
          <option value="">Válassz mérési célt</option>
          {protocol.artifact.proposal.endpoints.map((e) => (
            <option key={e.endpoint_key} value={e.endpoint_key}>
              {e.endpoint_key} · {metricLabels[e.metric_key] ?? e.metric_key}
            </option>
          ))}
        </Select>
      </fieldset>
      {endpoint && metric && (
        <form
          key={endpointKey}
          className="mt-6"
          onSubmit={(event) => {
            event.preventDefault();
            try {
              submit(
                measurementProposal(
                  new FormData(event.currentTarget),
                  protocol,
                  endpoint,
                  crypto.randomUUID(),
                ),
              );
            } catch (error) {
              invalid(
                error instanceof Error
                  ? error.message
                  : "Ellenőrizd az űrlapot.",
              );
            }
          }}
        >
          <fieldset disabled={locked} className="space-y-5">
            <div className="space-y-2 rounded-xl bg-zinc-950 p-4 text-sm leading-6 text-zinc-300">
              <p className="font-semibold text-zinc-100">
                {metricLabels[metric.metric_key]} · {metric.unit} ·{" "}
                {evidenceLabels[metric.evidence_kind]}
              </p>
              <p>
                Kiinduló ablak: {dateLabel(endpoint.baseline_window.starts_at)}{" "}
                – {dateLabel(endpoint.baseline_window.ends_at)}
              </p>
              <p>
                Záró ablak: {dateLabel(endpoint.followup_window.starts_at)} –{" "}
                {dateLabel(endpoint.followup_window.ends_at)}
              </p>
              <details>
                <summary className="cursor-pointer text-teal-200">
                  A pontos mérési eljárás
                </summary>
                <div className="mt-3 space-y-2 whitespace-pre-wrap">
                  <p>{endpoint.procedure.exercise_or_task}</p>
                  <p>{endpoint.procedure.procedure}</p>
                  <p>{endpoint.procedure.equipment_and_processing}</p>
                  <p>Forrás: {endpoint.procedure.source_reference}</p>
                </div>
              </details>
            </div>
            <Field
              label={`Mért érték (${metric.unit})`}
              name="value"
              inputMode="decimal"
              required
              hint="A tizedesvessző is használható. A beírt számjegyeket kerekítés nélkül küldjük el."
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Végrehajtás kezdete (UTC)"
                name="startedAt"
                type="datetime-local"
                step="1"
                required
              />
              <Field
                label="Végrehajtás vége (UTC)"
                name="endedAt"
                type="datetime-local"
                step="1"
                required
              />
            </div>
            <Select
              label="Végrehajtás teljessége"
              name="completion"
              defaultValue=""
              required
            >
              <option value="">Válassz állapotot</option>
              <option value="complete">Teljes</option>
              <option value="incomplete">Nem teljes</option>
              <option value="unknown">Ismeretlen</option>
            </Select>
            <Select
              label="Az eredmény szintje"
              name="resultLevel"
              defaultValue=""
              required
            >
              <option value="">Válassz eredményszintet</option>
              <option value="complete_protocol_result">
                A teljes protokoll eredménye
              </option>
              <option value="within_protocol_trial">
                Protokollon belüli részpróba
              </option>
              <option value="unknown">Ismeretlen</option>
            </Select>
            <Field
              label="Méréskor rögzített testtömeg (kg) · opcionális"
              name="bodyMass"
              inputMode="decimal"
              hint={
                metric.metric_key === "VO2MAX_RELATIVE"
                  ? "Mért relatív VO₂max esetén a testtömeg hiánya visszatartott értékelést eredményez."
                  : "Akkor töltsd ki, ha a méréshez tartozó testtömeg rendelkezésre áll."
              }
            />
            {endpoint.procedure.comparability_conditions.map((condition, i) => (
              <fieldset
                key={i}
                className="space-y-4 rounded-xl border border-zinc-700 p-4"
              >
                <legend className="max-w-full px-2 text-sm font-medium">
                  {condition}
                </legend>
                <Select
                  label={`Feltétel állapota: ${condition}`}
                  name={`condition.${i}.status`}
                  defaultValue=""
                  required
                >
                  <option value="">Válassz megfigyelt állapotot</option>
                  <option value="met">Teljesült</option>
                  <option value="not_met">Nem teljesült</option>
                  <option value="unknown">Ismeretlen</option>
                </Select>
                <Area
                  label={`Megfigyelés: ${condition}`}
                  name={`condition.${i}.observation`}
                  required
                />
                <Area
                  label={`Megfigyelés forrása: ${condition}`}
                  name={`condition.${i}.evidence`}
                  required
                />
              </fieldset>
            ))}
            <Area
              label="A teljes végrehajtás bizonyítéka / forráshivatkozása"
              name="executionEvidence"
              required
            />
            <p className="text-sm text-zinc-400">
              Az ismeretlen és a nem teljesült feltételt is megőrizzük. A
              rögzítés a megadott végrehajtási adatokat tárolja; nem igazol
              független ellenőrzést.
            </p>
            <button type="submit" className={buttonClass}>
              Mérési eredmény mentése
            </button>
          </fieldset>
        </form>
      )}
    </Card>
  );
}
export function AssessmentForm({
  protocol,
  locked,
  submit,
  invalid,
}: {
  protocol: Receipt<ProtocolArtifact>;
  locked: boolean;
  submit: (proposal: unknown) => void;
  invalid: (message: string) => void;
}) {
  return (
    <Card title="Célértékelés készítése">
      <p className="mb-5 text-sm leading-6 text-zinc-300">
        Az értékelés a megadott záróidőpontig történt méréseket vizsgálja, a
        most elérhető adatokból. Ugyanez a záróidőpont ugyanazt a befagyasztott
        értékelést adja vissza. Későbbi időponttal a késve rögzített adatok is
        bekerülhetnek. A nyitott ablak és a hiányos vagy többértelmű mérés
        visszatartott értékeléshez vezet.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          try {
            const data = new FormData(event.currentTarget);
            submit({
              protocol_reference: reference(protocol.artifact),
              activity_cutoff_at: utcInput(text(data, "cutoff")),
            });
          } catch (error) {
            invalid(
              error instanceof Error
                ? error.message
                : "Ellenőrizd az időpontot.",
            );
          }
        }}
      >
        <fieldset disabled={locked} className="space-y-5">
          <Field
            label="Mérési záróidőpont (UTC)"
            name="cutoff"
            type="datetime-local"
            step="1"
            required
            hint="Nem lehet a jövőben. A teljes összehasonlításhoz mindkét mérési ablaknak le kell zárulnia."
          />
          <button type="submit" className={buttonClass}>
            Célértékelés készítése
          </button>
        </fieldset>
      </form>
    </Card>
  );
}
