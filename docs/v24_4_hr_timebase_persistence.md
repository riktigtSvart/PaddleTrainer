# V24.4 — Pulzus-időillesztési igazolás mentése és auditbekötése

## Eredmény

A sikeresen összevetett TCX-export időillesztési igazolása mostantól tartósan
menthető. Az adatkészültségi audit automatikusan visszaolvassa, újra ellenőrzi,
és az adott gyakorlat igazolt kezdőeltolásával számolja a pulzuslefedettséget.
A későbbi visszaolvasáshoz és audithoz már nem kell újra feltölteni a fájlt.
A kapcsolt Polar-fiók aktuális mintái továbbra is szükségesek az ellenőrzéshez.

Az igazolás sportolóhoz, szolgáltatóhoz, munkamenethez, gyakorlathoz és a teljes
aktuális API-forrás lenyomatához kapcsolódik. Az alkalmazás nem tartalmaz
felhasználóhoz vagy eszközhöz rögzített időeltolást. A tesztek személyes
edzésadatok helyett mesterséges példákat használnak.

**Az igazolt exportidő nem igazolja a pulzusmérés pontosságát, és nem engedélyezi
a modell tanítását vagy numerikus előrejelzését.** Az érzékelőazonosítás,
jelszerzési minőség, történeti prediktorok és adathalmaz-felosztás külön feladat.

## API és eredmények

Az alábbi útvonalak előtagja: `/api/v1/integrations/polar`.

| Művelet | Útvonal | Viselkedés |
|---|---|---|
| POST | `/sessions/{id}/hr-timebase/verify-tcx` | A V24.3 szerinti összevetés; nem ment igazolást. |
| POST | `/sessions/{id}/hr-timebase/persist-tcx` | Friss összevetés után tartósan menti az igazolást. |
| GET | `/sessions/{id}/hr-timebase/saved` | Fájl nélkül újra ellenőrzi a mentett igazolást a jelenlegi API-forrással. |
| GET | `/sessions/routes/inspect` | A meglévő útvonalvizsgálat auditja automatikusan használja az alkalmazható igazolást. |

A három `hr-timebase` végpont kötelező paramétere a `sample_date=YYYY-MM-DD`.
A POST-műveleteknél az opcionális `exercise_external_id` kiválaszt egy
gyakorlatot. A feltöltés továbbra is nyers TCX/XML vagy ZIP kérésbody, legfeljebb
16 MiB; nem multipart-feltöltés. Mindkét új végpont a jelenlegi felhasználóhoz
kapcsolt Polar-fiókot és annak `training_sessions:read` jogosultságát használja.
A projekt jelenlegi demófelhasználó-kezelése változatlan; ez a lépés nem vezet be
új bejelentkezési rendszert.

| `persistence.status` | Jelentés |
|---|---|
| `CREATED` | Az igazolás elmentve és az adatbázisból visszaolvasva ellenőrizve. |
| `ALREADY_PRESENT` | Pontosan ugyanaz az igazolás már létezik; ugyanaz a rekordazonosító. |
| `NOT_STORED` | Az összevetés nem igazolható; nem keletkezik mentett igazolás. |

Az ismétlés csak változatlan forrás, azonos feltöltési bájtok és azonos
gyakorlatválasztás mellett adja ugyanazt a döntést. Például egy újracsomagolt
ZIP és a belőle kinyert TCX külön forráslenyomatot adhat. Ha teljes időrácsuk
azonos, az audit egyenértékű igazolásként kezeli őket. Eltérő időrácsoknál
nem választja ki automatikusan a legújabb rekordot: az érintett gyakorlat
időillesztése visszatartott marad.

## Tartós tárolás és újraellenőrzés

Az új `heart_rate_timebase_snapshots` táblába az igazolás JSON-pillanatképe,
a pulzusminták időbélyegei, a tulajdonosi és forrásazonosítók, valamint a
fájl, XML, API-forrás és döntés lenyomatai kerülnek. Az eredeti feltöltött fájl,
annak neve, GPS-koordinátái és hozzáférési tokenje nem kerülnek ebbe a táblába.
Az alkalmazás nem írja felül a korábbi igazolást: megváltozott forrás külön
pillanatképet igényel. Adatbázis-egyediség kezeli az ismételt és versengő mentést.

