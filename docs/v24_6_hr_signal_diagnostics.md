# V24.6 — A rögzített pulzusjel leíró diagnosztikája

A V24.6 megmutatja az érvénytelen/hiányzó HR-minták, az ismétlődő pozitív
értékek és a legnagyobb szomszédos változások helyét. A nyers mintasor
változatlan marad. A mintázatok nem igazolnak fiziológiai hihetőséget,
mérési pontosságot vagy műterméket; a minőség és a modellhasználat
engedélyezési jelzői továbbra is `false` értékűek.

## Olvasási API

```text
GET /api/v1/integrations/polar/sessions/{session_external_id}/hr-diagnostics
    ?sample_date=YYYY-MM-DD&detail_limit=25
```

Az API a bejelentkezett alkalmazásfelhasználó Polar-kapcsolatát és
`training_sessions:read` jogosultságát használja. Csak az adott munkamenet
aktuálisan lekért teljes API-forrásához, sportolóhoz és gyakorlathoz illeszkedő
mentett időalapot és szenzornyilatkozatot alkalmazza. Nincs POST, feltöltés,
új adatbázistábla, diagnosztikai mentés vagy új migráció.

Az `input_provenance` a sportoló azonosítóját, a `POLAR` forrásszolgáltatót,
a teljes aktuális API-forrás hash-ét és a változatlan nyers HR-validátor
döntési hash-ét tartalmazza. A diagnosztikai döntés sportolóhoz kötött akkor is,
ha nincs mentett export vagy szenzornyilatkozat.

A `sample_date` kötelező. A `detail_limit` 1–100 közötti egész, alapértéke 25.
A teljes elfogadott sorozatot elemezzük; csak az eseménylisták hossza korlátos.
Minden listához `assessed`, `total_count`, `returned_count`, `truncated` és
`selection` tartozik. Legfeljebb 64 gyakorlat és összesen 100 000 HR-mintahely
fogadható el; túllépéskor a státusz `WITHHELD`, az ok
`HR_DIAGNOSTICS_SOURCE_LIMIT_EXCEEDED`. Ez erőforráskorlát.

## Megfigyelések

| Mező | Meghatározás | Sorrend |
|---|---|---|
| `invalid_runs` | Egymást követő, nem pozitív véges számként rögzített mintahelyek; a kategóriák külön számlálódnak. | Első előfordulás. |
| `constant_runs` | Legalább két szomszédos, pozitív véges, pontosan egyenlő rögzített érték. | Hossz szerint csökkenő, majd első mintaindex. |
| `largest_adjacent_changes` | Két szomszédos pozitív véges érték nem nulla különbsége; hiány fölött nem számítunk változást. | Abszolút különbség szerint csökkenő, majd első mintaindex. |

Az érvénytelen kategóriák a változatlan V24.2 validátorból származnak:
`MISSING`, `BOOLEAN`, `NON_NUMERIC`, `NON_FINITE`, `ZERO`, `NEGATIVE`.
Nem kanonizálható teljes forrásnál — például nem véges JSON-számnál — a
forrásigazolás visszatartja a diagnosztikát. Az üres vagy többértelmű sorozatot
nem helyettesítjük becsült adatokkal.

Az állandó sorozat kétmintás minimuma a mintázat definíciója. Nincs
fiziológiai HR-határérték, változási küszöb, automatikus hibacímke,
interpoláció vagy mintatörlés. A `physiological_plausibility_status` és az
`artifact_status` értéke `NOT_ASSESSED`. A bpm-különbség a rögzített adatok
leíró statisztikája, nem modell-előrejelzés.

## Hely és idő

Az indexek nullától indulnak; a `start_sample_index` beleértendő,
az `end_sample_index_exclusive` kizáró felső határ.

| Mező | Jelentés |
|---|---|
| `nominal_first_sample_offset_ms`, `nominal_last_sample_offset_ms` | Az első HR-mintahelytől számított relatív pozíció a közölt mintaperiódus alapján; nem edzéskezdethez kötött idő. |
| `sample_span_ms` | Az első és utolsó mintahely névleges távolsága: `(N−1) × periódus`. |
| `nominal_slot_occupancy_ms` | `N × periódus`; nem megfigyelt időtartam. |
| `first_sample_timestamp_utc`, `last_sample_timestamp_utc` | A mentett, aktuális forráshoz igazolt export tényleges időbélyegei; igazolás nélkül `null`. |
| `first_sample_offset_from_exercise_start_us`, `last_sample_offset_from_exercise_start_us` | Gyakorlatkezdethez kötött pozíció, csak igazolt exportból, egész mikroszekundumban. |

