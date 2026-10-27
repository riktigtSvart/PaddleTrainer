# P2.4C9R2 – A grafikonok részletes adatainak átvétele

Kiindulás: main / origin/main `5dbcf3b9b038f63c5b17eafa496eb3e0ea1014ca`,
a C9 már alkalmazott, még nem commitolt 13 fájljával. A C9R1 kizárólag a külső
tesztfuttatót javította, ezért ugyanaz az 1005 forráshely az alap.

## A hiány oka és a felület

A normál szinkronizálás eddig `include_enrichment=False` beállítással csak az
edzések alapadatait kérte. Így az új részletező helyesen jelezhetett üres mintasort
akkor is, amikor az idő, táv, kalória és átlagpulzus már megvolt. A korábbi
grafikontesztek tárolt mintákból indultak; nem igazolták a normál szinkronizálási
gomb és a részletes adatátvétel közötti kapcsolatot.

Új, külön megnevezett adatfajta: `session_details` – **Részletes edzésadatok és
grafikonok**. A felső kapcsolati gomb a szerver által engedélyezett adatfajtákat
kéri, így az új kérés ezt is tartalmazza. A régi, megőrzött kétadatfajtás kérés
bájtjai és bizonylatai változatlanul olvashatók és újraküldhetők.

A frissítés eredménye megkülönbözteti a korábban ellenőrzött, most lekért,
mintasorral / mintasor nélkül érkezett és még hátralévő edzésrészleteket.
Az API által vissza nem küldött edzés nem számít bizonyított mintahiánynak.
Az összesítő számokból továbbra sem készül mért görbe. A részletező megmondja,
hol indítható az adatátvétel; a tényleges szinkronjelzésre automatikusan újraolvas.

## Korlátos, folytatható munka

A meglévő, tulajdonoshoz kötött és tartósan foglalt szinkronfutás új adatfajtája
legfeljebb öt, még hiányos edzésnapot kér le, a legújabbaktól haladva. Egy napra
egy kérés megy, `features=statistics&features=samples` paraméterekkel; a kért
intervallum mindig egyetlen forrás szerinti nap. Ez illeszkedik a meglévő
180 másodperces futási és 240 másodperces foglalási korláthoz.

A teljes időszakot nem mutatjuk késznek az első rész után. A hátralévő darabszám
és napok száma része a hash-ellenőrzött bizonylatnak. Új szinkronkérés a még
hiányzó napokkal folytatja. Az eredeti kérés újraküldése az eredeti bizonylatot
adja vissza; nem indít új adatátvételt. A korábban sikeresen mentett napok egy
későbbi szolgáltatói hiba vagy időtúllépés után is megmaradnak.

A forrás verziójának lenyomata az edzésazonosítót és a szolgáltatói alapmezőket
kötözi össze. A már ellenőrzött verziót nem kérjük le újra minden kattintásnál.
A mintasor nélküli válasz csak öt percig számít friss negatív eredménynek,
ezután újra ellenőrizhető. A vizsgált időszak a normál szinkron visszamenőleges
beállítását követi; azon kívüli történelmi adatokat nem kér automatikusan.

## Forrásmegőrzés és tranzakciók

A szolgáltatói napi válasz teljes tartalma külön `ProviderDataRecord` rekordba
kerül. A módosított munkapéldány korábbi nyers tartalmát is megőrizzük. A lekérés
tényét tulajdonoshoz, edzéshez és forráslenyomathoz kötött, tartalomcímzett rekord
őrzi; sérült rekord nem jogosít csendes átugrásra. Új tábla vagy migráció nincs.

A részletes payload hálózati lekérése helyi olvasási tranzakció lezárása után
történik. Mentés előtt tulajdonosi és edzéssorzár, új forráslenyomat-ellenőrzés,
majd a napi nyers válasz, bővített nézet és lekérési rekord közös commitja következik.
Sikertelen commit nem számít elvégzett munkának.

A bővítés megőrzi a natív útvonalakat, ismeretlen mezőket és meglévő mintákat.
Hiányzó nézetet vagy csatornát egészít ki; eltérő meglévő mérési értéket nem ír
felül automatikusan. Az eltérés külön jelzett részleges eredmény, a beérkező
forráspayload archiválásával. A statisztikai összesítő mezők csak egyetlen
edzésrész esetén, kifejezetten közölt szolgáltatói értékből frissülnek. Több sport
adatait nem átlagoljuk és az első részt nem nevezzük teljes edzésátlagnak.

A tervezett és mért időpont, időtartam, táv, kalória és tervkapcsolat nem változik
ettől a művelettől. A már meglévő pontos Polar-párosítás a normál futás végén
továbbra is lefut. Nincs új tervezési jogosultság vagy szolgáltatói visszaírás.

## Ellenőrzés

A regresszió ugyanazzal az edzéssel, üres grafikonadatból indul. Tényleges
szinkronkérés, importer, forrásarchívum, adatbázis és részletező GET után már
megjelennek a mért sorok. A változó mintavételi adat útvonalát a valódi Polar
HTTP-kliens szintetikus transportja is ellenőrzi. A tesztek kezelik az adagolást,
folytatást, régi kérés újrajátszását, ismert hiányt, elmaradt szolgáltatói rekordot,
forrásütközést, tulajdonosi határt, részleges mentést és commit-hibát.

279 backendteszt, 440 frontendteszt, teljes TypeScript, módosított frontendkódra
ESLint és production Next build sikeres. Az interaktív DOM-próba a valódi felső
kapcsolati gombot és részletezőt köti a zárt átjárókhoz, FastAPI-hoz és izolált
SQLite-hoz. Kezdetben nincs minta; a gomb megnyomása után a tényleges frissítési
esemény hatására keletkezik görbe. A Polar szintetikus helyettesítés, a DOM
JSDOM; ez nem élő Polar-fiókos vagy natív Windows/böngészős ellenőrzés.
