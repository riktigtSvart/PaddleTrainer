# P2.4C8.1 — Naptári korlátok és gyorsszerkesztő

Kiindulási commit: `47e6e1ed16545e2f040e3bfa5012192e1702cc90`.

## Használat

A Napirend fejlécében az **Új idősáv / elfoglaltság**, illetve a napi `+` nyitja a gyorsszerkesztőt. Egy megadott elfoglaltságra vagy edzésablakra kattintva ugyanitt módosítható az adott elem.

- Egyszeri és heti ismétlődés, választható hétköznapokkal és opcionális utolsó nappal.
- Munka, utazás, személyes és egyéb elfoglaltság; rögzített vagy rugalmas kötöttség.
- Edzéslehetőség: külön edzésperc-keret, sportágak, terhelési felső korlát, eszközök, helyszín és megjegyzés.
- Éjfélen átnyúló idősávok; ismétlődő órában külön kezdő és befejező előfordulás.
- Heti szabály szerkesztésekor **csak ez az alkalom**, vagy **ettől a naptól minden következő alkalom**. A korábbi napok változatlanok.
- Alkalom elhagyása előnézettel és külön mentéssel. A látható időszak kihagyott alkalmai a naptár alatti listából visszaállíthatók.
- Korábban a sportolói felmérésnél rögzített edzésablakok gyorsszerkesztése teljes, ellenőrzött revízióval; a többi nap, ablak és kiegészítő adat megmarad.

Mentés előtt megjelenik az ellenőrzött dátumtartomány, az érintett edzéstervek és a megmaradó edzésablakok listája. A rögzített elfoglaltság kivonódik az edzésre megadott időablakból. A rugalmas elfoglaltság egyeztetést jelez, de nem törli automatikusan a kapacitást.

A naptár az elfoglaltságokat semleges, satírozott háttérrel jelöli; a rugalmas határ szaggatott. Az edzések saját célszínei és ikonjai megmaradnak. Az érintett edzésterveken figyelmeztető ikon jelenik meg, a részletek a közös ütközéslistából elérhetők. Az elfoglaltságok külön rétegen ki- és bekapcsolhatók. Havi nézetben nem foglalják el az edzések három kártyájának helyét. A 144 napos nézet edzésszámai nem számolják az elfoglaltságokat edzésnek.

## Határok

Ez a lépés a napirendi adatokat és az egyeztetendő terveket kezeli. Nem helyezi át, nem rövidíti le és nem írja újra az edzéstervet; a teljesítés mért időpontjai és nyers szolgáltatói adatai érintetlenek. Nem ír vissza a Polar vagy más szolgáltató naptárába.

A drag-and-drop, határhúzás és visszavonás a C8.2, a tervezett edzések ellenőrzött áthelyezése a C8.3 feladata. A tárolt idősávok használata nem jelent új terhelési vagy készültségi döntési jogosultságot.

## Adatmodell és tárolás

Új auditfajta: `calendar_constraint_revision`, séma: `calendar-constraints-v0.1`.

A tulajdonoshoz tartozó teljes napirendi deklaráció tartalmazza az időzónát, a stabil UUID-val azonosított heti / egyszeri szabályokat, valamint a szabályhoz és eredeti helyi dátumhoz kötött kivételeket. A `replacement: null` kihagyott alkalom. A helyi időpontok mellett az óraátállítási `fold` választások is megmaradnak. A kibontott UTC-időpontok olvasási vetületek, nem módosítják a tárolt szabályt.

A mentés új, változtathatatlan auditrekordot hoz létre SHA-256 tartalomlenyomattal, előző referencia-ellenőrzéssel és monoton revízióval. A tulajdonos sorának zárolása sorosítja az azonos fiók írásait PostgreSQL alatt. A mentést ugyanabban a friss munkamenetben ellenőrzött visszaolvasás és commit követi.

Az azonos kérésazonosító és azonos normalizált tartalom az eredeti bizonylatot adja vissza. Más tartalommal újrahasznált azonosító, vagy elavult előzmény elutasítás. Régi kérés ismétlése nem állít vissza régi állapotot. A korábban tárolt sportolói rendelkezésre állás külön auditfajta marad; annak gyorsszerkesztése a meglévő revíziós írófolyamatot használja.

A meglévő `planning_audit_artifacts.artifact_kind` szöveges oszlopát használjuk. Új tábla, oszlop vagy Alembic-migráció nem szükséges.

## API

