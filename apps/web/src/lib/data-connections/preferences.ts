import type { Dataset, Status, Provider } from "./contracts";
export type RefreshChoice =
  | { mode: "local" }
  | {
      mode: "provider";
      provider: string;
      pastDays: 7 | 35 | 89;
      datasets: Dataset[];
    };
export const LOCAL_REFRESH_EVENT = "paddletrainer:local-refresh";
export const localChoice: RefreshChoice = { mode: "local" };
export const preferenceKey = (owner: string) =>
  "paddletrainer.refresh-choice.v1:" + owner;
export function readChoice(raw: string, owner: string): RefreshChoice {
  const x = JSON.parse(raw);
  if (!x || x.version !== 1 || x.owner !== owner || !x.choice)
    throw Error("Másik sportolóhoz tartozó vagy hibás frissítési beállítás.");
  const c = x.choice;
  if (c.mode === "local") return { mode: "local" };
  if (
    c.mode !== "provider" ||
    typeof c.provider !== "string" ||
    !/^[A-Z][A-Z0-9_]{0,40}$/.test(c.provider) ||
    ![7, 35, 89].includes(c.pastDays) ||
    !Array.isArray(c.datasets) ||
    !c.datasets.length ||
    new Set(c.datasets).size !== c.datasets.length ||
    !c.datasets.every((d: unknown) =>
      ["sessions", "targets", "session_details"].includes(String(d)),
    )
  )
    throw Error("A frissítési beállítás nem értelmezhető.");
  return {
    mode: "provider",
    provider: c.provider,
    pastDays: c.pastDays,
    datasets: [...c.datasets],
  };
}
export function choiceProvider(
  choice: RefreshChoice,
  status: Status,
): Provider | null {
  if (choice.mode !== "provider") return null;
  const p = status.providers.find((p) => p.key === choice.provider);
  return p &&
    p.implemented &&
    p.connection_state === "connected" &&
    p.manual_sync_supported &&
    choice.datasets.every((d) => p.allowed_datasets.includes(d))
    ? p
    : null;
}
