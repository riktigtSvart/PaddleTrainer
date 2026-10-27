"use client";
import { useState } from "react";
import type { Block, Plan, SectionRow, Sections } from "@/lib/session-analysis/contracts";
import { clock } from "@/lib/session-analysis/chart-data";
import { axisNumber, speedValue } from "@/lib/session-analysis/presentation";
import type { SpeedUnit } from "@/lib/session-analysis/presentation";

const number = (v: number | null, unit: string) => v === null ? "Nincs adat" : axisNumber(v) + " " + unit;
const duration = (v: number | null) => v === null ? "Nincs adat" : clock(v * 1000);
function totalTimes(rows: SectionRow[]) {
  const result: (number | null)[] = []; let total: number | null = 0;
  for (const row of rows) {
    total = total !== null && row.duration_sec !== null && Number.isFinite(total + row.duration_sec) ? total + row.duration_sec : null;
    result.push(total);
  }
  return result;
}
function planOrder(blocks: Block[]) {
  const ordered: { block: Block; depth: number; unresolved: boolean }[] = [], visited = new Set<string>();
  function visit(parent: string | null, depth: number) {
    if (depth > 64) return;
    for (const block of blocks.filter(b => b.parent_block_id === parent).sort((a, b) => a.position - b.position)) {
      if (visited.has(block.id)) continue;
      visited.add(block.id); ordered.push({ block, depth, unresolved: false }); visit(block.id, depth + 1);
    }
  }
  visit(null, 0);
  for (const block of blocks) if (!visited.has(block.id)) ordered.push({ block, depth: 0, unresolved: true });
  return ordered;
}
export function SessionSections({ source, plan, speedUnit }: { source: Sections | undefined; plan: Plan | null; speedUnit: SpeedUnit }) {
  const groups = source?.groups.filter(g => g.rows.length > 0) ?? [];
  const overview = groups.find(g => g.kind === "exercises");
  const preferred = overview && overview.rows.length > 1 ? overview : groups.find(g => g.kind === "manual_laps") ?? groups.find(g => g.kind === "automatic_laps") ?? overview;
  const [groupId, setGroupId] = useState(preferred?.id ?? "");
  const group = groups.find(g => g.id === groupId) ?? preferred;
  const labels = { exercises: "Edzésrészek", manual_laps: "Rögzített körök", automatic_laps: "Automatikus körök" };
  const totals = totalTimes(group?.rows ?? []);
  return <section className="pt-analysis-card pt-section-summary" aria-label="Edzés szakaszai">
    <h2>Szakaszok és részidők</h2>
    {groups.length > 1 && <label className="pt-pulse-target">Szakaszbontás<select value={group?.id ?? ""} onChange={e => setGroupId(e.target.value)}>
      {groups.map(g => <option key={g.id} value={g.id}>{labels[g.kind]}{g.exercise_index === null ? "" : ` · ${g.exercise_index + 1}. edzésrész`}</option>)}
    </select></label>}
    {group ? <><div className="pt-analysis-table"><table>
      <caption>{labels[group.kind]} · szolgáltatói sorrend, az eredeti szakaszátlagokkal</caption>
      <thead><tr><th>Szakasz</th><th>Szakasz távja</th><th>Átlagpulzus</th><th>Átlagsebesség</th><th>Szakaszidő</th><th>Idő összesen</th>
        {group.rows.some(r => r.avg_power !== null) && <th>Átlagteljesítmény</th>}</tr></thead>
      <tbody>{group.rows.map((row, index) => {
        return <tr key={row.id}><th>{row.position + 1}.</th><td>{number(row.distance_m === null ? null : row.distance_m / 1000, "km")}</td>
          <td>{number(row.avg_hr, "bpm")}</td><td>{number(row.avg_speed === null ? null : speedValue(row.avg_speed, speedUnit), speedUnit)}</td>
          <td>{duration(row.duration_sec)}</td><td>{duration(totals[index])}</td>
          {group.rows.some(r => r.avg_power !== null) && <td>{number(row.avg_power, "W")}</td>}</tr>;
      })}</tbody></table></div>
      <details className="pt-zone-source"><summary>Szakaszadatok forrása</summary><p>{group.source_path}</p>
        <p>Az összes idő a szakaszidők összege; nem a szünetekkel együtt eltelt falióraidő. A hiányzó átlag nem a teljes edzés átlagából készül.</p>
        {group.rows.flatMap(row => row.issues).map((issue, i) => <p key={i}>{issue}</p>)}</details>
    </> : <p className="pt-notice">Még nincs tárolt szakaszbontás. A felső Polar-szinkronizálás a körök részletes adatait is lekéri.</p>}
    {plan && plan.blocks.length > 0 && <details className="pt-section-plan"><summary>Tervezett szakaszok · {plan.blocks.length} blokk</summary>
      <div className="pt-analysis-table"><table><thead><tr><th>Szakasz</th><th>Táv</th><th>Időtartam</th><th>Ismétlés</th><th>Cél</th></tr></thead>
        <tbody>{planOrder(plan.blocks).map(({ block: b, depth, unresolved }) => <tr key={b.id}>
          <th>{unresolved ? "Sorrend nem igazolt · " : depth ? "↳ " : ""}{b.name || (b.block_type === "REPEAT" ? "Ismétlési csoport" : b.block_type)}</th><td>{b.block_type === "REPEAT" ? "Alszakaszok szerint" : number(b.distance_m === null ? null : b.distance_m / 1000, "km")}</td>
          <td>{b.block_type === "REPEAT" ? "Alszakaszok szerint" : duration(b.duration_sec)}</td><td>{b.repeat_count === null ? "Nincs adat" : `${b.repeat_count}×`}</td><td>{b.block_type === "REPEAT" ? "Az alárendelt részek egymás után" : b.intensity_type ?? "Nincs megadva"}{b.intensity_min !== null ? ` · ${axisNumber(b.intensity_min)}` : ""}{b.intensity_max !== null ? `–${axisNumber(b.intensity_max)}` : ""}</td>
        </tr>)}</tbody></table></div><p className="pt-notice">A tervezett blokkok és a rögzített körök egyezése nincs igazolva. A tervből nem készül kitalált teljesített szakaszátlag.</p>
    </details>}
    {source?.issues.length ? <p className="pt-notice">Néhány forrásbeli szakaszadat nem értelmezhető: {source.issues.join(" · ")}</p> : null}
  </section>;
}
