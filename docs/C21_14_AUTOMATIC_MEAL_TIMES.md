# C21.14 – Automatikus étkezési időpontok

A mentett étrendek étkezési időpontjait az alkalmazás javasolja. A korábban mentett ételekhez is megjelennek az időpontok; emiatt nem kell újragenerálni az étrendet.

## Kiindulás és személyes beállítás

- Alapidőpontok: reggeli **07:30:00**, ebéd **12:30:00**, kisétkezés **16:00:00**, vacsora **19:00:00**.
- A beállított szokásos időpont az elsődleges kiindulás. Ennek hiányában legalább három, ténylegesen naplózott, azonos időzónában történt étkezésből a jellemző időpontot használjuk. Adat nélkül az alapidőpont érvényes.
- A napi **kézi időpont** mindig elsőbbséget kap. A másodpercek megmaradnak. Az adott napra kifejezetten üresen hagyott időpontot sem töltjük ki automatikusan.
- Az időpont mellett olvasható, hogy kézi beállítás, szokás, napló vagy automatikus alap alapján jelenik meg.
- A **Tervezett időpont** mező és az **Időpont mentése** gomb segítségével a napi javaslat átírható. Az **Automatikus időpont visszaállítása** gomb elhagyja a napi kézi felülírást és visszatér a számolt javaslathoz.

## Az edzésekkel való egyeztetés

A rendszer az adott felhasználó saját, aktív helyi edzésterveinek ismert időpontját és időtartamát használja. Polart vagy edzéstervezőt nem hív. A lemondott és más felhasználóhoz tartozó edzéseket figyelmen kívül hagyja. Éjfélen átnyúló edzést a következő napon is figyelembe vesz.

Az automatikus étkezési javaslat az ismert edzéssel nem fed át. Ehhez 30 perces étkezési ablakot, az edzés körül 15 perces ütemezési ráhagyást, az automatikus étkezések között legalább egyórás kezdési távolságot használunk. Ezek naptári szervezési alapértékek, nem személyre szabott emésztési vagy sporttáplálkozási előírások. Az elkészítési idő továbbra is külön adat.

Példa: a 19:00–19:57 közötti futásnál az alapból 19:00-ra eső vacsora 20:15-re kerül. Egy kézzel 18:12:34-re állított vacsora változatlan marad. Ütköző kézi időpontnál figyelmeztető szöveg jelenik meg, a rendszer nem írja át a választást.

Ismeretlen kezdés vagy időtartam esetén az időpontjavaslat jelzi a hiányos edzésadatot. Ha a megengedett időtartományban nincs szabad hely, az étel megmarad, az időpont pedig ellenőrizendő lesz. Korábbi napokra utólag nem gyártunk feltételezett tervezett időpontot; a már megadott időpontok és a tényleges fogyasztás megmaradnak. Az automatikus javaslat kerüli az óraátállítás nem létező és kétszer előforduló helyi óráit.

## Mentés és megjelenítés

Az automatikus időpont számolt javaslat. Az étrend és a tényleges fogyasztási napló megőrzött forrásait nem írjuk át. Az edzések későbbi változása friss beolvasáskor módosíthatja az automatikus időpontot; a napi kézi felülírás ekkor is megmarad.

A naptár és az étrendtervező ugyanazt a szabályt használja. A meglévő naptári gyorsítótár megmarad; az étkezési ablak megnyitása nem kér külön naplót és nem indít új tervezést. A régebbi mentések és korábbi válaszverziók továbbra is olvashatók. Adatbázis-migráció és új függőség nincs.

**Ez a bővítés az étkezések időzítését valósítja meg. Az energia-, makro- és mikrotápanyag-szükséglet számítása még nincs bekötve.**

## Telepítés és indítás

A Git-patch a `80eb4e1` C21.13 commitra épül, külön `codex/c21-14-automatic-meal-times` ágon alkalmazható. Állítsd le a régi frontend- és API-folyamatot a saját termináljában Ctrl+C-vel, majd a csomag README-jében lévő telepítési blokkot használd.

Ellenőrzés a projekt gyökeréből:

```powershell
& .\.venv\Scripts\python.exe .\tools\run_c21_14_checks.py
```

Az API külön ablakban, a projekt gyökeréből:

```powershell
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

A frontend másik ablakban az `apps\web` mappából:

```powershell
npm.cmd run start
```

A http://localhost:3000/nutrition fejlécében Ctrl+F5 után **C21.14** jelenjen meg. Sikeres helyi ellenőrzés után az új ág a saját GitHub-hitelesítéssel feltölthető:

```powershell
git push -u origin codex/c21-14-automatic-meal-times
```

## Kiadási ellenőrzések

- 115 backend- és 1952 frontend-regressziós teszt, TypeScript, ESLint, route typegen, 13 buildvédelmi teszt és Next.js 16.4.6 production build sikeres.
- Valódi FastAPI-válaszok és a frontend egymástól független időpontszámítása megegyezik. Külön ellenőrzött a kézi időpont és kézi üresség elsőbbsége, a szokások és a legalább három naplóbejegyzésből vett jellemző idő, az esti/éjszakai edzés, az ismeretlen időtartam, a lemondott és idegen edzés kizárása, a teljesen foglalt nap és a két óraátállítás.
- Valódi FastAPI + React StrictMode próba JSDOM-ban: automatikus 20:15-ös vacsora, kézi 18:12:34 mentése és újranyitása, naptári egyezés, visszaállítás automatikusra, nulla nyitáskori külön naplólekérés, változatlan tényleges fogyasztás és edzésadatok.
- Production HTTP-próba a táplálkozási oldalon és a naptáron. Ez nem képernyős mobil- vagy böngészőellenőrzés.
