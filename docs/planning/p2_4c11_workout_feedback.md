# P2.4C11 — saját edzés-visszajelzés

Az edzésrészletek jobb oldali oszlopában a **Saját visszajelzés** kártya jelenik meg. A két külön lap az edzés utáni és a másnap reggeli állapotot tárolja.

- Nehézség (RPE), fáradtság, izomláz, regeneráltság és energiaszint: 0–10, legfeljebb egy tizedes.
- Az üres mező ismeretlen; a nulla érvényes válasz. Nem szükséges minden kérdésre válaszolni.
- A megjegyzés opcionális, legfeljebb 2000 karakter. Legalább egy pontszám vagy nem üres megjegyzés szükséges.
- A magasabb RPE/fáradtság/izomláz erősebb érzetet, a magasabb regeneráltság/energia kedvezőbb saját állapotot jelöl. Ezek önbevallások, nem objektív élettani mérések.
- A megfigyelés időpontját a felhasználó adja meg, az egyértelműség érdekében UTC-ben. A mentés szerverideje külön adat. Utólagos kitöltésnél az időpontot módosítani kell.
- A megfigyelés nem előzheti meg a tárolt edzés végét (ennek hiányában a kezdetét), és nem lehet jövőbeli. A másnapi megfigyelés helyi napja a profil időzónájában az edzés befejezése utáni nap. A rendszer nem állítja, hogy ellenőrizte a felhasználó ébredési idejét.

## Tárolás és tudományos felhasználás

Új `SESSION_FEEDBACK` auditfajta a meglévő `planning_audit_artifacts` táblában. Új tábla vagy migráció nem szükséges, a korábban alkalmazott audit-migrációknak azonban jelen kell lenniük. Egy mentés egy új, változatlan tartalmú auditbejegyzés. Az adott edzés és időzítés javításai sorszámozott, hash-ekkel kapcsolt láncot alkotnak; az előzmények a kártyán megnyithatók.

A `WorkoutSession.rpe`, a Polar nyers adatai, a terv és a korábbi `AthleteResponse` sorok változatlanok. A felület a korábbi edzés-RPE-t „RPE · forrásérték” néven mutatja. A C11 saját RPE-je ettől külön szerepel.

A C11 auditjai **még nem kerülnek automatikusan** a korábbi `CurrentAppLockedAthleteResponseSource` tanulási adatfolyamába. A későbbi adapternek explicit módon ki kell választania a használni kívánt revíziót és a megfigyelés időzítését. Az összes javítás külön megfigyelésként való összegzése hibás lenne. A panel nem módosít edzéstervet és nem ad diagnózist vagy edzésengedélyt.

## API és tranzakció

`GET /api/v1/planning/calendar/sessions/{UUID}/feedback`: csak a kiválasztott tulajdonos edzése; a teljes, ellenőrzött lánc és a két időzítés legutóbbi változata. A korlát edzésenként 2000 bejegyzés; túllépéskor nincs csendes csonkítás.

`POST` ugyanitt: UUID `request_id`, `timing`, `expected_revision`, időzónás `observed_at`, öt nullable numerikus pontszám és `comment`. Az ismeretlen mezők, boolean/string pontszámok, nem véges számok és időzóna nélküli időpontok elutasítva.

A meglévő tulajdonosi sor `FOR UPDATE` zárolása sorosítja az írásokat PostgreSQL-en. Az elvárt revízió eltérése 409; idegen edzés 404. A kérésazonosító tulajdonoson belül egyedi. Az azonos kérés újraküldése a korábban commitolt bejegyzést adja vissza (200), más tartalommal vagy másik edzéshez nem használható fel. Új bejegyzés 201, kizárólag sikeres commit után. A szerver a tárolt tartalmat és annak hash-ét visszaolvassa és ellenőrzi.

A Next proxy csak a pontos UUID-s visszajelzési útvonalon enged GET/POST kérést; query és egyéb metódus nem engedélyezett. A meglévő origin-, méret-, credential- és redirect-korlátok megmaradnak.

## Piszkozat, megszakadás, párhuzamos lapok

A piszkozat a böngésző `localStorage` tárában, sportolóhoz és edzéshez kötve marad meg. Személyes megjegyzést is tartalmazhat: közös böngészőprofilban ennek megfelelően kezelendő. A piszkozat tartalmazza azt a revíziót, amelyen a szerkesztés elkezdődött. Egy újraolvasás nem adhat észrevétlenül engedélyt egy közben másik lapon mentett változat felülírására.

Mentés előtt a pontos kérés bájtjai és azonosítója tartósan megmaradnak. Ismeretlen kimenetelnél a mezők zároltak, és az **Azonos mentés újrapróbálása** gomb ugyanazokat a bájtokat küldi. Csak a tulajdonost, edzést, kérés tartalmát, támogatott sémát, hash-t és commitot igazoló válasz zárhatja le. Határozott 4xx elutasítás után a piszkozat szerkeszthető; 409 revízióütközésnél előbb explicit előzmény-újraolvasás szükséges. A Polar szinkron vagy az edzésnézet újratöltése nem törli a piszkozatot.

## Ellenőrzés

Izolált SQLite HTTP-tesztek: tulajdonosi védelem, zero/null, külön időzítések, revízióütközés, azonos kérés ismétlése, elutasított és fizikailag sikeres, de visszaigazolás nélküli commit, szolgáltatói összesítő változása. A tesztkapu nem hív szolgáltatót vagy alkalmazás-adatbázist. A SQLite-tesztek nem szimulálják a PostgreSQL tényleges párhuzamos sorzárolását; azt a szolgáltatás meglévő tulajdonosi zárolási mintája biztosítja.

A Pythonból létrehozott szintetikus artifact-fixture-t a frontend hash- és válaszellenőrzője is feldolgozza. React DOM/JSDOM vizsgálatok tesztelik a piszkozat visszaállítását, az elveszett válasz utáni azonos ismétlést, a két lap revízióütközését és a szöveges megjegyzés biztonságos renderelését. További kapuk: teljes frontend tesztsor, TypeScript, érintett fájlok ESLint-ellenőrzése és production build. Helyi Windows böngésző és élő PostgreSQL/Polar próba nincs a szintetikus kapuban.
