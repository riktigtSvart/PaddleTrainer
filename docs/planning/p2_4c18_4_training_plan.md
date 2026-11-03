# C18.4 — Konkrét kezdőterv és események utáni újraértékelés

A C18.3 cél- és stratégiarétegére épülő első, menthető edzésterv. A felület helye:
**Felkészülés → kiválasztott felkészülés → Edzésterv és újraértékelés**.

## Elkészült működés

1. A mentett mezociklus-képességszerepekből, aktuális profilból, naptári
   időablakokból és a közelmúlt tárolt teljesítéseiből 1–28 napos javaslat készül.
2. A sportoló látja a konkrét edzéseket, blokkokat, célkapcsolatot, megtartást,
   lecserélést, kimaradó napokat és a még nem lefedett képességeket.
3. A javaslat mentése külön, explicit elfogadás. A szerver ugyanabban a zárolt
   tranzakcióban újraolvassa a forrásokat és újraszámolja a döntést. Elavult
   előnézetből nem ír tervet. A teljes tervváltoztatás és bizonylata együtt commitol.
4. Az első elfogadás után az API percenként ellenőrzi az aktív programokat.
   A teljesítések, linkek, javított visszajelzések, napi állapot, célok és naptár
   változása, valamint az edzésidő lejárta újraértékelést eredményez.
   Újraindításkor az ellenőrzés a tartós adatokból folytatódik; nyitott böngésző
   nem szükséges. Kikapcsolt API mellett nem fut háttérmunka.
5. Azonos tartalmú bemenet az eredeti értékelést adja vissza. A szinkronfutás
   azonosítója és az olvasás időbélyege önmagában nem készít új tervváltozatot.
   A felülvizsgálat jóváhagyásig nem írja át a naptárt.

## Első három edzésminta

| Minta | Konkrét kezdőforma | További feltétel |
| --- | --- | --- |
| Könnyű technikai kajak | 10 perc bemelegítés, 15 perc nyugodt technikai evezés, 5 perc levezetés | Kajakos cél, megengedett sport és könnyű intenzitás, deklarált kajak/eszköz, legalább 30 perc |
| Hosszabb könnyű evezés | 10 + 45 + 5 perc | Az előző 14 napban tárolt, befejezett legalább 60 perces kajak; 60 perces időablak és keret |
| Erőreferencia | 5 perc bemelegítés, 20 perces helyfoglalás pihenőkkel, 5 perc levezetés; 2 ismert gyakorlat, 2 × 6, RIR 3–4 | Befejezett legalább 30 perces erőedzés az előzményben; erőnlétet és mérsékelt terhelést engedő ablak; kézisúlyzó |

A családhivatkozás, a meglévő mintatár hash-e és a család védőszabályai a
javaslatban megmaradnak. Az erőminta időblokkja helyfoglalás; a sorozat/ismétlés
a leírásban szereplő előírás. Nem állítjuk, hogy 20 perc folyamatos munka kell.
A saját időtartamreferencia nem bizonyítja a terhelés optimális voltát vagy a
mozgás technikai alkalmasságát. Terhelésnövelés vagy maximális teszt nincs.

## Idő- és terhelési korlátok

Az induló termékpolitika napi legfeljebb egy, gördülő hét nap alatt legfeljebb
három alkalmat és 180 percet enged. Ha a deklarált megszokott gyakoriság vagy
idő kisebb, az a korlát. Ismeretlen heti keretnél két alkalom / 90 perc az
átlátható kezdőalap; ez felső korlát, nem kitöltendő cél. Minimum 36 óra kerül
a tárolt és javasolt alkalmak közé. Ezek verziózott termékszabályok, nem
kutatással igazolt személyes küszöbök.

A meglévő és importált edzések, a tényleges teljesítések és a kiválasztott
tartományon túli hat nap ismert tervei is beleszámítanak a gördülő korlátokba.
A párosított terv és tényleges teljesítés nem számít kétszer. Hiányzó terhelési
időtartamból nem lesz nulla. A közös eredeti ablakkeretet nem lehet a két
naptári napon vagy az elfoglaltsággal szétvágott részeken többször felhasználni.
Az ismeretlen sport- vagy intenzitáskorlát nem jelent szabad felhatalmazást.

Az érintetlen, jövőbeli saját edzések előre foglalják a keretüket. Új üres nap
feltöltése nem tolhatja el automatikusan a már felülvizsgált következő edzést.
Kimaradáskor az eredeti alkalom tervezési kerete foglalt marad: ez nem tényleges
fiziológiai terhelés, hanem az automatikus pótlást akadályozó tervezési szabály.

## Események és bizonytalanság

| Állapot | Újraértékelési jelentés |
| --- | --- |
| Tárolt, tervhez kapcsolt befejezett edzés | Tervezett és teljesített; tényleges időtartam és megfigyelt terhelési adatok |
| Tárolt, tervhez nem kapcsolt befejezett edzés | Nem tervezett teljesítés; a további idő- és gördülő keretben figyelembe vett plusz alkalom |
| Lejárt, kapcsolt teljesítés nélküli terv | `execution_unknown`; a sikeres szinkron sem bizonyít biztos kihagyást |
| Sportoló által megerősített kihagyás | `confirmed_missed`; nincs automatikus bepótlás |
| Hiányos / még folyamatban levő teljesítési rekord | `execution_incomplete`; az ismeretlen adat látható marad |