A visszaolvasás először a felhasználóra, a szolgáltatóra, a munkamenetre és az
aktuális teljes API-forráslenyomatra szűr. A korábbi lenyomathoz tartozó rekord
megmarad, de nem alkalmazható automatikusan. Már egy API-metaadat változása is
új ellenőrzést tehet szükségessé; az azonos pulzusdarabszám önmagában nem elég.

Az alkalmazható rekordnál az oszlopok és a JSON azonossága, a két döntéslenyomat,
a teljes aktuális API-pulzussor, a gyakorlat azonosítója, kezdete, vége és minden
mentett pulzus-időbélyeg újraellenőrzésre kerül. Sérült, más tulajdonoshoz tartozó
vagy ellentmondó igazolás nem oldja fel az audit korlátozását.

A lenyomat tartalmi integritást ellenőriz; nem digitális aláírás. Az eredeti TCX
nincs eltárolva, ezért a visszaolvasás a szerver által előzőleg létrehozott
igazolást ellenőrzi, nem végzi el újra az eredeti XML beolvasását. Az API nem
fogad el kliensoldalon készített igazolás-JSON-t mentésre.

## Mit változtat az auditban?

Az audit verziója `0.2.0`; a séma továbbra is `0.1`, az új mezők hozzáadások.
Az auditjelentés csak az igazolás azonosítóit és alkalmazási eredményét tartalmazza,
nem másolja bele az összes pulzus-időbélyeget.

| Auditmező | Igazolt, alkalmazható export esetén |
|---|---|
| `export_timebase_verified_route_count` | Az igazolást alkalmazó útvonalak száma. |
| `hr_timebase_evidence.status` | `VERIFIED_WITH_LIMITATIONS` |
| `routes[].export_timebase_verified` | `True` az érintett gyakorlat útvonalán. |
| `routes[].hr_timebase.sample_grid_source` | `VERIFIED_SAVED_EXPORT` |
| `routes[].hr_timebase.sample_grid_origin_us` | Az adott exportból származó kezdőeltolás. |
| `training_authorized` / `numeric_output_authorized` | Továbbra is `False`. |

Az érintett útvonalnál az `HR_SAMPLE_TIME_ORIGIN_NOT_VERIFIED` helyébe a
szolgáltató saját órájának és szünetkezelésének továbbra sem igazolt szemantikája
kerül. A pulzusmérési minőség és a többi fennmaradó korlátozás megmarad.
Egy gyakorlat igazolása nem lesz az egész munkamenet vagy minden felhasználó
időeltolása. A kohorsz összesítése az egyes auditok tényleges korlátozásait egyesíti.

A szegmensablak kezdete beleértendő, vége kizárt: `[kezdés, vég)`.
A számítás egész mikroszekundumokat használ. Nem interpolálunk vagy töltünk ki
hiányzó mintát. A megváltozott időrács miatt a lefedett szegmensek száma is
változhat. Igazolás nélkül megmarad a korábbi, kifejezetten nem igazolt
nullakezdőidős projektkonvenció. A környezeti és modellbemeneti tiltások az
igazolás megléte mellett is érvényesek.

## Telepítés Windows és PowerShell alatt

### 1. A V24.3 legyen commitolva

A V24.4 a már ellenőrzött, **helyileg commitolt V24.3 tartalomra** épül.
Nem követel meg egyetlen konkrét V24.3 commithash-t; az ismert tartalmakat ellenőrzi.
A `bc505b4` alapnak az előzmények között kell szerepelnie. A távoli push nem
telepítési feltétel.

```powershell
git log -1 --oneline
git status --short
git diff --cached --stat
```

Ha a hat V24.3-fájl még csak stage-elve van:

```powershell
git commit -m "Add optional TCX heart-rate timebase verification"
git push origin main
```

Ha a PowerShell egy befejezetlen idézőjel miatt `>>` jelet mutat, előbb `Ctrl+C`,
majd a teljes, lezárt parancs. Az LF/CRLF figyelmeztetések önmagukban nem hibák.
Más módosított követett fájlt ne dobj el a telepítés kedvéért.

### 2. A csomag alkalmazása

Állítsd le a futó backendet. A letöltött csomagot új könyvtárba bontsd ki.
Az alábbi parancsok a projekt gyökeréből futnak; szükség esetén módosítsd a
letöltött ZIP vagy a már használt Python-környezet útvonalát.

