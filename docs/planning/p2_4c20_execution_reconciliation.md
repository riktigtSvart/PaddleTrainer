# C20.0 – automatikus teljesítésegyeztetés

Ez a tervező továbbfejlesztésének első lépése a C19.1 után. A rögzített
teljesítéseket, lejárt terveket és a teljesítések importjának tartós bizonylatát
egyezteti. A három meglévő edzésminta és a jelenlegi tervezési korlátok
változatlanok; az edzések paraméterezése a következő fejlesztési egység.

## Állapotok és elsőbbség

| Elérhető adat | Tervezési értékelés |
| --- | --- |
| Befejezett, tervhez kapcsolt teljesítés | Tervezett és teljesített. A tényleges rekord egyszer számít. |
| Egyedi, tárolt Polar-célazonosító alapján kapcsolható teljesítés | Ugyanez, a felülvizsgálatban dokumentált `provider_exact` kapcsolattal. |
| Befejezett, nem kapcsolható teljesítés | Nem tervezett teljesítésként számít. Név vagy időbeli közelség nem hoz létre kapcsolatot. |
| Kifejezetten teljesítettnek vagy kihagyottnak jelölt terv | A meglévő jelentését megőrzi. |
| Lejárt terv, nincs hozzá rögzített teljesítés, sikeres és időben megfelelő teljesítésimport lefedi | `not_recorded_after_sync`: a tervezésben kihagyásként kezelt, szinkronellenőrzött hiány. |
| Nincs megfelelő szinkron vagy a kapcsolódás többértelmű | `execution_unknown`, konkrét forráshiány vagy kapcsolati probléma. |
| Folyamatban levő / hiányos tényleges teljesítés | `execution_incomplete`, nem változik kihagyássá. |

A `not_recorded_after_sync` nem mért nulla terhelés és nem végleges felhasználói
nyilatkozat. Nem ír `SKIPPED` státuszt a forrásrekordra, nem változtatja meg az
importált tervet, és nem írja át a teljesítés kapcsolatát. Az egyeztetés és
annak forrásai a tartós tervfelülvizsgálat részei. Később beérkező tényleges
teljesítés elsőbbséget kap, és új értékelést eredményez.

## Mikor megfelelő egy szinkron?

- A sportoló saját, tartós `DATA_SYNC_STARTED` és befejezett bizonylata
  összetartozik; a kérés, forráshivatkozás és tartalomlenyomat ellenőrzött.
- A `sessions` adathalmaz sikeresen importált, ismert számlálókkal, nulla
  kihagyott rekorddal és hibakód nélkül. Csak terv- vagy mintavételi
  részletimport nem igazolja a teljesítési lista ellenőrzését.
- Az import a terv várható befejezése után indult. Nem elég, ha egy korábban
  elkezdett lekérés csak a tervezett befejezés után fejeződött be.
- A lekért időszak UTC-ben lefedi a terv időablakát. A szinkron eredeti
  időzónája megmarad, ezért az időzónaváltás és óraátállítás is helyes.
- Ismeretlen tervezett időpont vagy időtartam esetén a teljes, dátummal jelölt
  helyi nap lezárultát és lefedését várja meg. Nem talál ki befejezési időt.
- A bizonylat a bemeneti felvétel időpontjáig ténylegesen elérhető volt.
  Más sportoló, jövőbeli forrás és csonkolt előzmény nem használható.

A szinkron összesített eredménye lehet részleges, ha például a teljesítések
importja sikeres, de a tervimport védett terveket hagyott ki. Ez önmagában nem
érvényteleníti a teljesítések ellenőrzését. A teljesítésimport saját hibája vagy
kihagyott rekordja viszont kizárja a hiányból levont tervezési következtetést.

## Kapcsolatok és terhelés

Az egyedi szolgáltatói célazonosító a teljesítések szűk metaadat-projekciójából
olvasható; a teljes mintasorokat nem kell betölteni. A több tervhez tartozó
azonosító vagy a már létező, eltérő kapcsolat megmarad tisztázandóként. A
meglévő kapcsolatot nem írja felül. A szolgáltatói szinkron már meglévő
kapcsolatmentési folyamata továbbra is külön működik.

A teljesítés nélkül maradt, ellenőrzött régi importált terv nem lesz tényleges
terhelés, nem tart fenn ismeretlen időtartam miatti blokkot, és nem kényszerít
regenerációs időközt. A saját, korábban elfogadott terv kihagyott alkalma
megtartja a tervezési kvótáját, hogy az újraértékelés ne váljon automatikus
bepótlássá. Ez a foglalás nem élettani terhelés. Ismeretlen kihagyott időtartam
nem lesz kitalált mért nulla vagy valós ismeretlen terhelés.

## Újraértékelés és felület

A már elfogadott programok eddigi automatikus figyelése megmarad. Ezen felül a
már felülvizsgált, még aktuális időszakú program is figyelt, ha egy akadály
miatt első tervelfogadásig sem jutott el. Egy megfelelően lezárt import után
a következő figyelési kör újraértékeli. A figyelés a helyi tárolt adatokat
olvassa; nem indít szolgáltatói lekérést és nem igényel nyitott böngészőt.

Az azonos eredményű ismételt szinkron önmagában nem gyárt új tervváltozatot.
A korábbi értékelés és annak eredeti, továbbra is érvényes forráshivatkozása
marad meg. Új tényleges teljesítés vagy megváltozott besorolás új értékelést
eredményez. Mentés előtt a forrásokat ismét ellenőrzi, az elavult felülvizsgálat
elfogadását a meglévő védelem elutasítja. A javaslat naptárba írása továbbra is
kifejezett elfogadás.

A felületen külön csoport: **Nincs rögzített teljesítés · szinkronellenőrizve**.
Látható az alapul vett import kezdési időpontja, a tervezési jelentés és a
késői teljesítés elsőbbsége. Ehhez nincs kézi kihagyásmegerősítés. A kézzel
megerősített kihagyások külön csoportban maradnak. A böngésző ellenőrzi az új
forrás tulajdonosát, azonosítóit, számlálóit, időbeli lefedését és a tervhez
tartozását. A korábbi, új egyeztetési mező nélküli felülvizsgálatok olvashatók.

## Használat és ellenőrzés

Ha a szükséges importbizonylat már rendelkezésre áll, elég friss
tervfelülvizsgálatot kérni. Egyébként az Adatfrissítésnél a teljesítések
lekérését kell lefuttatni. Az aktuális program a következő automatikus körben
is frissül. A még nem támogatott edzésminta ettől külön akadály maradhat.

Nincs új adatbázismigráció vagy függőség. A forrásrekordok módosítása helyett a
meglévő auditált felülvizsgálati tárolást használja. Új tudományos vagy élettani
állítást, illetve egyénre szabott dózisoptimalizálást nem vezet be.

A kiadási kapu `python tools/run_c20_checks.py --build`. Az új backendtesztek
valós HTTP-végponttal és SQLite tárolással ellenőrzik a szinkronforrásokat,
késői teljesítést, egyedi és többértelmű kapcsolatot, részleges importot,
kvótavédelmet, elavult elfogadást, óraátállítást és az első elfogadás előtti
automatikus újraértékelést. A frontend a backend által ténylegesen előállított,
szintetikus értékeléseket és módosított források elutasítását ellenőrzi.
