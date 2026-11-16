# C21.9.2 – Futás referencia nélkül és történeti Polar-betöltés

A futóedzés hiányzó vagy rövid friss előzmény esetén is tervezhető, ha a sportolói belépési feltételek, a célhoz illeszkedő sportági lehetőség, a felszerelés és az időkeret rendelkezésre állnak. A heti/ciklusszakaszos keret, a pihenőidő, a funkcionális korlátozások és a napfénykorlát továbbra is érvényes.

## Három külön kiindulás

| Bizonyíték | Kezdőutasítás | Az adat szerepe |
| --- | --- | --- |
| Az elmúlt 56 napban befejezett, legalább 20 perces saját futás | Könnyű, beszélgetős futás; a legutóbbi legfeljebb három használható futás legrövidebb időtartamáig, az időablakhoz és cikluskerethez igazítva | Időtartam-tájékozódási pont, legfeljebb 45 perc. Személyes intenzitásküszöböt nem igazol. |
| Csak rövidebb futás, régebbi futóedzés, megadott futótapasztalat vagy futóeredmény | 5 perc séta/bemelegítés, 10 perc könnyű futás bármikori sétára váltással, 5 perc levezető séta | 20 perces tájékozódó termék-alapérték. A sportmúlt és egy régi csúcs nem igazolja a mai terhelhetőséget. |
| Nincs használható futási referencia vagy megadott futótapasztalat | 5 perc séta, 4 × (1 perc könnyű kocogás + 90 másodperc séta), 5 perc levezető séta | Konkrét, 20 perces kezdő futás–séta. Nem maximális teszt. |

Egy rövid teszt, bemelegítő vagy regeneráló futás nem zárja ki a hosszabb használható előzményeket. A 12 perces Cooper-eredmény is megőrzött információ; időtartama önmagában nem lesz az összes futás felső korlátja. A közelmúlt és a régebbi sportmúlt külön marad.

Az instrukció könnyű, beszélgetős erőfeszítést kér, RPE 2–3/10 kiindulással. Az érintett rövidíthet, sétára válthat, panasz esetén megáll. Nem számítunk régi egyéni csúcsból mai tempót, pulzuszónát vagy VO2max-ot. Nincs automatikus progresszió vagy személyes válaszmodellre vonatkozó állítás.

Az NHS kezdőprogramja ad mintát a rövid futó- és sétaszakaszok váltására. A fenti négy ismétlés és a 20 perces keret **saját, rövidebb kezdő termékválasztás**, nem az NHS teljes programja és nem külön validált felmérési protokoll. Az NHS első alkalma 28:30, összesen nyolc egyperces futással.