A saját mintaterv lejárt alkalma mellett a sportoló külön megerősítheti, hogy
az kimaradt. Ez idempotens, tulajdonosi ellenőrzéssel és tartalomellenőrzéssel
védett állapotmentés. Ha közben teljesítés kapcsolódik hozzá, az elavult
kihagyási kérés elutasítás. Késői szinkron után az új értékelés a teljesítést
veszi figyelembe; az eredeti sportolói nyilatkozat auditja megmarad.

A friss másnap reggeli magas fáradtság/fájdalomjelzés a C18.3 szabályával a
közeli napokra felülvizsgálatot kér. A friss betegségjelzés előbb profil- és
állapotfelülvizsgálatot igényel. Az azonnali RPE nem lesz rossz alkalmazkodás
vagy személyes edzéshatás bizonyítéka. Főverseny előtti frissítő/átvezető
szakaszra még nincs dózissablon; az ismert versenynap szabadon marad.

Az automatikus figyelés az elfogadott időszakra vonatkozik, és annak vége után
14 napig a késői adatok értékelését is elvégzi. Nem hosszabbítja meg magától a
jóváhagyott tervidőszakot. A következő időszak külön kérhető a felületen.

## Megőrzési és jogosultsági határok

Csak a C18.4 által létrehozott, auditbizonylattal igazolt, változatlan tartalmú,
még el nem kezdett saját edzés cserélhető. Importált, kézzel módosított,
teljesített, már elkezdett vagy az autoritatív tervrétegbe átvett terv védett.
A lecserélés `CANCELLED` státuszt ír; az eredeti sor és blokkjai megmaradnak.
Változatlan edzés azonosítója megmarad. A szolgáltatói naptárba nincs visszaírás.

A C18.1 GET-szerződés változatlanul csak olvasó bemeneti pillanatkép. Az új író
külön, korlátozott, felülvizsgált alkalmazási mintatervet ment `PlannedWorkout`
és `WorkoutBlock` sorokba. Nem állít P0/P1 `planner_created` autoritatív
`WorkoutPlanContract`-ot, és nem változtatja át az eddigi elhalasztott döntéseket
globális tervezési felhatalmazássá. A személyes válaszmodell továbbra sem kerül
előírásra alkalmazásra. Ez nem kész adaptív élettani optimalizáló vagy teljes
versenyfelkészítés; a még nem lefedett képességek a felületen látszanak.

## API és tárolás

Az `/api/v1/planning/cycles/programs/{identity}/training-plan` alatt:

| Művelet | Útvonal | Hatás |
| --- | --- | --- |
| GET | üres | Legutóbbi ellenőrzött értékelés és elfogadás |
| POST | `/review` | Friss adatolvasás és tartós javaslat; edzést nem módosít |
| POST | `/accept` | Explicit felülvizsgálati nyilatkozat, pontos értékeléshivatkozás és kérésazonosító alapján atomikus tervmentés |
| POST | `/missed` | Saját lejárt alkalom megerősített kihagyása |

Három új szöveges auditfajta: `training_plan_review`, `training_plan_acceptance`,
`training_plan_outcome`. A meglévő audit-táblát használják; új migráció nincs.
A teljes felhasznált bemenet és tervpillanatkép az értékelés mellett rögzített.
A tulajdonosi sor, az érintett tervek, blokkok, teljesítések és napi állapotok
zárolása védi a mentést. A kérésazonosító tartalomhoz kötött; elveszett válasz
után az eredeti kérés bizonylata visszakérhető, a történeti retry nem állítja
vissza a régi tervet. A frontend remount után sem küld automatikus mentést.

Az auditlista és az érintett rekordhalmaz korlátja egyaránt 2000; túllépés
elutasítást okoz, nem csendes csonkolást. A háttérfolyamat hibánál naplóz és
újrapróbál; egy program hibája nem állítja meg a többinek az ellenőrzését.

## Források és az alkalmazási következtetés határa

- García-Pallarés et al. (2009), DOI 10.1007/s00421-009-1061-2:
  https://pubmed.ncbi.nlm.nih.gov/19396614/ . Gyakorlati példa az állóképességi
  és erőedzés együttes periodizálására elit kajakosoknál. Nem igazolja a fenti
  kezdő dózisokat vagy azok személyes eredményességét.
- ACSM (2009), DOI 10.1249/MSS.0b013e3181915670:
  https://pubmed.ncbi.nlm.nih.gov/19204579/ . Az edzéselőzmény és cél szerinti
  kontextus fontosságát támasztja alá; a konkrét 2 × 6 / RIR 3–4 / 30 perces
  referencia itt saját mintapolitika, nem a közleményből igazolt személyes recept.
- A három család a projekt meglévő `workout_family_registry_v0.1` mintatárából
  származik. A felületen közölt blokkok, heti keretek, időközök és visszalépési
  szabályok a jelen verzió explicit, később módosítható implementációs választásai.
