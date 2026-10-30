"use client";
import { createPortal } from "react-dom";
import { useEffect, useMemo, useState, useId } from "react";
import { metricInfo } from "@/lib/session-analysis/contracts";
import type {
  Analysis,
  MetricKey,
  Series,
} from "@/lib/session-analysis/contracts";
import {
  atCursor,
  clock,
  displayValue,
  extent,
  paceValue,
  withPace,
} from "@/lib/session-analysis/chart-data";
import {
  axisNumber,
  targetOnChart,
  timeTicks,
  valueAxis,
  zonesOnChart,
} from "@/lib/session-analysis/presentation";
import type { SpeedUnit } from "@/lib/session-analysis/presentation";
import {
  defaultChoices,
  distanceAt,
  distanceSource,
  explorerKey,
  plotRuns,
  readChoices,
  selectMetric,
  timeAtDistance,
} from "@/lib/session-analysis/explorer";
import type { Choices } from "@/lib/session-analysis/explorer";
import {
  phaseResults,
  phaseTarget,
} from "@/lib/session-analysis/phase-statistics";
import { pickedCandidateTime } from "@/lib/session-analysis/phase-candidates";
import type { PhaseCandidate } from "@/lib/session-analysis/phase-candidates";
import { PlanBoundaryControls, useBoundaryView } from "./plan-boundaries";
import { PhaseAssessment } from "./phase-assessment";
import { SpeedUnitControl } from "./speed-unit-control";
import { PhaseSummary } from "./phase-summary";
import { RouteMap } from "./route-map";

const COLORS = ["#34cddd", "#f27eaa"],
  ZONE_COLORS = ["#8194aa", "#43b68b", "#5aabdf", "#edb65f", "#ee7b8c"];
const fallback = (rows: Series[], wanted: MetricKey) =>
  selectMetric(rows, wanted)?.metric_key ??
  rows.find((s) => s.interval_ms !== null && s.valid_sample_count > 0)
    ?.metric_key ??
  "none";
