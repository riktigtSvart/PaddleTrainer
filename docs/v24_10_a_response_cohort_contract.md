# V24.10-A — több edzés közös bemeneti szerződése

Állapot: a bemeneti séma, annak tisztán formai ellenőrzése és az alábbi
elfogadási feltételek elkészültek. A kohorsz tényleges összeállítása és időrendi
ellenőrzése a következő részek feladata. Új API-végpont, adatbázistábla,
migráció vagy modellillesztés ebben a részben nincs.

Kiinduló Git-commit: `69d2a476302e91401f2ffde44c0cf6c6ff803532` (V24.9).
A migrációs head változatlan: `d83b9c61f204`.

## 1. Modellezési cél és vizsgálati egység

A szerződés egy sportoló több teljes Polar-edzésének, mentett környezeti
pillanatképekre épülő kiválasztását írja le. Az első támogatott feladat:
`RETROSPECTIVE_HR_RESPONSE_WITHIN_ATHLETE`.

Ez az edzés közben megfigyelt mozgás és környezet időrendi előzményeit
feltételként használó későbbi HR-válaszmodell előkészítése. A javasolt értékelési
cél ugyanazon sportoló későbbi edzéseire vonatkozó teljesítmény vizsgálata,
azok utólag megfigyelt bemeneteivel. Ez nem az edzés előtti információkból
történő előrejelzés, és nem más sportolókra igazolt általánosítás.

Az edzés a kiválasztási és besorolási egység: `(provider, athlete_id,
session_external_id)`. Minden gyakorlata, útvonala, megfigyelése, HR-sorozata
és terhelési előzménye ugyanahhoz az egységhez tartozik. Részútvonal vagy
mintatartomány kiválasztását a bemeneti séma nem fogadja el.

A GPS-alapú mozgás és a környezet megfigyelt feltételek; nem nevezzük őket
közvetlen metabolikus terhelésmérésnek. A HR külön célmintasorozat marad.
A kezdeti élettani állapot, a megfigyelés előtti terhelés és a megfigyelés
utáni recovery korlátait a V24.8/V24.9 csomagból meg kell őrizni.

## 2. Bemeneti manifest

Python-séma: `app.schemas.response_cohort.ResponseCohortManifest`.
Publikált JSON Schema: `docs/contracts/response_cohort_manifest_v0_1.schema.json`.

| Gyökérmező | Követelmény |
| --- | --- |
| `schema_version` | Kötelező, `0.1`. |
| `manifest_id` | Kötelező, 1–200 karakteres, szélső szóköz nélküli azonosító. |
| `task` | A fenti támogatott feladat; elhagyáskor ugyanez az alapérték. |
| `members` | Kötelező, 1–100 teljes edzés; ebben a szerződésben egy sportoló. |
| `split_manifest` | Opcionális V24.8-séma, alapértéke `null`. |

Minden taghoz:

| Mező | Szerep |
| --- | --- |
| `provider` | Kötelező, `POLAR`. |
| `athlete_id`, `session_external_id` | Kötelező elvárt tulajdonosi/edzésazonosítók, a meglévő csomagból. A kliens azonosítója nem jogosultságigazolás. |
| `route_date` | Kötelező, valódi `YYYY-MM-DD` dátum, a V24.9 Polar-lekéréséhez; `9999-12-31` nem támogatott. Ez lekérési segédérték, nem hiteles edzéskezdés vagy időrendi bizonyíték. |
| `replay_snapshot_id` | Kötelező, konkrét V24.9 pillanatkép UUID-je. |
| `expected_snapshot_hash` | Kötelező, a kiválasztott pillanatkép elvárt hash-e. |
| `expected_evidence_set_id`, `expected_evidence_hash` | Kötelező, a pillanatképhez tartozó környezeti bizonyíték elvárt azonosítója és hash-e. |
| `expected_unassigned_replay_package_hash` | Kötelező, a teljes, V24.9 `/response-dataset/replay` válasz hash-e, `split_manifest` nélkül, alapértelmezett `UNASSIGNED` besorolással. |
| `expected_dataset_version` | `0.1.0`; elhagyáskor ugyanez az alapérték. |
| `expected_snapshot_schema_version` | `0.1`; elhagyáskor ugyanez az alapérték. |

A SHA-256 értékek 64 kisbetűs hexadecimális karakterből állnak. Az UUID-k
36 karakteres, kisbetűs, kötőjeles alakban adandók meg. Az azonosítók
adatbázisbeli létezését ez a séma nem ellenőrzi.

**A három csomaglenyomat különbözik:**

- A `snapshot_hash` a mentett teljes környezeti bemenethez tartozik.
- A V24.9 listában szereplő `captured_unassigned_package_hash` a capture során
  létrehozott, replay-proveniencia nélküli alapcsomag lenyomata.
- Az itt elvárt `expected_unassigned_replay_package_hash` a tényleges, teljes
  replay-válasz `package_hash` értéke, adatbázis-ellenőrzési provenienciával.

