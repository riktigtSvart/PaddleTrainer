# P2.4C6 — közös alkalmazáskeret és valódi adatokra épülő naptár

## Kiindulás és hatókör

A 2026-10-24-én átadott, 911 fájlos munkafa az alap: `main`, HEAD
`3ca1165cc9d21b6b83a3b1e95090261d49524173`, a C5 + R1 + R2 még nem commitolt
változtatásaival. A C6 ezeket megőrzi. Új csomagfüggőség és DB-migráció nincs.

Ez az elfogadott frontendterv első megvalósítási csomagja. Működő elemei:

- közös navigáció, összecsukható oldalsáv, magyar alkalmazáscím;
- világos, sötét és rendszert követő téma, böngészőben megjegyzett választással;
- a kezdőlapon közös időrácsú napi és heti naptár, továbbá 28 és 144 napos nézet;
- a tárolt edzéstervek, tényleges edzések és az R2-ben megadott edzéslehetőségek;
- rétegek, teljes 24 órás megjelenítés, éjfélen átnyúló események, átfedési sávok;
- külön sor az időpont nélküli terveknek, részletező és terv/teljesítés összevetés;
- kifejezetten megadott elsődleges edzéscél, tartós és előzményeket megőrző mentéssel;
- célcsalád szerinti színek, sportágikon és külön teljesítési jelölés;
- kiválasztott napi tárolt állapotadatok, megőrzött forrásokkal és kézi helyesbítésekkel;
- a korábbi kezdőlap teljes edzéslistája külön, a `/coach` címen.

Az idősávok teljes R2-szerkesztője a naptárból közvetlenül megnyitható.
A C6 naptárrácsában még nincs drag&drop vagy idősávhatár-húzás. A következő
csomag ezekhez a tartós naptári módosításokat és a korlátszabályokat készíti el.

## Nézet és idő

A közös függőleges tengely a sportoló mentett időzónájának polgári ideje.
A blokkok pozíciója és magassága a rács arányában számolódik; a rács magassága
a képernyőhöz igazodik. A 45 és 90 perces események aránya minden méretben 1:2.
Az alapnézet 06–22 óra, a teljes 24 óra külön bekapcsolható. A kívül eső
eseményekhez jelzés és teljes napra váltás tartozik. A listanézet minden
betöltött eseményt külön is elérhetővé tesz.

Az ismert kezdés és hiányzó időtartam pontjelölést kap. A kezdés nélküli tervet
nem helyezzük el feltételezett időpontra. Ha egy teljesített edzés végidő nélkül,
de rögzített időtartammal érkezett, a megjelenített végidő becslésként szerepel.
A szüneteket tartalmazó, két ismert időpont közötti eltelt idő eltérhet az aktív
időtartamtól; a rács az időpontokat, a részletező a forrás időtartamát mutatja.

Az éjfél utáni rész a következő napra kerül. Az óraátállítás visszaforduló óráját
érintő, egy napon belül visszafelé látszó intervallum külön jelölt pontként
jelenik meg; az eredeti időpontok megmaradnak. A böngésző időzónája nem írja felül
a sportolóét. A 28/144 nap megjelenítési lépték, nem merev mezociklushossz.

## Színek és jelentés

Az elsődleges cél a meglévő képességkatalógus kulcsa, illetve `RECOVERY`, `MIXED`
vagy kifejezett nullérték lehet. A képesség pontos neve megmarad; a színek
áttekinthető célcsaládokat jelölnek. A sportág külön ikont, a teljesítés külön
pipát kap. A színezés nem következtet célra névből, sportágból vagy pulzusból.
A cél nélküli bejegyzés semleges marad.

A teljesítés alapértelmezetten átveheti a saját sportolóhoz tartozó kapcsolt
terv céljelölését. Saját céljelölés — az explicit nullértéket is beleértve — ezt
felülírja. A felület jelzi, ha a cél a kapcsolt tervből származik.

Ez edzéshez rendelt, deklarált céljelölés. A C1/C2 protokollokat, képességcélokat,
eredményeket és tudományos bizonyítékokat nem módosítja és nem helyettesíti.

## Backend és határok

- `GET /api/v1/planning/calendar/feed`: opcionális, páros `start_date`, `end_date`;
  alapértelmezés a sportoló helyi aktuális hete. Legfeljebb 366 nap.