export function SessionExplorer({
  data,
  exercise,
  speedUnit,
  onSpeedUnitChange,
  mapTarget,
  summaryTarget,
  positionTarget,
  creditTarget,
}: {
  data: Analysis;
  mapTarget?: HTMLElement | null;
  summaryTarget?: HTMLElement | null;
  positionTarget?: HTMLElement | null;
  creditTarget?: HTMLElement | null;
  exercise: number;
  speedUnit: SpeedUnit;
  onSpeedUnitChange: (unit: SpeedUnit) => void;
}) {
  const source = useMemo(
    () => data.samples.series.filter((s) => s.exercise_index === exercise),
    [data.samples.series, exercise],
  );
  const series = useMemo(() => withPace(source), [source]),
    end = extent(series),
    part = data.samples.exercises.find((e) => e.index === exercise);
  const key = data.plan_timeline
    ? `paddletrainer:plan-reference:v2:${data.athlete_id}:${data.session.id}:${exercise}:${data.plan_timeline.content_hash}:${data.samples.content_hash ?? "legacy"}`
    : undefined;
  const view = useBoundaryView(
    data.plan_timeline,
    key,
    data.samples.exercises.length === 1,
    source,
    part?.clock_issues ?? [],
  );
  const [choices, setChoices] = useState<Choices>(() => ({
    ...defaultChoices,
    left: fallback(series, "speed_kmh"),
    right: selectMetric(series, "heart_rate_bpm") ? "heart_rate_bpm" : "none",
  }));
  const [cursor, setCursor] = useState(0),
    [from, setFrom] = useState(0),
    [to, setTo] = useState(end),
    [selected, setSelected] = useState<{ from: number; to: number } | null>(
      null,
    );
  const [candidate, setCandidate] = useState<PhaseCandidate | null>(null),
    [picked, setPicked] = useState<number | null>(null),
    [zoneSide, setZoneSide] = useState(1);
  const [notice, setNotice] = useState("");
  const [rangeError, setRangeError] = useState("");
  const clip = useId().replaceAll(":", "");
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        const saved = localStorage.getItem(explorerKey(data.athlete_id));
        if (saved) setChoices(readChoices(saved));
      } catch {
        setNotice(
          "A grafikon beállításai most csak ebben a nézetben maradnak meg.",
        );
      }
    });
    return () => {
      active = false;
    };
  }, [data.athlete_id]);
  function choose(patch: Partial<Choices>) {
    const next = { ...choices, ...patch };
    if (next.left !== "none" && next.left === next.right) next.right = "none";
    setChoices(next);
    try {
      localStorage.setItem(explorerKey(data.athlete_id), JSON.stringify(next));
    } catch {
      setNotice(
        "A grafikon beállításai most csak ebben a nézetben maradnak meg.",
      );
    }
  }
  const distance = useMemo(() => distanceSource(source), [source]),
    syncAllowed = !part?.clock_issues?.length;
  const mode =
    choices.x === "distance" && distance && syncAllowed ? "distance" : "time";
  const rows = useMemo(
    () => [
      selectMetric(series, choices.left),
      choices.right === choices.left
        ? null
        : selectMetric(series, choices.right),
    ],
    [series, choices.left, choices.right],
  );
  const phaseZones = useMemo(
    () => ({
      heart_rate: part?.heart_rate_zones ?? null,
      speed: part?.speed_zones ?? null,
      power: part?.power_zones ?? null,
    }),
    [part],
  );
  const phases = view.part?.phases ?? [];
  const summaries = useMemo(
    () =>
      syncAllowed
        ? phaseResults(
            view.part,
            view.alignment.gaps,
            series.filter((s) => s.metric_key !== "pace_sec_km"),
            data.plan,
            phaseZones,
          )
        : [],
    [
      view.part,
      view.alignment.gaps,
      series,
      data.plan,
      phaseZones,
      syncAllowed,
    ],
  );
  const family = (metric: MetricKey) =>
    metric === "heart_rate_bpm"
      ? "heart_rate"
      : metric === "power_w"
        ? "power"
        : ["speed_kmh", "pace_sec_km"].includes(metric)
          ? "speed"
          : null;
  const bands = rows.map((s) =>
    s
      ? phases.flatMap((p) => {
          if (p.from_ms === null || p.to_ms === null) return [];
          const target = targetOnChart(
            phaseTarget(p, data.plan, phaseZones),
            s.metric_key,
            speedUnit,
          );
          return target ? [{ phase: p, target }] : [];
        })
      : [],
  );
  const zoneDefinition = rows[zoneSide]
    ? zonesOnChart(
        phaseZones[family(rows[zoneSide]!.metric_key) ?? "heart_rate"],
        rows[zoneSide]!.metric_key,
        speedUnit,
      )
    : null;
  const runs = useMemo(
    () => [
      plotRuns(rows[0], from, to, mode, distance, speedUnit),
      plotRuns(rows[1], from, to, mode, distance, speedUnit),
    ],
    [rows, from, to, mode, distance, speedUnit],
  );
  const axes = runs.map((runs, index) => {
    let low = Infinity,
      high = -Infinity;
    for (const run of runs)
      for (const p of run) {
        low = Math.min(low, p.y);
        high = Math.max(high, p.y);
      }
    if (choices.targets && index === zoneSide)
      for (const b of bands[index]) {
        low = Math.min(low, b.target.low!);
        high = Math.max(high, b.target.high!);
      }
    if (choices.zones && index === zoneSide && zoneDefinition)
      for (const z of zoneDefinition.zones) {
        low = Math.min(low, z.low);
        high = Math.max(high, z.high);
      }
    return valueAxis(low, high, rows[index]?.metric_key === "pace_sec_km");
  });
  const [xmin, xmax] = useMemo(() => {
    if (mode === "time") return [from, to];
    let low = Infinity,
      high = -Infinity;
    for (const collection of runs)
      for (const run of collection)
        for (const p of run) {
          low = Math.min(low, p.x);
          high = Math.max(high, p.x);
        }
    return Number.isFinite(low) && Number.isFinite(high) ? [low, high] : [0, 1];
  }, [mode, from, to, runs]);
  const xpos = (value: number) =>
    70 + ((value - xmin) / Math.max(1, xmax - xmin)) * 860;
  const xtime = (ms: number) => {
    const value = mode === "time" ? ms : distanceAt(distance, ms);
    return value === null ? null : xpos(value);
  };
  const ypos = (value: number, index: number) => {
    const a = axes[index],
      scale = Math.max(1, Math.abs(a.low), Math.abs(a.high)),
      ratio =
        (value / scale - a.low / scale) / (a.high / scale - a.low / scale || 1);
    return rows[index]?.metric_key === "pace_sec_km"
      ? 22 + ratio * 180
      : 202 - ratio * 180;
  };
  const yformat = (value: number, index: number) =>
    rows[index]?.metric_key === "pace_sec_km"
      ? paceValue(value)
      : axisNumber(value);
  const points = rows.map((s) => (s ? atCursor(s, cursor) : null)),
    route =
      data.samples.routes?.find((r) => r.exercise_index === exercise) ?? null;
  function pick(ms: number) {
    setCursor(Math.max(0, Math.min(end, ms)));
  }
  function point(event: React.PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width) return null;
    const value =
      xmin +
      Math.max(
        0,
        Math.min(
          1,
          (((event.clientX - rect.left) / rect.width) * 1000 - 70) / 860,
        ),
      ) *
        (xmax - xmin);
    return mode === "time" ? value : timeAtDistance(distance, value);
  }
  function resetSelection() {
    setSelected(null);
    setCandidate(null);
    setPicked(null);
    setFrom(0);
    setTo(end);
    setCursor(0);
  }
  const controls: typeof view = {
    ...view,
    setPartIndex: (value) => {
      view.setPartIndex(value);
      resetSelection();
    },
    setTransition: (id, text) => {
      view.setTransition(id, text);
      resetSelection();
    },
    acceptCandidate: (id, text) => {
      view.acceptCandidate(id, text);
      resetSelection();
    },
    apply: () => {
      view.apply();
      resetSelection();
    },
    clear: () => {
      view.clear();
      resetSelection();
    },
  };
  const activeBand = bands[zoneSide].find(
    (b) =>
      b.phase.from_ms !== null &&
      b.phase.to_ms !== null &&
      cursor >= b.phase.from_ms &&
      cursor < b.phase.to_ms,
  );
  const label = (s: Series | null) =>
    s
      ? `${metricInfo[s.metric_key].label} · ${s.metric_key === "speed_kmh" ? speedUnit : s.unit}`
      : "Kikapcsolva";
  const routeMap = (
    <RouteMap
      square={mapTarget !== undefined}
      creditTarget={creditTarget}
      key={`${exercise}:${data.samples.route_content_hash ?? data.samples.content_hash ?? data.retrieved_at}`}
      route={route}
      cursor={cursor}
      onCursor={pick}
      syncAllowed={syncAllowed}
      selected={selected}
    />
  );
  function axisControl(side: "left" | "right", index: number) {
    return (
      <label className="pt-axis-choice" style={{ color: COLORS[index] }}>
        {index === 0 ? "Bal tengely" : "Jobb tengely"}
        <select
          aria-label={
            index === 0 ? "Bal tengely adatsora" : "Jobb tengely adatsora"
          }
          value={choices[side]}
          onChange={(e) =>
            choose({ [side]: e.target.value as Choices["left"] })
          }
        >
          <option value="none">Kikapcsolva</option>
          {Object.entries(metricInfo).map(([key, info]) => (
            <option
              key={key}
              value={key}
              disabled={!selectMetric(series, key as MetricKey)}
            >
              {info.label}
              {selectMetric(series, key as MetricKey)
                ? ""
                : " · nincs mintasor"}
            </option>
          ))}
        </select>
      </label>
    );
  }
  function valueReadout(index: number) {
    const s = rows[index];
    return (
      <div
        className="pt-side-readout"
        style={{ color: COLORS[index] }}
        aria-label={
          index === 0
            ? "Bal tengely aktuális értéke"
            : "Jobb tengely aktuális értéke"
        }
      >
        {s ? (
          <>
            <strong>
              {displayValue(s, points[index]?.value ?? null, speedUnit)}
            </strong>
            <small>
              {metricInfo[s.metric_key].label}
              {points[index] && points[index]!.ms !== cursor
                ? ` · minta ${clock(points[index]!.ms)}`
                : ""}
            </small>
          </>
        ) : (
          <span>Kikapcsolva</span>
        )}
      </div>
    );
  }
  const targetReadout =
    activeBand && choices.targets ? (
      <p className="pt-side-target">
        Cél: {activeBand.target.zoneLabel ?? activeBand.target.label} ·{" "}
        {yformat(activeBand.target.low!, zoneSide)}–
        {yformat(activeBand.target.high!, zoneSide)}{" "}
        {rows[zoneSide]?.metric_key === "speed_kmh"
          ? speedUnit
          : rows[zoneSide]?.unit}
      </p>
    ) : null;
  const positionReadout = (
    <div className="pt-chart-readout pt-position-readout" aria-live="off">
      <strong>Idő · {clock(cursor)}</strong>
      <span>
        Táv ·{" "}
        {distanceAt(distance, cursor) === null
          ? "Nincs adat"
          : `${axisNumber(distanceAt(distance, cursor)! / 1000)} km`}
      </span>
    </div>
  );
  const speedSide =
    rows[0] && ["speed_kmh", "pace_sec_km"].includes(rows[0].metric_key)
      ? 0
      : rows[1] && ["speed_kmh", "pace_sec_km"].includes(rows[1].metric_key)
        ? 1
        : 0;
  return (
    <div className="pt-explorer">
      {positionTarget === undefined
        ? positionReadout
        : positionTarget
          ? createPortal(positionReadout, positionTarget)
          : null}
      {summaryTarget
        ? createPortal(
            <PhaseSummary
              results={summaries}
              cursor={cursor}
              speedUnit={speedUnit}
              sourceLabel={view.sourceLabel}
            />,
            summaryTarget,
          )
        : null}
      <section
        className="pt-analysis-card pt-combined-chart"
        aria-label="Közös edzésgrafikon"
      >
        <aside
          className="pt-chart-side pt-chart-side-left"
          aria-label="Bal tengely és általános beállítások"
        >
          {axisControl("left", 0)}
          {valueReadout(0)}
          {speedSide === 0 && (
            <SpeedUnitControl value={speedUnit} onChange={onSpeedUnitChange} />
          )}
          {zoneSide === 0 && targetReadout}
          <div className="pt-explorer-controls">
            <div role="group" aria-label="Vízszintes tengely">
              <button
                type="button"
                aria-pressed={mode === "time"}
                onClick={() => choose({ x: "time" })}
              >
                Idő
              </button>
              <button
                type="button"
                disabled={!distance || !syncAllowed}
                aria-pressed={mode === "distance"}
                title={
                  !distance
                    ? "Nincs egyértelmű, folytonosan növekvő távmintasor"
                    : !syncAllowed
                      ? "A mintasor időalapja tisztázandó"
                      : "Mért táv a kezdőértékhez képest"
                }
                onClick={() => choose({ x: "distance" })}
              >
                Táv
              </button>
            </div>
            <label>
              Célsáv
              <select
                value={zoneSide}
                onChange={(e) => setZoneSide(Number(e.target.value))}
              >
                <option value="0">Bal tengely</option>
                <option value="1">Jobb tengely</option>
              </select>
            </label>
            <details>
              <summary>Megjelenítés</summary>
              {(
                [
                  ["boundaries", "Szakaszhatárok"],
                  ["targets", "Előírt célsávok"],
                  ["zones", "Edzési zónák"],
                ] as const
              ).map(([key, title]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={choices[key]}
                    onChange={(e) => choose({ [key]: e.target.checked })}
                  />
                  {title}
                </label>
              ))}
            </details>
            <button
              type="button"
              onClick={() => {
                setFrom(0);
                setTo(end);
                setSelected(null);
                setCandidate(null);
              }}
            >
              Teljes edzésrész
            </button>
          </div>
        </aside>
        <aside
          className="pt-chart-side pt-chart-side-right"
          aria-label="Jobb tengely beállításai"
        >
          {axisControl("right", 1)}
          {valueReadout(1)}
          {speedSide === 1 && (
            <SpeedUnitControl value={speedUnit} onChange={onSpeedUnitChange} />
          )}
          {zoneSide === 1 && targetReadout}
        </aside>
        {series.some(
          (s) => s.interval_ms !== null && s.valid_sample_count > 0,
        ) ? (
          <>
            <svg
              preserveAspectRatio="none"
              className="pt-combined-svg"
              viewBox="0 0 1000 240"
              role="img"
              aria-label={`${label(rows[0])}; ${label(rows[1])}. Közös ${mode === "time" ? "idő" : "táv"}tengely.`}
              onPointerMove={(e) => {
                const ms = point(e);
                if (ms !== null) pick(ms);
              }}
              onPointerDown={(e) => {
                const ms = point(e);
                if (ms !== null && candidate) {
                  const value = pickedCandidateTime(candidate, ms);
                  setPicked(value);
                  pick(value);
                }
              }}
            >
              <defs>
                <clipPath id={clip}>
                  <rect x="70" y="22" width="860" height="180" />
                </clipPath>
              </defs>
              {[0, 1].map(
                (i) =>
                  rows[i] && (
                    <g key={i} style={{ color: COLORS[i] }}>
                      {axes[i].ticks.map((v) => (
                        <g key={v}>
                          <line
                            x1="70"
                            x2="930"
                            y1={ypos(v, i)}
                            y2={ypos(v, i)}
                            className={
                              i === 0
                                ? "pt-combined-grid"
                                : "pt-combined-right-grid"
                            }
                          />
                          <text
                            x={i === 0 ? 60 : 940}
                            y={ypos(v, i) + 4}
                            textAnchor={i === 0 ? "end" : "start"}
                            fill="currentColor"
                          >
                            {yformat(v, i)}
                          </text>
                        </g>
                      ))}
                    </g>
                  ),
              )}
              {timeTicks(xmin, xmax).map((v) => (
                <g key={v}>
                  <line
                    x1={xpos(v)}
                    x2={xpos(v)}
                    y1="22"
                    y2="202"
                    className="pt-combined-grid"
                  />
                  <text x={xpos(v)} y="224" textAnchor="middle">
                    {mode === "time" ? clock(v) : axisNumber(v / 1000) + " km"}
                  </text>
                </g>
              ))}
              <g clipPath={`url(#${clip})`}>
                {choices.boundaries &&
                  view.show &&
                  view.alignment.gaps
                    .filter((g) => g.to_ms > from && g.from_ms < to)
                    .map((g) => {
                      const a = xtime(Math.max(from, g.from_ms)),
                        b = xtime(Math.min(to, g.to_ms));
                      return a === null || b === null ? null : (
                        <rect
                          key={g.id}
                          data-gap-kind={g.kind}
                          x={a}
                          width={Math.max(0, b - a)}
                          y="22"
                          height="180"
                          fill="var(--pt-muted)"
                          opacity="0.1"
                        >
                          <title>
                            {g.kind === "wait"
                              ? "Köztes várakozás · kézi referencia"
                              : "Szakaszhoz nem rendelt idő"}{" "}
                            · {clock(g.from_ms)}–{clock(g.to_ms)}
                          </title>
                        </rect>
                      );
                    })}
                {choices.zones &&
                  zoneDefinition?.zones.map((z) => {
                    const a = ypos(z.low, zoneSide),
                      b = ypos(z.high, zoneSide);
                    return (
                      <g key={z.index}>
                        <rect
                          x="70"
                          y={Math.min(a, b)}
                          width="860"
                          height={Math.abs(a - b)}
                          fill={ZONE_COLORS[z.index - 1]}
                          opacity="0.09"
                        />
                        <line
                          x1="70"
                          x2="930"
                          y1={a}
                          y2={a}
                          stroke={ZONE_COLORS[z.index - 1]}
                          strokeDasharray="3 4"
                        />
                        <text x="76" y={Math.min(a, b) + 12}>
                          Z{z.index} · {yformat(z.low, zoneSide)}–
                          {yformat(z.high, zoneSide)}
                        </text>
                      </g>
                    );
                  })}
                {choices.targets &&
                  bands[zoneSide].map(({ phase, target }) => {
                    const a = xtime(phase.from_ms!),
                      b = xtime(phase.to_ms!);
                    if (a === null || b === null) return null;
                    const low = ypos(target.low!, zoneSide),
                      high = ypos(target.high!, zoneSide);
                    return (
                      <g key={phase.id} className="pt-prescribed-band">
                        <rect
                          x={a}
                          width={Math.max(0, b - a)}
                          y={Math.min(low, high)}
                          height={Math.abs(high - low)}
                          fill={COLORS[zoneSide]}
                          opacity="0.12"
                        />
                        {[low, high].map((v, i) => (
                          <line
                            key={i}
                            x1={a}
                            x2={b}
                            y1={v}
                            y2={v}
                            stroke={COLORS[zoneSide]}
                            strokeDasharray="5 3"
                          />
                        ))}
                        <title>
                          {phase.label} · {target.label} · {target.low}–
                          {target.high}{" "}
                          {rows[zoneSide]?.metric_key === "speed_kmh"
                            ? speedUnit
                            : rows[zoneSide]?.unit}
                        </title>
                      </g>
                    );
                  })}
                {selected &&
                  xtime(selected.from) !== null &&
                  xtime(selected.to) !== null && (
                    <rect
                      x={xtime(selected.from)!}
                      width={Math.max(
                        0,
                        xtime(selected.to)! - xtime(selected.from)!,
                      )}
                      y="22"
                      height="180"
                      fill="var(--pt-warning)"
                      opacity="0.1"
                    />
                  )}
                {choices.boundaries &&
                  view.show &&
                  view.boundaries
                    .filter((b) => b.ms >= from && b.ms <= to)
                    .filter(
                      (b, i, all) =>
                        all.length <= 160 || i === 0 || i === all.length - 1,
                    )
                    .map((b, i) => {
                      const x = xtime(b.ms);
                      return x === null ? null : (
                        <line
                          key={i}
                          x1={x}
                          x2={x}
                          y1="22"
                          y2="202"
                          className={`pt-combined-boundary is-${view.manual ? "manual" : view.hasReferences ? "reviewed" : view.alignment.distanceUsed ? "distance" : "plan"}`}
                        >
                          <title>
                            {b.labels.join(" · ")} · {view.sourceLabel}
                          </title>
                        </line>
                      );
                    })}
                {runs.map((collection, i) =>
                  collection.length > 1500
                    ? null
                    : collection.map((run, n) =>
                        run.length === 1 ? (
                          <circle
                            key={`${i}-${n}`}
                            cx={xpos(run[0].x)}
                            cy={ypos(run[0].y, i)}
                            r="2"
                            fill={COLORS[i]}
                          />
                        ) : (
                          <path
                            key={`${i}-${n}`}
                            d={run
                              .map(
                                (p, k) =>
                                  `${k ? "L" : "M"}${xpos(p.x).toFixed(2)},${ypos(p.y, i).toFixed(2)}`,
                              )
                              .join(" ")}
                            fill="none"
                            stroke={COLORS[i]}
                            strokeWidth="1.7"
                            vectorEffect="non-scaling-stroke"
                          />
                        ),
                      ),
                )}
                {xtime(cursor) !== null && (
                  <line
                    x1={xtime(cursor)!}
                    x2={xtime(cursor)!}
                    y1="22"
                    y2="202"
                    className="pt-chart-cursor"
                  />
                )}
                {points.map((p, i) => {
                  const x = p ? xtime(p.ms) : null;
                  return p && x !== null ? (
                    <circle
                      key={i}
                      cx={x}
                      cy={ypos(
                        rows[i]?.metric_key === "speed_kmh"
                          ? p.value *
                              (speedUnit === "m/s"
                                ? 1 / 3.6
                                : speedUnit === "knots"
                                  ? 1 / 1.852
                                  : 1)
                          : p.value,
                        i,
                      )}
                      r="3"
                      fill={COLORS[i]}
                    />
                  ) : null;
                })}
              </g>
            </svg>
          </>
        ) : (
          <p className="pt-notice">
            Ehhez az edzésrészhez nincs megjeleníthető tárolt mintasor. Az
            összesítőkből nem készül mért görbe.
          </p>
        )}
        {runs.some((r) => r.length > 1500) && (
          <p className="pt-notice">
            Túl sok különálló mintaszakasz; a részletes nézetben szűkítsd az
            időtartományt.
          </p>
        )}
        {phases.length > 0 && (
          <div className="pt-phase-ribbon" aria-label="Edzésszakaszok">
            {phases.slice(0, 80).map((p) => (
              <button
                type="button"
                key={p.id}
                disabled={p.from_ms === null || p.to_ms === null}
                title={`${p.label} · ${p.from_ms === null || p.to_ms === null ? "bizonytalan határ" : clock(p.from_ms) + "–" + clock(p.to_ms)} · ${view.sourceLabel}`}
                style={{
                  flex:
                    p.from_ms !== null && p.to_ms !== null
                      ? Math.max(1, p.to_ms - p.from_ms)
                      : 1,
                }}
                onClick={() => {
                  setSelected({ from: p.from_ms!, to: p.to_ms! });
                  pick(p.from_ms!);
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
        )}
        {source.length > 0 && (
          <input
            className="pt-linked-cursor"
            aria-label="Közös grafikon és térkép pontja"
            type="range"
            min="0"
            max={end}
            step="1000"
            value={Math.min(end, cursor)}
            onChange={(e) => pick(Number(e.target.value))}
          />
        )}
        {notice && (
          <p className="pt-notice" role="status">
            {notice}
          </p>
        )}
      </section>
      {mapTarget === undefined
        ? routeMap
        : mapTarget
          ? createPortal(routeMap, mapTarget)
          : null}
      <details className="pt-analysis-card pt-explorer-method">
        <summary>Szakaszillesztés és részletes beállítások</summary>
        <form
          className="pt-chart-range"
          onSubmit={(event) => {
            event.preventDefault();
            const values = new FormData(event.currentTarget),
              a = Number(values.get("from")) * 1000,
              b = Number(values.get("to")) * 1000,
              maximum = Math.max(end, view.boundaries.at(-1)?.ms ?? 0);
            if (
              Number.isFinite(a) &&
              Number.isFinite(b) &&
              a >= 0 &&
              a < b &&
              b <= maximum
            ) {
              setFrom(a);
              setTo(b);
              setSelected(null);
              setCandidate(null);
              setCursor(a);
              setRangeError("");
            } else
              setRangeError(
                "A tartomány maradjon a mintasor vagy terv időhatárain belül; a vég legyen később a kezdetnél.",
              );
          }}
        >
          <label>
            Kezdet · mp
            <input
              name="from"
              key={`from-${from}`}
              type="number"
              min="0"
              step="0.001"
              defaultValue={from / 1000}
              required
            />
          </label>
          <label>
            Vég · mp
            <input
              name="to"
              key={`to-${to}`}
              type="number"
              min="0"
              step="0.001"
              defaultValue={to / 1000}
              required
            />
          </label>
          <button type="submit" className="pt-button">
            Tartomány nagyítása
          </button>
        </form>
        {rangeError && (
          <p className="pt-notice" role="alert">
            {rangeError}
          </p>
        )}
        <PlanBoundaryControls
          view={controls}
          end={end}
          onZoom={(a, b) => {
            setFrom(a);
            setTo(b);
            pick(a);
          }}
        />
        <p className="pt-notice">
          Az idő az edzésrész mintasorának ideje; a szünetekkel a falióraideje
          eltérhet. A GPS-jelölés legfeljebb 5 másodpercre lévő forráspontot
          mutat, nem interpolált helyzetet. A szaggatott szakaszhatárok
          tervillesztések, nem igazolt óragombnyomások.
        </p>
      </details>
      <SourceSamples series={series} cursor={cursor} unit={speedUnit} />
      <PhaseAssessment
        view={controls}
        series={series}
        plan={data.plan}
        zones={phaseZones}
        speedUnit={speedUnit}
        onSelect={(row) => {
          if (row.from_ms !== null && row.to_ms !== null) {
            setSelected({ from: row.from_ms, to: row.to_ms });
            pick(row.from_ms);
          }
        }}
        onPreview={(value) => {
          setCandidate(value);
          setPicked(null);
          setFrom(value.goal_ms);
          setSelected({ from: value.from_ms, to: value.to_ms });
          pick(value.start_ms);
          setTo(value.preview_to_ms);
        }}
        pickedMs={picked}
        onCancelPreview={() => {
          setCandidate(null);
          setPicked(null);
        }}
      />
    </div>
  );
}

function SourceSamples({
  series,
  cursor,
  unit,
}: {
  series: Series[];
  cursor: number;
  unit: SpeedUnit;
}) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="pt-analysis-card"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>Forrásminták és időalap</summary>
      {open && (
        <>
          <p className="pt-notice">
            Tárolt minták, soronként legfeljebb 101 forráshely a kijelölt idő
            körül. A hiányok nem jelentenek nulla értéket. Az iram a sebességből
            számított; az összteljesítményhez együtt mért bal és jobb csatorna
            kell.
          </p>
          {series.map((s) => {
            const center =
                s.interval_ms === null ? 0 : Math.round(cursor / s.interval_ms),
              first = Math.max(0, center - 50);
            return (
              <details key={s.id}>
                <summary>
                  {metricInfo[s.metric_key].label} · {s.source_path}
                </summary>
                <div className="pt-analysis-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Sorszám</th>
                        <th>Minta ideje</th>
                        <th>Érték</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.values.slice(first, first + 101).map((value, i) => (
                        <tr key={i}>
                          <td>{first + i}</td>
                          <td>
                            {s.interval_ms === null
                              ? "Ismeretlen"
                              : clock((first + i) * s.interval_ms)}
                          </td>
                          <td>{displayValue(s, value, unit)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            );
          })}
        </>
      )}
    </details>
  );
}
