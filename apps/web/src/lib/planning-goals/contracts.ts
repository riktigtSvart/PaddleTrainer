import { RESOURCES, SCHEMAS } from "./types";
import type {
  ArtifactPage,
  Catalog,
  Receipt,
  Reference,
  Resource,
} from "./types";

const identity = "APPLICATION_DEMO_USER";
export function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Hibás szerverválasz.");
  return value as Record<string, unknown>;
}
export function reference(artifact: Reference): Reference {
  return {
    artifact_id: artifact.artifact_id,
    content_hash: artifact.content_hash,
  };
}
export function readReceipt(value: unknown, resource: Resource): Receipt {
  const data = object(value),
    artifact = object(data.artifact),
    authority = object(artifact.authority);
  const prefix =
    resource === "assessments"
      ? "pt-goal-assessment"
      : resource === "measurements"
        ? "pt-goal-measurement"
        : "pt-goal";
  if (
    data.identity_scope !== identity ||
    data.committed !== true ||
    typeof data.reused !== "boolean" ||
    typeof data.measurement_schedule_preregistered !== "boolean" ||
    typeof data.durable_available_at !== "string" ||
    !Number.isFinite(Date.parse(data.durable_available_at)) ||
    artifact.schema_version !== SCHEMAS[resource] ||
    typeof artifact.artifact_id !== "string" ||
    !new RegExp(`^${prefix}:[0-9a-f]{64}$`).test(artifact.artifact_id) ||
    typeof artifact.content_hash !== "string" ||
    !/^[0-9a-f]{64}$/.test(artifact.content_hash) ||
    authority.shadow_only !== true ||
    [
      "planning_authorized",
      "planning_utility_supported",
      "physiological_adaptation_established",
    ].some((key) => data[key] !== false || authority[key] !== false)
  ) {
    throw new Error("A szerverválasz nem igazol érvényes, tartós mentést.");
  }
  if (resource === "assessments") {
    if (
      !Array.isArray(artifact.endpoint_assessments) ||
      !Array.isArray(artifact.capability_assessments)
    )
      throw new Error("Hiányos értékelés.");
  } else object(artifact.proposal);
  return data as Receipt;
}
export function readPage(
  value: unknown,
  resource: Resource,
  offset: number,
): ArtifactPage {
  const data = object(value);
  if (
    data.identity_scope !== identity ||
    !Array.isArray(data.items) ||
    data.offset !== offset ||
    data.limit !== 25 ||
    data.items.length > 25 ||
    typeof data.has_more !== "boolean" ||
    (data.has_more && data.items.length !== 25)
  )
    throw new Error("Hiányos verziólista.");
  return {
    ...data,
    items: data.items.map((item) => readReceipt(item, resource)),
  } as ArtifactPage;
}
export function readCatalog(value: unknown): Catalog {
  const data = object(value);
  if (
    data.catalog_version !== "capability-measurement-catalog-v0.1" ||
    typeof data.catalog_content_hash !== "string" ||
    !/^[0-9a-f]{64}$/.test(data.catalog_content_hash) ||
    !Array.isArray(data.capabilities) ||
    data.capabilities.length !== 13 ||
    !Array.isArray(data.metrics) ||
    data.metrics.length !== 25 ||
    !Array.isArray(data.goal_roles) ||
    data.goal_roles.length !== 4
  )
    throw new Error("Nem támogatott képességkatalógus.");
  return data as Catalog;
}
export function decimal(value: string): string {
  // Preserve the entered decimal digits; never convert training outcomes through JS Number.
  const text = value.trim().replace(",", ".");
  if (text.length > 80 || !/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(text))
    throw new Error("Egyszerű tizedes számot adj meg, ezreselválasztó nélkül.");
  const result = text.includes(".")
    ? text.replace(/0+$/, "").replace(/\.$/, "")
    : text;
  return /^-?0$/.test(result) ? "0" : result;
}
export function utcInput(value: string): string {
  // datetime-local fields on this screen are explicitly UTC, independent of the browser zone/DST.
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value))
    throw new Error("Adj meg teljes UTC időpontot.");
  const full = value.length === 16 ? value + ":00" : value;
  const date = new Date(full + "Z");
  if (
    !Number.isFinite(date.getTime()) ||
    date.toISOString().slice(0, 19) !== full
  )
    throw new Error("Érvénytelen időpont.");
  return date.toISOString();
}
export function toUtcField(value: string): string {
  return new Date(value).toISOString().slice(0, 19);
}
export function lines(value: string): string[] {
  const result = value
    .split(/\r?\n/)
    .map((v) => v.trim())
    .filter(Boolean);
  if (
    !result.length ||
    result.length > 32 ||
    new Set(result).size !== result.length
  )
    throw new Error(
      "Adj meg 1–32 különböző összehasonlíthatósági feltételt, soronként egyet.",
    );
  return result;
}
export type PendingRequest = { resource: Resource; body: string };
export const PENDING_KEY = "paddletrainer.goal-workflow.pending.v1";
export function readPending(text: string): PendingRequest {
  const data = object(JSON.parse(text));
  if (
    !RESOURCES.includes(data.resource as Resource) ||
    typeof data.body !== "string" ||
    new TextEncoder().encode(data.body).length > 1048576
  )
    throw new Error("Hibás függő kérés.");
  object(JSON.parse(data.body));
  return data as PendingRequest;
}
export function prepareRequest(
  resource: Resource,
  proposal: unknown,
): PendingRequest {
  const body = JSON.stringify(proposal);
  if (new TextEncoder().encode(body).length > 1048576)
    throw new Error(
      "A kérés túl nagy; csökkentsd a szöveges leírások hosszát.",
    );
  return { resource, body };
}
