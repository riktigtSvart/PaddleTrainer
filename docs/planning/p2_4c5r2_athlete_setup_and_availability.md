# P2.4C5R2 — sportolói felmérés, tényleges edzéslehetőségek, adatforrások

A C5R1-re épülő változat a sportolói kereteket összekapcsolja a felkészülés
rögzítésével. Új oldal: `/athlete-setup`. A heti szokásos keret külön adat a
konkrét napokra és alkalmakra megadott edzéslehetőségektől.

## Felhasználói út

1. **Sportolói alapok:** születési dátum (ebből számított, dátumhoz kötött életkor),
   élettani referencia szerinti nem, opcionális versenykategória, célsportág.
   A sportmúlt sportáganként/szakáganként rögzíthető: kezdet, jelenlegi vagy
   korábbi részvétel, elért szint, heti gyakoriság, kihagyások. A sportmúlt
   hiánya különbözik a még fel nem mért sportmúlttól.
2. **Korlátozások:** állandó vagy ideiglenes; mozgás, látás, hallás, egészségi
   állapot/kezelés, egyéb. Az érintett terület, kerülendő mozgások, alkalmazkodás,
   segítség/eszköz, szakemberi utasítás és felülvizsgálati nap is megadható.
   A címkéből nem számítunk képességhiányt. A felülvizsgálat napja nem törli
   a korlátozást, és nem jelent automatikus gyógyulást.
3. **Gyakorlati keret:** hozzávetőleges heti edzésnap és perc, visszatérés/kihagyás,
   eszközök, helyszínek, hozzáférési segítség és regenerációs körülmények.
4. **Naponkénti edzéslehetőségek:** 7/14/28 napos gyorsválasztás, egyedi
   1–366 napos időszak, illetve egy meglévő mezociklus teljes, aktuális időkerete.
5. **Mérések és órás adatok:** tárolt előzmények áttekintése, új Polar-lekérés,
   megfigyelések kijelölése, kézi adatok és kifejezett korrekciók. A kijelölést
   a felmérés mentése véglegesíti. A naptár külön menthető.
6. **Felkészülés:** a friss felmérés és naptár pontos hivatkozása a programba
   kerül. A program előnézete és mentett nézete mutatja a felülvizsgálandó
   kereteket és az első mezociklus naptári hiányait.

A részek közötti váltás megőrzi a szerkesztett adatokat. A még el nem küldött
piszkozat oldalelhagyáskor/frissítéskor elveszhet; mentés előtt ezt a felület
jelzi. A már elküldött, még nem igazolt írás pontos törzse külön megmarad.
Chatbot, új szolgáltatói kulcs vagy új frontend-függőség nem szükséges.

## Célonkénti mezők

| Cél | Strukturált mezők |
| --- | --- |
| Testsúlycsökkentés | Jelenlegi és céltestsúly, pozitív decimális kg; kisebb célérték |
| Testsúly megtartása | Jelenlegi testsúly; ez a megtartandó érték |
| Állóképesség, erő, mobilitás | Fejlesztés vagy szinten tartás |
| Rendszeres mozgás | Opcionális heti edzésszámcél |
| Versenyteljesítmény | Célversenyek, opcionális eredménycél; külön szűkítés nélkül a főversenyek |
| Közérzet | A kiválasztott cél önmagában elegendő |

Minden célhoz adható opcionális kiegészítés. Kötelező szabad szöveg nincs.
A kompatibilitási `target_description` automatikusan készül el. A pontos
képességcélok, mérési protokollok és sikerkritériumok továbbra is a C1/C2
folyamatban, előzetesen rögzítendők. A csökkentés és a megtartás a strukturált
felületen egymást követő célok, egy programban nem jelölhetők egyszerre.
A testsúlyértékből nem készül kalóriacél, fogyási ütem vagy étrend.

## Naptári szerződés

- Minden nap külön állapot: `unknown`, `unavailable`, `available`.
  Az időszak minden napját pontosan egyszer, időrendben tároljuk.
- Naponta legfeljebb nyolc ablak: helyi kezdés/befejezés, következő napi
  befejezés, maximális edzésperc, opcionális napi összes időkorlát,
  sportági lehetőség, terhelési felső keret, eszköz, helyszín, megjegyzés.
- Az ablakok lehetőségek, az összes ablak kihasználása nem kötelező. A heti
  átlag nem tölti ki a konkrét naptár hiányzó napjait. Üres sport/eszközlista
  nincs ismert lehetőségként értelmezve; a sportági állapot külön mező.
- A napi összes keret az adott napon kezdődő ablakokra vonatkozik. Átfedő
  ablak, az ablaknál hosszabb edzésidő és túl nagy napi keret elutasítandó.
  Éjfél után végződő ablak nem nyúlhat teljesen elérhetetlennek jelölt napba.
