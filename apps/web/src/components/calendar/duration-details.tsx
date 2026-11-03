import Link from "next/link";
import {
  formatDay,
  formatDuration,
  formatNumber,
  localParts,
} from "@/lib/calendar/contracts";
import { estimateLabel, estimateRange } from "@/lib/calendar/duration-estimate";
import type { DurationEstimate } from "@/lib/calendar/duration-estimate";
export default function DurationDetails({
  estimate,
  zone,
}: {
  estimate: DurationEstimate;
  zone: string;
}) {
  return (
    <section className="pt-duration-estimate" aria-label="Naptári időbecslés">
      <h3>Naptári időbecslés · {estimateLabel(estimate)}</h3>
      <p>
        Tájékozódási tartomány: <strong>{estimateRange(estimate)}</strong>.{" "}
        {estimate.sample_count} saját, azonos sportágú
        {estimate.method === "personal_similar_distance_median_v1"
          ? ", hasonló távú"
          : ""}{" "}
        megfigyelésből.
      </p>
      {estimate.method === "personal_power_law_median_v1" && (
        <>
          <p>
            {estimate.extrapolated
              ? "A megfigyelt távokon túli becslés."
              : "A megfigyelt távtartományba illesztett becslés."}{" "}
            Távduplázáskor a kétszeres időn felül{" "}
            {estimate.doubling_slowdown_pct}% többlettel számolunk.
          </p>
          <p>
            {estimate.coefficient_source === "profile_setting"
              ? "A felmérésben megadott saját feltételezésedet használjuk."
              : "Az 5% kezdeti tervezési feltételezés."}{" "}
            A körülmények és a terhelés összehasonlíthatósága nincs igazolva. A
            tartomány tájékozódási sáv; az egyéni pontossága még nincs
            visszamérve.
          </p>
          <Link href="/athlete-setup">
            Becslési beállítás módosítása a felmérésben
          </Link>
        </>
      )}
      <p className="pt-notice">
        A tempó, a pihenők és a körülmények módosíthatják az időtartamot. A
        forrásban külön tervezett idő nincs megadva.
      </p>
      <details>
        <summary>A becslés alapjául vizsgált előzmények</summary>
        <ul>
          {estimate.samples.map((s) => (
            <li key={s.session_id}>
              <Link href={`/sessions/${s.session_id}`}>
                {formatDay(localParts(s.started_at, zone).date)}
              </Link>
              {" · "}
              {formatNumber(s.distance_m / 1000, "km", 2)} ·{" "}
              {formatDuration(s.elapsed_sec)}
              {s.basis === "elapsed"
                ? " · eltelt idő"
                : " · rögzített időtartam"}
              {!s.used ? " · eltérő időtartam, a becslésből kihagyva" : ""}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
