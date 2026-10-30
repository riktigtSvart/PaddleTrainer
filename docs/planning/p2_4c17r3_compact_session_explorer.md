# P2.4C17R3 – Kompakt edzésrészletek

A C17R2-re épülő frontend-változás. Nincs backend-, API-, import-, tanulási vagy mérési változás.

- A grafikon megtartja a 290–420 px közötti, 36dvh magasságot. A bal tengelyhez tartozó érték és általános vezérlők bal oldalt, a jobb tengely értéke jobb oldalt vannak. A sebesség mértékegysége a sebességet/iramot megjelenítő oldalra kerül; ha mindkét oldal ilyen, a közös egységválasztó balra kerül.
- Az aktuális idő és táv az összesítők alatt van, ugyanazt a kurzort használja, mint a grafikon és a térkép. A táv csak az eredeti, egyértelmű távsor alapján jelenik meg. A duplázott szakasznév a grafikonból kikerül.
- A teljes edzés és a szakasznézet azonos magasságú névsort és azonos méretű kártyákat használ. A teljes edzés neve elsődlegesen a párosított terv címe. A hosszú cím rövidül, teljes szövege a címre mutatva elérhető. A szakaszátlagok magyarázata külön, kinyitható információ.
- A térkép 230–300 px közötti, nézetmagassághoz igazodó területet kap. A vezérlők és a továbbra is olvasható, kattintható forrásmegjelölések rákerülnek a térképre. A vetület és a mutatókoordináták a ténylegesen mért szélességhez és magassághoz igazodnak.
- Az útvonal élénk magenta, sötét körvonallal, a kijelölt szakasz sárga. Az adatkimaradások különálló vonalszakaszai, a kézi referenciák és az időalap-figyelmeztetések megmaradnak.
- Az alsó szakaszsáv és a közös pontkövető teljes szélességű. Mobilon az oldalsávok a grafikon fölé kerülnek; az oldal szabadon görgethető, a tartalom nincs levágva.

Az elrendezés a megadott 2880×1800 / 175% nézetre törekszik. A tényleges Windows-betűméret, böngészősáv és további nagyítás befolyásolhatja a hajtás helyét. A DOM-próba nem helyettesíti a natív képernyőn történő próbát.

A telepítő a teljes 1122-fájlos feltöltött forrásállapotot ellenőrzi. A nyolc módosított/új fájlról eredeti bájtmentést készít, a Next-cache-t külön menti. Eltérő, staged vagy részlegesen alkalmazott forrást elutasít. Teljes alkalmazás után az újrafuttatás idempotens. Nincs Git-írás vagy szolgáltatói kérés.
