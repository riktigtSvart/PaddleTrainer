# V24.5 — Érzékelőnyilatkozatok és adatminőségi korlátok

A V24.5 az adott sportoló, Polar-munkamenet és gyakorlat pulzusmérésére vonatkozó
felhasználói közlést menti. Megőrzi a közlés eredetét és a helyesbítési előzményeket,
majd az aktuális API-forrással ellenőrizve felhasználja az adatkészültségi auditban.

Alap: a commitolt V24.4, `6b7bad71369bc3d8c4d533784abd54a27924b947`.
Az új adatbázis-head `c5e83a9d2714`; elődje `a6d2c4e91b70`.

## Mit jelent az érzékelőadat?

Három külön adatforrást kezelünk:

| Adat | Eredete | Következtetés |
|---|---|---|
| Rögzítőeszköz modellje | Polar API `product.modelName` | A rögzítőeszköz szolgáltatói metaadata. |
| Szenzor módja, helye, gyártója, modellje | Az adott gyakorlat felhasználói nyilatkozata | Forráshoz kötött, felhasználó által közölt mérési körülmény. |
| Technikai érték- és időellenőrzés | V24.2 validátor és V24.4 mentett TCX-igazolás | A meglévő technikai és időalap-eredmény saját korlátaival. |

A rögzítőeszköz modelljéből a program nem következtet arra, hogy a pulzus az óra
beépített érzékelőjéből vagy külön szenzorból származott. Nincs beégetett gyártó,
óratípus, sportoló, konkrét edzés vagy minden edzésre érvényes időeltolás.

Az `USER_DECLARATION` ismertté teszi a közölt mérési körülményt. **Nem igazolja a
szenzor azonosságát szolgáltatói bizonyítékkal vagy a pulzusmérés pontosságát.**
Az `acquisition_quality_verified`, `sensor_identity_verified`, `training_authorized`
és `numeric_prediction_authorized` továbbra is `False`.

Ez a lépés backend API-t ad. Az általános sportolói szenzorprofil és a webes
beviteli felület későbbi fejlesztés; egy nyilatkozat nem kerül át automatikusan
más gyakorlatokra, napokra vagy más sportolókhoz.

## API

Előtag: `/api/v1/integrations/polar`.

| Művelet | Útvonal | Hatás |
|---|---|---|
| POST | `/sessions/{id}/hr-acquisition/declarations?sample_date=YYYY-MM-DD` | Új felhasználói nyilatkozat vagy explicit helyesbítés mentése. |
| GET | `/sessions/{id}/hr-acquisition?sample_date=YYYY-MM-DD` | Az aktuális forráshoz tartozó közlések, előzmények és feloldás visszaolvasása. |
| GET | `/sessions/routes/inspect?route_date=YYYY-MM-DD` | Az audit automatikusan betölti a megfelelő sportolóhoz és aktuális API-forráshoz kötött közlést. |

A POST JSON bodyt fogad. Kötelező az `exercise_external_id` és a `sensor_modality`.

| JSON-mező | Elfogadott tartalom |
|---|---|
| `sensor_modality` | `OPTICAL_PPG`, `ELECTRICAL`, `OTHER`, `UNKNOWN` |
| `body_location` | `WRIST`, `CHEST`, `UPPER_ARM`, `FOREARM`, `OTHER`, `UNKNOWN`; alapérték `UNKNOWN` |
| `sensor_manufacturer`, `sensor_model` | Opcionális, legfeljebb 100 karakter; ismeretlen adatnál elhagyható vagy `null`. |
| `reported_issue_codes` | `LOOSE_CONTACT`, `SIGNAL_DROPOUT`, `SENSOR_MOVED`, `OTHER`; alapérték üres lista. |
| `supersedes_declaration_ids` | Helyesbítéskor az összes aktuálisan aktív közlés UUID-je az adott gyakorlaton. |

Az üres problémalista azt jelenti, hogy ilyen probléma nem lett közölve; nem
jelminőségi igazolás. Ismeretlen extra mező — például kliensoldali
`acquisition_quality_verified=True` vagy `athlete_id` — HTTP 422 elutasítást kap.
A tulajdonost és a `USER_DECLARATION` eredetet a szerver állítja be. Mindkét
végpont az aktuális felhasználó Polar-kapcsolatát és `training_sessions:read`
jogosultságát ellenőrzi. A projekt meglévő demófelhasználó-kezelése megmarad.

