# P2.4C15 — tömör Napirend és közös kezelőszervek

A Napirend felső része egy tömör eszközsáv: dátumléptetés, Ma, négy
időlépték, Nézet, Visszavonás és + Idősáv. Az ismétlődő cím/leírás
vizuálisan elmarad, a szemantikus H1 megmarad. A rétegek és a teljes
24 órás nézet a Nézet lenyílóban érhetők el. A ciklusok és a jelmagyarázat
megnyitható részletekbe kerültek. A hibák és függő írások láthatók maradnak.

A heti/napi naptár a nézetmagassághoz igazodik, szükség esetén saját görgetést
kap; a napfejlécek rögzítettek. Az órák bal oldali oszlopából az időzóna a
naptár időszaksorába került, az Időpont nélkül felirat explicit sortörést kap.
Az idősávok időarányossága, a rövid edzések minimális látható magassága,
az áthelyezés és határhúzás logikája nem változik.

A korábbi „Keret nincs megadva” napi edzésidő-beállítási hiányt jelentett,
nem tiltott napot. Az ismeretlen napi érték rövid vonalként látszik, teljes
akadálymentes szöveggel és megnyitható közös magyarázattal. Nem következtetünk
az adathiányból sem korlátlan edzésidőre, sem elérhetetlenségre. A + Idősáv
felirat az edzéslehetőség/elfoglaltság közötti meglévő választóhoz vezet.

## Frissítés

A közös felső sávban a Frissítés főgomb és a mellette lévő beállításnyíl
külön művelet. A lenyíló megőrzi a meglévő Adatkapcsolatok dialógust,
kapcsolatállapotokat, engedélymegújítást és részletes eredményeket.

A főgomb alapértelmezett választása tárolt adatok újraolvasása. Az explicit
választóban elérhető a megvalósított, csatlakozott, kézzel frissíthető
szolgáltató, visszamenőleges 7/35/89 nap és a jelenleg engedélyezett
adatfajták. A tervekhez a meglévő 30 napos előretekintés marad.
A választás önmagában nem indít POST-ot, oldalbetöltés és preferencia-
visszaállítás sem indít szolgáltatói adatátvételt.

A preferencia sportolónként külön localStorage kulcsba kerül:
`paddletrainer.refresh-choice.v1:{athlete_id}`. Nem tartalmaz hitelesítési
adatot vagy korábbi kérésazonosítót. Tárhelyhiba esetén a választás csak a
jelenlegi megnyitásban él; a bizonytalan írás megőrzésére szolgáló korábbi
sessionStorage-protokoll ettől külön megmarad. Ugyanazon profil következő
megnyitásakor a választás visszaáll, másik profilnál nem használható.

Minden indításnál újra ellenőrizzük a szolgáltató állapotát és engedélyezett
adatfajtáit. Visszavont kapcsolat vagy adathozzáférés esetén a beállítóablak
nyílik meg; nem választunk helyette másik szolgáltatót vagy nagyobb adatkört.
Új kéréshez új UUID készül. Bizonytalan eredménynél viszont a korábbi pontos
kérést kell újraküldeni, és a főgomb nem indíthat mellé másik írást.

A helyi újraolvasás saját `paddletrainer:local-refresh` eseményt ad, nem
színlel szolgáltatói szinkronizálást. A Napirend a feedet és a korlátokat,
a Személyes tapasztalat a meglévő GET-bemenetét olvassa újra; a Célok és
mérések akkor olvas újra, ha nincs folyamatban szerkesztés/függő írás.
A kapcsolati állapot is GET-tel frissül. A többi oldal belső adatkezelőinek
átalakítása későbbi, külön lépés.

## Fejlődés

A két Fejlődés-nézet közös 1480 px maximális külső szélességet, azonos
felső/oldalsó paddinget és tabpozíciót kap. A Célok és mérések korábbi
keskenyebb belső korlátja megszűnik. A gyökér layout explicit közös CSS-
importja mindkét nézeten elérhetővé teszi a látható aktív füleket.

## Terjedelem és ellenőrzés

Frontend-változtatás, backend/API/adatbázis-migráció nélkül. A C14 már
alkalmazott, még nem commitolt állapotára épül, Git HEAD és origin/main:
`9e206f645a268c7eb2b86ca797c6af6ee3577ad3`. Az alkalmazó a teljes C14
forrásállapotot ellenőrzi, a meglévő C14 módosításokat megőrzi. A patch csak
az új C15 eltéréseket írja. Commit és push külön lépés.

A kapu a teljes frontend tesztsort, típusgenerálást, TypeScriptet, a változó
frontend fájlok lintjét és production buildet futtat. A DOM-próbák kizárják
az automatikus szolgáltatói indítást, ellenőrzik a tulajdonoshoz kötött
preferenciát, az egykattintásos ismétlést és az azonos függő törzs újraküldését.
Nincs élő szolgáltatói vagy alkalmazásadatbázis-hozzáférés. A layout tényleges
Windows-képernyőn történő kipróbálása a felhasználói próba része.
