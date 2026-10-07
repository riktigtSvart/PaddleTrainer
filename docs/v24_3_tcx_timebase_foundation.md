# V24.3 — TCX-import és ellenőrzött pulzus-időillesztés

## Mire szolgál?

A V24.3 az opcionálisan megadott TCX-export explicit időbélyegeit kapcsolja a
Polar API pulzusmintáihoz. Az összekapcsolás csak egyértelmű forrásazonosítás,
teljes, sorrendhelyes értékegyezés és megfelelő időadatok mellett igazolható.
A fájl neve, GPS-koordinátái és a készülék neve nem illesztési feltételek.

**A végleges alkalmazás alapműködéséhez nem tervezünk kötelező TCX-feltöltést.**
Az adatgyűjtés és a jelenlegi auditok továbbra is használhatók fájl nélkül.
Ha egy adatforrás nem közli a minták kezdőidejét, az adott edzés időillesztése
kiegészítő bizonyíték nélkül korlátozott marad. A TCX az egyik ilyen bizonyíték.
Egy későbbi, megfelelő időbélyegeket szolgáltató integráció ugyanezt a szerepet
kézi export nélkül is betöltheti; ez a V24.3-ban még nincs megvalósítva.

Ez egy **külön, csak olvasó ellenőrzési útvonal**. Visszaadja az igazolt,
exportból származó időbélyegeket, de nem menti a fájlt vagy az igazolást az
adatbázisba, és nem módosítja a korábbi audit eredményét. A tartós bizonyítékkezelés
és az auditba történő bekötés későbbi lépés.

## Mi igazolható, és mi marad külön feladat?

| Eredménymező | Sikeres összevetés esetén |
|---|---|
| `status` | `VERIFIED_EXPORT_TIMEBASE_WITH_LIMITATIONS` |
| `export_timebase_verified` | `True` |
| `api_native_time_origin_verified` | `False` |
| `pause_clock_semantics_verified` | `False` |
| `acquisition_quality_verified` | `False` |
| `training_authorized` | `False` |
| `numeric_prediction_authorized` | `False` |

A két forrás egyezése az exportban szereplő időbélyegek felhasználását alapozza
meg. Nem független referencia a pulzusmérés pontosságához, és nem tisztázza
általánosan a szolgáltató saját mintavételi vagy szünetkezelési óráját.
Az érzékelőre vonatkozó felhasználói közlés külön, sportolóhoz vagy edzéshez
kapcsolódó adatként kezelendő; a készüléknév önmagában nem bizonyítja az érzékelőt.

## Az illesztés feltételei

1. A kiválasztott Polar-munkamenet azonosítója egyezik, és pontosan egy
   munkamenet található a kapcsolt Polar-fiók válaszában.
2. Az API-gyakorlatok azonosítói rendelkezésre állnak és egyediek. Az illesztés
   nem listapozíció alapján történik. Az `exercise_external_id` paraméterrel
   egy gyakorlat kifejezetten kiválasztható.
3. A kiválasztott API-pulzussor technikailag tiszta. A teljes darabszám és
   minden pulzusérték egyezik, azonos sorrendben. Részsorozat, átlag, minimum,
   maximum vagy azonos darabszám önmagában nem elegendő.
4. A TCX minden vizsgált trackpontjának időbélyege használható, időzónával
   rendelkezik, és szigorúan növekszik. Legalább két pulzusminta szükséges.
   A pulzusminták időköze pontosan egyezik az API `intervalMillis` értékével.
5. Egész másodpercre megadott API-kezdőidőnél a TCX-aktivitás kezdete ugyanabba
   a jelentett UTC-másodpercbe esik. Törtmásodperces API-kezdőidőnél pontos
   egyezés szükséges. Ez konzervatív illesztési szabály, nem a szolgáltató
   kerekítési szabályának igazolása.
6. A trackpontok az API gyakorlatának jelentett időablakán belül vannak.
   Egész másodperces záróidőnél a jelentett másodperc elfogadható; pontos
   törtmásodperces záróidőnél a határértékig fogadjuk el a pontokat.