Ezek nem helyettesíthetők egymással. Összefoglaló válaszban megtalálható a
teljes csomag hash-e, de teljes tartalmi ellenőrzéshez a teljes válasz kell.

## 3. Formai és csoportosítási szabályok — elkészültek

- Egy manifest egy sportolót és 1–100 különböző teljes edzést választ.
- Egy edzés nem szerepelhet kétszer, eltérő pillanatképpel sem.
- Egy pillanatkép-azonosító nem választhat két eltérő edzést.
- Opcionális besorolás csak a kiválasztott edzéseket érintheti. A V24.8
  manifest korábbi, más csoportokat is tartalmazó változatát előbb a jelen
  kohorszra kell szűkíteni; nincs csendes figyelmen kívül hagyás.
- Egy edzéshez legfeljebb egy `TRAIN`, `VALIDATION` vagy `TEST` kérés tartozhat.
- A besorolás lehet részleges vagy elmaradhat. Ez formai szempontból érvényes
  kérés, nem kész értékelési felosztás; a besorolatlan tag `UNASSIGNED` marad.
- Ismeretlen mezők, töredék-kiválasztás, tanítási/minőségi állítások és a
  támogatottól eltérő feladatok elutasítandók, akkor is, ha állításuk `False`.

A JSON Schema a mezőket, típusokat és lokális mintákat írja le. Az egy
sportolóra, duplikációra, valódi naptári dátumra és besorolási tagságra vonatkozó
szabályokat a Python-modell ellenőrzi. Külső JSON Schema-ellenőrzés önmagában
nem helyettesíti ezeket a szabályokat.

## 4. Kéréslenyomat — elkészült

A `canonical_payload()` az alapértékeket és a `null` besorolást explicit
alakba hozza. A tagokat `(provider, athlete_id, session_external_id)` szerint
rendezi; a besorolást a meglévő V24.8 normalizáló rendezi.

A `request_manifest_hash()` SHA-256 lenyomatot számol ezen a tartalmon:
rendezett objektumkulcsok, kompakt JSON, `allow_nan=false`, a Python JSON
alapértelmezett ASCII-karakterescape-je, UTF-8 bájtok. A bemeneti taglista vagy
a besorolási lista átrendezése nem változtatja meg a lenyomatot; egy pin,
dátum, manifestazonosító vagy besorolás megváltoztatása megváltoztatja.

Ez **a kérés tartalmának vállalása**, nem adatforrás-, jogosultsági,
időrendi vagy kohorsz-bizonyíték. Az azonosítók szerinti rendezés a manifest
kanonizálása; nem helyettesíti a valódi megfigyelési időrendet.

## 5. Következő részek elfogadási feltételei — még nincs megvalósítva

### V24.10-B: forráshoz kötött kohorsz-összeállítás

Minden taghoz szerveroldalon szükséges:

1. A hitelesített tulajdonos, a kiválasztott pillanatkép, az edzés és a
   környezeti bizonyíték valódi kapcsolata.
2. A V24.9 szerinti adatbázissor-, döntési lánc-, aktuális Polar-forrás- és
   HR-bizonyíték-ellenőrzés; a verziók és minden elvárt pin egyezése.
3. A teljes replay-csomag újraelőállítása először `UNASSIGNED` állapotban,
   teljes hash- és belső hivatkozásellenőrzés, majd egyezés az elvárt
   `expected_unassigned_replay_package_hash` értékkel. Kért besorolás nem
   módosíthatja ezt az alapellenőrzést.
4. Egyetlen hibás vagy hiányzó tag esetén az egész kért kohorsz igazolása
   visszatartott. Nem hagyunk ki tagot csendben, nem választunk másik
   pillanatképet, és nem indítunk automatikus környezeti újralekérést.
5. A tagok terhelési előzményei, hiányjelölései, cenzúrázott határai és
   eredeti HR-helyei megmaradnak. Előkészítési jelölt nem tanítási engedély.

A közös eredmény elsődlegesen ellenőrzött taghivatkozásokat és összesítéseket
tartalmazó index legyen: kéréslenyomat, forrás-/pillanatkép-/csomaglenyomatok,
tagállapotok, darabszámok, időrendi bizonyítékok és korlátok. A tagok teljes
adatai külön, saját hash-sel ellenőrizhetők maradnak. Nem kell az összes nagy
HR-/megfigyelési tartalmat egyetlen JSON-ba újra bemásolni.

A 100 tagos bemeneti korlát nem ígéret korlátlan teljes válaszra. A B részben
külön végrehajtási és memóriahatárt kell megadni, és a tagokat egymás után
ellenőrizni. Az alapértelmezett API-válasz később is rövid összefoglaló legyen.

### V24.10-C: időrend és értékelési felosztás

- Az időrendet forráshoz kötött, időzónával igazolt tényleges edzésintervallumok
  alapján kell meghatározni, az egész edzés gyakorlatait figyelembe véve.
  A kliens `route_date` értéke vagy egy időzóna nélküli kezdés nem elég.
- Igazolt időrendi szétválasztás csak akkor állítható, ha az összes kiválasztott
  edzés megfelelő intervalluma ismert. Bizonytalan határnál ezt vissza kell tartani.
