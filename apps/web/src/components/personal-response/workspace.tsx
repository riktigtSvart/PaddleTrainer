"use client";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  checkedRange,
  contextId,
  loadPersonalInputs,
} from "@/lib/personal-response/contracts";
import type { PersonalInputs, Range } from "@/lib/personal-response/contracts";
import {
  census,
  contexts,
  contextLabel,
  formatInstant,
  isolationLabels,
  limitationLabels,
  knownScore,
  selectedDataset,
  selectedObservations,
} from "@/lib/personal-response/presentation";
import { ScoreChart } from "./charts";
export function PersonalResponseData({ data }: { data: PersonalInputs }) {
  const [selected, setSelected] = useState(""),
    [page, setPage] = useState(0);
  const keys = contexts(data),
    key = keys.some((k) => contextId(k) === selected)
      ? selected
      : keys[0]
        ? contextId(keys[0])
        : "";
  const rows = selectedObservations(data, key),
    dataset = selectedDataset(data, key),
    counts = census(data);
  const pages = Math.max(1, Math.ceil(rows.length / 25)),
    index = Math.min(page, pages - 1),
    slice = rows.slice(index * 25, index * 25 + 25);
  const suff = data.assembly.data_sufficiency;
  return (
    <>
      <section
        className="pt-pr-summary"
        aria-label="A bekötött visszajelzések összesítése"
      >
        {[
          ["Edzések", counts.sessions],
          ["Visszajelzési alkalmak", counts.occasions],
          ["Számszerű válaszok", counts.known],
          ["Meg nem adott válaszok", counts.missing],
        ].map(([label, value]) => (
          <article key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </section>
      <p className="pt-notice">
        Egy visszajelzés legfeljebb öt választ tartalmaz; az öt válasz nem öt
        független edzés. Csak a kiválasztott, bekötött változatok szerepelnek.
      </p>
      {!keys.length ? (
        <section className="pt-pr-panel">
          <h2>Még nincs megjeleníthető személyes visszajelzés</h2>
          <p>
            Nyiss meg egy teljesített edzést a napirendben, adj saját
            visszajelzést, majd ellenőrizd a Tanulási kapcsolat részt. A még
            bekötésre váró válaszok itt nem jelennek meg.
          </p>
          <Link className="pt-button" href="/">
            Edzés keresése a napirendben
          </Link>
        </section>
      ) : (
        <>
          <section className="pt-pr-panel">
            <label className="pt-pr-select">
              Mit szeretnél megnézni?
              <select
                value={key}
                onChange={(e) => {
                  setSelected(e.target.value);
                  setPage(0);
                }}
              >
                {keys.map((k) => (
                  <option key={contextId(k)} value={contextId(k)}>
                    {contextLabel(k)}
                  </option>
                ))}
              </select>
            </label>
            <p className="pt-notice">
              Az eltérő sportágak és az edzés utáni, illetve másnap reggeli
              válaszok külön maradnak. Mind az öt mutató saját, 0–10 pontos
              értékelés.
            </p>
            <div className="pt-pr-charts">
              <ScoreChart observations={rows} zone={data.timezone_name} />
              <ScoreChart
                observations={rows}
                dataset={dataset}
                zone={data.timezone_name}
                scatter
              />
            </div>
            {dataset && (
              <p className="pt-notice">
                Edzésidővel párosítható: {dataset.eligible_numeric_pair_count}.
                Hiányos párok: {dataset.ineligible_pair_count}. Egyetlen pontból
                nem állapítható meg személyes összefüggés.
              </p>
            )}
          </section>
          <section className="pt-pr-panel">
            <h2>A pontok mögötti adatok</h2>
            <div className="pt-pr-table">
              <table>
                <caption>
                  {rows.length} megfigyelés · {index + 1}/{pages}. oldal ·{" "}
                  {data.timezone_name}
                </caption>
                <thead>
                  <tr>
                    <th>Megfigyelés</th>
                    <th>Válasz</th>
                    <th>Edzésidő</th>
                    <th>Adatként elérhető</th>
                    <th>Más edzés hatása</th>
                    <th>Forrás</th>
                  </tr>
                </thead>
                <tbody>
                  {slice.map((o) => {
                    const pair = dataset?.pairs.find(
                        (p) => p.response_observation_id === o.observation_id,
                      ),
                      duration =
                        pair?.eligibility === "eligible_numeric_pair"
                          ? pair.predictor_numeric_value
                          : null;
                    return (
                      <tr key={o.observation_id}>
                        <td>
                          {formatInstant(
                            o.response_observed_at,
                            data.timezone_name,
                          )}
                        </td>
                        <td>
                          {knownScore(o) ? `${o.value} / 10` : "Nincs megadva"}
                        </td>
                        <td>
                          {duration === null || duration === undefined
                            ? "Nincs ismert pár"
                            : `${(duration / 60).toLocaleString("hu-HU", { maximumFractionDigits: 1 })} perc`}
                        </td>
                        <td>
                          {formatInstant(
                            o.response_available_at,
                            data.timezone_name,
                          )}
                        </td>
                        <td>
                          {isolationLabels[o.isolation_status] ??
                            o.isolation_status}
                        </td>
                        <td>
                          <Link href={`/sessions/${o.workout_session_id}`}>
                            Edzés megnyitása
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="pt-pr-actions">
              <button
                type="button"
                className="pt-button"
                disabled={index === 0}
                onClick={() => setPage(index - 1)}
              >
                Előző oldal
              </button>
              <span aria-live="polite">
                {index + 1} / {pages}
              </span>
              <button
                type="button"
                className="pt-button"
                disabled={index >= pages - 1}
                onClick={() => setPage(index + 1)}
              >
                Következő oldal
              </button>
            </div>
          </section>
        </>
      )}
      <details className="pt-pr-panel">
        <summary>Mit tudunk az adatok teljességéről?</summary>
        <p>
          Edzéselőzmények: {coverage(suff.stimulus_coverage)}. Visszajelzések:{" "}
          {coverage(suff.response_coverage)}.
        </p>
        <p>
          {suff.status === "descriptive_supported"
            ? "Az ismert adatok leíró áttekintést támogatnak. Ez nem jelenti az előzmények teljességét vagy egy személyes hatásmodell igazolását."
            : "A személyes leíró referencia még hiányos vagy nem ismert."}
        </p>
        <ul>
          {suff.limitation_codes.map((code) => (
            <li key={code}>{limitationLabels[code] ?? code}</li>
          ))}
        </ul>
        <p className="pt-notice">
          Az önbevallás nem közvetlen élettani mérés. A nézet nem állapít meg
          VO₂max-változást, edzéshatást vagy terhelhetőséget, és nem módosít
          edzéstervet.
        </p>
      </details>
    </>
  );
}
const coverage = (x: string) =>
  ({ unknown: "nem ismert", partial: "részleges", complete: "teljes" })[x] ?? x;
export default function PersonalResponseWorkspace() {
  const [request, setRequest] = useState<{
    range: Range | null;
    nonce: number;
  }>({ range: null, nonce: 0 });
  const [data, setData] = useState<PersonalInputs | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(true);
  const [start, setStart] = useState(""),
    [end, setEnd] = useState("");
  useEffect(() => {
    const updated = () => {
      setData(null);
      setError("");
      setBusy(true);
      setRequest((x) => ({ ...x, nonce: x.nonce + 1 }));
    };
    window.addEventListener(LOCAL_REFRESH_EVENT, updated);
    return () => window.removeEventListener(LOCAL_REFRESH_EVENT, updated);
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    loadPersonalInputs(request.range, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) {
          setData(value);
          setBusy(false);
          setError("");
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setBusy(false);
          setError(
            e instanceof Error ? e.message : "Az adatok nem tölthetők be.",
          );
        }
      });
    return () => abort.abort();
  }, [request]);
  function reload(range: Range | null) {
    setData(null);
    setError("");
    setBusy(true);
    setRequest((x) => ({ range, nonce: x.nonce + 1 }));
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    try {
      reload(checkedRange(start, end));
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "Érvénytelen időszak.");
    }
  }
  return (
    <div className="pt-pr-workspace">
      <section className="pt-pr-panel">
        <form className="pt-pr-filters" onSubmit={submit}>
          <label>
            Kezdőnap
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              required
            />
          </label>
          <label>
            Zárónap
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              required
            />
          </label>
          <button type="submit" className="pt-button" disabled={busy}>
            Időszak megnyitása
          </button>
          <button
            type="button"
            className="pt-button"
            disabled={busy}
            onClick={() => {
              setStart("");
              setEnd("");
              reload(null);
            }}
          >
            Utolsó 90 nap
          </button>
          <button
            type="button"
            className="pt-button"
            disabled={busy}
            onClick={() => reload(request.range)}
          >
            Adatok újraolvasása
          </button>
        </form>
        <p className="pt-notice">
          A megadott napok a sportolói profil időzónájában értendők. Az
          újraolvasás a már bekötött adatokat olvassa; nem indít
          Polar-szinkronizálást.
        </p>
      </section>
      <div className="pt-pr-status" aria-live="polite">
        {busy ? (
          <p role="status">Személyes tapasztalatok betöltése…</p>
        ) : error ? (
          <p role="alert">{error}</p>
        ) : data ? (
          <p>
            {formatInstant(data.window_start_at, data.timezone_name)} –{" "}
            {formatInstant(data.response_window_end_at, data.timezone_name)} ·{" "}
            {data.timezone_name}
            <br />
            <small>
              Ismert adatok:{" "}
              {formatInstant(data.information_cutoff_at, data.timezone_name)}{" "}
              állapot szerint.
            </small>
          </p>
        ) : null}
      </div>
      {data && (
        <PersonalResponseData
          key={`${data.athlete_id}:${data.window_start_at}:${data.as_of}:${request.nonce}`}
          data={data}
        />
      )}
    </div>
  );
}