7. A feltételeknek pontosan egy API-gyakorlat / TCX-aktivitás pár felel meg.

A pulzus nélküli kezdő és záró trackpontok láthatók maradnak a jelentésben.
Belső hiányt, hibás értéket, duplikált időbélyeget vagy eltérő órát nem töltünk
ki és nem igazítunk el automatikusan. Több kör vagy track egy aktivitáson belül
a fájl sorrendjében kerül vizsgálatra. A számítás egész mikroszekundumokat
használ; az időeltolás az adott exportból származik.

## Fogadott fájlok és forrásnyom

- TCX v2 XML a `http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2`
  névtérben, vagy ZIP, amely pontosan egy `.tcx` fájlt tartalmaz.
- Nyers HTTP-kérés törzse: `application/xml`, `text/xml`, `application/zip`
  vagy `application/octet-stream`. Nem `multipart/form-data` feltöltés.
- A feltöltött fájl és a kicsomagolt XML legfeljebb 16 MiB lehet. További
  korlátok: 16 archívumbejegyzés, 32 aktivitás, 100 000 trackpont, 500 000 XML-elem,
  legfeljebb 64 szintű XML és 64 API-gyakorlat.
- Titkosított archívumot, nem támogatott tömörítést és DTD-t nem fogadunk el.
  ZIP_STORED és ZIP_DEFLATED támogatott. Az archívumot nem írjuk ki lemezre.
- A parser az illesztéshez szükséges mezőket ellenőrzi; nem teljes TCX-XSD-validator.
- A fájl, az XML, az API-forrás és a döntés SHA-256 lenyomata bekerül az eredménybe.
  A válasz nem tartalmazza a fájl nevét, GPS-koordinátáit vagy a hozzáférési tokent.

A normál negatív ellenőrzési eredmény HTTP 200 és `WITHHELD`. A fájlméretkorlát
túllépése HTTP 413, a hibás kérésformátum HTTP 415, a hiányzó jogosultság HTTP
403, a hibás szolgáltatói válasz HTTP 502. Hibás vagy hiányzó mintasort nem
minősítünk időben igazoltnak.

## Telepítés és ellenőrzés Windows alatt

A csomag az elmentett, commitolt V24.2 tartalomra épül, amelynek távoli commitja
`bc505b4`. Hat projektfájlt tartalmaz. Az `APPLY_PATCH.py` ellenőrzi a commitolt
alapot, a tiszta követett fájlokat és a csomag lenyomatait; csak a felsorolt
fájlokat írja. Biztonsági másolatot készít a módosított routerről, és hiba esetén
visszaállítja az érintett fájlokat. A nem követett személyes fájlokhoz nem nyúl.

A letöltött ZIP-et egy új ideiglenes könyvtárba bontsd ki. A projekt gyökerében:

```powershell
# A könyvtárat a kicsomagolt csomag tényleges helyére állítsd.
$v243Patch = 'A_KICSOMAGOLT_CSOMAG_KONYVTARA'
.\.venv\Scripts\python.exe "$v243Patch\APPLY_PATCH.py" --project-root . --verify-only
if ($LASTEXITCODE -ne 0) { throw 'A V24.2 alap ellenőrzése nem sikerült.' }
.\.venv\Scripts\python.exe "$v243Patch\APPLY_PATCH.py" --project-root .
if ($LASTEXITCODE -ne 0) { throw 'A V24.3 telepítése nem sikerült.' }

.\.venv\Scripts\python.exe -m pytest -q apps/api/tests/test_tcx_heart_rate_timebase.py apps/api/tests/test_polar_tcx_timebase_api.py apps/api/tests/test_heart_rate_sample_validation.py apps/api/tests/test_training_data_readiness_audit.py apps/api/tests/test_route_expected_response_model.py
.\.venv\Scripts\python.exe -m pytest -q apps/api/tests
git diff --check
```

Az ellenőrzött környezetben a célzott kör **257**, a teljes kör **937** sikeres
tesztet adott. A függőségek verziójától függően figyelmeztetés is megjelenhet;
nálunk a Starlette tesztkliensének elavulási figyelmeztetése szerepelt.

