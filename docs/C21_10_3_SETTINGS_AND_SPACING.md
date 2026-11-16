# C21.10.3 — naptári láthatóság és edzésrend mentése

## Naptári beállítások

A napi, heti, négyhetes és áttekintő nézet az Edzéslehetőségek, Elfoglaltságok, Tervezett edzések, Teljesített edzések, Felkészülés és Állapotadatok választását külön tárolja. A Teljes 24 óra kapcsoló is a saját nézethez tartozik. A tárolás a böngésző localStorage-jában, sportolónként és nézetenként elkülönített `calendar-visibility-v0.1` adattal történik.

A visszaolvasás nem ír alapbeállításokat a mentett értékekre. Írás csak a felhasználó kapcsolóválasztásakor történik. Az owner és a nézet ellenőrzött; sérült vagy ismeretlen formátum esetén alapérték és látható visszajelzés jelenik meg. A sérült bejegyzést csak egy új, kifejezett választás váltja fel. A másik böngészőfül változásait a storage esemény visszaolvassa, ismételt írás nélkül. A tárolás hibája nem tiltja le a naptár vagy az edzésmentés működését.

## Az edzésrend és a helyszínek közös adatcsomagja

A felkészülési oldal a már meglátogatott blokkokat életben tartja, hogy a piszkozatok megmaradjanak. A helyszínek és az edzésrend ugyanannak a revisionált adatcsomagnak a részei. Korábban egy másik blokk sikeres mentése után a már megnyitott blokk nem olvasta újra ezt az adatcsomagot. A próbában emiatt az új helyszín hiányzott az időablak szerkesztőjéből, és elavult mentési alap maradt az edzésrendnél.

A blokkok most sikeres beállításmentés és visszatérő ablakfókusz után újraolvassák a közös állapotot. A korábbi betöltések generációszáma nem enged egy későn beérkező választ a folyamatban lévő vagy már igazolt mentés fölé írni. Az igazolt revisionális fejet külön megőrizzük; annál régebbi visszaolvasást, illetve ugyanahhoz a revízióhoz más lenyomatot nem jelenítünk meg új állapotként.

Az általános órarend piszkozata a saját mezőit birtokolja: érvényesség, heti idősávok és az azokhoz kapcsolódó kivételek. A helyszínnevek és választható helyek a friss adatból jönnek. A mentés a friss, közös adatcsomaghoz illeszti a szerkesztett órarendet, így a közben felvett helyszín és más független beállítás megmarad. A puszta helyszínfrissítés nem indítja újra az órarendszerkesztőt. Az érintetlen órarend új mentett változatot átvehet; saját módosítás mellett a valódi órarendütközés látható, és a piszkozat megmarad.

A friss helyszínnel történő idősávátvétel validálása is az aktuális helyszínlistát használja. A mentési siker és hiba a blokk alsó mentőgombjánál is megjelenik. Más blokk függő mentési kérése nem írható felül új kérés tárolásával. A korábbi kérés visszaállítása továbbra sem küld automatikus POST-ot.

## Elrendezés és ellenőrzés

A napok hangsúlyos, témához illeszkedő keretet és bal oldali színes jelzést kaptak. Az adott nap idősávjai egymás melletti, külön keretes kártyák; szűk helyen új sorba törnek, oldalirányú görgetés helyett.

Ellenőrzések: teljes frontendteszt-készlet; Next típusgenerálás; TypeScript; érintett fájlok ESLintje; production build. A backend forrása nem változik; a meglévő helyszín-, órarend-, úszás/terhelés- és földrajzi API-tesztekből 59 sikeres.

Valódi FastAPI és React StrictMode/JSDOM próbák: nyitott edzésrend mellett új helyszín mentése, az új hely kiválasztása és tényleges mentése egy idősávban, a korábbi piszkozat megőrzése, mentés utáni újranyitás írás nélkül, valódi másik órarendmódosítás mellett megmaradó piszkozat, és egy mesterségesen régi mentés utáni GET elutasítása majd friss visszaolvasása. A szűrőknél négy külön nézet, felhasználók elkülönítése, gyors kapcsolóváltás, újranyitás, másik fül frissítése és sérült böngészőadat kezelése ellenőrzött.