Az igazolt időalap státusza `VERIFIED_SAVED_EXPORT_TIMEBASE`.
Igazolás nélkül `NOMINAL_SAMPLE_GRID_ONLY`, `time_mapping_available=false`.
Nem feltételezzük, hogy az első HR-minta az edzés kezdetén keletkezett.
Hibás mintaperiódus mellett a mintaindex megmarad, a névleges idő és a
periódus alapján számított változási sebesség `null`.

Az exportigazolás nem bizonyítja a Polar API natív mintavételi órájának vagy
a szünetkezelésnek a szemantikáját. Más gyakorlathoz vagy sportolóhoz nem
terjed át az eltolás. Megváltozott forrás, sérült vagy ellentmondó igazolás
nem adhat UTC-időbélyeget.

## Szenzor és audit

Az `acquisition_context` a V24.5 mentett nyilatkozatának forrását,
azonosítóit, megadott szenzoradatait és jelzett problémáit mutatja.
`USER_DECLARATION` mellett a szenzorazonosság és a minőség továbbra sem
ellenőrzött. A termék neve nem válik automatikusan HR-szenzorazonosítássá.

Az útvonal-inspection munkamenetenként új
`heart_rate_signal_diagnostics` mezőt ad vissza. Az audit verziója `0.4.0`:

- `diagnostics_available_route_count`: illesztett diagnosztikával rendelkező útvonalak.
- `diagnostics_verified_clock_route_count`: igazolt exportórával illesztett diagnosztikák.
- `hr_signal_diagnostics_evidence`: forrás, verzió, döntési hash és korlátok.
- `routes[].hr_signal_diagnostics`: gyakorlatösszegzés és korlátos ablaklista.
- A belső teljes audit `segments[].hr_signal_diagnostics` mezője az adott szakasz megfigyeléseit tartalmazza.

Szakaszhoz kötött új diagnosztikai mintaszám és időbélyeg csak igazolt
exportórával keletkezik. Az ablak `[kezdet, vég)` alakú. Egész
mikroszekundumokkal számolunk, az eredeti exporteltolást nem kerekítjük
milliszekundumra. A szomszédos párok mindkét tagjának az ablakon belül kell
lennie. A megfigyelt mintasor utáni névleges rácshelyek külön
`unrecorded_grid_slot_count` értékként jelennek meg.

A szakaszstátuszok: `COMPLETE_WITH_LIMITATIONS`, `PARTIAL_WITH_LIMITATIONS`,
`NO_GRID_SLOTS`, `NO_POSITIVE_FINITE_SAMPLES`, `TIMEBASE_NOT_VERIFIED`,
`SOURCE_NOT_APPLIED`, `INVALID_WINDOW`. Az összegzés az első 25, lefedettség
szempontjából áttekintendő ablakot mutatja; a teljes szám külön szerepel.
A prefixszámlálók útvonalanként egyszer épülnek fel.

A korábbi jelöltképzés és jogosultsági szabályok változatlanok. A diagnosztika
nem oldja fel a környezeti, upstream modell-, időalap- vagy adatminőségi
blokkolókat. A V24.2 nyers validátor, a TCX-igazolás, a mentett snapshotok
és a szenzornyilatkozatok formátuma és tárolása változatlan.

## Ellenőrzés

A három új tesztmodul a lokalizálást, listakorlátokat, pontos ablakhatárokat,
forrásváltozást, sportolói elkülönítést, sérült/ellentmondó igazolásokat,
adatbázis-írásmentes GET-et és a korábbi auditkapuk megtartását ellenőrzi.
Az API-tesztek valódi SQLite ORM-tárolást és FastAPI TestClientet használnak.
Az adatbázis-head továbbra is `c5e83a9d2714`.

## Elsődleges háttérforrások

- [Polar API v4](https://www.polar.com/polar-api-v4/): az `IntervalValues` közölt típusa, periódusa és értéksorozata.
- [Polar: wrist-based heart rate measurement](https://support.polar.com/en/support/the_what_and_how_of_polars_wrist_based_heart_rate_measurement): mérési körülmények és mozgás hatása; ebből nem vezetünk le műtermék-küszöböt.
