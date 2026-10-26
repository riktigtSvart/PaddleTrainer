import type { CSSProperties, ReactNode } from "react";
export type IconName =
  | "calendar"
  | "user"
  | "settings"
  | "cart"
  | "target"
  | "chart"
  | "sun"
  | "moon"
  | "monitor"
  | "refresh"
  | "left"
  | "right"
  | "close"
  | "check"
  | "clock"
  | "wave"
  | "strength"
  | "running"
  | "cycling"
  | "swimming"
  | "kayak"
  | "activity"
  | "menu"
  | "alert"
  | "info";
// The warning shape remains distinguishable without relying on its color.
const paths: Record<IconName, ReactNode> = {
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M7 3v4m10-4v4M3 11h18M7 15h2m3 0h2m3 0h1" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21v-2a8 8 0 0 1 16 0v2z" />
    </>
  ),
  settings: (
    <>
      <path d="m10 3-1 3-3 1-3-1-1 4 3 2v3l-2 2 3 3 3-1 3 2 3-2 3 1 3-3-2-3v-3l2-2-2-4-3 1-3-3z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  cart: (
    <>
      <path d="M2 3h3l3 13h10l3-9H6M9 20h.01M18 20h.01" />
      <circle cx="9" cy="20" r="1" />
      <circle cx="18" cy="20" r="1" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" />
    </>
  ),
  chart: <path d="M3 3v18h18M6 15l4-5 4 3 6-8" />,
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1" />
    </>
  ),
  moon: <path d="M20 15a9 9 0 0 1-11-12A9 9 0 1 0 20 15z" />,
  monitor: (
    <>
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8m-4-4v4" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 7V2m0 5h-5M4 17v5m0-5h5M4 9a8 8 0 0 1 14-5l2 3M4 17l2 3a8 8 0 0 0 14-5" />
    </>
  ),
  left: <path d="m15 5-7 7 7 7" />,
  right: <path d="m9 5 7 7-7 7" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  check: <path d="m4 12 5 5L20 6" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 6v6l4 2" />
    </>
  ),
  wave: (
    <>
      <path d="M2 8q3-4 6 0t6 0 6 0M2 14q3-4 6 0t6 0 6 0M2 20q3-4 6 0t6 0 6 0" />
    </>
  ),
  strength: (
    <>
      <path d="M7 12h10M3 8v8m4-11v14M17 5v14m4-11v8" />
    </>
  ),
  running: (
    <>
      <circle cx="15" cy="4" r="2" />
      <path d="m12 9-4 3-4-1m8-2 4 4h4m-8-4-2 6-5 6m5-6 5 2v5" />
    </>
  ),
  cycling: (
    <>
      <circle cx="5" cy="17" r="4" />
      <circle cx="19" cy="17" r="4" />
      <path d="m5 17 5-8 5 8H5m5-8h7l2 8M8 6h4m4-1h3" />
    </>
  ),
  swimming: (
    <>
      <circle cx="17" cy="5" r="2" />
      <path d="m3 12 6-7 7 7M2 17q3-3 6 0t6 0 6 0M2 22q3-3 6 0t6 0 6 0" />
    </>
  ),
  kayak: (
    <>
      <path d="M2 17q9-5 20-2-5 8-16 5zM6 4l12 12M4 2l4 2-2 3-4-3zm14 14 4 3-2 3-4-3z" />
    </>
  ),
  activity: <path d="M2 12h5l3-8 4 16 3-8h5" />,
  menu: <path d="M3 5h18M3 12h18M3 19h18" />,
  alert: (
    <>
      <path d="M12 3 2 21h20L12 3zM12 9v5m0 3h.01" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6m0-10h.01" />
    </>
  ),
};
export function sportIcon(sport: string): IconName {
  return (
    (
      {
        KAYAK: "kayak",
        RUNNING: "running",
        CYCLING: "cycling",
        SWIMMING: "swimming",
        STRENGTH: "strength",
      } as Record<string, IconName>
    )[sport] ?? "activity"
  );
}
export default function Icon({
  name,
  className,
  style,
}: {
  name: IconName;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <svg
      className={className}
      style={style}
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