Natív Chromium elrendezéspróbát a futtatókörnyezet socketkorlátozása nem engedett elindítani. A működési ellenőrzés DOM-alapú, a CSS production buildben ellenőrzött; natív böngészős vizuális jóváhagyást nem állítunk.

## A jelenlegi edzésközi térköz értelmezése

A `training-start-spacing-v0.1` a kezdőidők közötti különbséget vizsgálja, tehát nem a befejezéstől számolt teljes pihenést. Jelenlegi döntési sorrendje:

| Előzmény és következő edzés | Kezdőidők közti alsó korlát |
|---|---:|
| Két erősítés | 48 óra |
| Nincs ismert saját minta, és nincs 1–3/10 RPE-vel könnyűnek jelzett teljesítés | 36 óra |
| Ismert saját minta vagy könnyűnek jelzett teljesítés: erősítés–más sportág | 24 óra |
| Ismert saját minta vagy könnyűnek jelzett teljesítés: ugyanaz a sportág, vagy kajak–úszás | 24 óra |
| Más, ismert saját mintával vagy könnyű visszajelzéssel rendelkező aerob sportágpár | 12 óra |

A korlátok óvatos termékszabályok. A jelenlegi modell sportágpárt és az intenzitás ismertségét kezeli, az izomcsoportonkénti helyreállást és az edzések egymásra hatását még nem becsüli személyre szabottan. A csomag ezeket a számokat nem változtatja meg.

A generátor jelenleg egy napra egy új edzésjavaslatot választ. Az idősávnál jelölhető kombinálhatóság mellett a támogatott automatikus minták még egy sportágat írnak elő; külön erő- és állóképességi részekből álló összetett alkalmat vagy egy napra két új edzést ez még nem készít. A már meglévő vagy külső teljesítések ettől függetlenül több alkalmat is tartalmazhatnak.

## Erősítés és állóképesség váltogatása — szakirodalmi háttér

Schumann és munkatársai 43 tanulmányt összegző elemzésében a kombinált állóképességi és erősítő munka átlagosan nem csökkentette a maximális erő és izomtömeg fejlődését az azonos erősítőprogramhoz képest. A robbanékony erő fejlődésénél kedvezőtlenebb eredményt találtak, különösen közvetlenül egy alkalomba tett munkánál. A legalább három órára szétválasztott alcsoport kedvezőbb képet mutatott; ez nem igazol mindenkire érvényes háromórás határt.

- Schumann és mtsai. (2022), Sports Medicine: [DOI 10.1007/s40279-021-01587-7](https://doi.org/10.1007/s40279-021-01587-7), [PubMed 34757594](https://pubmed.ncbi.nlm.nih.gov/34757594/).

Robineau és munkatársai egy hét hetes, 58 amatőr rögbijátékost vizsgáló kísérletben 0, 6 és 24 óra különválasztást hasonlítottak össze. A közvetlen összekötés több mutatónál kedvezőtlenebb fejlődést adott. A konkrét sportolói kör, program és elemzési módszer miatt ebből sem adódik általános, személyre szabott óraszám.

- Robineau és mtsai. (2016), Journal of Strength and Conditioning Research: [DOI 10.1519/JSC.0000000000000798](https://doi.org/10.1519/JSC.0000000000000798), [PubMed 25546450](https://pubmed.ncbi.nlm.nih.gov/25546450/).

A tervező továbbfejlesztésére ezekből az a következtetésünk: a képességcímke mellé szükséges az edzés tényleges dózisa, intenzitása, érintett izomzata, az előző és következő kiemelt feladat, valamint az egyéni visszajelzés. Külön kezelnénk az akut végrehajtási minőséget és a többhetes alkalmazkodást. A ciklus fontos kulcsedzésének friss állapotot biztosítanánk, és köré helyeznénk az összeillő könnyebb munkát. A más sportág vagy más képesség címkéje önmagában nem jelenti az előző edzéstől független terhelést.