- `POST /api/v1/planning/calendar/goals`: `request_id`, `entity_kind`, `entity_id`,
  `previous_reference`, `primary_goal`. Más mező nem fogadható el.
- A frontend zárt, azonos eredetű útvonala: `/api/calendar/feed`, `/api/calendar/goals`.
- Minden válasz `no-store`. A meglévő, konfigurált sportolót használjuk;
  olvasás miatt nem keletkezik új felhasználó.
- Az olvasások tulajdonosra és időszakra szűrtek. A sorlimitet meghaladó választ
  explicit elutasítás követi; nincs teljesnek bemutatott csonka lista.
- A céljelölés új `WORKOUT_GOAL_TAG` auditbejegyzés. Séma:
  `calendar-workout-goal-v0.1`, azonosító:
  `pt-workout-goal:<sportoló/típus/edzés hash>:<request UUID hex>`.
- Tulajdonosi sorzár, előző verzióra vonatkozó CAS, kanonikus tartalomhash,
  visszaolvasás és commitigazolás tartozik a mentéshez. A beágyazott szülőhash
  része a tartalomnak. A korábbi, azonos kérés ismétlése nem aktivál régi célt.
- `planning_authorized=false`, `workouts_changed=false`. Sem az edzés előírása,
  sem az órából kapott nyers rekord, sem a terv hiteles verziója nem változik.

A függő frontendkérés azonos bájtokkal megmarad a `sessionStorage`-ban.
Újratöltéskor nincs automatikus újraküldés. A bizonytalan kimenetel csak azonos
kéréssel próbálható újra; sikert kizárólag ellenőrzött tartós válasz igazol.
Az ismerten elutasított kérés külön művelettel elvethető, majd újraolvasható.

A C6 **Frissítés** gombja a tárolt alkalmazásadatokat olvassa újra.
Nem indít Polar-lekérést. Az R2 explicit órás adatátvétele továbbra is a profil
előzmények lapján érhető el. Az állapotnézet forrásonként mutatja a kiválasztott
nap adatait; több eszközt nem összegez. A kézi helyesbítés és annak korábbi
forrása megkülönböztethető, a hiány nem nulla, nincs kitalált regenerációs pontszám.

## Következő megvalósítási lépések

1. Naptári korlátok: állandó/heti szabály, eseti esemény, egyedi kivétel,
   rögzített/rugalmas feltétel, tulajdonosi és verzióütközési védelem.
2. Kattintásos gyorsszerkesztő, blokkmozgatás, határhúzás, előnézet és visszavonás.
   A szabad időablak és az edzés előírásának változása külön művelet. A terv
   módosítása a meglévő hiteles tervverziózásra és alkalmazási kapukra épüljön;
   közvetlen `PlannedWorkout`-átírás nem kerülheti meg ezeket.
3. Teljesített edzés grafikonjai, forrás szerinti minták és hiányok, kapcsolható
   adatsorok. Az eredeti teljesítés idejét húzás nem írhatja át.
4. Polar-frissítés induláskor és kérésre, szerveroldali, folytatható és ismétlésbiztos
   adatátvétellel, ellenőrzési idő és legfrissebb adatidő külön jelölésével.
5. Külső naptárak: kiválasztott foglaltságok beolvasása, külön PaddleTrainer-naptár,
   majd kétirányú időpontmódosítás. Ismétlődés, kivétel, törlés és duplázás elleni
   védelem szükséges. A Google/Microsoft/iCloud kapcsolatokhoz külön szolgáltatói
   konfiguráció és tényleges engedélyezés kell; a C6 nem állít be kapcsolatot.
6. Későbbi étrend- és bevásárlómodul. A mostani helyük kifejezetten előkészített
   felületi hely, táplálkozási javaslat vagy bevásárlási művelet még nem keletkezik.

## Ellenőrzés

A csomaghoz hordozható backend- és frontendtesztkapu, teljes TypeScript-ellenőrzés,
ESLint és production build tartozik. A helyi integrációs próba valódi React DOM,
production Next-proxy és valódi HTTP/domain/repository kód között, elkülönített,
szintetikus SQLite-adatbázison fut. Ez funkcionális DOM-próba, nem valódi böngészős
képernyőkép-ellenőrzés. A tényleges Windows/175%-os megjelenítés helyi átnézése
továbbra is szükséges. Éles alkalmazásadatbázist és külső fiókot a kapu nem használ.
