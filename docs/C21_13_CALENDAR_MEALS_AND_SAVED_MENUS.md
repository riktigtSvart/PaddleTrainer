# C21.13 – Mentett étrend és naptári étkezésnapló

## Mit lehet használni?

- A táplálkozási oldalon az **Étrend tervezése és mentése a naptárba** gomb az összeállítás után rögtön elmenti az étrendet és a bevásárlólistát. Újranyitáskor a legutóbbi mentett időszak töltődik be.
- Ételcsere, adagszorzó és bevásárlólista szerkesztése után a **Mentés a naptárba** vagy **Módosítások mentése** gombbal menthetsz. A félbehagyott módosítások ugyanabban a böngészőben piszkozatként megmaradnak. A piszkozat még nem adatbázisba mentett étrend.
- A naptárban az **Étkezések és étkezési napló** réteg be- és kikapcsolható, nézetenként megjegyezve. Nap/hét nézetben a nap fejlécében látszanak a tervezett étkezések és az időpontjaik. Négyhetes és áttekintő nézetben a napi étkezésösszesítő gomb nyitja a listát.
- Egy étkezésre kattintva a **Megettem**, **Kihagytam**, illetve **Más adag / időpont** kezelhető. A fogyasztás egy személy saját adagjára vonatkozik; a háztartás létszámát nem számoljuk saját bevitelnek.
- Az **Étkezési napló / hozzáadás** gombból nem tervezett étel vagy ital is rögzíthető, és a korábbi bejegyzés javítható. A naptárban kiválasztott napot kínáljuk fel; a tényleges időt meg kell adni. Jövőbeli fogyasztás nem jelölhető megtörténtnek.
- A felugró ablak a Bezárás gombbal, Escape-pel vagy az ablakon kívülre kattintva bezárható. Az adatbázisba már mentett fogyasztás megmarad.
- Az ételkártya tetején az étkezési időpont szerepel. Az elkészítési idő az **Alapanyagok és elkészítés** részben van. Meg nem adott étkezési időpont helyett nem használunk elkészítési időt.

## Új étrend és meglévő dátumok

Az új mentés a kijelölt dátumok teljes étkezési tervét cseréli. Más dátumok korábbi étrendje a naptárban megmarad. Hárométkezéses napra váltáskor például nem marad vissza az előző terv negyedik étkezése.

Az étkezésnapló ettől független történeti adat. A korábbi étel elfogyasztása megmarad, de egy eltérő receptet vagy személyes adagot nem jelölünk emiatt automatikusan elfogyasztottnak. A bevásárlólista puszta mentése nem vonja vissza az ugyanolyan ételre és adagra adott fogyasztási visszajelzést.

Az étrendtervező a legutóbbi mentést nyitja meg, a korábbi időszakok a naptárból érhetők el. Ha közben másik ablakból megváltozott a mentett állapot, a helyi piszkozat megmarad, és külön gombbal lehet átvenni az új alapot. A figyelmeztetés újranyitáskor is megmarad, amíg ez meg nem történt.

## Edzések és energiaigény

**Az edzésekből számított személyes energia- és makrotápanyagigény még nincs bekötve.** A bevitt erősítés, futás vagy kajakozás önmagában nem módosítja a receptadagokat. A jelenlegi mennyiségek általános, szerkeszthető kiinduló adagok; nem egyénre számolt kalória- vagy makróelőírások.

A korábbi cél-, labor- és szakembertől kapott étrendicél-rögzítés megmarad. Nincs automatikus mikrotápanyag-megfelelőségi értékelés vagy pótlási dózis. Ezt a korlátozást az étrendtervező is jelzi.

## Sebesség és adatok

A naptári étkezésréteg mentett helyi adatokat olvas. Nem hívja a Polart, nem indít edzéstervezést, nem ír edzéstervet és nem foglal edzésidőkeretet. A betöltött hónapon belüli nap/hét váltás helyi adatokból történik; az étkezési ablak megnyitásakor nincs új naplólekérés.

A mentés kérésazonosítóhoz kötött. Megszakadt válasz esetén az eredeti kérés eredménye ellenőrizhető, így a fogyasztás nem duplázódik. Az étkezésréteg olvasási hibája nem rejti el a működő edzésnaptárt. A naptári API csak a beállított felhasználó saját adatait és legfeljebb 366 napot olvas. A történetkeresés 3000 mentett étrendre korlátozott; hiányos történetet nem mutat hiánytalan állapotként.

## Frissítés Git-patchből

A kiadás a `8ea52d1` commitra épül. A forrás külön helyi Git-ágon elkészült; ebben a környezetben nincs GitHub írási hitelesítés, ezért a csomag egy teljes, bináris tesztadatot is tartalmazó Git-patchből telepíthető. A patch saját commitot készít a helyi repóban.

Állítsd le a korábbi frontend- és API-folyamatot a saját termináljukban Ctrl+C-vel. Csomagold ki a `PaddleTrainer_C21_13_Git.zip` fájlt a Letöltések mappába, és az ott található README lépéseit használd. A telepítés előbb `git apply --check` ellenőrzést végez, majd külön `codex/c21-13-calendar-nutrition` ágat készít és `git am` paranccsal alkalmazza a commitot.

A projekt gyökerében az ellenőrzés:

```powershell
& .\.venv\Scripts\python.exe .\tools\run_c21_13_checks.py
```

Függőségváltozás nincs; a már telepített Next.js 16.4.6-ot használjuk. A kapu friss production buildet készít. Sikeres kapu után a saját hitelesítéseddel feltölthető az ág:

```powershell
git push -u origin codex/c21-13-calendar-nutrition
```

Az API külön terminálban, az eredeti projekt gyökeréből:

```powershell
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

A frontend másik terminálban:

```powershell
Set-Location 'C:\Users\gyula\OneDrive\Dokumentumok\PaddleTrainerProject\apps\web'
npm.cmd run start
```

Nyisd meg a http://localhost:3000/nutrition oldalt, és frissíts Ctrl+F5-tel. A fejlécben **C21.13** legyen látható. A naptár az alkalmazás kezdőoldala.

## Ellenőrzés

- 102 backend és 1932 frontend regressziós teszt.
- Next route typegen, TypeScript, ESLint és 13 buildvédelmi teszt.
- Next.js 16.4.6 production build; a táplálkozási oldal és a naptár production HTTP-válasza.
- Valódi FastAPI + React StrictMode integráció: tervezés és mentés, oldalváltás utáni piszkozat, ismételt újranyitáskor is megőrzött párhuzamos szerkesztési ütközés, korábbi időszak megőrzése, naptári közvetlen fogyasztás, elveszett mentési válasz duplázás nélküli helyreállítása, saját/háztartási adag különválasztása, nem tervezett étel mentése, külső kattintásos bezárás, nap/hét váltás új étkezéslekérés nélkül, négyhetes réteg és változatlan edzések.

A React/FastAPI próba JSDOM-ban futott; ez nem helyettesít képernyős mobil- vagy böngészőellenőrzést. Személyes adatbázist vagy valódi Polar-adatot a tesztek nem használtak.
