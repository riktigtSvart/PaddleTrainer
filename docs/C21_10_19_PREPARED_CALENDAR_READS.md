# C21.10.19 — Előkészített naptáradatok és gyors megjelenítés

## Működés

A naptár, a mentett edzésrészletek és az alternatívák olvasása külön útvonalat kapott a tervezéstől. Az alternatívaablak megnyitása, fókuszba kerülése és háttérfrissítése kis méretű GET-kérést küld. Ezek nem indítanak tervezési felülvizsgálatot, nem foglalják le a tervező tulajdonosi zárolását, és nem hoznak létre új tervváltozatot.

Az új felülvizsgálat és elfogadás mentésekor elkészül egy saját hash-sel ellenőrizhető, tömör megjelenítési változat és egy kisméretű keresőbejegyzés. A megjelenítési adat tartalmazza a kész gyakorlatokat, sorozatokat, terhelést, bemelegítést, levezetést, célokat, időpontokat és alternatívánkénti lejáratot. A keresés a rövid katalógusbejegyzéseken fut. A teljes eredeti adat- és igazolási fa változatlanul megmarad; egyszerű megjelenítéshez nem olvassuk vissza és nem ellenőrizzük végig ezt a történetet.

A naptár és a ciklusrészletek is ezeket a megjelenítési változatokat használják. A régi Windows-kódolású rutinszöveg ismert eseteit olvasáskor is helyesen kezeljük; ez nem írja át a mentett edzésadagot vagy az eredeti forrásrekordot. A naptár listanézetéhez a teljesített edzések nagy eredeti nyers adatcsomagját sem töltjük be feleslegesen.

## Kiválasztás

A felugró ablakban továbbra is egymás alatt láthatók a választható blokkok. Külön csoport marad a más edzés és ugyanannak az edzésnek egy másik időpontja vagy helyszíne. A fő cél / alcél / fenntartás szerep és az eredeti céltól való eltérés olvasható. A lejárt kártyák helyben eltűnnek, és az ajánlás a megmaradók közül választ.

A megnyitás a mentett javaslatokat mutatja. Választáskor egy friss, az adott napra korlátozott ellenőrzés fut, majd a mentés a jelenlegi adatokat tranzakcióban ismét ellenőrzi. A választott fizikai edzésadag nem cserélhető észrevétlenül másikra. A korábbi rövid heti terv és a koordinált mezociklus saját ütemezési módját is megőrizzük a csere során.

Nem kell külön nyilatkozni arról, hogy a mai edzés még nem történt meg. A megváltozott előírás, teljesített/kihagyott állapot, tényleges teljesítési bizonyíték és külső jóváhagyás továbbra is kizárja a cserét. Az új teljesítési adatot az olvasási végpont is ellenőrzi, ezért a mentett lista nem tarthatja nyitva a már lezárt napot. A választás más nap edzését nem írhatja át.

Megmarad az egykattintásos mentés, a dupla kattintás elleni védelem, az elveszett mentési válasz azonos kérésű helyreállítása, valamint az ablak mellé kattintásos bezárás. Az eredeti tervezési API a korábbi mentett felülvizsgálatokhoz kompatibilisen megmarad.

## Nézetváltás és részletek

A naptár munkaterülete a már ellenőrzött adatokat memóriában tartja. Egy betöltött tágabb időszakból a heti és napi nézet helyben kivágható; ilyenkor nincs új szerverkérés. A háttérben a környező hat hét betöltésével előkészítjük az egyhetes és négyhetes nézet közti váltást. A napirend és a ciklusszínezés adatai is újrahasznosíthatók a lefedett időszakon belül. Az éjszakán átnyúló időpontokat, időzónát, óraátállítást és az időbecslés felső határát a kivágás figyelembe veszi.

A gyorsítótár a munkaterülethez tartozik, nem kerül tartós böngészőtárba. Importálási, mentési és frissítési értesítés, kézi frissítés, illetve az ablak újbóli fókusza új olvasási generációt indít. Az alternatívák memóriabeli listája sportolóhoz, edzéshez és pontos előíráshash-hez kötött.