## Tartós mentés és helyesbítés

Az `hr_acquisition_declarations` tábla felhasználói idegen kulcsot, szolgáltatót,
edzés- és gyakorlat-azonosítót, API-forráslenyomatot, nyilatkozatlenyomatot,
JSON-közlést és szerveroldali UTC-rögzítési időt tárol. Nem másolja bele a nyers
pulzusmintákat, GPS-útvonalat, TCX-fájlt vagy a hozzáférési tokent.

Azonos közlés, azonos tulajdonos, gyakorlat, API-forrás és helyesbítési lista
ismétlése `ALREADY_PRESENT` státuszt és azonos `declaration_id`-t ad. Az adatbázis
egyediségi feltétele versengő azonos mentéseknél is érvényes.

A visszaolvasás az oszlopokat, a JSON-közlést és annak lenyomatát újra ellenőrzi.
Megváltozott API-forrásnál a korábbi sor megmarad, de nem alkalmazható
automatikusan. A GET előzményei kifejezetten az **aktuális API-forrásra** vonatkoznak.
A lenyomat tartalmi integritást ellenőriz, nem digitális aláírás.

Helyesbítéskor az aktuális `active_declaration_ids` listát kell a
`supersedes_declaration_ids` mezőbe másolni, és megadni a helyes érzékelőadatokat.
Új sor keletkezik; a korábbi közlés változatlanul megmarad. Más sportolóhoz,
gyakorlathoz, forráshoz vagy már helyesbített közléshez tartozó cél HTTP 409-et ad.
Az előző kérés ismétlése nem aktiválja újra a már helyesbített közlést.

Eltérő új közlés explicit helyesbítési lista nélkül ellentmondást hozhat létre.
A program nem választja ki a legújabbat: `REVIEW_REQUIRED` állapotot ad. Minden
aktív közlést megnevező helyesbítés oldhatja fel az ellentmondást. Versengő,
egymásnak ellentmondó helyesbítési ágak szintén felülvizsgálatot igényelnek.

Egy sportoló–munkamenet–API-forrás alatt legfeljebb 512 sor kezelhető, az
előzményekkel együtt. Ismeretlen vagy körkörös helyesbítési kapcsolat nem alkalmazható.

## Audit és meglévő TCX-igazolás

Az audit verziója `0.3.0`. Az új mezők:

- `heart_rate_acquisition_context` az útvonalvizsgálat munkamenetében;
- `hr_acquisition_evidence` és `user_declared_acquisition_route_count` az auditban;
- `routes[].hr_acquisition` az adott útvonal közlésével, eredetével és korlátaival.

Egyező, problémát nem közlő nyilatkozat az auditban
`USER_DECLARED_WITH_LIMITATIONS` állapotú. Önmagában nem tesz új szegmenst
adat-előkészítésre alkalmassá. A hiányzó környezeti és modellbemeneti feltételek,
a HR-fedettség és az egyéb auditkorlátok továbbra is érvényesek.

Közölt mérési probléma esetén a `HR_USER_REPORTED_ACQUISITION_ISSUES_REQUIRE_REVIEW`
ok visszatartja az érintett gyakorlat szegmenseinek előkészítését. Ez megőrzött
felhasználói közlés; nincs automatikus műtermékdetektor, mintatörlés vagy interpoláció.
Ellentmondó vagy sérült nyilatkozat szintén visszatartja az érintett illesztést.
Egy másik gyakorlat ellentmondása nem kerül át a jól azonosított útvonalra.

**A nyers V24.2 pulzusvalidátor és a V24.4 TCX-időigazolás változatlan.**
A nyers validátor `acquisition` mezője továbbra is kizárólag az eredeti forrás
technikailag igazolható adatait jelzi. A felhasználói közlés az új, külön mezőben
látható. A meglevő TCX-forrás- és döntéslenyomatok ellenőrizhetők maradnak;
az érzékelőnyilatkozathoz új TCX-feltöltés nem kell.

## Telepítés Windows / PowerShell alatt

### 1. Előkészítés és csomag

A V24.4 legyen helyileg commitolva. Ellenőrzés:

```powershell
git log -1 --oneline
git status --short
```

A futó API-ablakban `Ctrl+C`. A projekt gyökerében készítsd elő a Python útvonalát:

```powershell
$v245Python = (Resolve-Path '.\.venv\Scripts\python.exe').Path
$env:PYTHONPATH = (Resolve-Path '.\apps\api').Path
```

A ZIP-et a beszélgetésben kapott fájlválasztó blokk bontja ki új ideiglenes
mappába; ennek elérési útja `$v245Patch`. Így a letöltés mentési helyét nem kell
kitalálni. A telepítő 17 projektfájlt ír; először ellenőrizhető, írás nélkül:

```powershell
& $v245Python "$v245Patch\APPLY_PATCH.py" --project-root . --verify-only
if ($LASTEXITCODE -ne 0) { throw 'A V24.4 alap ellenőrzése nem sikerült.' }
& $v245Python "$v245Patch\APPLY_PATCH.py" --project-root .
if ($LASTEXITCODE -ne 0) { throw 'A V24.5 telepítése nem sikerült.' }
```

A telepítő tiszta követett/stage-elt fájlokat és commitolt V24.4-tartalmat követel.
A személyes, nem követett fájlokat megőrzi. Célnévütközésnél megáll; írási hiba
esetén visszaállítja az érintett fájlokat. A ZIP-ben lévő `CHECK_V24_5.ps1`
ellenőrző segéd a kibontási mappában marad, nem települ az alkalmazás kódjába.

### 2. Tesztek és adatbázis-migráció

```powershell
$v245Tests = @(
    'apps/api/tests/test_hr_acquisition_declarations.py',
    'apps/api/tests/test_hr_acquisition_persistence.py',
    'apps/api/tests/test_hr_acquisition_readiness_audit.py',
    'apps/api/tests/test_polar_hr_acquisition_api.py',
    'apps/api/tests/test_hr_acquisition_migration.py',
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
& $v245Python -m pytest -q @v245Tests
if ($LASTEXITCODE -ne 0) { throw 'A célzott tesztkör nem sikerült.' }
& $v245Python -m pytest -q apps/api/tests
if ($LASTEXITCODE -ne 0) { throw 'A teljes tesztkör nem sikerült.' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'A diff ellenőrzése nem sikerült.' }

docker compose up -d --wait --wait-timeout 60 db
if ($LASTEXITCODE -ne 0) { throw 'Az adatbázis indítása nem sikerült.' }
& $v245Python -m alembic -c apps/api/alembic.ini upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Az adatbázis-migráció nem sikerült.' }
& $v245Python -m alembic -c apps/api/alembic.ini current
```

Várt adatbázis-head: `c5e83a9d2714 (head)`. Új tábla és index keletkezik;
a V24.4 igazolásait és az edzésadatokat a migráció nem módosítja.
A Docker Desktop motorjának futnia kell.

### 3. Backend és élő próba

Egy második PowerShell-ablakban, a projekt gyökeréből:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

Az első ablakban futtasd a `CHECK_V24_5.ps1` segédet az ellenőrizni kívánt edzés
és gyakorlat azonosítóival, dátumával és a ténylegesen használt érzékelőadataival.
A konkrét élő parancsot a beszélgetés tartalmazza. Az általános paraméterek:

| Paraméter | Tartalom |
|---|---|
| `-SessionId`, `-SampleDate`, `-ExerciseId` | A kiválasztott valódi munkamenet, dátum és gyakorlat. |
| `-SensorModality`, `-BodyLocation` | A közölt érzékelőtípus és viselési hely; ismeretlen adatnál `UNKNOWN`. |
| `-SensorManufacturer`, `-SensorModel` | A ténylegesen használt szenzor gyártója és modellje, ha ismert. |
| `-ReportedIssueCodes` | Opcionális, ténylegesen észlelt mérési problémák. |

A segéd ment, ismétel, visszaolvas, majd elküld egy tiltott kliensoldali
minőségigazolást. Utóbbi HTTP 422-t kell kapjon, új rekord nélkül. Ellenőrzi a
korábbi exportigazolás megőrzését, és kiírja az audit új érzékelőmezőit is.
Nem hoz létre hamis érzékelőhelyesbítést a valós edzésen.

Várt állapot problémát nem közlő, egyértelmű nyilatkozatnál:

| Eredmény | Várt érték |
|---|---|
| Első / ismételt mentés | `CREATED` vagy korábbi azonos mentésnél `ALREADY_PRESENT`; ismételve `ALREADY_PRESENT` |
| Rekordazonosító egyezése, visszaolvasási integritás | `True`, `True` |
| Érzékelőközlés állapota / eredete | `USER_DECLARED_WITH_LIMITATIONS` / `USER_DECLARATION` |
| Szenzorazonosság / mérési minőség igazolása | `False` / `False` |
| Tiltott minőségmező HTTP-státusza | `422` |
| Korábbi alkalmazható TCX-igazolás megőrzése | `True`, ha a próba előtt volt ilyen igazolás |
| Modelltréning / numerikus előrejelzés | `False` / `False` |

Az audit egészének `WITHHELD` státusza a környezeti és egyéb bemeneti feltételek
miatt továbbra is indokolt lehet. A sikeres érzékelőmentés nem oldja fel ezeket.

### 4. Commit az élő ellenőrzés után

```powershell
$v245Files = @(
    'apps/api/alembic/versions/c5e83a9d2714_add_hr_acquisition_declarations.py',
    'apps/api/app/api/router.py',
    'apps/api/app/api/routes/polar.py',
    'apps/api/app/api/routes/polar_hr_acquisition.py',
    'apps/api/app/models/__init__.py',
    'apps/api/app/models/hr_acquisition_declaration.py',
    'apps/api/app/schemas/hr_acquisition.py',
    'apps/api/app/services/hr_acquisition_declarations.py',
    'apps/api/app/services/hr_acquisition_persistence.py',
    'apps/api/app/services/training_data_readiness_audit.py',
    'apps/api/tests/test_hr_acquisition_declarations.py',
    'apps/api/tests/test_hr_acquisition_persistence.py',
    'apps/api/tests/test_hr_acquisition_readiness_audit.py',
    'apps/api/tests/test_polar_hr_acquisition_api.py',
    'apps/api/tests/test_hr_acquisition_migration.py',
    'apps/api/tests/test_hr_timebase_migration.py',
    'docs/v24_5_hr_acquisition_declarations.md'
)
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'A diff ellenőrzése nem sikerült.' }
git add -- @v245Files
if ($LASTEXITCODE -ne 0) { throw 'A stage-elés nem sikerült.' }
git diff --cached --stat
git commit -m "Add scoped HR sensor declarations and acquisition provenance"
if ($LASTEXITCODE -ne 0) { throw 'A commit nem sikerült.' }
git push origin main
if ($LASTEXITCODE -ne 0) { throw 'A push nem sikerült.' }
git status --short
```

A régi HR-migráció tesztje az új headre lett igazítva; maga a V24.4 migráció
változatlan. A csomag többi tesztadata mesterséges, személyes exportot nem tartalmaz.

## Elvégzett ellenőrzés

A teljes tesztkörben **1120 teszt sikeres**, egy meglevő Starlette tesztkliens
elavulási figyelmeztetéssel. A tárolási és JSON-visszaolvasási próbák valódi
SQLite/SQLAlchemy adatbázist használnak. A PostgreSQL-migráció és JSONB DDL
ellenőrzése offline történt; az élő PostgreSQL-migrációt a saját környezetben
kell lefuttatni. A Windows/PowerShell segéd élő végrehajtása szintén ott következik.

A korábban megadott valós adatokkal végzett külön próba 3038 mintát és 1663 ms
eltolást igazolt. Az eredeti HR-validálási és TCX-döntéslenyomatok változatlanok
maradtak. Az érzékelőnyilatkozat mentése után a korábbi exportigazolás továbbra is
alkalmazható volt. A személyes fájlok kizárólag külön ellenőrzési bemenetként
szerepeltek, nem kerülnek a telepítő vagy a tesztadatok közé.

## Az érzékelőtípusok értelmezésének forrása

A Polar dokumentációja megkülönbözteti az optikai PPG és az elektromos
szívműködésen alapuló pulzusmérést. Ez a típusleírás technológiai kategória;
az adott edzés pontosságát nem igazolja.

- [Polar: optikai és mellkaspántos pulzusmérési módszerek](https://support.polar.com/en/support/what_are_the_pros_and_cons_of_wrist_based_heart_rate_measurement_and_measuring_heart_rate_with_a?category=training)
- [Polar: a csuklós pulzusmérés működése](https://support.polar.com/en/support/the_what_and_how_of_polars_wrist_based_heart_rate_measurement)
