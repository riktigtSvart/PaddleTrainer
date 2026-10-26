# P2.4C8.2 — Idősávok húzása, átméretezése és visszavonás

Alapállapot: `9fa0af006a92a965db77134bd4597e8c30de7b22`, a P2.4C8.1 és R1–R2 közös, feltöltött commitja.

## Felület

A C8.2 R1 felületi javítás a **Visszavonás** gombot a naptár felső eszköztárának jobb oldalára, az **Új idősáv / elfoglaltság** elé helyezi. Nyílikont és rövid feliratot kap; betöltés közben, illetve visszavonható módosítás hiányában is ugyanott látszik, letiltva. Rámutatva a gomb környezete a letiltás okát vagy a visszaállítandó időpontok rövid leírását mutatja. A letiltott vezérlő leírása billentyűzettel is elérhető. Az előnézet és a külön **Visszavonás mentése** megerősítés a meglévő folyamatot használja. A korábbi visszavonási és függő mentési adatok megmaradnak.

Az 1 és 7 napos, órák szerint rendezett nézetben az elfoglaltságok és az edzéslehetőségek egérrel vagy tollal húzhatók. A kártya belsejét húzva az egész idősáv mozdul, a megjelenő felső / alsó fogantyúval a kezdés / befejezés változik. A fogantyúk rámutatáskor vagy billentyűzetes fókusznál látszanak. Az egyszerű kattintás, illetve az Enter/Space továbbra is a pontos mezős szerkesztőt nyitja; érintőképernyőn is ez használható.

A húzás 5 perces lépésekben, a ténylegesen mért oszlopmagasságból számol. Az eredeti, nem ötre kerek percérték nem kerekítődik át magától. A napok közti húzás a naptár helyi dátumait használja, a böngésző rendszeridőzónájától függetlenül. A teljes 24 órás nézet ugyanezt a mérést használja. A képernyőn kívüli célt nem mentjük; a teljes nap vagy a mezős szerkesztő választható.

Mozgás közben külön szellemkártya mutatja a javaslatot. Az eredeti adat nem változik. Elengedés után az új dátummal és időkkel kitöltött gyorsszerkesztő nyílik. **Módosítás áttekintése → Napirendi módosítás mentése** véglegesíti a változást. Az Escape, megszakított pointer, ablakváltás, görgetés vagy nézetméret-változás elveti a folyamatban lévő húzást. A szerkesztő bezárása is megtartja az eredeti állapotot.

Az edzéstervek és mért teljesítések nem kapnak húzási fogantyút. A C8.3 kezeli majd a tervek engedélyezett áthelyezését. A személyes időbecslés és a rövid edzéskártyák olvashatósági jelölése megmarad.

## Ismétlődés és napváltás

- Azonos napon szerkesztett heti alkalomnál a kivétel és az ettől a naptól érvényes szabálymódosítás választható marad. A korábbi napok, illetve a későbbi külön kivételek megőrzése a C8.1 folyamatát használja.
- Másik napra helyezett heti alkalom csak egyszeri áthelyezés. Egyetlen teljes napirendi revízióban az eredeti alkalom kihagyott kivételt, a cél új egyszeri szabályt kap. A sorozat többi alkalma és kivétele változatlan.
- Egyszeri esemény napváltása megtartja a szabály azonosítóját.
- A sportolói profil korábbi edzésablaka is mozgatható. Teljes rendelkezésreállási revízió őrzi meg a többi napot, ablakot, eszközt, sportágat, megjegyzést és felső korlátot. A célnap kifejezetten elérhetetlen állapota felülvizsgálatot kér, nem oldódik fel automatikusan.
- Másik napra vitt ablaknál a célnap meglévő napi kerete megmarad. A forrásnap kerete legfeljebb a megmaradó ablakok keretének összegére csökken; az utolsó ablak után a nap ismeretlen, napi kerete null. Null nem nulla edzéskapacitást jelent. A megadott dátumhalmaz bővíthető 366 napig, korábbi adatok eldobása nélkül.
- Rövidítéskor a megadott edzéspercek nem csökkennek automatikusan. Ha már nem férnek az ablakba, a felület külön pontosítást kér mentés előtt.

## Időpontok

