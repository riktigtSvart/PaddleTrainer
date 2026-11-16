import { sha } from "@/lib/planning-cycles/contracts";
import { key } from "./contracts";

export type RecoveryInputs = { draft: string | null; pending: string | null };
export type RecoveryBackup = { key: string; payload: string };

// Write and read back a separate immutable copy before replacing a broken
// editor draft. The original pending body is retained as a string, byte for byte.
export async function preserveLocalRecovery(
  storage: Pick<Storage, "getItem" | "setItem">,
  owner: string,
  inputs: RecoveryInputs,
  namespace: "initial-assessment" | "guided-strength" = "initial-assessment",
): Promise<RecoveryBackup> {
  const identity = { owner, ...inputs }, digest = await sha(identity);
  const prefix = namespace === "initial-assessment" ? key(owner, "draft") : `paddletrainer.guided-strength.draft.v1:${owner}`;
  const backupKey = prefix + ":recovery:" + digest;
  const payload = JSON.stringify({ version: namespace + "-recovery-v0.1", ...identity });
  const existing = storage.getItem(backupKey);
  if (existing !== null && existing !== payload) throw Error("A korábbi helyreállítási másolat nem ellenőrizhető.");
  if (existing === null) storage.setItem(backupKey, payload);
  if (storage.getItem(backupKey) !== payload) throw Error("A helyi adatok megőrzését nem sikerült ellenőrizni.");
  return { key: backupKey, payload };
}
export const preserveAssessmentRecovery = (storage: Pick<Storage, "getItem" | "setItem">, owner: string, inputs: RecoveryInputs) =>
  preserveLocalRecovery(storage, owner, inputs);
