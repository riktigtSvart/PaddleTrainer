# C21.9 – Helyszínek és napfényhez kötött kizárás

Az edzéshelyszín földrajzi szélessége, hosszúsága és IANA időzónája tartósan menthető. A tervező sportáganként alkalmazhat napfénykorlátot, amelyet egy adott helyszínen felül lehet bírálni. A teljes edzésnek, a bemelegítéssel és levezetéssel együtt, bele kell férnie a megengedett világos időszakba.

## Felhasználói folyamat

1. **Edzéstervezési alapadatok → Edzéshelyszínek → Szerkesztés.** A földrajzi hely az érintett helyszín saját szerkesztőjében adható meg. Tizedes fokok szükségesek; a vessző és a pont is használható a felületen. Az időzóna kezdőértéke a sportoló mentett időzónája, amely más országban lévő helyszínnél átírható.
2. **Napfényidők ellenőrzése.** A választott dátumra megjelenik a polgári hajnal, napkelte, napnyugta és polgári alkonyat vége. Az előnézet nem menti a helyszínt. Végül **Helyszín mentése**.
3. A helyszínek fölötti **Sportági napfénykorlátok** részben sportáganként választható: nincs korlát; napkelte–napnyugta; polgári hajnal–alkonyat. A reggeli ráhagyás a világos időszak elejét késlelteti, az esti a végét hozza előrébb. Mindkét érték 0–120 perc lehet. **Napfénykorlátok mentése**.
4. Beltéri helyszínnél vagy más helyi feltételnél az adott helyszín szerkesztőjének **Napfénykorlát ezen a helyszínen** részében sportáganként felülbírálható az alapbeállítás. Az öröklés a sportági szabályt használja; a „Nincs napfénykorlát” itt kifejezetten kikapcsolja azt az adott helyszínen és sportágban.
5. **Naptár → Terv frissítése most.** Az új tervezés már ellenőrzi a megengedett világos időszakokat. Az alkalmazás saját, cserélhető jövőbeli tervei újraértékelődnek; a korábban érvényes esti edzés kikerülhet és nappali javaslat kerülhet a helyére, ha van hozzá megfelelő időablak és terhelési keret.

Nem kapcsolunk be automatikusan szabályt a korábbi felhasználóknál. A koordináták mentése önmagában sem aktivál kizárást. Ha aktív korlát mellett a helyszín vagy a koordináta hiányzik, az érintett sportág nem tervezhető abba az időablakba, és ennek külön magyarázata látszik. A többi sportág ettől még tervezhető.

Egy közös helyszín kajakozásának és erősítésének eltérő szabálya lehet. Ha a vízi kajakozás és a beltéri kajakergométer eltérő napfénykorlátot igényel, a jelenlegi sportági modellben két külön helyszínként add meg őket. A tervező nem következtet beltéri edzésre pusztán abból, hogy a felszerelések között ergométer is szerepel.

A heti órarend továbbra is a sportoló időzónájában értendő. Az időpontokat UTC-re alakítva, a földrajzi pont alapján ellenőrizzük; a napfény-előnézet a helyszín saját időzónájában jelenik meg. Változó helyszínnél a tényleges edzési hely koordinátáját kell naprakészen tartani.

## Számítás és hatókör

- Módszerazonosító: `noaa-meeus-light-v1`. Nincs új Python- vagy npm-függőség.
- A NOAA/Meeus napdeklináció- és időegyenlet-képleteiből számított geometriai napmagasságot használjuk. A napkelte és napnyugta küszöbe −0,833°, a polgári hajnal és alkonyat küszöbe −6°.
- A világos időszakok folytonos UTC-intervallumok. A széleket befelé, egész másodpercre kerekítjük; a kijelzett óraidők perc pontosságúak. Az időráhagyás a tényleges csillagászati határhoz tartozik, nem minden helyi éjfélhez.
- Az algoritmus a napi szélsőértékeket is keresi: puszta mintavétellel egy nagyon rövid sarki éjszaka vagy nappal kimaradhatna. A sarki nappal/éjszaka külön állapot; nem kap kitalált napkeltét vagy napnyugtát.
- Az óraátállítás 23 és 25 órás helyi napjai, a szökőnapok, a negatív koordináták, a nulla és a dátumvonal kezelése külön teszteseteket kapott.
- Ez számított csillagászati ablak, sík horizonttal. A légkör, domborzat és megfigyelési magasság befolyásolhatja a tényleges eseményeket; a felhőzet és terep a látási viszonyokat is. A másodperces belső tárolás nem jelent másodperces megfigyelési pontosságot.
- Időjárási előrejelzést ez a változat még nem kér le. A földrajzi pont az ehhez szükséges későbbi alapadat is. A napfényszámítás helyben, a backendben történik, a böngésző pedig ugyanazzal a matematikával ellenőrzi a választ; a koordináták nem kerülnek külső napfényszolgáltatóhoz.

Elsődleges háttéranyagok:

