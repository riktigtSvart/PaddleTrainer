import type { Preparation } from "@/lib/guided-strength/contracts";
import type { StrengthCatalog } from "@/lib/training-options/strength-catalog";

const reminders: Record<
  string,
  { steps: string[]; source: string; url: string }
> = {
  barbell_benchpress: {
    steps: [
      "Feküdj stabilan a padra, a talpak támaszkodjanak a talajon. A lapockákat tartsd stabilan, a törzset feszesen.",
      "A rudat a megszokott fogással, kontrolláltan engedd a mellkas irányába, majd egyenletesen nyomd vissza. Ne pattintsd és ne rántsd a súlyt.",
      "A pad és a rúdtartó beállítása, a fogás és a mozgástartomány maradjon azonos az összehasonlítandó sorozatokban. A rúd teljes tömegét, a tárcsákkal együtt rögzítsd.",
    ],
    source: "NASM: Barbell Bench Press",
    url: "https://www.nasm.org/resource-center/exercise-library/barbell-bench-press",
  },
  seal_row_barbell: {
    steps: [
      "Helyezkedj hason a mellhezhúzó padra. A mellkas és a medence támasza maradjon stabil; a rúd mozgatásához legyen szabad hely a pad alatt.",
      "A megszokott fogással húzd a rudat a pad alja, a mellkas vonala felé, majd kontrolláltan engedd vissza. A törzs megemelése vagy láblendítés ne segítse a húzást.",
      "Jegyezd fel a padot, a fogást és a mozgás végpontját. A rúd teljes tömegét, a tárcsákkal együtt rögzítsd; más eszközön mért értékkel ne vond össze.",
    ],
    source: "Ronai és Taber: The Barbell Bench Pull",
    url: "https://digitalcommons.sacredheart.edu/pthms_exscifac/56/",
  },
  squat: {
    steps: [
      "Állj stabil, körülbelül csípőszéles vagy kissé szélesebb terpeszben. A talpak maradjanak a talajon, a törzs legyen kontrollált.",
      "A csípőt és a térdet együtt hajlítva ereszkedj a megszokott, panaszmentes mélységig. A térd kövesse a lábfej irányát, majd egyenletesen állj fel.",
      "Saját testsúlyos végrehajtást rögzíts. Az összehasonlításhoz tartsd meg ugyanazt a mélységet, támaszt és végrehajtást; ne válts közben súlyozott változatra.",
    ],
    source: "ACE: Bodyweight Squat",
    url: "https://www.acefitness.org/resources/everyone/exercise-library/135/bodyweight-squat/",
  },
  hanging_leg_raise: {
    steps: [
      "A már ismert függeszkedő helyzetből, stabil fogással indulj. Lendítés nélkül emeld a lábat, majd kontrolláltan engedd vissza.",
      "A törzs kontrollja és az azonos mozgástartomány fontosabb, mint a magasabb lábemelés vagy a több ismétlés.",
      "A megjegyzésben rögzítsd: bordásfal vagy nyújtó, hajlított vagy nyújtott térd, illetve milyen magasságig emeltél. A különböző változatok eredményeit ne kezeld azonosként.",
    ],
    source:
      "Catalyst Athletics: függeszkedő térdemelés és lábemelés változatai",
    url: "https://www.catalystathletics.com/exercise/490/Knees-To-Elbows/",
  },
};

export function ExerciseInstructions({
  exerciseId,
  catalog,
}: {
  exerciseId: string | null;
  catalog: StrengthCatalog;
}) {
  const exercise = catalog.exercises.find((e) => e.id === exerciseId);
  const reminder = exerciseId ? reminders[exerciseId] : undefined;
  const guide = catalog.guides.find((g) => g.id === exercise?.guide_id);
  return (
    <div className="pt-guided-instructions">
      {reminder ? (
        <>
          <h4>Végrehajtási emlékeztető</h4>
          <ol>
            {reminder.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          <a href={reminder.url} target="_blank" rel="noopener noreferrer">
            {reminder.source}
          </a>
        </>
      ) : (
        <p>
          Ehhez a gyakorlathoz még nincs külön részletes végrehajtási leírás.
          Csak a már ismert, panaszmentes változatodat mérd; azonos beállítással
          és mozgástartománnyal. A használt változatot a megjegyzésben rögzítsd.
        </p>
      )}
      {guide && (
        <p>
          <a href={guide.src} target="_blank" rel="noopener noreferrer">
            Képes segítség: {guide.title}
          </a>
        </p>
      )}
    </div>
  );
}

export default function ProtocolPreview({
  preparation,
  locationId,
  selectedIds,
  catalog,
}: {
  preparation: Preparation;
  locationId: string;
  selectedIds: string[];
  catalog: StrengthCatalog;
}) {
  const place = preparation.locations.find((p) => p.location_id === locationId);
  const selected = selectedIds.flatMap(
    (id) => place?.entries.find((e) => e.entry_id === id) ?? [],
  );
  const p = preparation.protocol;
  return (
    <section className="pt-panel" aria-label="Felmérőalkalom előzetes menete">
      <h3>A felmérőalkalom menete — indítás előtt</h3>
      <p>
        A gyakorlatok a fenti saját kijelölésedből kerülnek az alkalomba, a
        kijelölés sorrendjében.
      </p>
      <ol>
        <li>
          <strong>Bemelegítés:</strong> {p.warmup_minutes[0]}–
          {p.warmup_minutes[1]} perc könnyű, ismert mozgás.
        </li>
        <li>
          <strong>Gyakorlatonként:</strong> legfeljebb {p.max_practice_sets}{" "}
          választható könnyű próbasorozat, {p.practice_repetitions[0]}–
          {p.practice_repetitions[1]} ismétléssel. Utána legalább{" "}
          {p.rest_seconds / 60} perc nyugodt pihenő.
        </li>
        <li>
          <strong>Kiinduló referenciasorozat:</strong> {p.max_reference_sets}{" "}
          könnyű sorozat, {p.reference_repetitions[0]}–
          {p.reference_repetitions[1]} kontrollált ismétléssel; ismert tartás
          esetén {p.reference_hold_seconds[0]}–{p.reference_hold_seconds[1]}{" "}
          másodperc. Maradjon bőven szabályos ismétlés tartalékban. A tényleges
          eredményt írd be.
        </li>
      </ol>
      <p>
        Saját testsúlyos gyakorlatnál a testsúlyod adott: a kiválasztott változatban elvégzett szabályos ismétléseket rögzíted, külön súlyválasztás nélkül.
        Külső súlyos gyakorlatnál ismert, könnyű terhelést használj. Panasz, romló
        kivitelezés vagy túl nagy erőkifejtés esetén állj meg, és ezt rögzítsd.
      </p>
      {selected.length ? (
        selected.map((e, i) => (
          <details key={e.entry_id} open>
            <summary>
              {i + 1}. {e.label}
            </summary>
            <ExerciseInstructions
              exerciseId={e.exercise_id}
              catalog={catalog}
            />
          </details>
        ))
      ) : (
        <p>
          A gyakorlatonkénti leíráshoz válassz gyakorlatot a fenti listából.
        </p>
      )}
      <p>
        <strong>Mit mér ez a lépés?</strong> Gyakorlatonként egy kiinduló
        sorozatot rögzít. Az erőállóképesség, a több egymást követő sorozat
        elviselése és a következő edzésig tartó regeneráció ebből még nem
        állapítható meg. Ezekhez külön, ismételt megfigyelések szükségesek.
      </p>
    </section>
  );
}