```powershell
$v244Python = (Resolve-Path '.\.venv\Scripts\python.exe').Path
$v244Zip = Join-Path $env:USERPROFILE 'Downloads\paddletrainer_v24_4_hr_timebase_persistence.zip'
$v244Patch = Join-Path $env:TEMP ('paddletrainer_v24_4_' + [guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath $v244Zip -DestinationPath $v244Patch

& $v244Python "$v244Patch\APPLY_PATCH.py" --project-root . --verify-only
if ($LASTEXITCODE -ne 0) { throw 'A commitolt V24.3 alap ellenőrzése nem sikerült.' }
& $v244Python "$v244Patch\APPLY_PATCH.py" --project-root .
if ($LASTEXITCODE -ne 0) { throw 'A V24.4 telepítése nem sikerült.' }
$env:PYTHONPATH = (Resolve-Path '.\apps\api').Path
```

A telepítő 16 projektfájlt ír. Ellenőrzi a tiszta követett és stage-elt fájlokat,
a commitolt alapot, a fájllistát és a csomaglenyomatokat. Biztonsági másolatot
készít, írási hiba esetén visszaállítja az érintett fájlokat. A személyes, nem
követett fájlokat nem módosítja. Nem indít adatbázis-migrációt vagy Git-commitot.

### 3. Tesztek és adatbázis-migráció

```powershell
$v244Tests = @(
    'apps/api/tests/test_hr_timebase_snapshot.py',
    'apps/api/tests/test_hr_timebase_persistence.py',
    'apps/api/tests/test_hr_timebase_readiness_audit.py',
    'apps/api/tests/test_polar_hr_timebase_persistence_api.py',
    'apps/api/tests/test_hr_timebase_migration.py',
    'apps/api/tests/test_tcx_heart_rate_timebase.py',
    'apps/api/tests/test_polar_tcx_timebase_api.py',
    'apps/api/tests/test_heart_rate_sample_validation.py',
    'apps/api/tests/test_training_data_readiness_audit.py',
    'apps/api/tests/test_route_expected_response_model.py'
)
& $v244Python -m pytest -q @v244Tests
if ($LASTEXITCODE -ne 0) { throw 'A célzott tesztkör nem sikerült.' }
& $v244Python -m pytest -q apps/api/tests
if ($LASTEXITCODE -ne 0) { throw 'A teljes tesztkör nem sikerült.' }
git diff --check

& $v244Python -m alembic -c apps/api/alembic.ini upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Az adatbázis-migráció nem sikerült.' }
& $v244Python -m alembic -c apps/api/alembic.ini current
```

Az új adatbázis-head: **`a6d2c4e91b70`**, elődje `f3c91ab84d27`.
A migráció egy új táblát, idegen kulcsot, egyediségi feltételt és indexet hoz létre.
A meglévő edzésadatokat nem módosítja. Az Alembic-konfiguráció most a saját
könyvtárához képest oldja fel az útvonalakat, ezért a fenti parancs gyökérből is fut.
A szokásos projektkonfigurációban megadott adatbázist használja.

Ellenőrzött eredmény: **350 célzott, 1030 teljes teszt**. A meglevő Starlette
tesztkliens elavulási figyelmeztetése megmaradhat. A tartós JSON-visszaolvasás és
egyediség valódi SQLite/SQLAlchemy adatbázison, a PostgreSQL-migráció és JSONB
DDL offline ellenőrzésben szerepelt. Az élő PostgreSQL-migrációt nálad kell futtatni.

```powershell
& $v244Python -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

## Élő ellenőrzés egy másik PowerShell-ablakban

A változókat az ellenőrzött edzésre és exportjára állítsd; az alábbi azonosító
és fájlútvonal helykitöltő. Az összevetés a tartalmat vizsgálja, nem a fájl nevét.

```powershell
$v244SessionId = 'A_POLAR_MUNKAMENET_AZONOSITOJA'
$v244Date = '2026-09-30'
$v244Export = 'AZ_ILLESZKEDO_TCX_VAGY_ZIP_TELJES_ELERESI_UTJA'
$v244Base = 'http://127.0.0.1:8000/api/v1/integrations/polar'
$v244SaveUri = "$v244Base/sessions/$v244SessionId/hr-timebase/persist-tcx?sample_date=$v244Date"
$v244SavedUri = "$v244Base/sessions/$v244SessionId/hr-timebase/saved?sample_date=$v244Date"

