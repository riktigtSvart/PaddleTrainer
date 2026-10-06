# PaddleTrainer V24.2 – pulzusminták ellenőrzése

A V24.1 audit után most a **nyers pulzusértékeket és az időadatok konzisztenciáját**
ellenőrizzük. Az ellenőrzés eredménye a meglévő inspect válaszban jelenik meg:

```text
route_sessions[].heart_rate_sample_validation
```

Verzió: `0.1.0`, séma: `0.1`. Forrásszerződés:
`POLAR_V4_INTERVAL_VALUES_2026_10_06`.

## Mit ellenőriz?

| Terület | Ellenőrzés |
|---|---|
| Forrás | Egyértelmű sessionazonosító és egyetlen sample-session |
| Pulzussorozat | Egyetlen HEART_RATE-sorozat, érvényes intervallum és értéktömb |
| Értékek | Hiány, logikai érték, nem numerikus, nem véges, nulla és negatív minták külön számlálása |
| Hiányok | Első/utolsó használható slot, szélső hiányok, leghosszabb hibás szakasz |
| Mintázatok | Megfigyelt minimum/maximum, egymás melletti érvényes minták legnagyobb ugrása, leghosszabb azonos értéksor |
| Időadatok | UTC-kezdő/záró idő, időtartam, szünetek, feltételezett mintarács darabszáma |
| Mérési metaadatok | Rögzítő készülékmodell, RR-minták és offline jelölések leltára |

A szüneteknél a hibás, egymást átfedő vagy az edzésen kívüli időablakok külön
jelzést kapnak. Az átfedő időablakok unióját leíró diagnosztikaként számoljuk.
A transitionSamples adatai nem kerülnek az exercise HR-sorozatába.

## Az eredmény határai

A Polar v4 `IntervalValues` dokumentációja típust, intervallumot és értékeket ír
le. Az első HR-mintához külön időbélyeget vagy offsetet nem ad meg ebben a
sémában. A slotok száma és az időtartam egyezése ezért csak konzisztenciajel.
A mintarács 0. slotját továbbra is feltevésként helyezzük az exercise kezdetére.

