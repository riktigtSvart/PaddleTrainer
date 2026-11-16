# C21.10.11 — naptárbetöltés kalibrált erősítő edzés mellett

A telepített C21.10.10-re készült javítás. A backend futó forrásai, adatbázisa, a mentett felmérések és az edzésadagolás változatlanok.

## A hiba

Az új részletes edzésutasítás naptári ellenőrzése minden erősítő sorozatnál már ismert, legalább három ismétlésnyi tartalékot várt. A kalibrált kezdősorozat azonban más adattípus: a felmért ismétlésszámból csökkentett tervszám készül, és a még el nem végzett sorozat tényleges tartaléka helyesen `unknown`. A hozzá tartozó `calibration_derivations` külön tárolja a mért tartalékot és az új sorozatra előírt minimumot.

Valódi, korábban exportált kalibrációs adatokon reprodukáltuk az „Az edzés gyakorlatsora eltér a mentett terheléstől vagy időkerettől” hibát. A felmérés és a tervezett dózis szabályos volt; a C21.10.10-es frontend tévesen utasította el. Az opcionális részlet elutasítása az egész naptári válasz betöltését megszakította.

## Javítás

A kalibrált kezdősorozat jövőbeli, ismeretlen tartaléka elfogadható, ha az eredeti levezetés összefüggései megmaradnak: a gyakorlat és megfigyelés azonosítója egyezik, van formailag helyes forráshivatkozás, egyetlen csökkentett sorozat készül, az ismétlésszám `min(8, mért ismétlés − 2)`, a felmért tartalék támogatott, az előírt minimum három és a pihenő három perc. A hiányzó, ismétlődő, másik megfigyelésre hivatkozó vagy ellentmondó levezetés nem fogadható el. A hagyományos saját referenciasorozatnál az ismeretlen tartalék ettől még nem válik elfogadhatóvá.

A táblázat a mért tartalékot mutatja a referencia oszlopában. A szöveg világosan elkülöníti ezt az új kezdősorozat legalább háromismétléses előírásától. A még nem mért tartalékot nem írjuk ki `unknown ismétlés` formában. Tárcsás gépi levezetésnél a terhelés jelentése továbbra is a felrakott tárcsák össztömege.

Az opcionális részletes gyakorlatsor hibája most csak az érintett panelt teszi elérhetetlenné. A naptár megőrzi a dátumot, az eseményeket, a mentett célt és az eredeti edzésleírást, és rövid jelzést mutat. Nem ellenőrizhető súly- vagy sorozattáblázat nem jelenik meg. Az alapadatok, a célforrás és a cikluskapcsolat hibája továbbra is elutasítja a választ; a csak olvasó kiegészítés leválasztása ezeket az ellenőrzéseket nem kerüli meg. Az eredeti API-választ nem módosítjuk.

A teljes edzésadatlap ugyanezt a hibát elkülöníti, és újraolvasási lehetőséget ad. A rendes naptári működéshez nem szükséges új felmérés, újrahitelesítés vagy újratervezés.

## Ellenőrzés

- Négy új, valódi HTTP API-regressziós eset: régi és új elfogadás, két- és háromismétléses felmért tartalék. A mérések, hivatkozások, felmérési eredmények és a rekordok száma az olvasástól nem változik.
- A teljes frontendkészlet 1688 sikeres tesztje; ezekben új és régi tényleges API-válaszok betöltése, hibás levezetések elutasítása, a megmaradó események, az eredeti válasz változatlansága és az alapellenőrzések megőrzése.
- Next útvonaltípusok, TypeScript, az érintett fájlok figyelmeztetésmentes ESLint-ellenőrzése és production build sikeres.
- Valódi FastAPI + React StrictMode/JSDOM próba a teljes naptárral: kezdő betöltés és dátum, kalibrált edzésablak, mért és előírt tartalék külön, változatlan súly/ismétlés/pihenő, szándékosan hibás opcionális panel mellett is használható naptár, eredeti leírás, teljesadatlap-újraolvasás. Nem volt POST, az audit-, edzés- és teljesítéssorok száma nem változott. Natív Chromium vizuális ellenőrzés nem történt.

A C21.10.10 backendjének 2350 tesztje a felhasználó csatolt naplójában már sikeres. A javítás nem módosít backend-futókódot; ezért a csomag ajánlott telepítési ellenőrzése a `tools/run_c21_10_11_checks.py --frontend-only`. Kapcsoló nélkül a teljes backend-tervezési készlet is futtatható.
