# C20.6.4 — Látható indítási teendők és előzetes felmérési útmutató

## Megvalósított változás

A C20.6.3 képernyőképén a kezdeti szerkesztő nyitva van, ezért az előkészítő mezők és az indítás zároltak. A gyakorlatok feliratai ezenfelül még közös, mentett adatokhoz kapcsolódó akadályt jeleznek; a teljes felső oklista nincs a képen. A nyitott szerkesztő bezárása önmagában ezért nem bizonyítja, hogy minden szerverfeltétel rendeződött. A feltöltött C20.6.3 tesztkapu sikeres.

Az indítás mellett, a zárolt mezőcsoporton kívül is megjelenik a **Vissza a gyakorlatválasztáshoz** gomb. A felső és az alsó visszatérés egyaránt friss, ellenőrzött szerverolvasást indít. A helyszín és a továbbra is megfelelő gyakorlatok kijelölése megmarad; a bezárás nem indít mentést vagy alkalmat. Ha a közös feltételek továbbra sem teljesülnek, az indítás alatt is teljes, konkrét oklista és az érintett szerkesztőhöz vezető hivatkozás látható.

A **Felmérőalkalom előzetes menete** megjeleníti a már ellenőrzött protokollból származó bemelegítést, próba- és referenciasorozatot, ismétlés-/tartásidő-tartományt és pihenőt. A gyakorlatok az adott helyszínen kijelölt, tényleges bejegyzésekből származnak, a kijelölés sorrendjében. Új gyakorlatot nem választ helyettük a program. A leírás indítás nélkül is olvasható.

Négy gyakorlathoz saját szövegezésű végrehajtási emlékeztető és szakmai hivatkozás került be: fekvenyomás rúddal; mellhezhúzás hason fekve; saját testsúlyos guggolás; függeszkedésben lábemelés. A meglevő képes segédlethez helyi hivatkozás tartozik, ha az adott katalóguselem rendelkezik vele. Más gyakorlatnál a részletes leírás hiánya kifejezetten látszik. Az aktuális gyakorlat emlékeztetője a végrehajtási lépésben is megjelenik, az alkalom befagyasztott katalógusából választva.

Ezek az emlékeztetők a már ismert végrehajtást segítik; nem jelentenek személyre szabott technikai betanítást. A súlyválasztás továbbra is a felhasználó saját ismert, könnyű terhelése. Nincs új kg-, 1RM-, sorozatszám- vagy erőállóképességi előírás.

## Mi állapítható meg jelenleg?

| Terület | Jelenlegi állapot |
|---|---|
| Gyakorlatonkénti kiinduló sorozat | A jelenlegi alkalomban menthető, tényleges saját eredmény |
| Maximális erő | Ezzel a könnyű referenciasorozattal nincs megmérve |
| Helyi erőállóképesség | Nincs külön felmérve |
| Egymást követő munkasorozatok elviselése | Egyetlen referenciasorozatból nincs meghatározva |
| Egész edzés terhelhetősége és következő edzésig tartó regeneráció | Nincs a jelenlegi felmérésből meghatározva |

A meglévő alkalom legfeljebb egy próba- és egy referenciasorozatot kezel. A következő táblázatok és szabályok **a következő fejlesztés termékkövetelményei, nem már működő felmérési vagy tervezési jogosultságok**. Ebben a frissítésben nem bővült a tárolt sorozatséma vagy a tervező adagolási szabálya.

## Következő fejlesztés: ismételt sorozatok és regeneráció

Három külön megfigyelési mód szükséges, külön eredménnyel és forrásokkal:

1. **Kiinduló referencia:** ismert gyakorlat, ismert változat és beállítás, tényleges terhelés, szabályos ismétlés vagy tartás, önbevallott tartalék, kivitelezés és panasz. A jelenlegi felmérés ehhez ad első adatot.
2. **Erőállóképességi megfigyelés:** azonos gyakorlatváltozat, terhelésjelentés, mozgástartomány, végrehajtási szabály és pihenő mellett követett ismétléses teljesítés. A magasabb ismétlésszám önmagában nem jelent személyes erőállóképességi minősítést.
3. **Sorozattűrés és edzésterhelés megfigyelése:** az egymást követő sorozatok és az egész alkalom eredménye, a megszakítás vagy kihagyás oka, majd időben rögzített utánkövetés a következő edzésig. A teljes edzés elviselése különbözik egy gyakorlat egyetlen sorozatának teljesítésétől.

### Szükséges adatok

| Adat | Szabály |
|---|---|
| Gyakorlat, változat, gép és beállítás | Pontos azonosítás; más gép, fogás, rásegítés vagy lábemelés-változat nem vonható automatikusan össze |
| Sorozat sorszáma és rendeltetése | Próba, munkasorozat, referencia és ismételt megfigyelés elkülönítve |
| Előírt és tényleges terhelés/mennyiség | Külön mező; ismétlés és tartásidő külön típus; kg összesen/kézenként/rásegítés jelentése megmarad |
| Pihenő | Előírt és tényleges pihenő külön; az ismeretlen tényleges pihenő nem kapja meg automatikusan az előírt értéket |
| Kivitelezés és mozgástartomány | Az összehasonlítás feltételei; romló végrehajtással elért további ismétlés nem tiszta javulás |
| Tartalék és erőkifejtés | Önbevallott adat, nem objektív erőmérés; a bizonytalanság megőrzendő |
| Fájdalom, megszakítás, kihagyás oka | A valós adat mentendő akkor is, ha tervezési referenciának nem használható |
| Előző sorozatok és edzésbeli sorrend | A korábbi fárasztó gyakorlatok és a sportági kiegészítő terhelések külön kontextust alkotnak |
| Alkalom utáni és későbbi visszajelzés | Rögzítési idő és időbeli viszony megmarad; az elmaradt válasz ismeretlen, nem panaszmentes nulla |

