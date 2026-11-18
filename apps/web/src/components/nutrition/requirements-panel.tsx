'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { civilDay } from '@/lib/nutrition/contracts';
import { NUTRITION_CHANGED, nutritionChangeKey } from '@/lib/nutrition/events';
import { loadRequirements, nutrientDetails } from '@/lib/nutrition/requirements';
import type { DayRequirements, Nutrient, Requirements } from '@/lib/nutrition/requirements';
import { LOCAL_REFRESH_EVENT } from '@/lib/data-connections/preferences';

const numbers = new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 3 });
const dates = new Intl.DateTimeFormat('hu-HU', { month: 'short', day: 'numeric', weekday: 'short', timeZone: 'UTC' });
const displayDay = (day: string) => dates.format(new Date(day + 'T12:00:00Z'));
const number = (value: string) => numbers.format(Number(value));
const rangeLabel = ([low, high]: [string, string]) => low === high ? number(low) : `${number(low)}–${number(high)}`;

const sourceLabel = {
  efsa: 'EFSA felnőtt referencia', sport: 'Sporttáplálkozási referencia',
  sport_strength: 'Erőfejlesztéshez használt referencia', energy_model: 'Súlytartási becslés',
} as const;

function referenceLabel(r: NonNullable<DayRequirements['references'][Nutrient]>, unit: string) {
  if (r.minimum !== null && r.maximum !== null) return `${rangeLabel([r.minimum, r.maximum])} ${unit}`;
  if (r.minimum !== null) return `${r.source === 'assessment' ? 'Legalább ' : ''}${number(r.minimum)} ${unit}`;
  return `Legfeljebb ${number(r.maximum!)} ${unit}`;
}

function IntakeAmount({ value, unit }: { value: DayRequirements['planned']['amounts'][Nutrient]; unit: string }) {
  return value.amount === null ? <span className="pt-muted">Nincs adat</span> :
    <>{number(value.amount)} {unit}{value.partial && <small className="pt-muted"> · részösszeg</small>}</>;
}

function NutrientTable({ day, items }: { day: DayRequirements; items: Nutrient[] }) {
  return <div className="pt-meal-table-scroll">
    <table className="pt-meal-shopping pt-nutrient-table">
      <thead><tr><th scope="col">Tápanyag</th><th scope="col">Napi referencia</th><th scope="col">Tervezett bevitel</th><th scope="col">Naplózott bevitel</th></tr></thead>
      <tbody>{items.map(key => {
        const [label, unit] = nutrientDetails[key], r = day.references[key];
        return <tr key={key}>
          <th scope="row">{label}</th>
          <td>{r ? <>{referenceLabel(r, unit)} <small className="pt-muted">
            {r.source === 'assessment' ? `${r.source_name} · ${r.scope === 'total_intake' ? 'teljes bevitel' : 'ételekből'}` : sourceLabel[r.source]}
          </small></> : <span className="pt-muted">Nincs referencia</span>}</td>
          <td><IntakeAmount value={day.planned.amounts[key]} unit={unit} /></td>
          <td><IntakeAmount value={day.logged.amounts[key]} unit={unit} /></td>
        </tr>;
      })}</tbody>
    </table>
  </div>;
}

const bodyGoals = { weight_loss: 'Fogyás', weight_gain: 'Súlygyarapodás', weight_maintenance: 'Súlytartás', recomposition: 'Testösszetétel változtatása' };
const muscleGoals = { maintain: 'Izomtömeg megtartása', gain: 'Izomtömeg növelése' };
const performanceGoals = { strength: 'Erőfejlesztés', endurance: 'Állóképesség-fejlesztés', wellbeing: 'Jó közérzet' };
const fields = { adult_age: 'felnőtt kor a születési dátumból', sex_reference: 'a képlet szerinti nemi referencia', height: 'dátummal rögzített magasság', body_mass: 'dátummal rögzített testsúly' };