- A sportoló meglévő IANA-időzónáját használjuk. A nem létező DST-időpont
  elutasítandó; ismétlődő óránál az első/második előfordulást ki kell választani.
  A tényleges UTC-kezdés/befejezés és eltelt perc a mentett változat része.
- Kijelölt napokra másolható egy konkrét nap kerete. Az átfedő napok az
  időszak átméretezésekor megmaradnak, az új napok ismeretlenek.
- Teljes mezociklus mentésekor a szerver ellenőrzi a tulajdonost, típust és
  aktuális dátumokat. Időközben módosított határral új áttekintés szükséges.
  A korábban mentett naptár pontos újraküldése változatlan bizonylatot ad.
- Egy új naptárverzió teljes pillanatkép. A korábbi változat megmarad.
  A tervezési kontextusba kért, kitöltetlen vagy a horizonton kívüli napok
  ismeretlenek; nem lesznek automatikusan szabad vagy pihenőnapok.

## Történelmi adatok és források

A csak olvasó forrásadapter a sportoló meglévő `WorkoutSession`,
`PhysiologicalMeasurement`, `Assessment`/`Measurement` és `AthleteReadiness`
adataiból készít javaslatokat. Csak ismert metrikakulcs és megfelelő egység
kerül át; a módszer vagy lefedettség hiánya látható bizonytalanság.
Az ismeretlen időtartamú edzés ad egy rögzített eseményt, de nem nulla percet.
A kiválasztott javaslat friss lenyomatát első átvételkor újra ellenőrizzük.
A már elfogadott profil megfigyelései a későbbi profilverzióban változatlanul
megőrizhetők akkor is, ha az élő forrás időközben változott.

A kézi érték és a tört lefedettségi idő pontos decimális szöveg.
Így a Python és a JavaScript számábrázolása nem módosítja a bizonylat lenyomatát. Tartozik hozzá dátum/időszak, egység,
sportág, módszer, opcionális protokoll és körülmények. Az érték jelentése
külön `single`, `total`, `mean` vagy `median`; többnapos adat nem jelölhető
hallgatólagosan egyetlen napi értéknek. A kézi korrekció azonos metrikát,
időszakot és összesítési módot követel, és megőrzi az eredeti kijelölt adatot.

Az új Polar-útvonal az alkalmazás meglévő, saját tulajdonoshoz tartozó OAuth-
kapcsolatát használja. Kifejezetten kiválasztott adatkör és nap kérhető le:

| Adatkör | API | Jogosultság | Felismert javaslat |
| --- | --- | --- | --- |
| Edzések | `/training-sessions/list` | `training_sessions:read` | Tevékenység és edzésperc |
| Alvás | `/sleeps` | `sleep:read` | Alvásidő és pontszám, eszközbecslés |
| Éjszakai regeneráció | `/nightly-recharge-results` | `nightly_recharge:read` | Éjszakai RMSSD |
| Folyamatos pulzus | `/continuous-samples` | `continuous_samples:read` | Csak háttérminták átlaga, mintaszám és időbeli tartomány |
| Aktivitás | `/activity/list` | `activity:read` | Eszközönkénti rögzített lépésminták összege és lefedett idő |
| Órás felmérések | `/tests/list` | `tests:read` | Polar Fitness Test / OwnIndex, kifejezetten becslésként |

Hivatalos, ellenőrzött szerződés: <https://www.polar.com/polar-api-v4/>.
A napi aktivitás részletes mintái csak egynapos kérésben érhetők el; a `to`
nap kizáró felső határ. A felület legfeljebb 31 napot kér le egy adagban,
naponként külön, megőrzött kérésazonosítóval. Ez alkalmazáspolitikai adagméret,
nem a szolgáltató által garantált teljes történelmi hozzáférés.

Az új importútvonal a teljes dekódolt szolgáltatói JSON-t őrzi, az egyelőre
nem értelmezett mezőkkel együtt. A tartalmilag megváltozott válasz külön
`ProviderDataRecord`-változat, azonos válasz új kérésből is újrahasználható.
A nyers rekord és az importbizonylat együtt commitolódik. Forgatott OAuth-
frissítőtoken külön, a következő adatkérés előtt mentődik; így egy későbbi
szolgáltatói hiba miatt nem veszítjük el az új tokent. A kliensnek token vagy
nyers szolgáltatói válasz nem kerül vissza.

A profil kiválasztása külön művelet az importtól. A háttérpulzus nem nyugalmi
pulzus, a minták nem jelentenek folytonos egész napos lefedettséget. Több
óra lépéseit nem összegezzük; hibás/átfedő lépésvektorból nem gyártunk adatot.
Az OwnIndex nem lesz laboreredmény. A célzott protokoll szerinti mérést nem
állítjuk elő egy tetszőleges edzésből. A régebbi teljes edzésszinkronizáló
folyamatok és az új felmérési import külön műveletek maradnak.

