# PFT mérési integráció, v0.1

A PaddleTrainer API-ba beillesztettük a PFT-RUN 0.1 mérési feldolgozását,
a javított RHRI v0.2 számítással. A működés méréseket és összehasonlítható
megfigyeléseket tárol; fáradtság/fittség pontszámot vagy edzésterhelés-emelést
nem ad. Új referenciafelvételek nélkül is használható adatgyűjtési alap.

## A jelen változat hatóköre

A PFT teljes TCX-felvétele beolvasható. A nyers XML megmarad, a feldolgozás
megtartja a pulzus- és teljesítményidőket, az észlelt terhelésváltásokat,
a 11 alapmutatót, az RHRI-változatokat és a minőségi jelzéseket.
A szakaszok utolsó 30/45/60 másodpercének átlagpulzusa és tényleges
teljesítménye külön kontextusriportot kap.

A közvetlen Polar PFT-capture még nincs bekapcsolva: a v4 intervallumos
pulzus- és POWER-sorok első mintájának közös időkezdete nincs igazolva.
A jelen API-alapú időillesztési munka emiatt nem tekinthető automatikusan
pulzus–teljesítmény időbizonyítéknak. A PFT TCX-ág erre az első mérésre
teljes feldolgozási útvonalat ad. Nem kerülünk át becsült GPS-terhelésre,
és nem címkézzük a feltöltést szolgáltató által hitelesített API-forrásnak.

A frontend forrása nem volt a kapott API-projektben. Ez a csomag backend
integráció és API-s felület; külön grafikus PFT-képernyőt nem tartalmaz.

## Végpontok

Az alapértelmezett előtag `/api/v1`.

| Művelet | Útvonal | Eredmény |
| --- | --- | --- |
| GET | /pft/capabilities | Protokoll, forrástípus és korlátok |
| POST | /pft/measurements/tcx | Nyers TCX beolvasása és mentése |
| GET | /pft/measurements | Mérési változatok listája |
| GET | /pft/measurements/{id} | Feldolgozási eredmény és kontextus |
| POST | /pft/measurements/{id}/reprocess | Új feldolgozási/kontextusváltozat |
| POST | /pft/measurements/{id}/compare | Leíró összehasonlítás |

A TCX-POST törzse maga az XML. A `X-PFT-Context` fejléc JSON-deklaráció;
ne Unicode karaktereket írjunk közvetlenül a HTTP-fejlécbe, hanem a JSON
ASCII-escape formáját használjuk. A fejlécben kötelező a profilazonosító és
a három célwatt. A 380/460/550 W csak a felhasználó példaprofiljában szerepel,
nem általános sportolói alapérték.

A `pft_start_offset_s` alapértéke 0. Ha a felvétel a PFT előtt bemelegítést is
tartalmaz, itt jelölhető a PFT kezdete az első TCX-mintától. A feldolgozás
legfeljebb 810 s-nyi PFT-környezetet vesz: a névleges 780 s és az észlelt
leállás késéséhez szükséges rövid végablak. Az eredeti teljes felvétel megmarad.

A részletes GET `include_samples=true` kapcsolóval visszaadja a nyers,
időbélyeges adatokat. A megjelenített `speed_mps_derived` kifejezetten
a TCX távolságváltozásából és tényleges időközéből számított sebesség;
nem nevezzük eredetileg rögzített SPEED-sornak.

## Tárolás és tulajdonos

Két új, központi adatbázistábla keletkezik:

- `pft_recordings`: eredeti TCX, ellenőrző összeg, időbélyegek és a
  kanonikus, időbélyeges minták azonosítója.
- `pft_measurements`: algoritmus, beállítások és deklarált körülmények
  szerinti feldolgozási változat, eredmény és ellenőrző összeg.

Azonos sportoló azonos időbélyeges jelét nem számoljuk új felvételnek,
akkor sem, ha a fájlneve vagy a XML szóközei változtak. Az újrafeldolgozás
új mérési változatot adhat, de ugyanahhoz a felvételhez kapcsolódik.
A korábbi változatokat nem írjuk felül. A tulajdonos kötése adatbázisban
összetett idegen kulccsal is szerepel.

A jelen alkalmazás a meglévő `get_or_create_demo_user` azonosságmodellt
használja; új bejelentkezési rendszert nem vezettünk be. A kérésből nem
fogadunk sportolóazonosítót vagy fiziológiai hitelesítési állítást.
A szerver minden listázást és lekérdezést a kiválasztott alkalmazásbeli
felhasználóra szűr. Többfelhasználós hitelesítéshez később a
`pft_owner` függőséget kell a valódi bejelentkezett felhasználóhoz kötni.

## Összehasonlítás és időbeliség