- [NOAA – Solar Calculation Details](https://gml.noaa.gov/grad/solcalc/calcdetails.html)
- [NOAA – General Solar Position Calculations](https://gml.noaa.gov/grad/solcalc/solareqns.PDF)
- [US Naval Observatory – Rise, Set, and Twilight Definitions](https://aa.usno.navy.mil/faq/RST_defs)
- [Reda–Andreas: Solar Position Algorithm for Solar Radiation Applications, NREL/TP-560-34302](https://docs.nlr.gov/docs/fy08osti/34302.pdf): a közölt 2003. október 17-i példa geometriai napmagassága független nagyságrendi ellenőrzési pont az egyszerűbb NOAA-modellhez; nem állítjuk, hogy a teljes SPA algoritmust implementáltuk.

## Tartós mentés és tervezés

A `training-options-v0.1` beállítások opcionális `coordinates`, `daylight_overrides` és `daylight_rules` mezőket kapnak. Hiányzó mezők esetén a régi szerializált forma és a korábbi bizonylatok lenyomata változatlan. A koordináták szöveges tizedesek, hogy a Python és a böngésző pontosan ugyanazt a mentési tartalmat ellenőrizze. Ismeretlen koordináta nem válik nullává.

A korábbi tulajdonos-, revízió-, tartalomlenyomat- és azonos kérésre vonatkozó ellenőrzések továbbra is működnek. A `POST /planning/training-options/daylight/preview` kizárólag a beküldött pontot és dátumot számolja, visszaadja a pontos kérést és lenyomatait; nem ír adatot. A proxy csak ezt az egy POST útvonalat engedi, query és idegen origin nélkül.

Aktív szabályoknál a tervezési pillanatkép a legfrissebb, saját beállításbizonylatot is tartalmazza. A lehetőségek eredeti időkerete és közös perckerete megmarad; a tervező sportáganként metszi ezeket a fényablakkal. A teljes javaslat a metszetbe kerül, és a böngésző ezt önállóan is újraszámolja. A változatlan időtartam-, regenerációs és heti keretszabályok továbbra is érvényesek.

A naptári áthelyezés előnézete és tulajdonoszárolt mentése is ellenőrzi a napfénykorlátot. Az alkalmazás által létrehozott terv helyszíne az eredeti, ellenőrzött tervjavaslatból származik. A kemény napfénykizárás nem felülírható ütközési figyelmeztetés. Egy közben megváltozott napfénybeállítás érvényteleníti a korábbi áthelyezési előnézetet.

A teljesített, külső, jóváhagyott vagy más okból védett edzéseket ez a módosítás nem törli automatikusan. A napfénykorlát a támogatott edzésminták javaslatait és az ellenőrizhető helyszínhez tartozó áthelyezést szabályozza.

## A korábbi erőfelmérés megőrzése

Kizárólag a koordinátákat és napfénykorlátokat érintő helyszínmentés nem teszi elavulttá a jártasság- és erőfelmérést. Az ellenőrzött közvetlen szülői revíziókon visszakeresett, gyakorlatvégrehajtás szempontjából legutóbb változott beállításbizonylat marad a felmérés forrása. Az eredeti forráslenyomat-algoritmus és a történeti bizonylatok változatlanok. A felszerelés, sportlehetőség vagy más korábban vizsgált adat módosítása továbbra is felülvizsgálatot kérhet.

A tervező ettől függetlenül mindig a legfrissebb napfénybeállítást ellenőrzi; a korábbi erőfelmérésre támaszkodás nem engedi meg egy új kizárás kihagyását.

## Ellenőrzés

Sikeres: **2191 backendteszt, 1371 frontendteszt**, route-típusgenerálás, TypeScript, ESLint és production build.

A teljes backend tervezési regresszió, a frontend regresszió, route-típusgenerálás, TypeScript, ESLint és production build a csomag tesztkapujában szerepel. Az új célzott tesztek a valódi API-n ellenőrzik a tartós mentést, az azonos kérés ismétlését, az esti kizárást, a nappali alternatívát, az elavult elfogadás visszautasítását, a jövőbeli saját tervek újraértékelését, a naptári áthelyezést és a felmérési forrás megőrzését.

React StrictMode + DOM + valódi FastAPI-folyamatban a vesszős koordinátabevitel, az előnézet megjelenése, a mentés, újranyitás, a sportági szabály mentése és a felmérés forrásának megmaradása is ellenőrzött. Natív böngészős képernyőképes ellenőrzés nem készült.

## Telepítés és visszaállítás

A C21.8.3 forrására készült ellenőrzött overlay, backend- és frontendmódosításokkal. Nincs séma-migráció, a meglévő adatbázist nem módosítja a telepítő. Mindkét szervert újra kell indítani. A forrásfrissítő biztonsági másolatot készít és helyi eltérésnél írás nélkül megáll.

A forrás-visszaállítás nem adatbázis-visszaalakítás: a C21.9-ben mentett új helyszínmezőket a C21.8.3 backend még nem ismeri. Ilyen mentés után a régebbi backend használatához a frissítés előtti, külön megőrzött adatbázis is szükséges; ez a későbbi mentések elvesztésével járhat. Rendes visszaállítás helyett ilyenkor a C21.9 ismételt alkalmazása őrzi meg az új adatokat. A telepítő nem végez automatikus adatbázis-visszaállítást.
