"use client";
import { useState } from "react";
import { protocolProposal } from "@/lib/planning-goals/forms";
import { toUtcField } from "@/lib/planning-goals/contracts";
import {
  capabilityLabels,
  evidenceLabels,
  metricLabels,
  metricLimit,
  roleLabels,
} from "@/lib/planning-goals/labels";
import type {
  Catalog,
  Endpoint,
  MacroArtifact,
  Metric,
  Period,
  ProtocolArtifact,
  Receipt,
} from "@/lib/planning-goals/types";
import {
  Area,
  buttonClass,
  Card,
  Field,
  secondaryClass,
  Select,
} from "./fields";

function EndpointFields({
  id,
  catalog,
  capabilities,
  endpoint,
  remove,
}: {
  id: string;
  catalog: Catalog;
  capabilities: string[];
  endpoint?: Endpoint;
  remove: () => void;
}) {
  const [metricKey, setMetricKey] = useState(endpoint?.metric_key ?? "");
  const [role, setRole] = useState(endpoint?.role ?? "");
  const metric: Metric | undefined = catalog.metrics.find(
    (m) => m.metric_key === metricKey,
  );
  const key = `e.${id}.`,
    p = endpoint?.procedure,
    r = endpoint?.change_requirement;
  return (
    <fieldset className="space-y-5 rounded-xl border border-zinc-600 p-4 sm:p-5">
      <legend className="px-2 font-semibold">Mérési cél</legend>
      <div className="flex justify-end">
        <button type="button" onClick={remove} className={secondaryClass}>
          Mérési cél eltávolítása
        </button>
      </div>
      <Field
        label="Mérési cél neve"
        name={key + "key"}
        defaultValue={endpoint?.endpoint_key}
        required
        maxLength={200}
        hint="A protokollon belül egyedi, később a méréseknél is ezt látod."
      />
      <Select
        label="Mérőszám"
        name={key + "metric"}
        value={metricKey}
        onChange={(event) => setMetricKey(event.target.value)}
        required
      >
        <option value="">Válassz mérőszámot</option>
        {catalog.metrics
          .filter((m) => capabilities.includes(m.capability_key))
          .map((m) => (
            <option key={m.metric_key} value={m.metric_key}>
              {capabilityLabels[m.capability_key]} ·{" "}
              {metricLabels[m.metric_key] ?? m.metric_key} ({m.unit})
            </option>
          ))}
      </Select>
      {metric && (
        <div className="rounded-lg bg-zinc-950 p-4 text-sm leading-6 text-zinc-300">
          <p>
            {evidenceLabels[metric.evidence_kind]} · kedvező irány:{" "}
            {metric.favourable_direction === "higher"
              ? "növekedés"
              : "csökkenés"}
          </p>
          <p>{metricLimit(metric.metric_key, metric.interpretation_limit)}</p>
        </div>
      )}
      <Select
        label="A mérési cél szerepe"
        name={key + "role"}
        value={role}
        onChange={(event) => setRole(event.target.value)}
        required
      >
        <option value="">Válassz mérési szerepet</option>
        <option value="primary" disabled={!metric?.primary_endpoint_eligible}>
          Elsődleges · célértékeléshez
        </option>
        <option
          value="supporting"
          disabled={metric?.evidence_kind === "subjective_context"}
        >
          Kiegészítő · leíró adat
        </option>
        <option value="context">Háttéradat</option>
      </Select>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Protokoll neve / kulcsa"
          name={key + "protocolKey"}
          defaultValue={p?.protocol_key}
          required
          maxLength={200}
        />
        <Field
          label="Protokoll verziója"
          name={key + "protocolVersion"}
          defaultValue={p?.protocol_version}
          required
          maxLength={200}
        />
      </div>
      <Select
        label="Protokoll eredete"
        name={key + "origin"}
        defaultValue={p?.origin ?? ""}
        required
      >
        <option value="">Válassz eredetet</option>
        <option value="external_reference">Külső hivatkozás alapján</option>
        <option value="explicit_custom">
          Kifejezetten megadott saját eljárás
        </option>
      </Select>
      <Area
        label="Az eljárás forrása / hivatkozása"
        name={key + "source"}
        defaultValue={p?.source_reference}
        required
      />
      <Field
        label="Mozgásforma"
        name={key + "modality"}
        defaultValue={p?.modality_key}
        required
        maxLength={200}
      />
      <Area
        label="Pontos gyakorlat vagy feladat"
        name={key + "task"}
        defaultValue={p?.exercise_or_task}
        required
      />
      <Area
        label="A mérés teljes menete"
        name={key + "procedure"}
        defaultValue={p?.procedure}
        required
      />
      <Area
        label="Eszközök, beállítások és eredményfeldolgozás"
        name={key + "equipment"}
        defaultValue={p?.equipment_and_processing}
        required
      />
      <Area
        label="Összehasonlíthatósági feltételek · soronként egy"
        name={key + "conditions"}
        defaultValue={p?.comparability_conditions.join("\n")}
        required
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Kiinduló ablak kezdete (UTC)"
          name={key + "baselineStart"}
          type="datetime-local"
          step="1"
          defaultValue={
            endpoint && toUtcField(endpoint.baseline_window.starts_at)
          }
          required
        />
        <Field
          label="Kiinduló ablak vége (UTC)"
          name={key + "baselineEnd"}
          type="datetime-local"
          step="1"
          defaultValue={
            endpoint && toUtcField(endpoint.baseline_window.ends_at)
          }
          required
        />
        <Field
          label="Záró ablak kezdete (UTC)"
          name={key + "followupStart"}
          type="datetime-local"
          step="1"
          defaultValue={
            endpoint && toUtcField(endpoint.followup_window.starts_at)
          }
          required
        />
        <Field
          label="Záró ablak vége (UTC)"
          name={key + "followupEnd"}
          type="datetime-local"
          step="1"
          defaultValue={
            endpoint && toUtcField(endpoint.followup_window.ends_at)
          }
          required
        />
      </div>
      {role === "primary" ? (
        <fieldset className="space-y-4 border-t border-zinc-700 pt-5">
          <legend className="text-sm font-semibold">
            Előre rögzített változási követelmény
          </legend>
          <p className="text-sm leading-6 text-zinc-300">
            A pozitív változás mindig kedvező: például rövidebb sprintidőnél az
            idő csökkenése számít pozitívnak. Fejlesztésnél pozitív minimum
            kell. Szinten tartásnál adj meg alsó és felső határt, amelyek
            közrefogják a nullát. Megengedett visszaesésnél negatív alsó határ
            kell, a nulla megengedésével.
          </p>
          <Select
            label="A változás mértéke"
            name={key + "basis"}
            defaultValue={r?.basis ?? ""}
            required
          >
            <option value="">Válassz mértéket</option>
            <option value="favourable_absolute_change">
              Abszolút változás · a mérőszám egységében
            </option>
            <option
              value="favourable_percent_change"
              disabled={metric?.scale !== "ratio"}
            >
              Százalékos változás · pozitív kiinduló értékből
            </option>
          </Select>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Elfogadható változás alsó határa"
              name={key + "minimum"}
              defaultValue={r?.minimum}
              inputMode="decimal"
              required
            />
            <Field
              label="Felső határ · ha szükséges"
              name={key + "maximum"}
              defaultValue={r?.maximum ?? ""}
              inputMode="decimal"
            />
          </div>
          <Field
            label="Becsült változási mérési hiba · opcionális"
            name={key + "error"}
            defaultValue={r?.measurement_error_estimate ?? ""}
            inputMode="decimal"
            hint="A választott változás egységében. Hiánya esetén a célértékelés visszatartott marad; a hiány nem nulla."
          />
          <Area
            label="A mérési hiba becslésének forrása · a becsléssel együtt"
            name={key + "errorSource"}
            defaultValue={r?.measurement_error_source ?? ""}
          />
        </fieldset>
      ) : (
        <input
          type="hidden"
          name={key + "basis"}
          value="favourable_absolute_change"
        />
      )}
    </fieldset>
  );
}

