import {
  formatInstant,
  knownScore,
  scale,
} from "@/lib/personal-response/presentation";
import type { Observation, Dataset } from "@/lib/personal-response/contracts";
const left = 48,
  right = 600,
  top = 20,
  bottom = 210;
export function ScoreChart({
  observations,
  dataset,
  zone,
  scatter = false,
}: {
  observations: Observation[];
  dataset?: Dataset;
  zone: string;
  scatter?: boolean;
}) {
  const eligible = new Map(
    dataset?.pairs
      .filter((p) => p.eligibility === "eligible_numeric_pair")
      .map((p) => [p.response_observation_id, p]),
  );
  const points = observations.filter(knownScore).flatMap((o) => {
    const pair = eligible.get(o.observation_id);
    if (scatter && !pair) return [];
    return [
      {
        o,
        x: scatter
          ? pair!.predictor_numeric_value! / 60
          : Date.parse(o.response_observed_at),
        y: Number(o.value),
      },
    ];
  });
  const title = scatter ? "Edzésidő és visszajelzés" : "Visszajelzések időben";
  if (!points.length)
    return (
      <div className="pt-pr-chart">
        <h3>{title}</h3>
        <p className="pt-notice">
          {scatter
            ? "Még nincs ebben a környezetben ismert edzésidővel összekapcsolt, számszerű válasz."
            : "Ebben a környezetben még nincs számszerű válasz."}
        </p>
      </div>
    );
  if (points.length > 500)
    return (
      <div className="pt-pr-chart">
        <h3>{title}</h3>
        <p className="pt-notice">
          Több mint 500 pont tartozik ide. A grafikonhoz válassz rövidebb
          időszakot. Az összes adat továbbra is szerepel a lapozható
          táblázatban.
        </p>
      </div>
    );
  const low = scatter ? 0 : Math.min(...points.map((p) => p.x)),
    high = Math.max(...points.map((p) => p.x));
  const xs = high === low ? [low] : [low, (low + high) / 2, high];
  return (
    <div className="pt-pr-chart">
      <h3>{title}</h3>
      <svg viewBox="0 0 640 260" role="group" aria-label={title}>
        <text x={left} y={13} className="pt-pr-axis">
          pont
        </text>
        {[0, 2, 4, 6, 8, 10].map((y) => (
          <g key={y}>
            <line
              x1={left}
              x2={right}
              y1={scale(y, 0, 10, top - bottom, bottom)}
              y2={scale(y, 0, 10, top - bottom, bottom)}
              className="pt-pr-guide"
            />
            <text
              x={left - 10}
              y={scale(y, 0, 10, top - bottom, bottom) + 4}
              textAnchor="end"
              className="pt-pr-axis"
            >
              {y}
            </text>
          </g>
        ))}
        {xs.map((x, i) => (
          <g key={i}>
            <line
              x1={scale(x, low, high, right - left, left)}
              x2={scale(x, low, high, right - left, left)}
              y1={top}
              y2={bottom}
              className="pt-pr-guide"
            />
            <text
              x={scale(x, low, high, right - left, left)}
              y={232}
              textAnchor="middle"
              className="pt-pr-axis"
            >
              {scatter
                ? new Intl.NumberFormat("hu-HU", {
                    maximumFractionDigits: 1,
                  }).format(x)
                : formatInstant(new Date(x).toISOString(), zone, true)}
            </text>
          </g>
        ))}
        {points.map(({ o, x, y }) => {
          const label = `${formatInstant(o.response_observed_at, zone)} · ${y} pont${scatter ? ` · ${x.toLocaleString("hu-HU", { maximumFractionDigits: 1 })} perc` : ""} · Edzés megnyitása`;
          return (
            <a
              key={o.observation_id}
              href={`/sessions/${o.workout_session_id}`}
              aria-label={label}
              tabIndex={0}
            >
              <title>{label}</title>
              <circle
                cx={scale(x, low, high, right - left, left)}
                cy={scale(y, 0, 10, top - bottom, bottom)}
                r={5}
                className="pt-pr-point"
              />
            </a>
          );
        })}
        <text x={right} y={255} textAnchor="end" className="pt-pr-axis">
          {scatter ? "Edzésidő (perc)" : zone}
        </text>
      </svg>
      <p className="pt-notice">
        {scatter
          ? "Egy pont egy megfigyelés. Az edzésidő nem azonos az élettani terheléssel; a pontok nem igazolnak okozati hatást."
          : "A hiányzó válaszok nem kerülnek a grafikonra. A pontokra kattintva megnyílik az edzés."}
      </p>
    </div>
  );
}