Helyi falióra-adatból készül javaslat, nem UTC-eltolásból új edzés. Az éjfélen átnyúlás kifejezett másnapi jelölés marad, legfeljebb 24 órás helyi ablakkal. Óraátállítást átszelő, a rácson nem egyértelműen rajzolható szakasz kattintással szerkeszthető. Áthelyezés után a korábbi fold-választás nem másolódik át automatikusan; ismétlődő óránál a felhasználó választ, nem létező óránál az előnézet hiba miatt nem menthető.

## Visszavonás és mentésbiztonság

Az utolsó, ebből a böngészőből indított és tartós bizonylattal igazolt napirendi mentés visszavonható. A gomb a naptár felső eszköztárában látszik; a visszavonás előtti / utáni idősávok és az ütközések külön előnézetben jelennek meg, majd külön mentés következik. A visszavonás új, idempotens, előző referenciához kötött revízió; az auditmúlt nem törlődik. Nincs automatikus redo-lánc.

A böngésző a korábbi és az új hash-ellenőrzött bizonylatot őrzi meg. Újratöltés után azonos tulajdonos és egymást követő mentési referencia igazolja a visszavonást. Első napirendi mentésnél az előző állapot a kifejezetten üres deklaráció. Rendelkezésre állásnál a teljes régi bizonylat szükséges. A régebbi C8.1 függő kérése újraküldhető marad, de abból nem találunk ki visszavonási előzményt.

A legújabb érintett revízió eltérése vagy fiók/időzóna váltása letiltja a régi visszavonást. A szerver mentési CAS-ellenőrzése a még nyitott előnézet után történt módosítást is visszautasítja. Másik adatfolyam változását a saját teljes állapot helyreállítása nem írja felül.

A pontos kérésbájtok és a visszavonáshoz szükséges előzmény egyetlen függő mentési objektumban kerülnek a helyi tárhelyre a POST előtt. Ismeretlen kimenetelnél nincs automatikus újraküldés vagy elvetés; külön gomb ismétli ugyanazt a kérést. Biztos elutasítás után külön elvetés és újraolvasás lehetséges. Az aktív szerkesztő, mentés és függő kérés alatt újabb húzás nem indítható.

Ha a mentés igazolt, de a visszavonási adat tárolása helyhiány vagy böngészőhiba miatt nem sikerül, a felület külön jelzi a sikeres mentést és a visszavonás hiányát. A helyreállítási adat csak az adott böngészőben van, nem szinkronizált felhasználói művelettörténet.

## Kód és ellenőrzés

Az API, a backend sémák és az adatbázis változatlan. Az új `slot-transform.ts` a naptári koordinátából készített javaslatot, az `editor-history.ts` a bizonylatellenőrzött visszavonást, az `editable-slot.tsx` a pointer állapotgépét kezeli. A gyorsszerkesztő és a teljes revíziós mentés közös marad. Új külső csomag vagy migráció nem szükséges.

A frontend regressziók saját backendből rögzített szintetikus bizonylatokat olvasnak. A felületi próba tényleges React DOM-ot köt valódi FastAPI és izolált SQLite folyamathoz stdin/stdout csatornán; a hálózat tiltott. A mért elrendezési téglalapok, dialog és pointer-capture műveletek JSDOM-helyettesítést kapnak: ez nem natív böngészős pixel-, pointer-capture- vagy Windows-teszt. Az installer a Windowsos alkalmazástesztek és a frontend build futtatását is tartalmazza.

Az R1 kis felületi módosításának helyi ellenőrzése külön React DOM-próbát használ: a tényleges gyorsszerkesztő és naptár komponens fut, a hiányzó, nem módosított API- és szerződésmodulokat kifejezett, a C8.2 csomag szintetikus mintájára épülő helyettesítések adják. Ellenőrzi az egyetlen felső gombot a szerveroldali HTML-ben és hidratálás után, az üres / aktív / elavult / más fiókhoz tartozó / függő állapotokat, a változatlan előnézet-megerősítés folyamatot és a letiltást szerkesztés közben. A teljes TypeScript-ellenőrzést, frontend teszteket és Next buildet az R1 telepítő a felhasználó teljes forrásfájljain futtatja; a részleges helyi munkapéldányon ezek teljes futását nem állítjuk.