## Tervezési keret és megőrzött hivatkozások

A `athlete-intake-review-policy-v0.1` önbevallott tervezési jelzőket képez a
meglévő belépési állapotok szókészletével. A szünet `HOLD`, a kifejezetten
szakemberrel tisztázandó részvétel és az aktív ideiglenes korlátozás
`REVIEW_REQUIRED`. Állandó fogyatékosság/adaptáció nem általános edzéstilalom.
A hiányzó lényeges keret adatkorlátozott, felülvizsgálandó állapot. A 18 év
alatti sportoló utánpótlási tervezési ágat kap; az életkor önmagában nem
orvosi diagnózis vagy biológiai érettségi becslés.

Ez nem validált sportorvosi szűrő vagy klinikai engedélyezés. Minden bizonylat
`planning_authorized=false`, `workouts_created=false`, a klinikai engedély
jelzője is hamis. A felmérés nem váltja ki a szakmai döntést; a testsúlyadatból
nem lesz automatikus felnőtt étrendi vagy edzésadagolási szabály.

A felmérés/naptár módosítását a tulajdonos sorának zárolása és az előző
hivatkozás ellenőrzése védi. Nincs alacsony, napi használattal hamar kimerülő
verziószámkorlát. A program mentése ugyanezen tulajdonost zárolja, és a legfrissebb
felmérés/naptár pontos hivatkozását ellenőrzi. Elavult tervnél a felület a friss
felmérés átvételét és új áttekintést kínálja, a szerkesztett célok megtartásával.

Az új program `cycle-program-registration-v0.3`: felmérési hivatkozások,
sportmúlt és demográfiai háttér, értékelés, korlátozások, általános lehetőségek,
az első mezociklus tényleges naptári kerete és a megfigyelések hivatkozott
száma kerül a pillanatképbe. A részletes forrásértékek a hivatkozott, változatlan
profilban maradnak. Későbbi profil/naptár-változás nem írja át ezt a tervet.
A v0.1/v0.2 programok és régi, már függő mentések pontosan visszajátszhatók.
Egy célverseny későbbi lemondása megőrzi az eredeti célhivatkozást, és látható
célfelülvizsgálati jelzést ad; nem akadályozza a versenynaptár pontosítását.
Zárolásra váró, azonos ciklusmentés a zárolás után ismét ellenőrzi a már
commitolt bizonylatot, így nem próbálja másodszor létrehozni a ciklusokat.

## API és működtetés

Új prefix: `/api/v1/planning/athlete`.

- `GET /context` — aktuális profil, naptár, mai értékelés, saját Polar-adatkörök;
  opcionális, együtt megadandó `start_date`/`end_date` naptári lekérdezés.
- `POST /profiles`, `POST /availability` — új teljes pillanatkép,
  `request_id`, `previous_reference`, `data`.
- `POST /availability/preview` — írásmentes, időzónát és ablakokat ellenőrző előnézet.
- `GET /profiles/{identity}`, `GET /availability/{identity}` — megőrzött saját változat.
- `GET /history?start_date=...&end_date=...` — saját, tárolt átvételi javaslatok.
- `POST /polar-imports` — egy adatkör/nap, megőrzött `request_id` mellett.

A meglévő same-origin proxy csak ezeket az útvonalakat engedi. Nem továbbít
sütit, Authorization fejlécet vagy tetszőleges cél-URL-t. Az Origin-ellenőrzés,
a ténylegesen beolvasott 1 MiB POST-limit, a zárt query és a `no-store` megmarad.
A jelenlegi alkalmazás konfigurált demo-tulajdonosát használjuk; új bejelentkezési
rendszert nem vezet be a változat.

Nincs új migráció vagy függőség. A korábbi `a2c31f5d9b70` adatbázis-head elegendő.
Az új auditfajták: `athlete_profile`, `athlete_availability`, `athlete_polar_import`.
A közvetlenül a böngészőből kezdeményezett adatírások előbb megőrzik a pontos
kérést. Bizonytalan eredménynél új azonosító helyett azonos kérés küldhető újra.
A napi importlista megállítható az aktuális kérés után; frissítéskor nem indul
magától, külön folytatás szükséges. Ismert elutasításnál elvethető a visszautasított
kérés és a még el nem küldött maradék. Ismeretlen kimenetel nem dobható el így.

A háttéradatok regisztrációja és az első mezociklus naptári ellenőrzése elkészült.
A személyes terhelés–válasz modell tanítása, a teljes automatikus edzésadagolás,
a mezociklushatárok automatikus áttervezése és a táplálkozási modul következő
fejlesztési lépések; ezeknek a felmérés és a megőrzött források bemenetet adnak.
