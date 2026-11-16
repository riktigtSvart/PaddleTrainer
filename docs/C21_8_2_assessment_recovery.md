# C21.8.2 – szerkeszthető ismert teljesítések és mentéshelyreállítás

Újranyitáskor a korábbi helyi piszkozat feltétel nélkül felülírta a frissen betöltött szerveradatokat. Egy eltárolt függő mentés az egész kérdéssort zárolta akkor is, ha ez a kérés már teljesült, és azóta újabb felmérési eredmények kerültek mentésre. Az idempotens újrapróbálás régi visszaigazolása is visszatehette a régebbi űrlapot az újabb eredmények helyére.

A javítás a piszkozat tényleges mentési alapjához képest egyesíti a saját módosításokat a legfrissebb mentett felméréssel. A változatlan régi válaszok helyét az újabb mentett adatok veszik át. A még mentetlen módosítások megmaradnak, és új átnézést igényelnek. Külön naphoz vagy végrehajtási körülményekhez tartozó, egymással ütköző sorozatokat külön gyakorlatsor őriz meg; az újabb sorozatok nem kapják meg a régebbi mérés dátumát.

## Korábbi mentés ellenőrzése

Az új `GET /api/v1/planning/initial-assessment/revisions/{token}` végpont a beállított sportoló pontos, tartósan mentett felmérési változatát olvassa. Nem indít mentést vagy tervezést. A token UUID; az útvonal nem fogad lekérdezési paramétereket. A tulajdonos, a tartalmi hash és a közvetlen előzmény ellenőrzése a meglévő tárolási szerződés szerint történik. Másik sportoló vagy hiányzó kérés esetén 404 a válasz. A frontend proxy ugyanezt a zárt GET útvonalat engedi, hitelesítő adatok továbbítása nélkül.

Az oldal megnyitásakor a függő kérés azonosítója alapján csak olvasás történik. Kizárólag a pontos eredeti kéréshez tartozó, ellenőrzött, committed visszaigazolás oldja fel automatikusan a függő állapotot. A hiányzó, hibás, idegen vagy elérhetetlen visszaigazolás nem jelent sikeres mentést; az eredeti kérés bájtjai változatlanul megmaradnak. POST csak a felhasználó műveletére indul.

A mezők függő mentés mellett is szerkeszthetők. Az ellenőrzőgomb először az eredeti, befagyasztott kérést folytatja. A közben szerkesztett válaszok megmaradnak, és külön, átnézett mentéssel rögzíthetők. A helyi piszkozat opcionális `pending_request_id` mezője megkülönbözteti az ellenőrzés közben szerkesztett új piszkozatot a korábbi alkalmazásból visszamaradt, a befagyasztott kérésnél is régebbi piszkozattól. Ez nem változtatja meg a szervernek küldött kérés szerződését vagy tartalmát.

## Tervezés

A mentett felmérésből és a helyi szerkesztési állapotból újraszámolódnak a meglévő tervezési előfeltételek. A javítás nem kapcsolja be önállóan az automatikus tervezést és nem kerüli meg a személyes, helyszíni, cél- vagy felmérési előfeltételeket. Egy régi helyi állapot miatt eltűnő négy friss referencia visszaállításához nem kell megismételni a fizikai felmérést.

## Ellenőrzés

- Teljes backend-tervezési regresszió: **2150 sikeres teszt**.
- Teljes frontend regresszió: **1335 sikeres teszt**; Next route-típusok, TypeScript, ESLint és production build.
- Valódi, tulajdonoshoz kötött HTTP API-ból készült regressziós adatok: régi augusztusi eredmények, régi teljesült kérés és négy frissebb használható referencia. Az egzakt régi olvasás nem változtatja meg az aktuális felmérést és nem hoz létre edzést.
- React DOM + valódi FastAPI tesztkliens: StrictMode, régi függő mentés és újabb vezetett eredmény, mezőszerkesztés, tartós mentés és újranyitás; párhuzamos új eredmény és mentetlen saját válasz; bizonytalan mentés melletti szerkesztés és változatlan újrapróbálás; elveszett válasz után újabb eredmény megőrzése.
- A teljes tervezési felület folyamatában a mentett kérdéssor és a friss erőeredmények után a felhasználó kifejezett indítása valódi tervezett edzéseket hozott létre.

A DOM-ellenőrzés nem natív böngészős képernyőképes vizsgálat. A felhasználó helyi adatbázisát és böngészőtárát innen nem olvastuk.

## Telepítés

C21.8.1 szükséges. A backend és a frontend is változik; mindkettőt újra kell indítani. Nincs új függőség vagy adatbázis-migráció. A forrásfrissítő ellenőriz, biztonsági másolatot készít és visszaállítható. A ZIP README-je tartalmazza a telepítési és visszaállítási parancsokat.