Forrás: [NHS Couch to 5K running plan](https://www.nhs.uk/better-health/get-active/get-running-with-couch-to-5k/couch-to-5k-running-plan/).

## Régebbi edzések átvétele

**Általános beállítások → Régebbi Polar-edzések betöltése.** Alapértelmezett kezdőnap: **2021-12-01**. Ez szerkeszthető a betöltés indítása előtt. A végdátum a szerver kapcsolati állapotának napja; a kérésben a következő nap kizáró végpont.

Az explicit indítás egymás után, legfeljebb 90 napos adagokban kéri a teljesített edzések összesítő adatait, a legújabb adagtól visszafelé. Minden sportág összesítője megmarad. A történeti művelet nem kér edzésterveket és másodpercenkénti mintasorokat. A részletes lekérés külön meglévő művelet marad.

A Polar V4 dokumentációja szerint a `training-sessions/list` kezdőpontja inkluzív, végpontja exkluzív; opcionális részletes funkciók nélkül a dátumtartomány legfeljebb 90 nap. Ez kérésenkénti tartománykorlát, nem 90 napos történeti megőrzési szabály. A ténylegesen visszakapott előzmény a csatlakoztatott fiókban és a szolgáltatónál elérhető adatoktól függ.

Forrás: [Polar AccessLink Dynamic API v4 – Training Sessions](https://www.polar.com/polar-api-v4/#list-user-training-sessions).

A felület az egyes adagok ellenőrzött bizonylata után lép tovább. Az üres, sikeresen lekért adag is lezárható, de ebből nem következtetünk edzésmúltra. Elveszett válasznál először az eredeti kérés azonosítójával olvassa vissza az eredményt. A folytatás böngészőben megőrzött állapota nem edzésadat és nem a tervező forrása: a tényleges edzések és bizonylatok a szerver adatbázisába kerülnek.

**Szünet az aktuális adag után** megvárja az éppen futó adag lezárását. Az oldal bezárása után a **Betöltés folytatása** használható ugyanabban a böngészőben. Újranyitás önmagában nem küld szolgáltatói lekérést. A korábban betöltött edzések újraolvasása az eredeti szolgáltatói azonosító alapján frissít, nem hoz létre újabb példányt. Más sportoló rekordja nem írható felül. A forrásból megőrzött részletes adatok nem vesznek el.

A betöltés a felhasználó gépén futó alkalmazás Polar-kapcsolatát használja. A fejlesztői tesztek szintetikus Polar-válaszokkal futnak; a csomag telepítése önmagában nem hívja le a személyes előzményeket.

## A tervező forrásai és a mentés

A friss futóreferencia az aktuális tervezési pillanatból származik akkor is, ha a heti kezdőkeret korábbi, megőrzött cikluskalibráláshoz kötött. Így az újonnan bekerült saját futásokat nem rejti el a fagyasztott heti keret. A történeti betöltés önmagában nem emeli meg ezt a keretet, és nem pótol kihagyott edzéseket.

A tervező külön, tulajdonoshoz kötött forráspillanatképet készít a legutóbbi legfeljebb 24 régebbi futásból. Ez tapasztalati háttér, nem teljes történeti statisztika vagy jelenlegi dózismérés. Minden lehívott edzés ettől függetlenül tartósan megmarad az adatbázisban. A megadott futóeredmények és a sportmúlt is külön megjelölt források.

Új futóutasítás: `training-prescription-v0.3`; összesített kontextus: `training-prescriptions-v0.3`. A böngésző újraszámolja a forrásválasztást és ellenőrzi a konkrét futóutasítást. A korábban tárolt v0.1/v0.2 tervek olvashatók maradnak. A mentés előtt módosult releváns forrás új tervezési áttekintést kér.

## Ellenőrzés és korlátok

Ellenőrzött esetek: üres futómúlt; csak rövid futás; hosszabb futások melletti 12 perces teszt; 2021-es saját és idegen tulajdonosú futás; régi egyéni csúcs; friss referencia cikluskalibrálás mellett; korábbi, csak erősítést tartalmazó terv újraosztása változatlan heti kerettel; következő frissítés duplikáció nélkül.

A történeti lekérés valódi API/tesztadatbázis folyamatban ellenőrzi a tartományhatárokat, 90 napos limitet, hibás dátumot, jövőbeli tartományt, kérésismétlést, részleges meghibásodást, forrástartományon kívüli választ és a szolgáltató időzónájában értelmezett napot. React StrictMode + valódi FastAPI tesztben a 2021 decemberéig visszanyúló betöltés 20 szintetikus adagot mentett, szüneteltetéssel, újranyitással, elveszett válasz visszaolvasásával és duplikáció nélkül. Natív böngészős képernyőképes ellenőrzés nem készült.

A kajakozás kizáró napfénykorlátjához továbbra is az érintett helyszínhez kötött koordináta és időzóna kell. A hiányzó földrajzi adatot a rendszer nem találja ki. Az úszás automatikus edzésmintája külön fejlesztés, ebben a csomagban még nincs bekötve.

Nincs új csomagfüggőség vagy adatbázis-migráció. A forrástelepítő kizárólag ellenőrzött forrásfájlokat módosít; adatbázist nem ír és nem állít vissza. A felhasználó korábbi TCX-fájlja és személyes úszóadatai nem részei a csomagnak.