$v244First = Invoke-RestMethod -Method Post -Uri $v244SaveUri -ContentType 'application/octet-stream' -InFile $v244Export
$v244Repeat = Invoke-RestMethod -Method Post -Uri $v244SaveUri -ContentType 'application/octet-stream' -InFile $v244Export
[pscustomobject]@{
    FirstSave = $v244First.persistence.status
    RepeatSave = $v244Repeat.persistence.status
    SnapshotId = $v244First.persistence.snapshot_id
    SameSnapshotId = ($v244First.persistence.snapshot_id -eq $v244Repeat.persistence.snapshot_id)
    RoundTripVerified = $v244First.persistence.round_trip_verified
    MatchedSamples = $v244First.verification.binding.matched_hr_sample_count
    OffsetMs = $v244First.verification.timebase.first_sample_offset_from_api_exercise_start_ms
    TrainingAuthorized = $v244First.persistence.training_authorized
} | Format-List

$v244Saved = Invoke-RestMethod -Uri $v244SavedUri
$v244Saved | Select-Object source_binding_verified, stored_current_source_snapshot_count, training_authorized
$v244Saved.saved_timebase | Select-Object status, verified_exercise_count, rejected_record_count, blocking_reasons
```

Első alkalommal `CREATED`, ismételve `ALREADY_PRESENT`, azonos rekordazonosító,
`round_trip_verified=True`, egy igazolt gyakorlat és `training_authorized=False`
várható. Korábbi azonos mentés esetén már az első hívás is `ALREADY_PRESENT`.
A következő GET nem tartalmaz feltöltött fájlt.

```powershell
$v244Inspect = Invoke-RestMethod -Uri "$v244Base/sessions/routes/inspect?route_date=$v244Date"
$v244Session = $v244Inspect.route_sessions | Where-Object { $_.external_id -eq $v244SessionId }
$v244Audit = $v244Session.training_data_readiness_audit
$v244Audit | Select-Object status, export_timebase_verified_route_count, candidate_segment_count, training_authorized, numeric_output_authorized
$v244Audit.hr_timebase_evidence | Format-List
$v244Audit.routes | Select-Object route_index, exercise_index, export_timebase_verified, status
$v244Audit.routes.hr_timebase | Format-List
$v244Audit.limitations
```

Ha korábban környezeti paramétereket adtál meg az útvonalvizsgálatnál, ugyanazokat
add meg itt is. Hiányzó környezeti vagy modellbemenet mellett az audit lehet
`WITHHELD`, miközben a pulzus-időillesztést külön igazoltnak jelzi. A sikeres
mentés nem ígér változatlan jelöltszámot vagy edzéstervet.

Negatív ellenőrzésként másik nap exportját küldd ugyanarra a `persist-tcx`
útvonalra. Várt eredmény: `verification.status=WITHHELD`,
`persistence.status=NOT_STORED`. A korábbi helyes igazolásnak meg kell maradnia.

## Commit a helyi és élő ellenőrzések után

```powershell
$v244Files = @(
    'apps/api/alembic.ini',
    'apps/api/alembic/versions/a6d2c4e91b70_add_hr_timebase_snapshots.py',
    'apps/api/app/api/routes/polar.py',
    'apps/api/app/api/routes/polar_tcx.py',
    'apps/api/app/models/__init__.py',
    'apps/api/app/models/hr_timebase_snapshot.py',
    'apps/api/app/services/hr_timebase_snapshot.py',
    'apps/api/app/services/hr_timebase_persistence.py',
    'apps/api/app/services/tcx_heart_rate_timebase.py',
    'apps/api/app/services/training_data_readiness_audit.py',
    'apps/api/tests/test_hr_timebase_snapshot.py',
    'apps/api/tests/test_hr_timebase_persistence.py',
    'apps/api/tests/test_hr_timebase_readiness_audit.py',
    'apps/api/tests/test_polar_hr_timebase_persistence_api.py',
    'apps/api/tests/test_hr_timebase_migration.py',
    'docs/v24_4_hr_timebase_persistence.md'
)
git diff --check
git add -- @v244Files
git diff --cached --stat
git commit -m "Persist verified HR timebase and wire readiness audit"
git push origin main
```