Indítsd újra a backendet, hogy az új végpont betöltődjön:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

## Élő pozitív ellenőrzés

A következő példa a már összevetett szeptember 30-i edzést választja ki.
A fájl és az azonosítók itt tesztbemenetek, nem az alkalmazás állandói.
A backendnek futnia kell; ezeket egy második PowerShell-ablakban futtasd.

```powershell
$v243SessionId = '0e27d18d-279f-2d26-1ae3-bb53e19b2b1f'
$v243Sep30Zip = Join-Path $env:USERPROFILE 'Downloads\Gyula_Fekete_2026-09-30_17-35-18.ZIP'
$v243Uri = "http://127.0.0.1:8000/api/v1/integrations/polar/sessions/$v243SessionId/hr-timebase/verify-tcx?sample_date=2026-09-30"

$v243 = Invoke-RestMethod -Method Post -Uri $v243Uri -ContentType 'application/zip' -InFile $v243Sep30Zip

[pscustomobject]@{
    Status = $v243.status
    ExportTimebaseVerified = $v243.export_timebase_verified
    ExerciseId = $v243.exercise_external_id
    MatchedSamples = $v243.binding.matched_hr_sample_count
    ValueMismatches = $v243.binding.ordered_value_mismatch_count
    FirstSampleUtc = $v243.timebase.first_sample_timestamp_utc
    LastSampleUtc = $v243.timebase.last_sample_timestamp_utc
    OffsetMs = $v243.timebase.first_sample_offset_from_api_exercise_start_ms
    TrainingAuthorized = $v243.training_authorized
    NumericAuthorized = $v243.numeric_prediction_authorized
    ApiSourceHash = $v243.input_provenance.api_source_hash
    DecisionHash = $v243.decision_hash
} | Format-List

$v243.source_import.activities | Format-List
$v243.limitations
```

Várt eredmény a feltöltött forrásadatokkal: `VERIFIED_EXPORT_TIMEBASE_WITH_LIMITATIONS`,
3038 egyező minta, 0 eltérés, 1663 ms kezdőeltolás. A TCX-ben 3042 trackpont,
köztük négy pulzus nélküli záró pont szerepel. A tanítás és a numerikus
előrejelzés engedélye `False`. Ha a fájl más könyvtárban van, a fájlútvonalat
módosítsd a parancsban.

## Élő negatív ellenőrzés

Az október 4-i exportot szándékosan ugyanahhoz a szeptember 30-i API-edzéshez
próbáljuk kapcsolni. Ennek elutasított eredményt kell adnia.

```powershell
$v243Oct4Zip = Join-Path $env:USERPROFILE 'Downloads\Gyula_Fekete_2026-10-04_17-02-18.ZIP'
$v243Wrong = Invoke-RestMethod -Method Post -Uri $v243Uri -ContentType 'application/zip' -InFile $v243Oct4Zip
$v243Wrong | Select-Object status, export_timebase_verified, training_authorized, blocking_reasons
$v243Wrong.candidates | Format-List
```

Várt eredmény: `WITHHELD`, `export_timebase_verified=False`, üres időillesztés.
A jelölt elutasítási okai között az eltérő mintaszám és kezdőidő szerepel.

## Commit az élő ellenőrzés után

```powershell
git add -- apps/api/app/api/router.py apps/api/app/api/routes/polar_tcx.py apps/api/app/services/tcx_heart_rate_timebase.py apps/api/tests/test_tcx_heart_rate_timebase.py apps/api/tests/test_polar_tcx_timebase_api.py docs/v24_3_tcx_timebase_foundation.md
git diff --cached --stat
git commit -m "Add optional TCX heart-rate timebase verification"
git push origin main
```

A személyes JSON- és TCX-exportokat ne add hozzá ehhez a commithoz. Az új
regressziós tesztek saját, személyes adatokat nem tartalmazó példákból készülnek.

## Technikai referencia

- [Python ElementTree: parser és TreeBuilder](https://docs.python.org/3/library/xml.etree.elementtree.html)
- [Python XML-biztonsági útmutató](https://docs.python.org/3/library/xml.html)