- A későbbi edzéseken végzett egyéni értékelésben a `TRAIN` intervallumok
  megelőzik a `VALIDATION`, azok pedig a `TEST` intervallumokat; eltérő
  csoportok időbeli átfedése vagy felcserélt sorrendje nem igazolható felosztás.
- Teljes értékelési felosztáshoz minden tag besorolt, és mindhárom csoportban
  van legalább egy edzés. A séma ennél kisebb/részleges előkészítési kérését
  nem szabad kész felosztásként jelenteni.
- Azonos edzésből származó ablakok, célminták és átfedő előzmények közös
  csoportban maradnak. A külön edzések közötti adatazonosságot vagy
  újraimportált másolatot külön vizsgálni kell.
- Időbeli nem átfedés nem bizonyít statisztikai függetlenséget. Az egymást
  követő edzések kapcsolata és a megfelelő elkülönítési távolság későbbi
  értékelési protokoll kérdése; itt nincs önkényes várakozási intervallum.
- Későbbi illesztett előfeldolgozás csak a `TRAIN` csoportból tanulhat.
  Ebben a kiadásrészben előfeldolgozás-illesztés sincs.

Az elvárt közös állapotok külön jelezzék a tagság/forrás ellenőrzését, az
időrendet, a kérésre vonatkozó besorolást és a taníthatóságot. Ezekből egyik
nem helyettesíti a másikat. Közös, forráshoz kötött kohorszlenyomatot csak a
teljes ellenőrzött eredményre lehet kiadni; az A rész kéréslenyomatát nem
szabad erre a célra átnevezni.

### V24.10-D/E: integráció és kiadás

Az API-, tárolási és hibaválasz-döntések a kész B/C eredményeire épüljenek.
Forrásváltozás, jogosultsághiány, sérülés, szolgáltatási hiba és nem igazolható
időrend külön, korlátozott diagnosztikát igényel; más tulajdonos adatai nem
szivároghatnak ki. A végső kiadáshoz teljes regresszió és a felhasználói
környezetben szükséges élő/migrációs ellenőrzés tartozik.

## 6. Megőrzendő tudományos határok

`training_authorized=false`, `numeric_output_authorized=false`;
`fixed_hr_shift_applied=false`, `physiological_lag_ms=null`.
A szerződés nem engedi, hogy kliensoldali mező ezeket feloldja.

Az exportóra-eltérés nem élettani késés. A terhelésváltozásra és a terhelés
utáni időszakra később külön dinamikát lehet vizsgálni; nem vezetünk be
egyetlen feltételezett késési értéket. Nincs fáradtságcímke, fáradtságpontszám,
hiánypótlás, helyi áramlási sebesség kikövetkeztetése vízállásból/vízhozamból,
edzés előtti vagy oksági előrejelzési állítás.

A szenzornyilatkozat, a jeldiagnosztika, a forrásigazolás és a hash-ellenőrzés
nem emeli igazolttá a mérési minőséget. Több edzés összegyűjtése önmagában
sem oldja fel ezeket a korlátokat.

## 7. Példák és az A rész ellenőrzése

A két JSON-fájl minden azonosítója és hash-e **szintetikus**. Nem létező
edzések formailag érvényes példái; nem kell és nem szabad őket élő API-kérésként
beküldeni.

- `docs/examples/response_cohort_unassigned.json`: két tag, nincs besorolás.
- `docs/examples/response_cohort_requested_split.json`: három tag, csak kért
  `TRAIN`/`VALIDATION`/`TEST` besorolás, igazolt időrend nélkül.

A projekt gyökeréből, a telepített környezetben:

```text
PYTHONPATH=apps/api python tools/check_response_cohort_manifest.py docs/examples/response_cohort_unassigned.json
```

A Windowsra készített csomag útmutatója önálló PowerShell-blokkot tartalmaz.
Az ellenőrző program csak fájlt olvas és kimenetet ír a terminálra. Nem ér el
adatbázist, Polar- vagy környezeti szolgáltatót, és nem ment manifestet.
A fájlkorlát 1 MiB, duplikált JSON-kulcs és nem véges szám elutasítandó.

Sikeres formai eredmény: `STRUCTURALLY_VALID_MANIFEST`,
`claim_scope=REQUEST_STRUCTURE_AND_COMMITMENT_ONLY`;
`source_evidence_verified=false`, `chronological_cohort_order_verified=false`.
Érvénytelen kérésnél nem nulla a folyamat kilépési kódja. A hibakimenet nem
ismétli meg az ismeretlen mezők beküldött értékeit.

Az A rész lezárásához szükséges: a két példa formai ellenőrzése, a pin- és
csoportosítási negatív esetek, a sorrendtől független kéréslenyomat, a JSON
parser korlátai, a kliensállítások elutasítása, a publikált séma egyezése és
a meglévő API-tesztkör regressziója. Ezek az A rész szerződését ellenőrzik;
nem helyettesítik a B/C rész még hiányzó forrás- és kohorsz-ellenőrzését.