A profilnak, szenzor-/teljesítmény-kontextusnak, protokollnak, előkészítésnek
és regenerációs módnak egyeznie kell. A feldolgozási szabályok és algoritmusok
eltérése is megállítja az összehasonlítást. Az egyező deklaráció nem bizonyít
azonos fáradtságot, hidratációt vagy tényleges külső terhelést.
A terhelésadatokat ezért a leíró eltérések mellett megőrizzük.

A szerver mentési ideje adja az eredmény rendelkezésre állási idejét.
A válasz jelzi, ha a referencia a másik PFT kezdete előtt még nem volt
feldolgozva/elérhető. Minden jelen összehasonlítás utólagos és leíró:
nem válik automatikusan edzés előtti prediktorrá. A 2026. október 9-i PFT
nem kerül vissza a május–augusztusi HR-modellek előzetes bemenetei közé.

A `baseline_eligible` a megtartott PFT-motorban numerikus/minőségi jelzés.
A wrapper ezt `FEATURE_NUMERICAL_COMPLETENESS_ONLY` hatókörrel jelöli;
nem bizonyít regeneráltságot vagy függetlenül hitelesített csuklós mérést.
Nem módosítjuk az AthleteReadiness, AthleteCapacity, edzéstervek vagy
korábbi ML-értékelések adatait.

## Migráció és követelmények

Az új Alembic revízió `b8e4d6a10f32`, szülője a meglévő
`e4f7a92c1836`. Csak a két új táblát és indexeiket hozza létre.
Az API csomag függőségei NumPy >=2.3.2,<3 és SciPy >=1.16.1,<2
követelménnyel bővülnek. A PFT-motor a csomag saját app.pft_engine névterében van, így nem ütközik
a külön PFT-subproject telepítésével. Az importok névterét igazítottuk ehhez;
a számítási algoritmus változatlan. Külső projektútvonal
vagy egy másik helyi repo nem szükséges.

A beillesztés őrzött: `apply_pft_integration.py` minden módosítandó fájlt és
az eredeti migrációs fejet előzetesen ellenőrzi. Eltérő aktuális forrásnál
érintetlenül megáll. Ekkor az eltérések alapján a csomagot kell frissíteni,
nem felülírni a jelenlegi kódot. A script csak kódfájlokat másol;
adatbázis-migrációt és függőségtelepítést nem futtat.

## Ellenőrzési státusz

Itt a valódi első TCX feldolgozása és a bemeneti szerződés 19 sikeres teszttel
ellenőrzött (Python 3.12.14; NumPy 2.3.5; SciPy 1.17.0; Pydantic 2.13.5).
A javított motor kódja a korábban 130 teszttel ellenőrzött csomagból származik.
Az új API-kód, a migrációs lánc és a csomag szintaktikai ellenőrzést kapott.

Ebben a környezetben FastAPI, SQLAlchemy, Alembic és HTTPX nem érhető el,
és telepítésük sem sikerült. Ezért a HTTP/ORM és migrációs teszteket itt
nem futtattuk; PostgreSQL éles migrációt sem végeztünk.
A `test_pft_measurement_api.py` és `test_pft_measurement_migration.py`
valódi TestClient/SQLite/ORM ellenőrzést tartalmaz, a PostgreSQL DDL-re is.
Ezeket a saját API-környezetben kell futtatni a használat előtt.

## Javasolt futási sorrend

1. Csomag kibontása, őrzött forrásbeillesztés.
2. Az API virtuális környezetében a bővített függőségek telepítése:
   `python -m pip install -e ".[dev]"`.
3. A `run_pft_api_checks.ps1` futtatása: PFT tesztek, érintett korábbi
   migrációs tesztek és a teljes API import/útvonal ellenőrzése.
4. Siker után az API könyvtárból `python -m alembic upgrade head`,
   majd az API újraindítása.
5. A mellékelt `probe_first_pft.py` feltölti az első felvételt, ismétli a
   mentést, és ellenőrzi az azonos mérésazonosítót és a visszaolvasást.

A próbafeltöltés a PFT-táblákba ír, a tesztek ideiglenes SQLite-adatbázisokba.
Ez továbbra is az első, egyetlen ismert referenciafelvétel beillesztése;
nem új fiziológiai mérés és nem személyes állapotmodell-tanítás.

## Hivatalos technikai támpontok

- [FastAPI aszinkron és szinkron végrehajtás](https://fastapi.tiangolo.com/async/):
  a számításigényes illesztést külön threadpool-feladatként indítjuk.
- [SQLAlchemy összetett idegen kulcsok](https://docs.sqlalchemy.org/en/20/core/constraints.html):
  egyetlen összetett kapcsolat köti a mérést a felvétel és tulajdonos párjához.
- [Alembic revíziós lánc](https://alembic.sqlalchemy.org/en/latest/tutorial.html):
  az új táblák a meglévő lánc végére kerülnek.