A jelenlegi megjegyzésmezőkbe írt szöveget nem szabad automatikusan validált pihenőidővé, sorozatszámmá vagy személyes kapacitásértékké alakítani. Ehhez kifejezett, verziózott adatmodell, vezetett felület és tartós mentés szükséges.

### Értékelési és tervezési határok

- Megfigyelt sikeres sorozatszám jelenthető, de ebből nem következik a maximálisan elviselhető vagy optimális sorozatszám.
- Ismétlés-visszaesés csak megfelelően egyező feltételek és ismert, nem nulla viszonyítás mellett számítható. Eltérő kg, pihenő vagy mozgás esetén az összehasonlíthatóság hiányát kell megjeleníteni.
- Több alkalom eredménye szükséges a stabilabb kiinduló kerethez. Egy jó nap nem válik általános személyes kapacitásgörbévé.
- A „2–3 sorozat” egy későbbi, felülvizsgálható protokoll paramétere lehet, nem a felhasználó már igazolt képessége. Nem szükséges ezt automatikusan minden izomcsoportra előírni.
- Az összetett gyakorlatok több izomcsoportot terhelnek. Külön kezelendő a gyakorlatonkénti és az egész edzés/ hét terhelése; egyetlen sorozat nem számolható minden érintett izomcsoportnak bizonyítottan azonos értékű teljes sorozatként.
- A fejlődés nem csak több gyakorlat és több sorozat lehet: azonos feltételek mellett több szabályos ismétlés, javuló kivitelezés vagy megfelelően választott más terhelés is megfigyelhető. Egyszerre több változó emelését egy első referenciasorozat nem alapozza meg.
- A cél (például kajakos kiegészítő erősítés), az aktuális állapot, a heti keret és a többi sport terhelése is része a későbbi tervfelülvizsgálatnak. Az új javaslatot külön kell áttekinteni és elfogadni.

## Források és bizonyítékhatár

A 2026-os ACSM állásfoglalás elkülöníti az erő, hipertrófia, teljesítmény és erőállóképesség eredményeit; az erőállóképesség optimális terhelési változóira korlátozott bizonyítékot jelez. Ez nem személyes kapacitásbecslő modell. Az NSCA terhelésválasztási áttekintése tárgyalja az ismétlésszám egyéni és fáradtságfüggő eltérését, valamint az önbevallott RIR bizonytalanságát. A fent javasolt termékfolyamat ezekből levont, még validálandó tervezési következtetés.

- ACSM (2026): [Resistance Training Prescription for Muscle Function, Hypertrophy, and Physical Performance in Healthy Adults](https://pubmed.ncbi.nlm.nih.gov/41843416/), DOI: 10.1249/MSS.0000000000003897.
- NSCA: [Using Intensity Based on Sets and Repetitions](https://www.nsca.com/education/articles/nsca-coach/using-intensity-based-on-sets-and-repetitions-over-50-years-of-experience-a-brief-overview-of-load-setting-and-programming-strategy/).
- NASM: [Barbell Bench Press](https://www.nasm.org/resource-center/exercise-library/barbell-bench-press).
- ACE: [Bodyweight Squat](https://www.acefitness.org/resources/everyone/exercise-library/135/bodyweight-squat/).
- Ronai és Taber (2021): [The Barbell Bench Pull](https://digitalcommons.sacredheart.edu/pthms_exscifac/56/).
- Catalyst Athletics: [Knees to Elbows és lábemelés-változatok](https://www.catalystathletics.com/exercise/490/Knees-To-Elbows/).

## Ellenőrzés

Az új frontendtesztek vizsgálják az előzetes protokollt, a saját gyakorlatok és sorrend megtartását, a hiányzó leírás őszinte jelölését, a kapacitásállítások hiányát, és a zárolt mezőcsoporton kívül megjelenő visszatérést. A React DOM-próba reprodukálja a képernyőkép állapotát: a legalsó visszatérő gomb külön szerverolvasást indít, írás nélkül; friss, rendezett adatokkal engedélyezi az indítást, fennmaradó akadálynál közvetlenül a gomb mellett mutatja annak okát.

A C20.6.3 teljes mentési/újrapróbálási és a korábbi teljes vezetett felmérési DOM-folyamat is újrafutott. Nincs backend-, tárolt szerződés-, katalógus-, adatbázis- vagy függőségváltozás. A célzott teljes frontendkapu parancsa: `python tools/run_c20_6_4_checks.py --frontend-only --build`; a kapcsoló nélkül a teljes backend regresszió is lefut.
