# C21.10.12 — Windows-kódolás és egyértelmű munkasorozatok

A telepített C21.10.11-re épülő backend- és frontendjavítás. Nincs új függőség, adatbázis-migráció vagy edzésadagolási változás.

## A tényleges elakadás

A megvizsgált naptári válaszban a saját referenciasorozatok és az eredeti edzésleírás összhangban voltak. A bemelegítő és nyújtó könyvtárból átvett szövegek viszont eltérő karakterkódolással jelentek meg. A `training_instructions.library()` korábban explicit kódolás nélkül olvasta az UTF-8 JSON-fájlt. Magyar Windows-környezetben a CP1250 alapértelmezés ebből hibás ékezeteket készített, miközben a frontend ugyanazt a könyvtárat helyesen importálta. Emiatt a pontos tartalomegyezést ellenőrző kód elutasította a részletes panelt.

A könyvtár olvasása most kifejezetten `encoding='utf-8'`. A felmérésekből származó súlyok, ismétlések, sorozatok és tartalékok változatlanok.

## Korábban elfogadott tervek

A hibás könyvtárszöveg bekerülhetett a már elfogadott, változtathatatlan felülvizsgálati forrásba. A puszta UTF-8 javítás után ennek a régi forrásnak az ellenőrzése is eltérést jelezne. Emiatt a javítás a két ismert régi Windows-értelmezést, CP1250-et és CP1252-t is felismeri.

A kompatibilitás teljes objektumegyezést követel az eredeti jelöltből, az eredeti előírásból és az ismert régi kódolású könyvtárból előállított változattal. Nem általános szövegjavítás: a felhasználó saját leírását, a súlyokat, ismétléseket, időket és forráshivatkozásokat nem alakítjuk át. Tetszőlegesen átírt gyakorlatsor vagy megváltoztatott munkadózis továbbra sem fogadható el.

A backend a régi elfogadást változatlanul ellenőrzi, de az olvasó naptári vetületbe már a helyes UTF-8 gyakorlatsort teszi. A frontend a még régi folyamatból érkező ismert kódolású választ is meg tudja jeleníteni. A teljes felülvizsgálati objektumot és annak eredeti hashét nem módosítja; a tervnézet a már ellenőrzött forrásból állítja elő a helyes megjelenítést.

Sem az eredeti auditforrást, sem az edzéssort, sem a felmérést nem írjuk át. A helyes szöveghez nem kell új felmérés, újrahitelesítés vagy újratervezés. A backend újraindítása szükséges a régi könyvtárcache elengedéséhez.

## Látható sorozatszám

Az erősítés főrésze külön **Előírt munkasorozatok** összegzést kap. Az összes munkasorozat mellett gyakorlatonként is szerepel például `1 × 12 ismétlés` vagy `2 × 8 ismétlés`. Különböző sorozatok eltérő ismétlésszámai és a tartásidők megmaradnak. A táblázat sorozatoszlopában a sorszám és az összes sorozat is látszik, például `1. / 1` vagy `2. / 2`.

A szöveg külön jelzi, hogy a sorozatszám rögzített: a megmaradó idő miatt nem kell új sorozatot hozzáadni. A 20 perces edzésnél az 5 perc bemelegítés, a legfeljebb 10 perces főrész pihenőkkel és az 5 perc levezetés a meglévő felső időkeret része. A frissítés nem növeli az edzés idejét vagy munkamennyiségét.

## Ellenőrzések

- A teljes backend-tervezési készlet: **2361 sikeres teszt**.
- A teljes frontendkészlet: **1703 sikeres teszt**.
- Next útvonaltípusok, TypeScript, az érintett fájlok figyelmeztetésmentes ESLint-ellenőrzése és production build sikeres.
- A Windows alapértelmezett kódolását szimuláló teszt ellenőrzi az explicit UTF-8 olvasást. Valódi HTTP-teszt mindkét régi kódlappal mentett és elfogadott tervet olvas újra, változatlan auditforrásokkal, edzésekkel és felméréssel.
- A frontend tényleges API-exportokon ellenőrzi a régi és új válaszokat, az eredeti forráshash megőrzését, a helyes magyar szöveget, a konkrét sorozatszámokat és a megváltoztatott dózis elutasítását. A tesztadatok mesterségesek; felhasználói azonosítók és személyes felmérési adatok nem kerültek a regressziós csomagba.
- Valódi FastAPI + React StrictMode/JSDOM próba a teljes naptárral, edzésablakkal, teljes edzésadatlappal és régi felülvizsgálattal. Helyes ékezetek és sorozatok mind a javított backend, mind a még régi kódolású válasz esetén; nincs POST vagy megváltozott audit-, edzés- és teljesítéssorszám. Natív Windows és natív Chromium vizuális próba nem történt.

`tools/run_c21_10_12_checks.py` kapcsoló nélkül a teljes kapu. A `--focused-backend` a kódolási és naptári regressziós részhalmaz után a teljes frontendkaput futtatja; telepítéskor ez az ajánlott rövidebb ellenőrzés. A `--frontend-only` csak azonos forrásokkal már sikeres backendellenőrzés után használható.
