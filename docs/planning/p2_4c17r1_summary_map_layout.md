# P2.4C17R1 – Összesítők és térkép a grafikon fölött

A C17 működő állapotára épülő frontend-elrendezés.

- A cím és szolgáltatói kapcsolat alatt balra háromoszlopos, kétsoros összesítő kerül; közepes szélességnél két oszlopra vált.
- Jobbra, 340 px széles oszlopban közel négyzetes térkép jelenik meg. A rajzolási magasság a tényleges, ResizeObserverrel mért szélességet követi, 230–340 px között. A GPS vetítése és a kurzor koordinátaszámítása az új magasságot is használja; nem pusztán a régi térkép képe nyúlik meg.
- A közös grafikon alul, teljes szélességben marad. Magassága nagy képernyőn a viewport 30%-a, 250–350 px között, a korábbi 24%-os beállítás helyett.
- A térkép React portal segítségével kerül a felső helyére. A kurzort és a kijelölt szakaszt továbbra is ugyanaz az explorer tartja, nem jön létre második térkép vagy külön kijelölés.
- 760 px alatt a felső blokk egymás alá rendeződik, a grafikon teljes szélességű marad. 480 px alatt az összesítők két oszlopban jelennek meg.

A visszajelzés, a szakaszillesztés, a zónák, a forrásértékek, a sebességegységek és a háttér-előkészítés változatlanul elérhetők. Nincs backend-, API-, adatbázis- vagy szinkronmódosítás; csak a frontend újraindítása szükséges.

A térkép szerveroldali rendereléskor helyet kap, majd a kliens felcsatolásakor ugyanide kerül az interaktív tartalom. A grafikon–térkép pontkapcsolat és a szakaszkijelölés külön DOM-próbával ellenőrzött. A Windows 175%-os, teljes képernyős elrendezést a helyi kipróbálás ellenőrzi; a teszt nem helyettesíti ezt a vizuális próbát.
