import { canonical } from "@/lib/planning-cycles/contracts";
import { sourceBody } from "@/lib/initial-assessment/contracts";
import type { Context } from "@/lib/initial-assessment/contracts";
export function registryExtension(c: Context): boolean {
  if (!c.sources_changed || !c.saved) return false;
  const before = c.saved.artifact.snapshot, after = c.sources;
  if (before.registry.content_hash === after.registry.content_hash) return false;
  const left = { ...sourceBody(before) }, right = { ...sourceBody(after) };
  delete (left as Partial<typeof left>).registry_hash;
  delete (right as Partial<typeof right>).registry_hash;
  if (canonical(left) !== canonical(right)) return false;
  const { version: av, content_hash: ah, patterns: ap, sports: as, ...am } = before.registry;
  const { version: bv, content_hash: bh, patterns: bp, sports: bs, ...bm } = after.registry;
  void av; void ah; void bv; void bh;
  if (canonical(am) !== canonical(bm) || as.some((v) => !bs.some((w) => canonical(v) === canonical(w)))) return false;
  return ap.every((p) => { const q = bp.find((v) => v.key === p.key); return q && p.label === q.label && p.exercise_ids.every((id) => q.exercise_ids.includes(id)); });
}
