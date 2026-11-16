# C21.10.4 — az órarend mentése és a mikrociklus következő iránya

## A csütörtöki elakadás konkrét oka

A beküldött képen a megkezdett csütörtöki időablak 18:30–20:00, tehát 90 perc. A maximumként megadott 120 perc nem fér bele. A korábbi felület csak általános érvényességi üzenetet adott; a felhasználó nem kapott érthető támpontot a javításhoz. Az API helyesen elutasította volna ezt az adatot. A C21.10.3 telepítésének naplója sikeres teszteket és buildet mutatott.

A szerver egy általános órarendben legfeljebb 128 heti idősávot fogad el. Ez nem egy hétköznaphoz kötött határ. Valódi API-tesztekben 32 és 128 idősáv menthető a hét minden napjával; 129-nél a korábbi mentett változat változatlan marad. A képen látható idősávmennyiség nem magyarázza a csütörtöki hibát.

Az új felület megmondja az időablak hosszát, a beírt keretet és a javítás módját. Az edzéskeret mező natív felső határa is az időablak hosszát követi. Külön gombbal a felhasználó igazíthatja 90 percre a 120 perces keretet; a kezdés vagy befejezés bővítése is választható. Érvényes, kisebb keretet nem írunk át: a 60 perces ablakhoz megadott 57 perc megmarad. Az éjfélátlépés és a meglévő ismétlődőóra-szabály megmarad.

## Piszkozat és szervermentés

Az általános edzésrend két lépésben menthető:

1. Az időablak szerkesztése után **Idősáv átvétele az órarend vázlatába**.
2. A teljes hét rögzítéséhez **Általános edzésrend mentése** a blokk alján.

A C21.10.4 ettől kezdve ugyanabban a böngészőfülben frissítés esetére megőrzi mind az átvett idősávokat, mind a még nyitott szerkesztőt. A részben kitöltött vagy érvénytelen értékek is visszahozhatók; így a hibás csütörtöki időablak miatt a hét eleji munka sem vész el. A visszaállított helyi változat látható jelzést kap, és továbbra is külön szervermentést igényel. A már korábban elveszett, nem tárolt bevitelt ez nem állítja helyre.

Technikailag a tárolás `sessionStorage`-ot használ, sportoló és időzóna szerint elkülönített `training-schedule-draft-v0.1` formátummal. A böngészőfül bezárása utáni vagy másik eszközön történő helyreállítást nem garantálja. A tároló elérhetetlensége látható figyelmeztetést ad; sérült helyi bejegyzést nem írunk felül csendben, annak elvetése külön művelet. A szerverre már igazoltan mentett és azóta nem módosult helyi piszkozat törlődik.

A helyi bejegyzés csak az órarend saját mezőit birtokolja: érvényesség, heti idősávok, kivételek és a nyitott időablak. A helyszínek és más beállítások a friss szerveradatból érkeznek. A helyi adat strukturális ellenőrzést kap, de nem tekinthető szervermentési jogosultságnak: mentéskor továbbra is a teljes szerződés, a friss revízió és a meglévő ellenőrzött bizonylat számít. Valódi másik órarendmódosítás esetén a saját piszkozat megmarad és az ütközés látható.

A már elküldött, visszaigazolásra váró kérés külön, változatlan tartalommal tárolódik. Az új helyi piszkozat nem írja át ezt a kérést. A betöltés és a helyreállítás nem küld automatikus POST-ot. A sikeres szerverírás után elvesztett válasz ugyanazzal a kéréssel, új revízió létrehozása nélkül ellenőrizhető.

## Ellenőrzések

- 1494 frontendteszt, Next route-típusgenerálás, TypeScript, érintett fájlok ESLintje és production build.
- Négy új valódi API-teszt: 32 és 128 idősáv; 129 visszautasítása adatvesztés nélkül; a 120/90 perces csütörtöki hiba, majd javítása és a 33. idősáv mentése.
- Valódi FastAPI és React StrictMode/JSDOM próba: hétfő–szerda átvett piszkozat, hibás csütörtöki szerkesztő, komponens újranyitása azonos böngészőtárral, értékek visszaállítása írás nélkül, kifejezett javítás, tényleges mentés, újranyitás a mentett változattal. Elvesztett mentési visszaigazolás és az eredeti kérés idempotens folytatása is ellenőrzött.
- A C21.10.3 helyszínfrissítési, valódi órarendütközési és régi GET-et elutasító integrációs próbája az új kóddal is sikeres.

A JSDOM-próba a böngészőtár megőrzésével bontja le és építi újra a valódi React felületet. Natív Chromium vizuális ellenőrzés a környezet socketkorlátozása miatt nem áll rendelkezésre. A teljes backend-tervezési regresszió ebben a csomagban nem futott újra; a backend futó forrása nem változik, a tesztkapu `--with-backend` kapcsolóval ezt is futtathatja.

## A támogatott következő tervezési irány: rugalmas mikrociklus

Ez a rész elfogadott tervezési irányt rögzít. A C21.10.4 az órarendszerkesztőt javítja; a generátor edzéssorrendjét és terhelési szabályait még nem alakítja át.

A mikrociklus rövidebb, ismétlődő terhelési és pihenési egység. Naptári alapértelmezésként hét nap használható, de a kezdetét és végét külön kell kezelni: nem szükségszerűen hétfőtől vasárnapig tart, és a hossza később az állapothoz, versenyhez és elérhetőséghez igazodhat. A gördülő hétnapos terhelési korlátoknak ettől függetlenül, ciklushatáron átnyúlva is érvényesülniük kell.

A javasolt alapminta erőhangsúlyos felkészülési szakaszban: pihenést követő friss állapot a kulcsfontosságú erő- vagy robbanékonysági munkához; körülötte összeillő, kisebb fáradást okozó munka; a későbbi napokon a rendelkezésre állásba és a tényleges terhelhetőségbe illő állóképességi hangsúly; majd tervezett pihenés. Ez preferencia, nem kötelező erősítés-először szabály. Állóképességi vagy technikai fő célnál annak kiemelt edzése kaphatja a friss állapotot. A hosszú aerob edzés maga is jelentős terhelés lehet; pusztán a kardió címke alapján nem tekinthető könnyűnek vagy regenerálónak.

A későbbi kiosztásnak az egyes edzések célját, dózisát, intenzitását, mozgás- és izomzati átfedését, a következő kulcsedzést, a heti terhelést, a lehetőségeket és az egyéni visszajelzést együtt kell értékelnie. A hét eleji erő és hét végi hosszabb aerob munka a felhasználó számára érthető alapminta lehet; az appnak láthatóan indokolnia kell az eltérést és a védett kulcsedzést.

Jelenleg napi egy új automatikus javaslat marad az alap. A jövőbeli napi több alkalmat az adatmodell ne zárja ki, de annak bevezetéséhez önmagában a regeneráció becslése nem elég: szükséges az összesített dózis, az átfedő terhelések, az időbeli elférés, a kulcsedzés minősége és a visszajelzés alapján ellenőrzött terhelhetőség is. A tanult regeneráció nem ad önmagában felhatalmazást a napi edzésszám automatikus emelésére.

A kombinált erő- és állóképességi munka szakirodalma nem igazol általánosan optimális heti sorrendet. Háttérként: [Schumann és mtsai., 2022, DOI 10.1007/s40279-021-01587-7](https://doi.org/10.1007/s40279-021-01587-7). A konkrét eredmények és a jelenlegi 12/24/36/48 órás, kezdőidők között mért termékszabályok értelmezése a `C21_10_3_SETTINGS_AND_SPACING.md` dokumentumban található.
