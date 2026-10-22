import {
  capabilityLabels,
  criterionLabels,
  dateLabel,
  evidenceLabels,
  metricLabels,
  metricLimit,
  reasonLabel,
  roleLabels,
} from "@/lib/planning-goals/labels";
import type {
  AssessmentArtifact,
  Criterion,
  Endpoint,
  ExactChange,
  MacroArtifact,
  MeasurementArtifact,
  ProtocolArtifact,
  Receipt,
  Resource,
} from "@/lib/planning-goals/types";
import { Card } from "./fields";

export function CriterionStatus({ value }: { value: Criterion }) {
  const style =
    value === "met_under_declared_error"
      ? "border-teal-500/50 bg-teal-950/40 text-teal-100"
      : value === "descriptive_only"
        ? "border-zinc-600 text-zinc-200"
        : "border-amber-500/50 bg-amber-950/30 text-amber-100";
  return (
    <span
      className={`inline-block rounded-lg border px-3 py-2 text-sm ${style}`}
    >
      {criterionLabels[value] ?? "Ismeretlen értékelési állapot"}
    </span>
  );
}
function Reasons({ codes }: { codes: string[] }) {
  return codes.length ? (
    <ul className="mt-3 list-disc space-y-1 pl-5 text-sm leading-6 text-zinc-300">
      {codes.map((code) => (
        <li key={code}>{reasonLabel(code)}</li>
      ))}
    </ul>
  ) : null;
}
function Exact({ value, unit }: { value: ExactChange | null; unit: string }) {
  return value ? (
    <div className="break-all">
      {value.display_decimal} {unit}
      <details className="mt-1 text-xs text-zinc-400">
        <summary className="cursor-pointer">Pontos törtérték</summary>
        {value.numerator}/{value.denominator}
      </details>
    </div>
  ) : (
    <span className="text-zinc-400">Nem számítható</span>
  );
}
export function VersionReference({ receipt }: { receipt: Receipt }) {
  return (
    <details className="mt-5 text-xs leading-6 text-zinc-400">
      <summary className="cursor-pointer">
        Pontos verzióhivatkozás és mentési idő
      </summary>
      <dl className="mt-2 space-y-2 break-all">
        <div>
          <dt>Azonosító</dt>
          <dd>{receipt.artifact.artifact_id}</dd>
        </div>
        <div>
          <dt>Tartalmi lenyomat</dt>
          <dd>{receipt.artifact.content_hash}</dd>
        </div>
        <div>
          <dt>Tartósan elérhető</dt>
          <dd>{dateLabel(receipt.durable_available_at)}</dd>
        </div>
      </dl>
    </details>
  );
}
export function EndpointDetails({ endpoint }: { endpoint: Endpoint }) {
  const requirement = endpoint.change_requirement;
  return (
    <details className="rounded-xl border border-zinc-700 p-4">
      <summary className="cursor-pointer font-medium">
        {endpoint.endpoint_key} ·{" "}
        {metricLabels[endpoint.metric_key] ?? endpoint.metric_key} ·{" "}
        {endpoint.role === "primary"
          ? "Elsődleges"
          : endpoint.role === "supporting"
            ? "Kiegészítő"
            : "Háttéradat"}
      </summary>
      <div className="mt-4 space-y-3 whitespace-pre-wrap text-sm leading-6 text-zinc-300">
        <p>Képesség: {capabilityLabels[endpoint.capability_key]}</p>
        <p>
          Kiinduló ablak: {dateLabel(endpoint.baseline_window.starts_at)} –{" "}
          {dateLabel(endpoint.baseline_window.ends_at)}
        </p>
        <p>
          Záró ablak: {dateLabel(endpoint.followup_window.starts_at)} –{" "}
          {dateLabel(endpoint.followup_window.ends_at)}
        </p>
        {requirement && (
          <div className="space-y-2 rounded-lg bg-zinc-950 p-4">
            <p>
              Kedvező{" "}
              {requirement.basis === "favourable_percent_change"
                ? "százalékos"
                : "abszolút"}{" "}
              változás: legalább {requirement.minimum}
              {requirement.basis === "favourable_percent_change" ? "%" : ""}
              {requirement.maximum !== null
                ? `, legfeljebb ${requirement.maximum}`
                : ", felső határ nélkül"}
              .
            </p>
            <p>
              Változási mérési hiba:{" "}
              {requirement.measurement_error_estimate ?? "nincs számszerűsítve"}
              .
            </p>
            {requirement.measurement_error_source && (
              <p>Becslés forrása: {requirement.measurement_error_source}</p>
            )}
          </div>
        )}
        <p>
          Protokoll: {endpoint.procedure.protocol_key} ·{" "}
          {endpoint.procedure.protocol_version}
        </p>
        <p>Mozgásforma: {endpoint.procedure.modality_key}</p>
        <p>{endpoint.procedure.exercise_or_task}</p>
        <p>{endpoint.procedure.procedure}</p>
        <p>{endpoint.procedure.equipment_and_processing}</p>
        <p>Forrás: {endpoint.procedure.source_reference}</p>
        <ul className="list-disc pl-5">
          {endpoint.procedure.comparability_conditions.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </div>
    </details>
  );
}
function AssessmentDetails({ artifact }: { artifact: AssessmentArtifact }) {
  return (
    <div className="space-y-6">
      <p className="text-sm text-zinc-300">
        Mérési záróidőpont: {dateLabel(artifact.activity_cutoff_at)}
      </p>
      <div>
        <h3 className="mb-3 font-semibold">Összes elsődleges követelmény</h3>
        <CriterionStatus value={artifact.all_primary_criteria_status} />
      </div>
      <p className="rounded-lg bg-zinc-950 p-4 text-sm leading-6 text-zinc-300">
        A megadott mérési hibával számolt tartomány feltételes
        érzékenységvizsgálat, nem statisztikai konfidenciaintervallum. A cél
        teljesülése önmagában nem bizonyít élettani adaptációt, oksági
        kapcsolatot vagy az edzéstervező hasznosságát.
      </p>
      {artifact.capability_assessments.map((cap) => (
        <div key={cap.capability_key} className="space-y-2">
          <h3 className="font-semibold">
            {capabilityLabels[cap.capability_key]}
          </h3>
          <p className="text-sm text-zinc-400">{roleLabels[cap.goal_role]}</p>
          <CriterionStatus value={cap.criterion_status} />
          <Reasons codes={cap.reason_codes} />
        </div>
      ))}
      {artifact.endpoint_assessments.map((endpoint) => (
        <section
          key={endpoint.endpoint_key}
          className="rounded-xl border border-zinc-700 p-4"
        >
          <h3 className="font-semibold">
            {endpoint.endpoint_key} ·{" "}
            {metricLabels[endpoint.metric_key] ?? endpoint.metric_key}
          </h3>
          <p className="my-2 text-sm text-zinc-400">
            {evidenceLabels[endpoint.evidence_kind]} ·{" "}
            {endpoint.endpoint_role === "primary"
              ? "Elsődleges"
              : "Leíró / háttéradat"}
          </p>
          <CriterionStatus value={endpoint.criterion_status} />
          <dl className="mt-5 grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-zinc-400">Kiinduló érték</dt>
              <dd className="mt-1 break-all">
                {endpoint.baseline_value === null
                  ? "Hiányzik / nem egyértelmű"
                  : `${endpoint.baseline_value} ${endpoint.metric_unit}`}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-400">Záró érték</dt>
              <dd className="mt-1 break-all">
                {endpoint.followup_value === null
                  ? "Hiányzik / nem egyértelmű"
                  : `${endpoint.followup_value} ${endpoint.metric_unit}`}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-400">
                Kedvező abszolút változás
              </dt>
              <dd className="mt-1">
                <Exact
                  value={endpoint.favourable_absolute_change}
                  unit={endpoint.metric_unit}
                />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-400">
                Kedvező százalékos változás
              </dt>
              <dd className="mt-1">
                <Exact value={endpoint.favourable_percent_change} unit="%" />
              </dd>
            </div>
          </dl>
          {endpoint.declared_error_sensitivity_low &&
            endpoint.declared_error_sensitivity_high && (
              <div className="mt-4 rounded-lg bg-zinc-950 p-4 text-sm">
                <p className="mb-2 text-zinc-400">
                  Változási tartomány a megadott mérési hiba mellett
                </p>
                <Exact
                  value={endpoint.declared_error_sensitivity_low}
                  unit={
                    endpoint.comparison_basis === "favourable_percent_change"
                      ? "%"
                      : endpoint.metric_unit
                  }
                />
                <span className="mx-2">–</span>
                <Exact
                  value={endpoint.declared_error_sensitivity_high}
                  unit={
                    endpoint.comparison_basis === "favourable_percent_change"
                      ? "%"
                      : endpoint.metric_unit
                  }
                />
              </div>
            )}
          <Reasons codes={endpoint.reason_codes} />
          <p className="mt-3 text-sm leading-6 text-zinc-400">
            {metricLimit(endpoint.metric_key, endpoint.interpretation_limit)}
          </p>
          <details className="mt-4 text-sm">
            <summary className="cursor-pointer text-teal-200">
              Vizsgált forrásadatok ({endpoint.candidates.length})
            </summary>
            <ul className="mt-3 space-y-3">
              {endpoint.candidates.map((candidate) => (
                <li
                  key={candidate.source_id + candidate.window}
                  className="rounded-lg bg-zinc-950 p-3"
                >
                  <p className="break-all text-xs text-zinc-400">
                    {candidate.source_id}
                  </p>
                  <p>
                    {candidate.window === "baseline"
                      ? "Kiinduló"
                      : candidate.window === "followup"
                        ? "Záró"
                        : "Ablakon kívüli"}{" "}
                    ·{" "}
                    {candidate.eligibility === "eligible"
                      ? "Megfelelő"
                      : candidate.eligibility === "ineligible"
                        ? "Nem megfelelő"
                        : "Tisztázatlan"}
                  </p>
                  <Reasons codes={candidate.reason_codes} />
                </li>
              ))}
            </ul>
          </details>
        </section>
      ))}
      <Unassigned keys={artifact.unassigned_capability_keys} />
    </div>
  );
}
function Unassigned({ keys }: { keys: string[] }) {
  return keys.length ? (
    <p className="text-sm leading-6 text-zinc-400">
      Nincs hozzárendelve:{" "}
      {keys.map((key) => capabilityLabels[key] ?? key).join(", ")}. A
      hozzárendelés hiánya nem engedély visszaesésre.
    </p>
  ) : null;
}
export default function ArtifactDetails({
  receipt,
  resource,
}: {
  receipt: Receipt;
  resource: Resource;
}) {
  return (
    <Card title="Kiválasztott, mentett verzió">
      {resource === "macrocycle-plans" &&
        (() => {
          const artifact = receipt.artifact as MacroArtifact;
          return (
            <div className="space-y-5">
              <p className="text-sm text-zinc-300">
                {artifact.proposal.revision}. verzió ·{" "}
                {artifact.proposal.rationale}
              </p>
              {artifact.proposal.goals.map((goal) => (
                <div key={goal.capability_key}>
                  <h3 className="font-semibold">
                    {capabilityLabels[goal.capability_key]} ·{" "}
                    {roleLabels[goal.role]}
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-zinc-300">
                    {goal.rationale}
                  </p>
                  <ul className="mt-3 space-y-2 text-sm">
                    {artifact.proposal.mesocycle_directives
                      .filter((d) => d.capability_key === goal.capability_key)
                      .map((d) => (
                        <li
                          key={d.mesocycle_period_id}
                          className="rounded-lg bg-zinc-950 p-3"
                        >
                          {artifact.sources.mesocycles.find(
                            (p) => p.period_id === d.mesocycle_period_id,
                          )?.title ?? d.mesocycle_period_id}
                          : <strong>{roleLabels[d.role]}</strong>
                          <p className="mt-1 text-zinc-400">{d.rationale}</p>
                        </li>
                      ))}
                  </ul>
                </div>
              ))}
              <Unassigned keys={artifact.unassigned_capability_keys} />
            </div>
          );
        })()}
      {resource === "mesocycle-protocols" &&
        (() => {
          const artifact = receipt.artifact as ProtocolArtifact;
          return (
            <div className="space-y-4">
              <p className="text-sm text-zinc-300">
                {artifact.proposal.revision}. verzió ·{" "}
                {artifact.proposal.rationale}
              </p>
              {artifact.proposal.endpoints.map((endpoint) => (
                <EndpointDetails
                  key={endpoint.endpoint_key}
                  endpoint={endpoint}
                />
              ))}
              <Unassigned keys={artifact.unassigned_capability_keys} />
            </div>
          );
        })()}
      {resource === "measurements" &&
        (() => {
          const artifact = receipt.artifact as MeasurementArtifact,
            observation = artifact.proposal.observation;
          return (
            <div className="space-y-4 text-sm leading-6 text-zinc-300">
              <p className="text-lg text-zinc-100">
                {artifact.proposal.endpoint_key}: {artifact.proposal.value}{" "}
                {artifact.metric_unit}
              </p>
              <p>
                {metricLabels[artifact.metric_key] ?? artifact.metric_key} ·{" "}
                {dateLabel(observation.started_at)} –{" "}
                {dateLabel(observation.ended_at)}
              </p>
              <p>
                Végrehajtás:{" "}
                {observation.completion === "complete"
                  ? "teljes"
                  : observation.completion === "incomplete"
                    ? "nem teljes"
                    : "ismeretlen"}
                . Eredmény:{" "}
                {observation.result_level === "complete_protocol_result"
                  ? "teljes protokoll"
                  : observation.result_level === "within_protocol_trial"
                    ? "részpróba"
                    : "ismeretlen"}
                .
              </p>
              {observation.body_mass_kg !== null && (
                <p>Testtömeg: {observation.body_mass_kg} kg</p>
              )}
              <ul className="space-y-3">
                {observation.conditions.map((c, i) => (
                  <li key={i} className="rounded-lg bg-zinc-950 p-4">
                    <strong>
                      {c.condition}:{" "}
                      {c.status === "met"
                        ? "teljesült"
                        : c.status === "not_met"
                          ? "nem teljesült"
                          : "ismeretlen"}
                    </strong>
                    <p>{c.observation}</p>
                    <p className="text-zinc-400">
                      Forrás: {c.evidence_reference}
                    </p>
                  </li>
                ))}
              </ul>
              <p>
                Végrehajtási forrás: {observation.execution_evidence_reference}
              </p>
              <p className="text-zinc-400">
                Ez az eredeti, befagyasztott rögzítés. Az alapul szolgáló mérési
                adatsorok későbbi módosulása vagy törlése nem változtatja meg;
                az értékelés külön adatfelvételt készít.
              </p>
            </div>
          );
        })()}
      {resource === "assessments" && (
        <AssessmentDetails artifact={receipt.artifact as AssessmentArtifact} />
      )}
      <VersionReference receipt={receipt} />
    </Card>
  );
}
