# P2.4C10 — Szakaszonkénti értékelés, kézi váltások és köztes idő

Alap: `c87b162c962220242384a2a76c902f7b97ebf75f`, tiszta main / origin/main.
A teljes forrás a megadott commitból helyreállított, ellenőrzött 1047 fájl.

## Használat

Az edzésrészletező grafikonjai mellett megjelenik a **Szakaszonkénti értékelés**:
táv, mért időablak, átlagpulzus, átlagsebesség és iram, átlagteljesítmény,
célban/alatta/fölötte töltött idő és adatlefedettség. A **Kijelölés** vagy a
határidőpontok **Mutasd** gombja közös időtartományra nagyít, és a saját szakasz
célját emeli ki. A km/h, m/s és knots váltás az időpontokat nem módosítja.

Az ismert automatikus váltások a saját idő- vagy távcéljuk után következnek.
A `REPEAT` tiszta szerkezeti csoport; a gyermekek saját `changeType` értéke
érvényesül. A két ismétlési csoport külön céljai és az ismétlések külön
előfordulásazonosítói megmaradnak.

**Kézi váltásnál** a célelérés és a következő kezdés külön esemény. A következő
kezdés ismerete nélkül a későbbi határok és szakaszértékelések bizonytalanok.
A grafikon összes mintája megmarad. A be nem sorolható maradék külön, semleges
időablakként és sorban jelenik meg.

A **Kézi szakaszkezdések** mezőiben az ismert következő kezdőpont a mintasor
0:00 pontjához viszonyítva, perc:mp formában adható meg. Az előző cél elérése és
ez a kezdőpont közé eső idő **Várakozás / szakaszok között**. Saját távja és
mért átlagai megmaradnak, célzóna-értékelés nem tartozik hozzá. Nulla várakozáshoz
a célelérés időpontját kell megadni. A mező ebben a változatban a célelérés
utáni kezdést kezeli; a cél elérése előtti váltás nem igazolható ilyen módon.

A kézi kezdőpontok helyi referenciaadatok, sessionStorage-ban, a sportolóhoz,
edzéshez, kiválasztott edzésrészhez, tervhash-hez és mintasorhash-hez kötve.
Új forrásváltozat nem használja a régi választ. A kezdőpont törlése ismét
bizonytalanná teszi az utána következő részeket. Tárolási hiba mellett a referencia
az aktuális nézetben használható, külön értesítéssel. Nem módosít tervet vagy
teljesítést, és nem válik igazolt szolgáltatói fázisváltássá.

## Adat és bizonytalanság

A meglévő tulajdonoshoz kötött GET megőrzi a levélszakasz indítási módját,
intenzitási előírását és natív forrásmutatóját. Meglévő ORM-blokkokhoz a natív
metaadat csak teljes hierarchia-, sorrend-, név-, ismétlés-, cél- és intenzitás-
egyezés mellett rendelhető. Egyezés hiányában a váltás módja `UNKNOWN` marad.
A tiszta MANUAL repeat-wrapper szabálya a korábbi fázisegyeztetés
`_repeat_policy` elvével egyezik. A korábbi, egy másodperces kutatási jelölteket
előállító egyeztető eredménye nem válik automatikusan igazolt grafikonhatárrá.

A `plan_timeline` továbbra is tervvetület; a grafikon időbeli illesztése külön
kezeli a kézi kezdést és az ismeretlen váltást. A név nem időzítési forrás.
A minták tartalmi hash-e független az újraolvasás időpontjától. Az adatforrás
alapján ismert belső rögzítési szünet külön időalap-egyeztetést igényel:
ilyenkor az automatikus fázisértékelés visszatartott, a görbék megmaradnak.
A felvétel végén kezdődő szünetből nem keletkezik belső várakozás.

A statisztika minden megfigyelt időintervallumot egyszer sorol munkához,
pihenőhöz, kézi referenciával lokalizált várakozáshoz vagy be nem sorolt időhöz.
Az előírt vég a mintasor vége után is megmarad, a mért időablak és a lefedettség
csak a rendelkezésre álló felvételt használja; a rövidebb utolsó rész **Részleges**.

## Számítás

Az értékelés a teljes, nem rajzolásra ritkított mintasort használja. Minden
csatorna saját időközével dolgozik. Az `[i*dt,(i+1)*dt)` időszakban a bal oldali
érték érvényes, ha mindkét szomszédos végpont ismert. A hiány nem hidalható át,
a legutolsó minta mögött nincs extrapoláció. Az átlag idővel súlyozott, a célban
töltött százalék az ismert időre vonatkozik, az ismeretlen idő külön jelenik meg.
Az ablakhatáron levő megfigyelés nem számít kétszer két szakaszhoz.

A táv a két pontosan illeszkedő távminta különbsége, köztes mintahiány vagy
számláló-visszaesés nélkül. A sebességátlag a sebességminták időátlaga; az iram
ebből számított, másodpercre kerekített érték. A nulla sebesség megmarad, hozzá
nem készül végtelen iram. A teljes teljesítmény a meglévő, egyidejű, azonos
felbontású bal+jobb összegből készül. Több versengő csatornából nem választ egyet.
A hiányzó zónahatárok és az ismeretlen időablak külön értékelhetetlenségi okok.

Az eredmény leíró nézet a terv végrehajtásáról. A mezociklus fejlődését továbbra
is a preregisztrált célokhoz és mérési protokollokhoz kell kötni.

## Technikai határ és ellenőrzés

Nincs új végpont, függőség vagy migráció. Az alkalmazás-adatbázisba nem ír,
Polar-kérést nem indít. A frontend továbbra is a zárt, no-store átjárót használja.
A forrásokban és a mért edzésben nem keletkezik módosítás olvasás vagy kézi
referenciaadás miatt.

Az új tesztek valódi, izolált tulajdonosi GET-et, natív/ORM-egyezést, levél-
és wrapper-szemantikát, forrásváltozást és rögzítési szünetet ellenőriznek.
A frontend számszerű időtartam-, táv-, átlag-, célidő-, lefedettség- és megőrzési
próbákat futtat. Az interaktív React/DOM ellenőrzés a zárt proxyn keresztül
FastAPI és ideiglenes SQLite adatbázis között működik.
