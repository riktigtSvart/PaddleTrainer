# C21.5 – Alapadatok és sportolási keretek szétválasztása

A C21.4 frissítésre épül. Az Alapadatok / tervezési adatok szerkesztőiben egyetlen látható mentési rész marad a blokk alján.

## Felület és mentés

- A Személyes alapadatok négy fő mezője: születési dátum, biológiai nem, testtömeg és magasság. A testméretek mérési dátuma lenyitható kísérőadatként megmarad. Hibás dátumnál a rész automatikusan kinyílik a mezőellenőrzéskor.
- A Sportelőélet elejére kerülnek a korlátozások és alkalmazkodás, a részvételi keret, a heti edzéskeret, a kihagyás és visszatérés. Ezek után következik a sportágankénti tapasztalat. A további sportolási beállítások lenyithatók.
- A Személyes adatok mentése csak a személyes mezők változásait rögzíti. A Sportelőélet mentése a sportmúlt mellett az áthelyezett sportolási kereteket is menti. A másik blokk mentetlen szerkesztése megmarad.
- A piszkozatjelzések és a mentett adatok hiányosságainak jelzése követi az új elrendezést. A tervezés teljes feltételrendszere továbbra is érvényes.
- A közös lábléc az eredeti mentési műveletet indítja. Az eredeti gomb a beágyazott szerkesztőben rejtett; így nincs második látható mentési gomb, miközben megmarad a natív űrlapellenőrzés és az eredeti mentési logika. Az önálló oldalakon az eredeti gomb látható.

## Adatok és kompatibilitás

Nincs backend-, séma- vagy adatbázis-módosítás, migráció vagy új függőség. A korábban mentett profiladatok visszatölthetők. A teljes profil továbbra is egy API-művelettel, az előző változathoz kötve kerül mentésre; a frontend állítja össze a kiválasztott blokk mezőiből és a többi blokk mentett adataiból. A C21.4 függő mentési visszaállítása és az eredeti kérés megőrzése változatlanul működik.

## Ellenőrzés

`python tools/run_c21_5_checks.py`: 1244 frontendteszt, Next route-típusok, TypeScript, ESLint és production build.

Külön DOM-ellenőrzés: egy látható személyes és sportelőélet-mentési gomb és magyarázat; az aktív helyszínszerkesztő mentése; a natív kötelezőmező-ellenőrzés; a rejtett rész hibás mérési dátumának megjelenítése; tiltott állapot és aktív alszakasz követése; navigáció közben nincs mentés.

Valódi API-val futó DOM-ellenőrzés: korábbi függő profilmentés igazolása, testméretek mentése befejezetlen sportbejegyzés és módosított edzéskeret mellett, a sportolási változtatások megőrzése és későbbi külön mentése. Böngészős képernyőképes ellenőrzés nem készült.

A csomag telepítője LF és CRLF sorvégekkel ellenőrzi az alapfájlokat, helyi eltérésnél írás nélkül megáll, biztonsági másolatot készít, ismételten is alkalmazható, és támogatja a pontos visszaállítást.