| Metódus | Útvonal az `/api/v1/planning/calendar` alatt | Eredmény |
| --- | --- | --- |
| GET | `/constraints?start_date=...&end_date=...` | Aktuális deklaráció, teljes eredeti rendelkezésre állási bizonylat, kibontott alkalmak, egyedi tervütközések és megmaradó edzésablakok |
| POST | `/constraints/preview` | Írás nélküli vetület egy rögzített javaslatra; opcionálisan a korábbi rendelkezésre állás módosítását is ellenőrzi |
| POST | `/constraints` | Tartós, idempotens deklarációmentés; 201 új, 200 ismétlés |

A meglévő `/feed` és `/goals` szerződése nem változik. Az új olvasási tartomány 1–366 nap. A szabályok száma legfeljebb 512, a kivételeké 4096; a kibontott alkalmak, ablakcsoportok és ütközések korlátja 4000. Túllépéskor elutasítás történik, nem csendes lapcsonkolás.

Az új Next proxy kizárólag a fenti naptári műveleteket engedi a meglévő feed / céljelölés mellett. Az új teljes állapotkéréseknél 1 MiB ténylegesen beolvasott bájt a felső határ; a korábbi céljelölés 16 KiB-os határa változatlan. A proxy megőrzi a JSON-bájtokat, ellenőrzi az Origin–Host egyezést, nem követ átirányítást és nem továbbít böngészős hitelesítési fejléceket. Minden válasz `no-store`.

## Időpontok és bizonytalanság

- Hiányzó rendelkezésre állás nem jelent tiltást, szabad időt vagy nulla kapacitást.
- A kifejezetten elérhetetlen nap elsőbbséget élvez az azon a napon megadott új pozitív lehetőséggel szemben.
- Egy szétvágott ablak részei közös eredeti perc-keretet tartanak meg. Az átfedő forrásablakok és napi keretek nem összegezhetők önálló kapacitásként.
- Az illeszkedési ellenőrzés egyedi edzésre vonatkozik. Nem állítja, hogy több külön edzés összesített napi terhelése vagy beosztása elfogadható.
- A már saját teljesítéshez kötött, valamint a befejezett / kihagyott / törölt tervek kimaradnak az áthelyezésre utaló ütközésjelzésből. Másik tulajdonos tervei sem kerülnek bele.
- Ismeretlen edzéskezdés vagy időtartam külön tisztázandó ok; a nulla időtartam nem ismeretlen.
- A pontosan dátumozott egyszeri esemény és kivétel hibás vagy nem létező helyi időpontja mentéskor elutasítás. Heti ismétlődés későbbi óraátállítási problémája a vetületben külön, UTC-időpont nélküli hiba; az érintett kapacitás ismeretlen marad.
- A megtekintett előnézet látható időponthibájával a gyorsszerkesztő nem enged mentést. A heti szabály határozatlan jövőjének valamennyi alkalma nem kerül egyszerre kibontásra.
- Profil-időzóna változásakor felülvizsgálati jelzés jelenik meg; nincs automatikus helyi időpont-átértelmezés.

## Mentés és újrapróbálás

Az előnézet javaslatlenyomattal igazolja az ellenőrzött tartalmat és tartományt. A felület mentés előtt megőrzi a pontos JSON-kérést, a műveletet és a tulajdonost a böngésző helyi tárhelyén. Az újrapróbálás azonos bájtokat küld. Újratöltéskor nincs automatikus POST; külön, látható ellenőrző gomb indítja az ismétlést.

Sikernek csak az adott sportolóhoz és kéréshez tartozó, hash-ellenőrzött, tartós mentési bizonylat számít. Ismeretlen kimenetelű kérés nem vethető el úgy, mintha biztosan sikertelen lett volna. Biztos elutasítás után külön művelettel elvethető, majd újraolvasható a friss állapot. Másik sportoló függő kérése nem küldhető el az aktuális fiókkal.

A natív dialog támogatja az Escape billentyűt, a billentyűzetes fókuszkezelést és a görgethető tartalmat. A mezők az alkalmazás sötét / világos témaváltozóit használják.

## Ellenőrzés

Az új tesztfájl a valódi API-útvonalakon, izolált SQLite-adatbázissal ellenőrzi a tulajdonosi szűrést, előnézetet, revízióütközést, idempotenciát, megszakadt válasz utáni helyreállást, dátum- és időzónaszabályokat, éjféli átnyúlást, óraátállítást, keretek megtartását és az edzésadatok változatlanságát.

A frontendtesztek valódi backendből előállított, kizárólag szintetikus bizonylatokat használnak. A React DOM-interakciós ellenőrzés a valódi API / tárolási réteget helyi stdin/stdout hídon éri el, külső hálózat nélkül. A natív dialog API-t JSDOM-ban helyettesítjük; ez nem helyettesít valós böngészős elrendezés- vagy Windows-tesztet. A részletes futási eredményeket a javítócsomag ellenőrzési mellékletei tartalmazzák.
