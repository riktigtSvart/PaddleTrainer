# P2.4C9R4 – Szakaszok, sebesség/iram/teljesítmény célok és szinkronvisszajelzés

## Használat

A sebességegység a fejlécben és közvetlenül a grafikonoknál is kiválasztható.
A két mező együtt váltja az átlagot, maximumot, szakaszátlagokat, mintatáblázatot,
a görbe értékeit és a célhatárokat: km/h, m/s, knots. Az iram perc/km marad.

A **Szakaszok és részidők** táblázat a mért távot, átlagpulzust, átlagsebességet,
szakaszidőt és a szakaszidők összegét mutatja szolgáltatói sorrendben. A rögzített
és automatikus körök alternatív bontások; nem adódnak össze. Több edzésrész
esetén először az összes rész áttekintése látszik. Teljesítményátlag is megjelenik,
ha a szolgáltató közvetlenül megadta. A hosszú tábla saját görgetést kap.

Az átlagok az adott rész vagy kör `statistics.statistics` listájából származnak.
A hiányzó részátlagot nem helyettesíti a teljes edzés átlaga; ismétlődő,
ellentmondó statisztikatípusból sem választ önkényesen. Nulla és hiány különböző.
Az összeadott idő nem a szünetekkel együtt mért falióraidő. Hiányzó időtartam
után az összeg is ismeretlen. A nyers `splitTimeMillis` megmarad a vetületben,
de nem használjuk egy feltételezett rajzhely vagy tervkapcsolat meghatározására.

A kapcsolt terv blokkjai külön lenyitható táblázatban látszanak. A gyerekek saját
ismétlési konténerük alatt maradnak; a nem rendezhető hivatkozások külön jelzést
kapnak, nem vesznek el. A tervezett blokk és a rögzített kör összetartozását a
megjelenítés nem állítja név, sorrend vagy hasonló táv alapján. A Polar-körök
nem feltétlenül egyeznek az edzésterv fázisaival.

## Célhatárok

Pulzus-, sebesség/iram- és teljesítménycél egymástól függetlenül választható és
kikapcsolható. A sebesség- és teljesítményzónákat az adott mért edzésrész
`ZONE_TYPE_SPEED` és `ZONE_TYPE_POWER` csoportjai adják. Öt, rendezett,
nem átfedő határ szükséges Z1–Z5 megnevezéshez. A nulla alsó határ megmarad.
A pulzus korábbi személyes zónakezelése változatlan.

A `SPEED_ZONES`/`SPEED_ZONE`, `POWER_ZONES`/`POWER_ZONE` tervtípusokat ezekhez a
forráshatárokhoz kötjük. Az explicit `SPEED_KMH`, `SPEED_MPS`, `PACE_SEC_KM` és
`POWER_W` számértékek a típusban megnevezett egységben értendők. Az ismeretlen,
százalékos vagy szöveges célt nem értelmezzük át. A tárolt terv nem változik.

A sebesség célja km/h alapon kerül átszámításra. Az iram reciproka miatt a két
számszerű végpont helyet cserél: 10–12 km/h = 5:00–6:00 perc/km. Nulla
sebességet tartalmazó sávnak nincs véges iram-felsőhatára; ilyenkor a teljes
sáv a sebességgrafikonon marad, külön magyarázattal.

Az összteljesítmény célját nem rajzoljuk önkényesen egyoldali pedálteljesítményre.
Egyértelmű, azonos edzésrészhez tartozó, egyidejű és azonos mintavételű bal és
jobb sorból külön **Teljesítmény · bal + jobb** sor készül. Hiányzó oldal,
eltérő felbontás vagy hossz, többértelmű forrás és hiányzó minta esetén nincs
kitalált összeg. A két eredeti sor továbbra is külön választható. Ha a célhoz
nincs megfelelő mért sor, külön **Csak tervcél** referencia látszik, egyértelmű
mérési hiányjelzéssel. A forrássorok és a tárolt összesítők nem módosulnak.

A célok továbbra is vízszintes referenciák: nem állítják, hogy a tervblokk mikor
volt teljesítve a mintasorban, és nem számítanak célban töltött időt.

## Részletes adatátvétel

A részletes szinkron `statistics`, `samples`, `zones`, `laps` jellemzőket kér.
A régi két- és háromjellemzős, ellenőrizhető markerek megmaradnak, de egy új
kérés egyszer kiegészíti őket a körökkel. A régi request ID megismétlése a régi
változatlan nyugtát adja. A már teljesen lekért forrásverzió újra felhasználható.
Megmarad az ötnapos adagkorlát és a legutóbbi nappal kezdődő folytatás.

A korábbi natív köradat hozzáadódik a preferált nézethez; eltérő megőrzött
értéket nem ír át. A teljes nyers adat, a mért idő, táv, energia és tervkapcsolat
megmarad. A szakaszvetület legfeljebb 4000 forráshelyet, 64 edzésrészt és
129 alternatív csoportot kezel; túllépéskor megáll, nem csonkít csendben.
A `session-analysis-v0.1` válasz új mezői opcionálisak a korábbi kliensoldali
olvasás kompatibilitásához; az új szerver minden ismert vetületet kiad.

## Szinkronjelzés

Az összesített hibakód az első jelzés lehet, így a védett terv megőrzése mögött
másik adatcsoport részlete maradhatott rejtve. Most a külön adatcsoportok fontos
jelzései a lenyitás előtt is látszanak, kóddal és magyarázattal.

Csak teljesen ellenőrzött darabszám, egyező kérési kör, sikeres részlépések,
kizárólag `details_batch_pending` hátralék és legfeljebb védett tervek megőrzése
mellett jelenik meg az **Átvétel folytatható** állapot. A történeti nyugta
`partial` marad. Az ismeretlen kihagyás, hiányos darabszám, nem visszaadott
forrás, ütközés, timeout, sikertelen részlépés és párosítási probléma továbbra is
figyelmeztetés. A kapcsolati jogosultsághibát a későbbi adatcsoportból is
felismeri a felület; ilyenkor a hozzáférés megújítása is elérhető.

A felhasználó képe önmagában nem mutatta a lenyitható futásrészleteket, ezért
annak konkrét szolgáltatói hibáját nem állítjuk bizonyítottnak. Az új felület
elkülöníti és láthatóvá teszi a lehetséges okokat; a valódi forrásproblémát
nem tünteti el sikerjelzéssel.

## Ellenőrzés és források

308 backendteszt, 513 frontendteszt, Next typegen, teljes TypeScript, módosított
forrásokra ESLint és production build. A külön DOM-próba a valódi vezérlők,
zárt átjárók, FastAPI és izolált SQLite együttműködését vizsgálja helyettesített
Polarral, beleértve a megőrzött terv + következő adag, majd a folytatás és a
valódi hozzáférési hiba esetét. Natív Windows/böngésző és élő Polar nem futott
az elkészítési környezetben. A telepítő külön helyi Git-próbákon megy át.

Ellenőrzött elsődleges API-leírás (2026-10-27):
https://www.polar.com/polar-api-v4/#trainingsessionlaps
https://www.polar.com/polar-api-v4/#trainingsessionlap
https://www.polar.com/polar-api-v4/#trainingsessionlapstatistics
https://www.polar.com/polar-api-v4/#trainingtargetphaseintensity
https://www.polar.com/polar-api-v4/#intervalvaluessampletype