A teljesített edzés naptári ablakában az alapadatok azonnal a már letöltött naptáradatból jelennek meg. A napló és a részletes elemzés a külön lenyitható rész megnyitásakor töltődik be. A teljes adatlap linkje is megmarad.

## Egyszeri előkészítés

A `tools/prepare_c21_10_19_views.py` a beállított helyi adatbázisban egyszer előállítja a meglévő tervforrások megjelenítési adatait. Az eredeti források, felmérések és edzések nem változnak. Az új adat az alkalmazás meglévő audit-táblájába kerül külön típussal; táblaséma-migráció nem szükséges.

A művelet újrafuttatható: a már előkészített forrásokat kihagyja. Egy nem használt, régi hibás dokumentum nem teszi használhatatlanná a teljes naptárat. Ha egy jelenleg használt edzés forrása hibás, ezt az előkészítő hibaként jelzi. Az alkalmazás ellenőrzéseit nem kerüli meg. Ez az előkészítés lehet hosszabb; a normál megnyitásnak nem kell megismételnie.

## Mérés

Ugyanazon SQLite tesztadatbázison, 24 megjelenített edzéssel és **500 korábbi, valódi felülvizsgálati szerkezetből képzett teszt-tervváltozattal** készült a méretpróba. Az eredeti archív dokumentumok összesen **484 461 500 bájtot, körülbelül 462 MiB-ot** tettek ki. Ez nem a felhasználó saját adatbázisa.

| Művelet | C21.10.18 | C21.10.19 |
| --- | ---: | ---: |
| Négyhetes naptár, 3 mérés mediánja | 18,64 s | 0,15 s |
| Mentett napi alternatívák, 5 mérés mediánja | — | 0,10 s |
| Kérés egy betöltött hónapon belüli heti/napi váltáskor | új lekérések | 0 |

A mérés backendidejét a tesztkörnyezet, tároló és terhelés befolyásolja; a saját Windows/PostgreSQL-rendszerre ez nem válaszidő-garancia. Az olvasásmérő eszköz (`tools/measure_c21_10_19_reads.py`) a helyi adatbázison is megméri a heti, négyhetes, napirendi, ciklus- és alternatívaolvasást. Nem hívja a Polart, nem tervez és nem ír adatot.

## Ellenőrzések

- 2462 teljes backend tervezési teszt sikeres.
- 1823 teljes frontendteszt sikeres.
- A régi és az új betöltés ugyanazon adatbázison mind a hét vizsgált állapotban pontosan azonos naptári JSON-t adott, az elfogadott napi cserét és a teljesített edzést is beleértve.
- A célzott tesztek tiltottá teszik a tervezés és a tervmentés hívását megnyitás közben; így ellenőrzik az olvasási útvonal különállását. A lejárat, tulajdonos, hash, teljesítés, sorozat/súly, régi kódolás és egyetlen napra korlátozott csere ellenőrzött marad.
- A memóriabeli heti/napi kivágást a valódi szűk backendválaszhoz hasonlítottuk. A napirendi eredmény a korábbi szerződésellenőrzést is teljesíti.
- Valódi FastAPI + React StrictMode/JSDOM próbák: olvasási hibából helyreálló naptár, helyi nézetváltás további kérés nélkül, mentett kártyák, közvetlen csere, dupla kattintás, ablakbezárás, elveszett válasz helyreállítása, teljesítési bizonyítékra megszűnő választás és külön kérésre betöltődő teljesítés-elemzés.

Natív Windows- és natív böngészős vizuális próba nem történt. A forrásfrissítés után mindkét kiszolgáló újraindítandó; a frontend új buildjét is használni kell. Az alapkapu az érintett backend- és frontendkészletet, a típusgenerálást, TypeScriptet, lintet és production buildet futtatja. A teljes készletek külön kapcsolóval kérhetők.
