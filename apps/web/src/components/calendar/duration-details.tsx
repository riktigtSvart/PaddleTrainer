import Link from "next/link";
import { formatDay, formatDuration, formatNumber, localParts } from "@/lib/calendar/contracts";
import { estimateLabel, estimateRange } from "@/lib/calendar/duration-estimate";
import type { DurationEstimate } from "@/lib/calendar/duration-estimate";
export default function DurationDetails({ estimate, zone }: { estimate: DurationEstimate; zone: string }) {
  return <section className="pt-duration-estimate" aria-label="Naptári időbecslés">
    <h3>Naptári időbecslés · {estimateLabel(estimate)}</h3>
    <p>Tájékozódási tartomány: <strong>{estimateRange(estimate)}</strong>. {estimate.sample_count} saját, azonos sportágú, hasonló távú megfigyelésből.</p>
    <p className="pt-notice">A tempó, a pihenők és a körülmények módosíthatják az időtartamot. A forrásban külön tervezett idő nincs megadva.</p>
    <details><summary>A becslés alapjául vizsgált előzmények</summary><ul>{estimate.samples.map((s) => <li key={s.session_id}>
      <Link href={`/sessions/${s.session_id}`}>{formatDay(localParts(s.started_at, zone).date)}</Link>{" · "}{formatNumber(s.distance_m / 1000, "km", 2)} · {formatDuration(s.elapsed_sec)}
      {s.basis === "elapsed" ? " · eltelt idő" : " · rögzített időtartam"}{!s.used ? " · eltérő időtartam, a becslésből kihagyva" : ""}
    </li>)}</ul></details>
  </section>;
}