Forrás: [Polar AccessLink v4](https://www.polar.com/polar-api-v4/),
`trainingsessionIntervalValues`, `trainingsessionExercise`,
`trainingsessionPauseTime`, `trainingsessionProductReference`,
`trainingsessionRRSample`. Ellenőrzés: 2026-10-06.

| Mező | Jelentés |
|---|---|
| `TECHNICALLY_CLEAN_WITH_LIMITATIONS` | A HR-sorozat technikai értékellenőrzése megfelelt; a mérési pontosság még nem igazolt |
| `TECHNICAL_ISSUES` | A technikai blokkoló okok között hibás intervallum, érték vagy konténer szerepel |
| `WITHHELD` | Nem egyértelmű forrás/sorozat vagy nem kanonikus bemenet |
| `UNAVAILABLE` | Nincs vizsgálható HR-sorozat |
| `CONSISTENT_WITH_REPORTED_METADATA` | Az időadatok és a feltételezett rács ellenőrzése nem talált eltérést |
| `REVIEW_REQUIRED` | Az időadatok hiányosak vagy eltérésük további vizsgálatot igényel |

A technikai státusz és az időbeli konzisztencia külön eredmény: tiszta HR-értékek
mellett is lehet `REVIEW_REQUIRED` a timebase. A session összesítése számlálja
az időbeli vizsgálatot igénylő gyakorlatokat.

A `sample_grid_span_ms` az első és utolsó slot közötti távolság: `(N-1)*interval`.
A `nominal_slot_occupancy_ms` értéke `N*interval`. Egyik sem igazolja a tényleges
első mintát. A szünetek alatti HR-óra működését sem következtetjük ki ezekből.
Egy eltérő végpontkezelés vagy szünetkezelés felülvizsgálatot igényelhet.

A hosszú állandó értéksor vagy nagy ugrás leíró adat. Validált artefaktumdetektor
és sportolóhoz/érzékelőhöz illesztett fiziológiai szabály nélkül nem címkézzük
automatikusan mérési hibának. Az ugrásokat hiányokon át nem számítjuk.
A rögzítő készülék neve és az RR-minták jelenléte nem igazolja a HR-érzékelő
azonosságát, modalitását vagy pontosságát.

Ezért az alábbi értékek ebben a verzióban mindig változatlanok:

```text
time_origin_verified = False
acquisition_quality_verified = False
verified_hr_label_count = 0
training_authorized = False
numeric_prediction_authorized = False
```

A leíró HR-statisztikák mért értékekből származnak, nem modellbecslések.
A V24/V24.1 kimeneteket az új ellenőrzés nem módosítja vagy lépteti előre.
Nem javít, interpolál vagy töröl mintákat; nincs adatbázisírás és új API-paraméter.

## Alkalmazás PowerShellből

A csomag a **commitolt V24.1 négy baseline-fájlját** ellenőrzi a Gitben tárolt
tartalom SHA256 értékével. Ez a commit hashétől függetlenül használható, és a
Windows CRLF/LF munkapéldány-eltérését is kezeli. Tracked vagy staged módosítás,
eltérő baseline vagy már létező új célfájl esetén megáll az átmásolás előtt.

A ZIP-et tedd a Downloads mappába. A projekt gyökerében:

```powershell
$v242Zip = Join-Path $env:USERPROFILE 'Downloads\paddletrainer_v24_2_heart_rate_sample_validation.zip'
Get-FileHash -Algorithm SHA256 -LiteralPath $v242Zip | Format-List
```

Hasonlítsd össze a kísérő válaszban megadott SHA256 értékkel, majd:

```powershell
$v242Stage = Join-Path $env:TEMP ('paddletrainer_v24_2_' + [guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath $v242Zip -DestinationPath $v242Stage
.\.venv\Scripts\python.exe (Join-Path $v242Stage 'APPLY_PATCH.py') --project-root (Get-Location).Path --verify-only
if ($LASTEXITCODE -ne 0) { throw 'A V24.2 baseline/csomag ellenorzese sikertelen.' }
.\.venv\Scripts\python.exe (Join-Path $v242Stage 'APPLY_PATCH.py') --project-root (Get-Location).Path
if ($LASTEXITCODE -ne 0) { throw 'A V24.2 csomag alkalmazasa sikertelen.' }
git diff --check
git status --short
```

A másolóprogram kizárólag a manifest négy megadott projektfájlját írja.
A korábbi célfájl mentési helyét kiírja. Nem commitol és nem pushol.
A három korábbi untracked fájl nem kerül a csomagba vagy a Git-checkpointba.

## Tesztek

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'apps/api'
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_heart_rate_sample_validation.py apps/api/tests/test_training_data_readiness_audit.py apps/api/tests/test_route_expected_response_model.py -q
if ($LASTEXITCODE -ne 0) { throw 'A celzott tesztek sikertelenek.' }
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
if ($LASTEXITCODE -ne 0) { throw 'A teljes regresszio sikertelen.' }
```

Ellenőrizve Python 3.12-n: **163 passed** célzott; **843 passed, 1 warning** teljes.
Az 54 új teszt a 789-es V24.1 baseline fölé kerül. A warning a meglévő
Starlette/httpx deprecation; a helyi függőségverziótól függhet.

## Élő ellenőrzés

Az API-t indítsd újra a projekt gyökeréből, külön PowerShell-ablakban:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

Az ellenőrző ablakban környezeti lekérés nélkül is vizsgálható a HR:

```powershell
$v242Result = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/integrations/polar/sessions/routes/inspect?route_date=2026-09-30'
foreach ($v242Session in $v242Result.route_sessions) {
    $v242Hr = $v242Session.heart_rate_sample_validation
    if ($null -eq $v242Hr) { throw 'Hianyzik a HR-ellenorzes. Ellenorizd az API ujrainditasat.' }
    $v242Hr | Select-Object session_external_id, status, source_binding_verified, exercise_count, technically_clean_exercise_count, timebase_review_required_exercise_count, verified_hr_label_count, training_authorized, numeric_prediction_authorized, blocking_reasons, limitations, decision_hash | Format-List
    foreach ($v242Exercise in $v242Hr.exercises) {
        $v242Exercise | Select-Object exercise_index, source_exercise_id, technical_status, hr_series_count, technical_blocking_reasons, time_origin_verified, acquisition_quality_verified, unrecognized_hr_series_fields | Format-List
        $v242Exercise.value_quality | Format-List
        $v242Exercise.value_quality.invalid_value_counts | Format-List
        $v242Exercise.timebase | Format-List
        $v242Exercise.timebase.pause_inventory | Format-List
        $v242Exercise.acquisition | Format-List
        $v242Exercise.acquisition.rr_inventory | Format-List
    }
    if ($v242Hr.training_authorized -ne $false -or $v242Hr.verified_hr_label_count -ne 0 -or $v242Hr.numeric_prediction_authorized -ne $false) { throw 'Varatlan HR-tanitasi engedely.' }
    if ($v242Session.route_expected_response_model.response_available -ne $false) { throw 'Varatlan fiziologiai becsles.' }
}
$v242Result.route_sessions.training_data_readiness_audit | Select-Object status, candidate_segment_count, training_authorized | Format-List
```

A korábbi Duna-kontrollon 3038 slot és 1000 ms intervallum volt. Az aktuális
forrás dönti el az új státuszokat és eltéréseket. Ebben a környezeti provider
nélküli kontrollban a V24.1 readiness továbbra is `WITHHELD` lehet, miközben
a HR-sorozat technikai ellenőrzése megfelel. Ez két külön vizsgálat eredménye.

Küldd vissza a tesztek végét és a teljes új HR-diagnosztikát, különösen a
timebase/pause_inventory és acquisition/rr_inventory mezőket. Nem szükséges
nyers személyes adatsorozatot exportálnod.

## Git-checkpoint az élő ellenőrzés után

```powershell
git diff --check
git add -- apps/api/app/api/routes/polar.py apps/api/app/services/heart_rate_sample_validation.py apps/api/tests/test_heart_rate_sample_validation.py docs/v24_2_heart_rate_sample_validation.md
git diff --cached --stat
git commit -m "Add heart rate sample and clock validation"
git status --short
```

Az élő eredmény alapján választjuk ki a következő feladatot: időeredet igazolása
dokumentált forrásból, az érzékelő/mérési körülmények rögzítése, vagy konkrét
technikai adatprobléma javítása. Ezek feloldását ez a technikai ellenőrzés
önmagában nem bizonyítja.
