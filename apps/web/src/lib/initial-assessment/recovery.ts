import { canonical, object } from "@/lib/planning-cycles/contracts";
import { emptyData, readAssessmentReceipt, readPending } from "./contracts";
import type { AssessmentReceipt, Context, Data, Pending, Proposal, Ref } from "./contracts";
import { mergeAssessmentAnswers, restoreAssessmentDraft } from "./draft-sync";

export function assessmentToken(owner: string, reference: Ref): string {
  const prefix = `pt-initial-assessment:${owner.replaceAll("-", "")}:`;
  const hex = reference.artifact_id.startsWith(prefix) ? reference.artifact_id.slice(prefix.length) : "";
  if (!/^[a-f0-9]{32}$/.test(hex)) throw Error("A korábbi felmérés nem ehhez a sportolóhoz tartozik.");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// Only reads are allowed here. A missing or unreadable receipt is never evidence
// that a pending write succeeded; its exact bytes must remain available for retry.
export async function recoverAssessment(
  context: Context,
  rawDraft: string | null,
  rawPending: string | null,
  readRevision: (token: string) => Promise<AssessmentReceipt | null>,
) {
  const owner = context.athlete_id;
  const issues: string[] = [];
  let pending: Pending | null = null;
  let draftPendingId: string | null = null;
  let restored: ReturnType<typeof restoreAssessmentDraft> | null = null;
  if (rawPending) try { pending = readPending(rawPending, owner); }
  catch { issues.push("A korábbi helyi mentési kérés nem ellenőrizhető. Az eredetijét külön megőrizzük; javított új mentés készíthető."); }
  if (rawDraft) try { restored = restoreAssessmentDraft(rawDraft, owner, context.data, context.local_today); }
  catch { issues.push("A helyi piszkozatot nem sikerült teljes egészében beolvasni. Az eredetijét külön megőrizzük."); }
  // A legacy frozen request can contain the newest answers even when its review
  // date is older than its observations. Recover only its owned, fully validated
  // answer data as a NEW draft; never modify or submit the original frozen body.
  if (rawPending && !pending) try {
    const envelope = object(JSON.parse(rawPending));
    if (envelope.owner !== owner || envelope.version !== "initial-assessment-pending-v0.1" || typeof envelope.body !== "string") throw Error();
    const body = object(JSON.parse(envelope.body));
    if (typeof body.request_id !== "string" || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(body.request_id)) throw Error();
    const frozen = restoreAssessmentDraft(JSON.stringify({
      version: "initial-assessment-draft-v0.1", owner, source_hash: body.source_hash,
      previous_reference: body.previous_reference, data: body.data, open: restored?.draft.open ?? 5,
    }), owner, context.data, context.local_today);
    draftPendingId = body.request_id;
    if (!restored || restored.draft.pending_request_id !== body.request_id) restored = frozen;
  } catch { /* Unverified data stays in the recovery copy, never in the editor. */ }
  const proposal: Proposal | null = pending ? JSON.parse(pending.body) : null;
  let committed: AssessmentReceipt | null = null;
  let checkFailure = "";
  const cache = new Map<string, AssessmentReceipt>();
  if (context.saved) cache.set(context.saved.artifact.proposal.request_id, context.saved);
  async function lookup(token: string) {
    const value = cache.get(token) ?? await readRevision(token);
    if (!value) return null;
    const checked = await readAssessmentReceipt(value, owner);
    if (checked.artifact.proposal.request_id !== token) throw Error("Másik felmérés visszaigazolása érkezett.");
    cache.set(token, checked);
    return checked;
  }
  if (pending) {
    try {
      const value = await lookup(proposal!.request_id);
      if (value) committed = await readAssessmentReceipt(value, owner, pending.body);
    } catch {
      checkFailure = "A korábbi mentés visszaigazolása még nem ellenőrizhető. Az eredeti kérés megmaradt; az ellenőrzőgombbal folytatható.";
    }
  }
  // Older versions locked the editor during a pending save. Their draft could
  // lag behind the frozen request. Only a draft explicitly linked to that
  // pending request can contain edits made after freezing it.
  let editable = restored && (!pending || restored.draft.pending_request_id === proposal!.request_id) ? restored : null;
  if (pending && restored && !editable && canonical(restored.draft.data) !== canonical(proposal!.data)) {
    let before: Data | null = null;
    const previous = restored.draft.previous_reference;
    if (canonical(previous) === canonical(context.reference)) before = context.data;
    else if (previous) try {
      const r = await lookup(assessmentToken(owner, previous));
      if (r?.artifact.content_hash === previous.content_hash) before = r.artifact.proposal.data;
    } catch { /* A conservative merge keeps both observations for review. */ }
    editable = { ...restored, draft: { ...restored.draft,
      data: mergeAssessmentAnswers(before, restored.draft.data, proposal!.data) } };
    issues.push("A helyi válaszok és a korábbi mentési kérés eltérnek. Mindkettő eredményeit megőrizzük; az összegzést újra át kell nézni.");
  }
  let data: Data = editable?.draft.data ?? proposal?.data ?? context.data ?? emptyData(context);
  let sourceHash = editable?.draft.source_hash ?? proposal?.source_hash ?? context.saved?.artifact.proposal.source_hash ?? context.sources.source_hash;
  let parent: Ref | null = editable ? editable.draft.previous_reference : proposal ? proposal.previous_reference : context.reference;
  let base = canonical(parent) === canonical(context.reference) ? context.data : null;
  let rebased = false;
  if (context.data && canonical(parent) !== canonical(context.reference)) {
    // The already committed request is the base of the restored editor, not an
    // unfinished edit to reapply over a newer guided result.
    if (committed && (!editable || canonical(parent) === canonical(committed.artifact.proposal.previous_reference) || parent?.artifact_id === committed.artifact.artifact_id)) {
      base = committed.artifact.proposal.data;
    } else if (parent) {
      try {
        const previous = await lookup(assessmentToken(owner, parent));
        if (!previous || previous.artifact.content_hash !== parent.content_hash) throw Error();
        base = previous.artifact.proposal.data;
      } catch {
        issues.push("A piszkozat korábbi mentési alapja nem ellenőrizhető. Az eltérő eredmények megmaradnak; az új mentés előtt át kell nézni őket.");
        base = null;
      }
    } else base = emptyData(context);
    data = mergeAssessmentAnswers(base, data, context.data);
    if (canonical(data) !== canonical(context.data)) data = { ...data, reviewed: false };
    parent = context.reference; sourceHash = context.saved!.artifact.proposal.source_hash; base = context.data;
    rebased = true;
  }
  if (editable?.recovered || issues.length) data = { ...data, reviewed: false };
  return { data, sourceHash, parent, base, step: restored?.draft.open ?? 0, pending: committed ? null : pending, committed, rebased, draftPendingId,
    recovered: editable?.recovered ?? false,
    recoveryRequired: issues.length > 0,
    message: issues.length ? issues.join(" ") + " A mezők szerkeszthetők. A mentés előkészítésével és az összegzés átnézésével folytathatod."
      : pending && !committed ? (checkFailure || "A korábbi mentés még nincs visszaigazolva. Az eredeti kérés az ellenőrzőgombbal folytatható; új kérést nem küldtünk.") + " A mezőket közben szerkesztheted; az új módosításokat külön mentés rögzíti."
      : committed ? "A korábbi mentést a szerver visszaigazolta. A legfrissebb mentett eredmények betöltődtek; a mezők szerkeszthetők."
      : rebased ? "A legfrissebb mentett eredmények betöltődtek. A még mentetlen saját módosításaid megmaradtak."
      : editable?.recovered ? "A korábbi piszkozat dátumütközése rendezve. Az eredmények megmaradtak; nézd át az összegzést, majd ments." : "",
  };
}