export default function ProtocolForm({
  catalog,
  macro,
  period,
  base,
  locked,
  submit,
  invalid,
}: {
  catalog: Catalog;
  macro: Receipt<MacroArtifact>;
  period: Period;
  base?: Receipt<ProtocolArtifact>;
  locked: boolean;
  submit: (proposal: unknown) => void;
  invalid: (message: string) => void;
}) {
  const [rows, setRows] = useState(() =>
    base
      ? base.artifact.proposal.endpoints.map((endpoint, index) => ({
          id: String(index),
          endpoint,
        }))
      : [{ id: "0", endpoint: undefined as Endpoint | undefined }],
  );
  const [counter, setCounter] = useState(rows.length);
  const directives = macro.artifact.proposal.mesocycle_directives.filter(
    (d) => d.mesocycle_period_id === period.id,
  );
  return (
    <Card
      title={
        base
          ? `Új mérési protokoll · ${base.artifact.proposal.revision + 1}. verzió`
          : "Mérési protokoll rögzítése · 1. verzió"
      }
    >
      <div className="mb-5 space-y-3 text-sm leading-6 text-zinc-300">
        <p>
          Minden hozzárendelt képességhez legalább egy elsődleges mérési cél
          kell. Az eljárásnak, a feltételeknek és az időablakoknak a kiinduló
          mérés előtt tartósan rögzítve kell lenniük. A külső hivatkozás
          önmagában nem igazol szabványosítást.
        </p>
        <p>
          Minden itt megadott időpont UTC. A ciklus naptári határait a forrás
          időzónájában ellenőrzi a rendszer:{" "}
          <strong>{macro.artifact.sources.timezone_name}</strong>.
        </p>
        <ul className="space-y-1">
          {directives.map((d) => (
            <li key={d.capability_key}>
              {capabilityLabels[d.capability_key]}:{" "}
              <strong>{roleLabels[d.role]}</strong>
            </li>
          ))}
        </ul>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          try {
            submit(
              protocolProposal(
                new FormData(event.currentTarget),
                catalog,
                macro,
                period.id,
                rows.map((r) => r.id),
                base,
              ),
            );
          } catch (error) {
            invalid(
              error instanceof Error ? error.message : "Ellenőrizd az űrlapot.",
            );
          }
        }}
      >
        <fieldset disabled={locked} className="space-y-6">
          {rows.map((row) => (
            <EndpointFields
              key={row.id}
              id={row.id}
              catalog={catalog}
              capabilities={directives.map((d) => d.capability_key)}
              endpoint={row.endpoint}
              remove={() => setRows(rows.filter((r) => r.id !== row.id))}
            />
          ))}
          <button
            type="button"
            disabled={rows.length >= 64}
            className={secondaryClass}
            onClick={() => {
              setRows([...rows, { id: String(counter), endpoint: undefined }]);
              setCounter(counter + 1);
            }}
          >
            Új mérési cél hozzáadása
          </button>
          <Area
            label="A protokoll indoklása"
            name="rationale"
            defaultValue={base?.artifact.proposal.rationale}
            required
          />
          <button type="submit" className={buttonClass} disabled={!rows.length}>
            Mérési protokoll mentése
          </button>
        </fieldset>
      </form>
    </Card>
  );
}
