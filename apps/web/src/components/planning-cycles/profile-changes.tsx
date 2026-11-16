import Link from "next/link";
import {profileFieldLabels} from "@/lib/planning-cycles/assessment-profile";
import type {ProfileComparison} from "@/lib/planning-cycles/assessment-profile";

export default function ProfileChanges({value}:{value:ProfileComparison|undefined}) {
  if(!value||(!value.changed_fields.length&&!value.source_reference_changed))return null;
  const other=value.changed_fields.filter(k=>!value.blocking_fields.includes(k));
  return <div className="pt-options-meta" aria-label="Az erőfelméréshez kapcsolódó profilváltozások">
    {!!value.blocking_fields.length&&<><p>Felülvizsgálandó profiladatok:</p><ul>{value.blocking_fields.map(k=><li key={k}>{profileFieldLabels[k]}</li>)}</ul></>}
    {value.source_reference_changed&&!value.blocking_fields.length&&<p>A jelenlegi lényeges értékek egyeznek, de a profil változási előzménye miatt a régi forráshivatkozás nem vehető át automatikusan.</p>}
    {value.reference_reusable&&<p>Ezek a profilfrissítések nem érvénytelenítik a mentett erőreferenciákat. A tervező az aktuális adatokat használja.</p>}
    {!!other.length&&<details><summary>További, az erőreferenciát nem érvénytelenítő profilfrissítések · {other.length}</summary><ul>{other.map(k=><li key={k}>{profileFieldLabels[k]}</li>)}</ul></details>}
    {!value.reference_reusable&&<p><Link href="/strength-assessment">Mentett erőfelmérési válaszok áttekintése →</Link> A felülvizsgálat önmagában nem ír elő új fizikai tesztet.</p>}
  </div>;
}
