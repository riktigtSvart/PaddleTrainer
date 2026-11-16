# C20.3 — Helyszíni erősítőeszközök és gyakorlatkatalógus

Az **Edzési lehetőségek → Helyszínek** szerkesztője a **Kondi** mozgásforma kijelölésekor képes, többválasztásos eszközlistát mutat. Az induló katalógus 55 felszereléstípust és 80 kapcsolódó gyakorlatot tartalmaz. Az adatok helyszínhez tartoznak; a heti lehetőségek a meglévő általános órarenden keresztül öröklik őket.

## Felhasználói működés

- Hét eszközcsoport: alapok és támaszok; szabad súlyok; állványok; csigák és tartozékok; erősítőgépek; funkcionális eszközök; ergométerek és kardiógépek.
- Saját, témához igazodó SVG ábra, név és rövid megkülönböztető szöveg minden eszközkártyán. A kártya egészében a natív jelölőnégyzet címkéje; billentyűzettel is használható.
- Keresés magyar névvel és ismert angol elnevezéssel, csoportszűrés, csak a kijelöltek nézet és kijelölésszámláló. A szűrés nem módosítja a kijelöléseket.
- Az új keresés minden csoportban indul. Utána a keresés és a csoportszűrő együtt szűkíthető.
- A gyakorlatlista külön, összecsukható rész: magyar/angol név, hat mozgáscsoport és a helyszínen kijelölt felszerelés szerinti szűrés.
- A négy feltöltött infografika eredeti képként, helyi állományból nyitható meg. A kapcsolódó gyakorlatok közvetlenül is megnyitják a megfelelő lapot. Bezárógomb, Escape és a megnyitó gombra visszatérő fókusz támogatott.
- Egyedi felszerelés szabad szöveggel hozzáadható. Egy korábbi, vesszőt is tartalmazó eszköznév nem darabolódik fel és nem vész el. Eltávolítása külön művelet.
- A Kondi kijelölés kikapcsolása elrejti az eszközkatalógust, megőrzi a korábban megadott felszerelést. Kondi nélkül a helyszín nem lesz erősítési lehetőség.
- A mentés a meglévő helyszínmentés része. Keresés, lapnyitás, kijelölés és elvetés önmagában nem küld hálózati írást.

## Eszköz és gyakorlat kapcsolata

Egy gyakorlat `requirements` mezője alternatív eszközkészleteket sorol fel. Egy belső lista minden eleme egyszerre szükséges; a külső lista készletei egymás helyett használhatók.

| Példa | Katalógusbeli feltétel |
| --- | --- |
| Goblet guggolás | Kézisúlyzó **vagy** kettlebell |
| Rudas evezés | Súlyzórúd **és** tárcsák **és** tárcsarögzítők |
| Csigás face pull | Megfelelő csiga **és** kötélfogantyú |
| Gumiszalagos Pallof nyomás | Gumiszalag **és** rögzítési pont |

Az egyezés az adott helyszín eszközlistájából számolódik. Más helyszín vagy a sportoló globális felszerelése nem egészíti ki. Állványból nem következtetünk automatikusan húzódzkodórúdra; általános „labda”, „multigép” vagy „evezőgép” szövegből nem találunk ki konkrét típust. A kajakergométer és az evezős ergométer külön eszköz és külön gyakorlat.

Az „Eszközei megvannak” kizárólag felszerelési egyezést jelent. Nem igazolja a gyakorlat ismeretét, az egyéni alkalmasságot vagy a terhelés megválasztását. Nem állít elő új erőedzési dózist, nem módosítja az erőedzéshez szükséges saját referencia feltételeit. Az új gépekre épülő edzésgenerálás és a gyakorlatonkénti jártasságfelmérés külön következő feladat.

## Adat- és kompatibilitási szerződés

- A meglévő `Location.resources` őrzi a neveket. A meglévő mentési séma nem kap új alapértelmezett mezőt; korábbi függő kérések, hash-ek és tartós nyugták változatlan tartalommal ellenőrizhetők.
- A helyszíni és a naptárba vetített felszereléslista felső határa 128. A globális sportolói profil korábbi korlátja változatlan.
- Az új `strength-catalog-v0.1` katalógus saját tartalmi hash-sel, stabil azonosítókkal, pontos név/alias egyezéssel és helyi segédlap-hivatkozásokkal érkezik.
- Az edzési lehetőségek GET válaszának új `strength_catalog` és `strength_options` mezői csak olvasható kiegészítések. A `strength_options` kizárólag aktív, Kondi mozgásformájú helyszíneket tartalmaz.
- A kliens ellenőrzi a katalógus hash-ét, a hivatkozásokat, az egyértelmű aliasokat, a feltétellistákat, a képek helyi útvonalát és méreteit. A helyszíni egyezéseket a saját eszközlistákból újraszámolja és pontosan összeveti.
- A régi válasz a két új mező nélkül is olvasható. A másik mezőhöz nem illő vagy önmagában érkező egyezéslista hibás válasz.
- A katalógus mindkét engedélyjelzője hamis: `planning_authorized`, `workouts_changed`. A mentés továbbra is csak a lehetőségeket verziózza; edzés vagy naptári terv nem változik.
- Nincs új útvonal, függőség vagy adatbázis-migráció.

## Képek és források

A kártyarajzok eredeti, kódból rajzolt SVG illusztrációk. Nincs külső képletöltés vagy képkiszolgáló. A feltöltött poszterek szerkesztés nélkül kerülnek a `public/strength-guides` mappába, valódi képméreteikkel:

1. `kayak-phases.png`: kajak mozgásfázisai.
2. `back-arms.png`: hát, vállöv és karok.
3. `trunk.png`: törzsizmok és törzsrotáció.
4. `legs.png`: csípő, láb és funkcionális gyakorlatok.

A poszterek szemléltető anyagok. Az izommunka-pontszámok nem kerülnek a személyes modellbe. A poszterek egyes sematikus ábrái nem határozzák meg az alkalmazás géptípusait; a két ergométert a katalógus önállóan megkülönbözteti.

Az induló névanyag a felhasználó feltöltött lapjaiból és az alábbi elsődleges gyakorlatkönyvtárakkal végzett ellenőrzésből áll össze. Külső gyakorlatfotókat és oktatószövegeket nem másolunk:

- [ACE Exercise Library](https://www.acefitness.org/resources/everyone/exercise-library/)
- [NASM Exercise Guidance](https://www.nasm.org/workout-exercise-guidance)

## Ellenőrzés

Az új backendtesztek valódi HTTP/tárolási környezetben ellenőrzik a helyszíni elkülönítést, az eszközfeltételeket, az 55 eszköz együttes mentését és naptári továbbadását, a pontos újrapróbálást, a saját nevek megőrzését és a 128-as határt. Az eszközcenzus önmagában nem oldja fel az erőedzés referenciafeltételét.

A böngészőoldali tesztadatot ugyanaz a valódi backend állítja elő. A tesztek a katalógust és a tartós nyugtát külön is ellenőrzik, és elutasítják a más helyszínről átvett gyakorlatot, a hiányos listát és az újrahash-elt, hibás katalógust. Külön DOM-interakció ellenőrzi a szerkesztést, szűrést, képlapokat, fókuszt, elvetést és az egyetlen kifejezett mentést.

A teljes projektellenőrzés: `python tools/run_c20_3_checks.py --build`.