export default function RequirementsPanel({ owner, today, start, end }: {
  owner: string; today: string; start: string; end: string;
}) {
  const [saved, setSaved] = useState<Requirements | null>(null);
  const [selected, setSelected] = useState('');
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const changed = (event: Event) => {
      if ((event as CustomEvent).detail?.owner === owner) setReload(n => n + 1);
    };
    const stored = (event: StorageEvent) => {
      if (event.key === nutritionChangeKey(owner)) setReload(n => n + 1);
    };
    const refresh = () => setReload(n => n + 1);
    window.addEventListener(NUTRITION_CHANGED, changed);
    window.addEventListener('storage', stored);
    window.addEventListener(LOCAL_REFRESH_EVENT, refresh);
    return () => {
      window.removeEventListener(NUTRITION_CHANGED, changed);
      window.removeEventListener('storage', stored);
      window.removeEventListener(LOCAL_REFRESH_EVENT, refresh);
    };
  }, [owner]);
  useEffect(() => {
    const abort = new AbortController();
    const timer = setTimeout(() => {
      setError('A tápanyagszámítás túl sokáig tartott.');
      abort.abort();
    }, 15000);
    void loadRequirements(owner, start, end, abort.signal).then(result => {
      if (!abort.signal.aborted) {
        setSaved(result);
        setError('');
      }
    }).catch(() => {
      if (!abort.signal.aborted) setError('A tápanyagszámítás most nem érhető el.');
    }).finally(() => clearTimeout(timer));
    return () => { clearTimeout(timer); abort.abort(); };
  }, [owner, start, end, reload]);

  const result = saved?.athlete_id === owner && saved.start_date === start && saved.end_date === end ? saved : null;
  const day = result?.days.find(d => d.date === selected) ?? result?.days.find(d => d.date === today) ?? result?.days[0];
  const goals = result ? [
    result.body_goal && bodyGoals[result.body_goal],
    result.muscle_goal !== 'unspecified' && muscleGoals[result.muscle_goal],
    result.performance_goal !== 'unspecified' && performanceGoals[result.performance_goal],
  ].filter(Boolean) : [];
  const all = Object.keys(nutrientDetails) as Nutrient[];

  return <section className="pt-meal-controls pt-requirements" id="nutrient-requirements" aria-labelledby="nutrient-heading" data-app-release="C21.15">
    <div className="pt-meal-summary">
      <div><h2 id="nutrient-heading">Napi energia- és tápanyagigény</h2><p>Saját adagok a mentett étrendből és az étkezési naplóból.</p></div>
      {day && result && result.days.length > 1 && <label>Nap<select value={day.date} onChange={event => setSelected(event.target.value)}>
        {result.days.map(d => <option key={d.date} value={d.date}>{displayDay(d.date)}</option>)}
      </select></label>}
    </div>
    {error && <p className="pt-warning" role="status">{error} <button className="pt-button" type="button" onClick={() => { setError(''); setReload(n => n + 1); }}>Újrapróbálás</button></p>}
    {!day && !error && <p role="status">A napi értékek betöltése…</p>}
    {day && <>
      {goals.length > 0 && <p className="pt-meal-note">Mentett célok · {goals.join(' · ')}</p>}
      <dl className="pt-requirements-metrics">
        <div><dt>Súlytartási energia, becslés</dt><dd>{day.maintenance_kcal ? `${rangeLabel(day.maintenance_kcal)} kcal` : 'Nincs teljes becslés'}</dd></div>
        <div><dt>Edzés nélküli napi alap</dt><dd>{day.baseline_kcal !== null ? `${number(day.baseline_kcal)} kcal` : 'Nincs adat'}</dd></div>
        <div><dt>Edzés becsült többlete</dt><dd>{day.workouts.extra_kcal ? `+${rangeLabel(day.workouts.extra_kcal)} kcal` : 'Nincs adat'}</dd></div>
      </dl>
      <p className="pt-meal-note">{day.workouts.recorded} rögzített és {day.workouts.planned} tervezett edzés.
        {day.workouts.unestimated > 0 && ` ${day.workouts.unestimated} edzés többletéhez hiányzik megfelelő adat vagy sportági referencia.`}
        {day.body_mass_on && ` A testsúlymérés dátuma ${day.body_mass_on}.`}
      </p>
      {day.missing_profile.length > 0 && <p className="pt-meal-note">
        A felnőtt energiabecsléshez szükséges adat · {day.missing_profile.map(key => fields[key]).join(', ')}. <Link href="/athlete-setup">Személyes alapadatok</Link>
      </p>}
      {day.logged.unquantified > 0 && <p className="pt-meal-note">{day.logged.unquantified} naplózott ételhez még nincs számítható adag vagy összetétel.</p>}
      <NutrientTable day={day} items={all.slice(0, 5)} />
      <details className="pt-meal-method">
        <summary>Vitaminok, ásványi anyagok és nyomelemek</summary>
        <NutrientTable day={day} items={all.slice(5)} />
        <p>A vas- és cinktartomány több EFSA-referenciaértéket fog át. A D-vitamin értéke minimális bőrben történő képződésre vonatkozik. A részösszeg a rendelkezésre álló összetételi adatokból készül.</p>
      </details>
      <details className="pt-meal-method">
        <summary>A számítás alapja</summary>
        <p>A napi alap egy kevés hétköznapi aktivitással számoló felnőtt súlytartási becslés. Ehhez adódik az edzés sportágból és időtartamból becsült nettó többlete. A makrótartományok tájékozódási értékek. A mentett, az adott napon érvényes személyes tápanyagcél megjelenik a táblázatban a forrásával együtt.</p>
        <p>Források · <a href="https://www.nationalacademies.org/read/26818/chapter/18">NASEM energiaegyenletek</a> · <a href="https://pacompendium.com/">Compendium of Physical Activities</a> · <a href="https://doi.org/10.1249/MSS.0000000000000852">Sporttáplálkozási állásfoglalás</a> · <a href="https://www.efsa.europa.eu/en/topics/topic/dietary-reference-values">EFSA referenciaértékek</a> · <a href="https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid">CoFID 2021</a> · <a href="https://fdc.nal.usda.gov/download-datasets">USDA FoodData Central</a></p>
      </details>
    </>}
  </section>;
}

export function SavedRequirements({ owner, today, plan }: {
  owner: string; today: string; plan?: { start_date: string; day_count: number } | null;
}) {
  const start = plan?.start_date ?? today;
  const end = plan ? civilDay(start, plan.day_count - 1) : today;
  return <RequirementsPanel owner={owner} today={today} start={start} end={end} />;
}
