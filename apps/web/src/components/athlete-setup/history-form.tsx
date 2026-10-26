"use client";
import { useState } from "react";
import {
  Area,
  Field,
  Select,
  secondaryClass,
  buttonClass,
} from "@/components/planning-goals/fields";
import { addDays } from "@/lib/planning-cycles/contracts";
import {
  aggregations,
  domains,
  methods,
  metrics,
  ref,
} from "@/lib/athlete-setup/contracts";
import type {
  Candidate,
  Context,
  Domain,
  Manual,
  Profile,
} from "@/lib/athlete-setup/contracts";
function description(c: Candidate) {
  return `${c.start_date} · ${metrics[c.metric]?.label ?? c.metric}: ${c.value} ${c.unit} · ${c.provider} · ${methods[c.method] ?? c.method} · ${aggregations[c.aggregation] ?? c.aggregation}`;
}
export default function HistoryForm({
  value,
  onChange,
  context,
  candidates,
  frozen,
  onSearch,
  onImport,
  busy,
  onError,
}: {
  value: Profile;
  onChange: (v: Profile) => void;
  context: Context;
  candidates: Candidate[];
  frozen: Candidate[];
  onSearch: (start: string, end: string) => void;
  onImport: (start: string, end: string, domain: Domain) => void;
  busy: boolean;
  onError: (s: string) => void;
}) {
  const [first, setFirst] = useState(
      value.source_window?.start_date ?? addDays(context.local_today, -13),
    ),
    [last, setLast] = useState(
      value.source_window?.end_date ?? context.local_today,
    ),
    [domain, setDomain] = useState<Domain>("sessions"),
    [page, setPage] = useState(0);
  const all = new Map(
    [...frozen, ...candidates].map((c) => [c.artifact_id, c]),
  );
  function select(c: Candidate, checked: boolean) {
    if (
      !checked &&
      value.manual_observations.some(
        (o) => o.supersedes_candidate_id === c.artifact_id,
      )
    ) {
      onError(
        "Ehhez az eredeti adathoz kézi korrekció tartozik. Először a korrekció kapcsolatát rendezd.",
      );
      return;
    }
    const remove = new Set(
      Array.from(all.values())
        .filter((o) => o.logical_key === c.logical_key)
        .map((o) => o.artifact_id),
    );
    onChange({
      ...value,
      source_selections: checked
        ? [
            ...value.source_selections.filter(
              (r) => !remove.has(r.artifact_id),
            ),
            ref(c),
          ]
        : value.source_selections.filter(
            (r) => r.artifact_id !== c.artifact_id,
          ),
    });
  }
  function edit(i: number, p: Partial<Manual>) {
    onChange({
      ...value,
      manual_observations: value.manual_observations.map((o, k) =>
        k === i ? { ...o, ...p } : o,
      ),
    });
  }
  return (
    <div className="space-y-6">
      <p className="text-sm leading-6 text-zinc-300">
        A már szinkronizált edzések és mérések innen átvehetők. A nyers órás
        adatok, a profilba kiválasztott megfigyelések és a kézi kiegészítések
        külön megmaradnak. A hiányzó nap nem nulla, az órás becslés nem célzott
        laboratóriumi mérés.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Vizsgált történelmi időszak kezdete"
          type="date"
          max={context.local_today}
          value={first}
          onChange={(e) => setFirst(e.target.value)}
        />
        <Field
          label="Vizsgált történelmi időszak vége"
          type="date"
          max={context.local_today}
          value={last}
          onChange={(e) => setLast(e.target.value)}
        />
      </div>
      <button
        className={buttonClass}
        type="button"
        disabled={busy}
        onClick={() => {
          setPage(0);
          onSearch(first, last);
        }}
      >
        Tárolt előzmények betöltése
      </button>
      <details className="rounded-xl border border-zinc-700 p-4">
        <summary className="cursor-pointer font-semibold">
          Új adatok lekérése a Polar-kapcsolaton keresztül
        </summary>
        <div className="mt-4 space-y-4">
          <p className="text-sm">
            {context.polar.connected
              ? "Polar-kapcsolat elérhető. Csak az engedélyezett adatkörök kérhetők le."
              : "Még nincs Polar-kapcsolat. A kézi bevitel és a már tárolt előzmények használhatók."}{" "}
            A lekérés naponta történik, legfeljebb 31 napos adagokban. A
            profilba ezután külön választhatod ki a megfigyeléseket.
          </p>
          <Select
            label="Lekérendő órás adatkör"
            value={domain}
            onChange={(e) => setDomain(e.target.value as Domain)}
          >
            {Object.entries(domains).map(([k, v]) => (
              <option
                key={k}
                value={k}
                disabled={!context.polar.domains[k as Domain]}
              >
                {v}
                {!context.polar.domains[k as Domain]
                  ? " · nincs hozzáférés"
                  : ""}
              </option>
            ))}
          </Select>
          <button
            type="button"
            className={secondaryClass}
            disabled={busy || !context.polar.domains[domain]}
            onClick={() => onImport(first, last, domain)}
          >
            Kijelölt időszak lekérése
          </button>
          <p className="text-xs text-zinc-400">
            A szolgáltató, az eszköz és a korábbi rögzítés határozza meg, mely
            adatok érhetők el. Egy sikertelen lekérés után ugyanaz a napi kérés
            folytatható.
          </p>
        </div>
      </details>
      <div className="space-y-4">
        <h3 className="font-semibold">
          Átvételi javaslatok ({candidates.length})
        </h3>
        {!candidates.length && (
          <p className="text-sm text-zinc-400">
            Ebben a nézetben még nincs betöltött, felismert megfigyelés. Ettől
            még a forrásban lehet más adat.
          </p>
        )}
        {candidates.slice(page * 20, page * 20 + 20).map((c) => (
          <label
            className="block rounded-lg border border-zinc-700 p-3 text-sm leading-6"
            key={c.artifact_id}
          >
            <span className="flex items-start gap-3">
              <input
                className="mt-1 h-4 w-4"
                type="checkbox"
                checked={value.source_selections.some(
                  (r) => r.artifact_id === c.artifact_id,
                )}
                onChange={(e) => select(c, e.target.checked)}
              />
              <span>
                {description(c)}
                {c.sport && ` · ${c.sport}`}
                {c.protocol && <span className="block">{c.protocol}</span>}
                <span className="block text-xs text-zinc-400">
                  Átvétel: {c.received_at} · Lefedettség:{" "}
                  {String(c.coverage.completeness ?? "unknown")}
                  {typeof c.coverage.sample_count === "number" &&
                    ` · ${c.coverage.sample_count} minta`}
                  {typeof c.coverage.observed_minutes === "string" &&
                    ` · ${c.coverage.observed_minutes} percnyi lépésminta`}
                </span>
                {c.metric === "background_hr_mean_bpm" && (
                  <span className="block text-xs text-zinc-400">
                    A háttérpulzus mintáinak átlaga, nem nyugalmi pulzus és nem
                    teljes napos folytonos mérés.
                  </span>
                )}
                {c.metric === "daily_steps" && (
                  <span className="block text-xs text-zinc-400">
                    Az eszköz rögzített mintáinak összege; több eszköz értékeit
                    nem adjuk össze.
                  </span>
                )}
              </span>
            </span>
          </label>
        ))}
        {candidates.length > 20 && (
          <div className="flex items-center gap-3">
            <button
              type="button"
              className={secondaryClass}
              disabled={!page}
              onClick={() => setPage(page - 1)}
            >
              Előző találatok
            </button>
            <span className="text-sm">
              {page + 1} / {Math.ceil(candidates.length / 20)}
            </span>
            <button
              type="button"
              className={secondaryClass}
              disabled={(page + 1) * 20 >= candidates.length}
              onClick={() => setPage(page + 1)}
            >
              Következő találatok
            </button>
          </div>
        )}
        <p className="text-sm font-semibold">
          A profilba kijelölve: {value.source_selections.length} megfigyelés. Az
          átvételt a felmérés mentése véglegesíti.
        </p>
        {!!value.source_selections.length && (
          <details>
            <summary className="cursor-pointer text-sm">
              Kijelölt adatok áttekintése
            </summary>
            <ul className="mt-3 space-y-3 text-sm">
              {value.source_selections.map((r) => {
                const c = all.get(r.artifact_id);
                return (
                  <li key={r.artifact_id}>
                    {c ? description(c) : "Korábban kijelölt forrás"}{" "}
                    <button
                      type="button"
                      className="ml-3 underline"
                      onClick={() => c && select(c, false)}
                    >
                      Kijelölés eltávolítása
                    </button>
                  </li>
                );
              })}
            </ul>
          </details>
        )}
      </div>
      <fieldset className="space-y-4">
        <legend className="mb-3 font-semibold">
          Kézi mérések, közelmúltbeli terhelés és kiegészítések
        </legend>
        <p className="text-sm text-zinc-400">
          Edzésmennyiségnél az időszak összes edzését vagy percét add meg.
          Alvásidő: másodperc; például 8 óra = 28 800 másodperc. Erőfelmérésnél
          a gyakorlatot, ismétlést és körülményeket is jegyezd fel.
        </p>
        {value.manual_observations.map((o, i) => (
          <div
            className="space-y-4 rounded-xl border border-zinc-700 p-4"
            key={o.observation_id}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Select
                label={`Kézi adat típusa · ${i + 1}`}
                value={o.metric}
                onChange={(e) => edit(i, { metric: e.target.value })}
              >
                {Object.entries(metrics).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v.label} ({v.unit})
                  </option>
                ))}
              </Select>
              <Field
                label={`Érték (${metrics[o.metric]?.unit ?? ""}) · ${i + 1}`}
                inputMode="decimal"
                required
                maxLength={22}
                value={o.value}
                onChange={(e) => edit(i, { value: e.target.value })}
              />
              <Field
                label={`Mérés / időszak első napja · ${i + 1}`}
                type="date"
                required
                max={context.local_today}
                value={o.start_date}
                onChange={(e) => edit(i, { start_date: e.target.value })}
              />
              <Field
                label={`Mérés / időszak utolsó napja · ${i + 1}`}
                type="date"
                required
                max={context.local_today}
                value={o.end_date}
                onChange={(e) => edit(i, { end_date: e.target.value })}
              />
              <Select
                label={`Mérés módszere · ${i + 1}`}
                value={o.method}
                onChange={(e) =>
                  edit(i, { method: e.target.value as Manual["method"] })
                }
              >
                {Object.entries(methods).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </Select>
              <Select
                label={`Az érték jelentése · ${i + 1}`}
                value={o.aggregation}
                onChange={(e) =>
                  edit(i, {
                    aggregation: e.target.value as Manual["aggregation"],
                  })
                }
              >
                {Object.entries(aggregations).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </Select>
              <Field
                label={`Sportág (opcionális) · ${i + 1}`}
                maxLength={200}
                value={o.sport}
                onChange={(e) => edit(i, { sport: e.target.value })}
              />
              <Field
                label={`Protokoll / gyakorlat / eszköz (ha ismert) · ${i + 1}`}
                maxLength={200}
                value={o.protocol}
                onChange={(e) => edit(i, { protocol: e.target.value })}
              />
              <Select
                label={`Melyik átvett adat kézi korrekciója? · ${i + 1}`}
                value={o.supersedes_candidate_id ?? ""}
                onChange={(e) =>
                  edit(i, {
                    supersedes_candidate_id: e.target.value || null,
                    ...(all.get(e.target.value)
                      ? { aggregation: all.get(e.target.value)!.aggregation }
                      : {}),
                  })
                }
              >
                <option value="">Önálló kézi adat</option>
                {value.source_selections.map((r) => {
                  const c = all.get(r.artifact_id);
                  return c &&
                    c.metric === o.metric &&
                    c.start_date === o.start_date &&
                    c.end_date === o.end_date ? (
                    <option value={r.artifact_id} key={r.artifact_id}>
                      {description(c)}
                    </option>
                  ) : null;
                })}
              </Select>
            </div>
            <Area
              label={`Körülmények, ismétlésszám, bizonytalanság (opcionális) · ${i + 1}`}
              maxLength={2000}
              value={o.conditions}
              onChange={(e) => edit(i, { conditions: e.target.value })}
            />
            <button
              type="button"
              className={secondaryClass}
              onClick={() =>
                onChange({
                  ...value,
                  manual_observations: value.manual_observations.filter(
                    (_, k) => k !== i,
                  ),
                })
              }
            >
              Kézi bejegyzés eltávolítása ebből a változatból
            </button>
          </div>
        ))}
        <button
          type="button"
          className={secondaryClass}
          disabled={value.manual_observations.length >= 200}
          onClick={() =>
            onChange({
              ...value,
              manual_observations: [
                ...value.manual_observations,
                {
                  observation_id: crypto.randomUUID(),
                  metric: "training_minutes",
                  value: "",
                  start_date: context.local_today,
                  end_date: context.local_today,
                  method: "self_report",
                  aggregation: "total",
                  sport: "",
                  protocol: "",
                  conditions: "",
                  supersedes_candidate_id: null,
                },
              ],
            })
          }
        >
          Kézi adat hozzáadása
        </button>
      </fieldset>
    </div>
  );
}
