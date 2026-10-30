"use client";
import { createPortal } from "react-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Route, RoutePoint } from "@/lib/session-analysis/contracts";
import {
  mercator,
  nearestRoute,
  routeRuns,
} from "@/lib/session-analysis/explorer";
import { clock } from "@/lib/session-analysis/chart-data";
export function RouteMap({
  route,
  cursor,
  onCursor,
  syncAllowed,
  selected,
  square = false,
  creditTarget,
}: {
  square?: boolean;
  creditTarget?: HTMLElement | null;
  route: Route | null;
  cursor: number;
  onCursor: (ms: number) => void;
  syncAllowed: boolean;
  selected: { from: number; to: number } | null;
}) {
  const [WIDTH, setWidth] = useState(1000);
  const [measuredHeight, setMeasuredHeight] = useState(300);
  const HEIGHT = square ? measuredHeight : 190;
  const viewport = useRef<HTMLElement>(null);
  useEffect(() => {
    const node = viewport.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (node.clientWidth > 0) setWidth(node.clientWidth);
      if (square && node.clientHeight > 0) setMeasuredHeight(node.clientHeight);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [square]);
  const [layer, setLayer] = useState<"topo" | "satellite">("topo"),
    [zoom, setZoom] = useState(0),
    [pan, setPan] = useState({ x: 0, y: 0 }),
    [failed, setFailed] = useState(false);
  const drag = useRef<{
    x: number;
    y: number;
    pan: { x: number; y: number };
  } | null>(null);
  const runs = useMemo(() => routeRuns(route?.points ?? []), [route]);
  const points = useMemo(() => runs.flat(), [runs]);
  const base = useMemo(() => {
    if (!points.length) return { z: 3, x: 512, y: 512 };
    let minx = Infinity,
      maxx = -Infinity,
      miny = Infinity,
      maxy = -Infinity;
    for (const p of points) {
      const v = mercator(p.lat!, p.lon!, 0);
      minx = Math.min(minx, v.x);
      maxx = Math.max(maxx, v.x);
      miny = Math.min(miny, v.y);
      maxy = Math.max(maxy, v.y);
    }
    let z = 16;
    for (; z > 1; z--)
      if (
        (maxx - minx) * 2 ** z < WIDTH - 80 &&
        (maxy - miny) * 2 ** z < HEIGHT - 90
      )
        break;
    return {
      z,
      x: ((minx + maxx) / 2) * 2 ** z,
      y: ((miny + maxy) / 2) * 2 ** z,
    };
  }, [points, WIDTH, HEIGHT]);
  const z = Math.max(1, Math.min(layer === "topo" ? 17 : 19, base.z + zoom)),
    factor = 2 ** (z - base.z),
    left = base.x * factor - WIDTH / 2 + pan.x,
    top = base.y * factor - HEIGHT / 2 + pan.y;
  const project = (p: RoutePoint) => {
    const xy = mercator(p.lat!, p.lon!, z);
    return { x: xy.x - left, y: xy.y - top };
  };
  const drawRuns = useMemo(() => {
    const budget = 3000;
    return runs.slice(0, 1500).map((run) => {
      const step = Math.max(1, Math.ceil(points.length / budget));
      return run.filter(
        (_, i) => i === 0 || i === run.length - 1 || i % step === 0,
      );
    });
  }, [runs, points.length]);
  const locations = useMemo(
    () => points.map((p) => ({ point: p, ...mercator(p.lat!, p.lon!, z) })),
    [points, z],
  );
  const active = syncAllowed ? nearestRoute(points, cursor) : null;
  const key = process.env.NEXT_PUBLIC_ARCGIS_API_KEY;
  const satellite = typeof key === "string" && key.trim().length > 0;
  const tiles = [];
  if (points.length)
    for (
      let y = Math.floor(top / 256);
      y <= Math.floor((top + HEIGHT) / 256);
      y++
    )
      for (
        let x = Math.floor(left / 256);
        x <= Math.floor((left + WIDTH) / 256);
        x++
      )
        if (y >= 0 && y < 2 ** z) {
          const wrapped = ((x % 2 ** z) + 2 ** z) % 2 ** z;
          tiles.push({
            x: x * 256 - left,
            y: y * 256 - top,
            url:
              layer === "topo"
                ? `https://a.tile.opentopomap.org/${z}/${wrapped}/${y}.png`
                : `https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${wrapped}?token=${encodeURIComponent(key ?? "")}`,
          });
        }
  function hover(event: React.PointerEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    if (!box.width) return;
    if (drag.current) {
      setPan({
        x:
          drag.current.pan.x -
          ((event.clientX - drag.current.x) * WIDTH) / box.width,
        y:
          drag.current.pan.y -
          ((event.clientY - drag.current.y) * HEIGHT) / box.height,
      });
      return;
    }
    if (!syncAllowed) return;
    const x = ((event.clientX - box.left) / box.width) * WIDTH,
      y = ((event.clientY - box.top) / box.height) * HEIGHT;
    let best: RoutePoint | null = null,
      d = Infinity;
    for (const location of locations) {
      const p = location.point;
      if (p.ms === null) continue;
      const n = Math.hypot(location.x - left - x, location.y - top - y);
      if (
        n < d - 0.01 ||
        (Math.abs(n - d) < 0.01 &&
          Math.abs(p.ms - cursor) < Math.abs((best?.ms ?? Infinity) - cursor))
      ) {
        d = n;
        best = p;
      }
    }
    if (best && d < 32) onCursor(best.ms!);
  }
  const credit =
    points.length > 0 ? (
      <div className="pt-route-credit">
        {layer === "topo" ? (
          <>
            <a
              href="https://www.openstreetmap.org/copyright"
              target="_blank"
              rel="noreferrer"
            >
              © OpenStreetMap
            </a>
            , SRTM ·{" "}
            <a
              href="https://opentopomap.org/about"
              target="_blank"
              rel="noreferrer"
            >
              OpenTopoMap · CC-BY-SA
            </a>
          </>
        ) : (
          <a
            href="https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9"
            target="_blank"
            rel="noreferrer"
          >
            Esri, Maxar, Earthstar Geographics, GIS User Community
          </a>
        )}
        {active ? ` · GPS ${clock(active.ms!)}` : ""}
      </div>
    ) : null;
  return (
    <>
      <section
        ref={viewport}
        className={`pt-route-panel${square ? " is-overview-map" : ""}`}
        aria-label="GPS útvonal"
      >
        <div className="pt-route-toolbar">
          <div role="group" aria-label="Térképréteg">
            <button
              type="button"
              aria-pressed={layer === "topo"}
              onClick={() => {
                setLayer("topo");
                setFailed(false);
              }}
            >
              Topó
            </button>
            <button
              type="button"
              disabled={!satellite}
              title={
                satellite
                  ? "Műholdas alaptérkép"
                  : "A műholdas térkép még nincs beállítva"
              }
              aria-pressed={layer === "satellite"}
              onClick={() => {
                setLayer("satellite");
                setFailed(false);
              }}
            >
              Műhold
            </button>
          </div>
          <div>
            <button
              type="button"
              aria-label="Térkép kicsinyítése"
              onClick={() => {
                setZoom((n) => n - 1);
                setPan({ x: 0, y: 0 });
              }}
            >
              −
            </button>
            <button
              type="button"
              aria-label="Térkép nagyítása"
              onClick={() => {
                setZoom((n) => n + 1);
                setPan({ x: 0, y: 0 });
              }}
            >
              +
            </button>
            <button
              type="button"
              onClick={() => {
                setZoom(0);
                setPan({ x: 0, y: 0 });
              }}
            >
              Útvonal
            </button>
          </div>
        </div>
        {points.length ? (
          <svg
            style={square ? { height: "100%" } : undefined}
            preserveAspectRatio="none"
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            role="img"
            aria-label="Tárolt GPS-útvonal. Húzással mozgatható; a közeli pontra mutatva a grafikon is követi."
            tabIndex={0}
            onKeyDown={(event) => {
              const amount = 32;
              if (
                ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(
                  event.key,
                )
              ) {
                event.preventDefault();
                setPan((old) => ({
                  x:
                    old.x +
                    (event.key === "ArrowLeft"
                      ? -amount
                      : event.key === "ArrowRight"
                        ? amount
                        : 0),
                  y:
                    old.y +
                    (event.key === "ArrowUp"
                      ? -amount
                      : event.key === "ArrowDown"
                        ? amount
                        : 0),
                }));
              }
            }}
            onPointerMove={hover}
            onPointerDown={(event) => {
              drag.current = { x: event.clientX, y: event.clientY, pan };
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerUp={() => {
              drag.current = null;
            }}
            onPointerCancel={() => {
              drag.current = null;
            }}
          >
            {tiles.map((t) => (
              <image
                key={t.url + ":" + t.x}
                href={t.url}
                x={t.x}
                y={t.y}
                width="256"
                height="256"
                onError={() => setFailed(true)}
              />
            ))}
            {drawRuns.map((run, i) => {
              const path = run
                .map((p) => {
                  const v = project(p);
                  return `${v.x},${v.y}`;
                })
                .join(" ");
              return (
                <g key={i} className="pt-route-track">
                  <polyline
                    points={path}
                    fill="none"
                    stroke="#152034"
                    strokeWidth="7"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                    vectorEffect="non-scaling-stroke"
                  />
                  <polyline
                    points={path}
                    fill="none"
                    stroke="#ff3fa4"
                    strokeWidth="3.5"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                    vectorEffect="non-scaling-stroke"
                  />
                </g>
              );
            })}
            {selected &&
              syncAllowed &&
              drawRuns.map((run, i) => (
                <polyline
                  key={"selection" + i}
                  points={run
                    .filter(
                      (p) =>
                        p.ms !== null &&
                        p.ms >= selected.from &&
                        p.ms <= selected.to,
                    )
                    .map((p) => {
                      const v = project(p);
                      return `${v.x},${v.y}`;
                    })
                    .join(" ")}
                  fill="none"
                  stroke="#ffe66d"
                  strokeWidth="5"
                  vectorEffect="non-scaling-stroke"
                />
              ))}
            {active && (
              <circle
                cx={project(active).x}
                cy={project(active).y}
                r="5"
                fill="#ff3fa4"
                stroke="#152034"
                strokeWidth="2"
              >
                <title>{`GPS · ${clock(active.ms!)}`}</title>
              </circle>
            )}
          </svg>
        ) : (
          <p className="pt-notice">
            Ehhez az edzésrészhez nincs megjeleníthető tárolt GPS-útvonal. A
            részletes szinkron az elérhető útvonalat is átveszi.
          </p>
        )}
        {creditTarget === undefined && credit}
        <div className="pt-route-status">
          {failed && (
            <p className="pt-notice">
              Az alaptérkép nem tölthető be. A tárolt útvonal ettől még látható.
            </p>
          )}
          {!syncAllowed && points.length > 0 && (
            <p className="pt-notice">
              Az útvonal és a mintasor időkapcsolata tisztázandó; a közös
              pontjelölés most nem aktív.
            </p>
          )}
        </div>
      </section>
      {creditTarget ? createPortal(credit, creditTarget) : null}
    </>
  );
}
