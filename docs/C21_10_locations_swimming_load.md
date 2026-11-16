# C21.10 – Helyszínváltozatok, úszás és aktuális heti terhelés

Forrásfrissítés C21.9.2-höz. Nincs új függőség és adatbázis-migráció. A korábbi, ellenőrzött felmérések és tervek olvashatók maradnak. A telepítés önmagában nem kér le személyes adatot és nem ír külső óraszolgáltatóhoz.

## Használat

1. **Edzéstervezési alapadatok → Edzéshelyszínek.** A meglévő helyszínt szerkeszd. Megadhatsz konkrét pontot vagy változó helyszínhez téglalap alakú edzési körzetet. Mindkettő térképen és kézzel is kijelölhető. A térkép kezdeti nézete nem mentett helymeghatározás.
2. Az általános sportági **napfénykorlát** lehet napkelte–napnyugta vagy polgári hajnal–alkonyat, külön reggeli és esti ráhagyással. A helyszín ezt felülírhatja. A teljes edzésnek bele kell férnie, nem elég a kezdésnek.
3. **Általános edzésrend.** Egy idősávhoz több helyszínt rendelhetsz alternatívaként. Ezek külön jelöltek: az egyik helyszín felszerelése nem pótolja a másikét. A változó kajakozási helyszínnél a hajó szállíthatósága továbbra is külön megadás.
4. Úszóhelyszínnél jelöld az **Úszómedence** felszerelést, és add meg a **medence pontos hosszát**. A 33 m és 33⅓ m eltér; az utóbbi például 33.333333 alakban tárolható. Nem változtatjuk automatikusan 25 vagy 50 méterre.
5. **Sportelőélet → Jelenlegi edzésmennyiség és úszási kiindulópont.** Itt külön menthető a most szokásos heti edzésszám és edzésidő, illetve az önálló úszástudás, ismert/előnyben részesített úszásnem és kényelmesen teljesíthető folyamatos táv/idő. A folyamatos mennyiség a választott úszásnemhez tartozik; úszásnemváltáskor újra meg kell adni.
6. **Naptár → Terv frissítése most.** A „Miért ezek az edzések?” rész megmutatja a heti keretet, annak forrását, az egyes sportágak lehetőségeit és a kimaradások okait. Az edzésre kattintva olvasható a végrehajtási utasítás.

Új erőfelmérés nem kell pusztán a meglévő helyszín földrajzi megadásának, medencehosszának vagy az új terhelési/úszási adatoknak a módosítása miatt. A felszerelések, sportok, hozzáférési feltételek és órarend változásainál a korábbi ellenőrzési szabályok érvényben maradnak.

## Földrajzi szabályok

Az új `training-area-v0.1` körzet dél/észak/nyugat/kelet határokat és IANA-időzónát tartalmaz. Egy helyszínhez konkrét pont vagy körzet tartozhat, egyszerre mindkettő nem. Körzet csak változó helyszínhez menthető; tengelyenként legfeljebb 20° kiterjedéssel, dátumválasztó meridián átlépése nélkül. A folyó kanyarulatait is a kijelölt téglalapnak kell tartalmaznia: két város nevéből nem találjuk ki az útvonalat vagy a területet.

A `noaa-meeus-light-v1` pontmodell megmarad. A körzet új számítása `area-common-light-v0.1`: minden UTC-perc közepén analitikusan keresi a legkisebb napmagasságot a teljes téglalapon. A belső szélsőértékek is számítanak, nem csak a négy sarok. Csak azokat a teljes perceket engedi, amelyek közepén a legkisebb magasság legalább 0,2°-kal a küszöb felett van. A támogatott 1900–2100 időszakban ez a perccellákon belüli napmozgást is befelé korlátozza. Ehhez adódnak a felhasználó ráhagyásai, a világos ablak határán, nem minden új edzés kezdetén.

Ez konzervatív, perces közelítés. Sík horizonttal számol; a domborzat, épületek, felhőzet és helyi látási körülmények nincsenek benne. A körzet előnézete **közös világos időszakot** mutat, nem egy kitalált középpont napkeltéjét. A helyi nap hossza a nyári időszámítás átállásakor 23 vagy 25 óra is lehet. A sarki világosság és sötétség nem kap kitalált napkeltét.

A térkép megnyitásakor OpenStreetMap-csempéket kér a böngésző; ehhez internet kell. Csak a látható terület csempéi töltődnek, nincs előletöltés. A kézi megadás és maga a napfényszámítás térképszolgáltatás nélkül is működik.

## Úszóedzés

Új család: `SWIM_EASY_AEROBIC`, a bővített `workout_family_registry_v0.2` része. A történeti v0.1-regiszter változatlan. Jelenleg medencés, könnyű aerob támogatás készül; nem állítjuk, hogy ez kajaktechnikai, VO₂max- vagy úszóverseny-specifikus felmérés.

Feltételei: mentett önálló úszástudás, ismert választott úszásnem, az adott helyszínen medence és pontos medencehossz, megfelelő idősáv és közös terhelési keret. Megadott tudás nélkül nem következtetünk úszásbiztonságra az óra perceiből.

- Friss, legfeljebb 56 napos megadásban legalább 1000 m vagy 10 perc kényelmes folyamatos úszás esetén folyamatos főrész készül, szükség szerinti pihenővel. Nem kötelező 50 méterenként megállni.
- Rövidebb vagy már nem friss folyamatossági adatnál egy vagy két teljes medencehossz és 30 másodperc pihenő ismétlődik a főrész időkeretében. Két hosszhoz a megadott távnak el kell érnie a medencehossz kétszeresét. Egy hossznál rövidebb ismert korlát esetén nem készül önálló medencés minta.
- 5 perc fokozatos könnyű bemelegítés, főrész, majd 5 perc nagyon könnyű levezetés. A 20–60 perces teljes keret a pihenőket is tartalmazza; a minták 5 perces időlépéssel illeszkednek a lehetőséghez. Az időkeret nem kitöltendő kötelezettség.
- A friss saját időtartam-referencia a legutóbbi legfeljebb három használható, legalább 20 perces úszóedzés legrövidebb ideje. Ha kényelmes folyamatos időt is megadtak, annak +10 perces teljes kerete további felső korlát. A szigorúbb korlát számít. Távból sebességet nem becsülünk.
- Ha csak megfelelő friss folyamatos táv ismert, a teljes induló keret legfeljebb 30 perc; rövid szakaszos kezdésnél 20 perc. Ezek látható alkalmazásbeállítások, nem mért optimális személyes adagok.
- Könnyű, egyenletes érzet, RPE 2–3/10; nincs régi rekordból vagy az óra pillanatnyi csúcssebességéből számolt pulzus- vagy tempócél. Egész medencehosszakat kell befejezni, az új hosszt a maradék időhöz igazítva.

Az eredet, a medencehossz, a választott mód, az időtartam-korlátok és az önbevallás dátuma a javaslatban ellenőrizhető. A frontend a mentett forrásból önállóan ellenőrzi a protokoll szövegét és adagját is.

## Heti terhelés és sportági összetétel

Új felső tervezési keret: `training-starting-budget-v0.2`, a `training-plan-policy-v0.9` része.

1. Elsőként a felhasználó által külön megadott **jelenlegi szokásos terhelés** használható: 2–8 hetes tényleges időszak, legfeljebb 14 napja lezárult véggel. Ez önbevallás, nem labor- vagy teljesítménymérés.
2. Ennek hiányában az utolsó legfeljebb négy, folyamatosan és megfelelően lefedett teljes hét edzésszámának/időtartamának mediánja adja a keretet. Legalább két teljes, nem üres legutóbbi hét kell. Az összes sportág teljesítése számít; nem szükséges ugyanabban a két hétben kajakozni is.
3. Megfelelő aktuális adat nélkül a korábbi kezdő felső keret marad: 3 alkalom/180 perc, ismeretlen rendelkezésre állásnál legfeljebb 2/90. Ez nem állapotminősítés. A szabad heti óraszám önmagában nem edzésadag.

Minden esetben számít a személyes rendelkezésre állás felső korlátja, a gördülő hét, a meglévő teljesítések és védett tervek, a napi keret és a ciklusszakasz kerete. Jelenleg legfeljebb egy új edzés/nap és hét új alkalom/hét támogatott. A felső keret nem garantált edzésszám: rövid idősáv, napfény, pihenő vagy célbeli korlát kevesebb alkalmat eredményezhet.

A hiányzó adat nem nulla edzés. Egy 2021-es futás vagy régi egyéni csúcs tapasztalati tájékozódási pont marad; nem emeli meg a mai heti keretet. A friss bizonyítékok és a külön mentett aktuális megadás a ciklus korábbi referenciái mellett is láthatók maradnak.

Az edzések közötti induló elhelyezési szabály (`training-start-spacing-v0.1`) ismert könnyű mintákra: két erősítés között 48 óra; erősítés és más sport között 24 óra; azonos aerob sportban és kajak–úszás párosban 24 óra; más könnyű aerob párosban 12 óra. Ismeretlen vagy nem könnyű intenzitású teljesítés után legalább 36 óra. Ezek **kezdési időpontok közti alkalmazásszabályok**, nem személyre illesztett regenerációs idők.

A képességcélok szerepe és a már lefoglalt aerob/erősítő idő együtt hat a következő választásra. Azonos fejlesztési prioritásnál az állóképességi fő sport aerob részének 2:1 induló súlya van az erősítéshez képest; ez átlátható heurisztika, nem általános élettani optimum. A ritka, nappali lehetőségeket és az egyetlen heti erősítésre alkalmas napot előbb kell lefoglalni, mint azokat a munkákat, amelyek sok más időpontban is teljesíthetők.

A szerkeszthető, saját jövőbeli tervek újraoszthatók. Az importált, átírt, teljesített vagy összekapcsolt alkalmak védettek. Az igazoltan kihagyott alkalom a korábbi költségkeretét továbbra is foglalja: elmaradt terhelést nem írunk át automatikus pótlássá. Azonos feltételek mellett az ismételt tervfrissítés nem cserélgeti a már elfogadott alkalmakat.

## Ellenőrzés

2262 backend tervezési teszt; 1435 frontendteszt; Next route-típusgenerálás; TypeScript; az érintett fájlok ESLint-ellenőrzése; production build.

Valódi FastAPI TestClient API-val, külön szintetikus adatbázisban és React StrictMode/JSDOM felülettel: körzet két térképes kattintással, helyszín és medencehossz mentése, napfénykorlát mentése, heti aktuális keret és úszástudás mentése/újranyitása, automatikus tervfrissítés. A naptárba mind a négy sport bekerült, a korábbi esti evezés kikerült. Újranyitás nem küldött írást; második tervfrissítés megtartotta a tervazonosítókat. Natív böngészős képernyőképes ellenőrzés nem készült.

Az API és a frontend földrajzi számítását egymástól függetlenül összevetettük, belső szélsőértékkel, negatív Unix-idővel, időzónaátállással és sarki esettel is. Ellenőrzött a hamisított medence, adag, tulajdonos és heti forrás elutasítása; a korábbi szerződésverziók olvasása; helyszíni eszközök kölcsönzésének tiltása; az ismételt alkalmazás.

## Határ és későbbi bővítés

Időjárási előrejelzés és időjárás szerinti helyszínválasztás még nincs bekötve. A körzet és a konkrét alternatív helyszínek a későbbi szűrés földrajzi alapját adják. A nyílt vízi úszás, összetett úszó-résztávok és mért küszöbtempó külön fejlesztés. Az erősítő körök részletesebb fejlesztő tervezése, gimnasztika, mobilitás és regenerációs gyakorlatsorok szintén következő feladatok.

## Szakmai és technikai források

- [NOAA – General Solar Position Calculations](https://gml.noaa.gov/grad/solcalc/solareqns.PDF): a pontmodell napállási alapja.
- [US Naval Observatory – Rise, Set, and Twilight Definitions](https://aa.usno.navy.mil/faq/RST_defs): napkelte/napnyugta és a −6°-os polgári szürkület definíciója.
- [OpenStreetMap – Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/): jelölés, látható térképcsempék és böngészős használat.
- [US Masters Swimming – Adult Swim Training](https://www.usms.org/fitness-and-training/guides/swimming-101/adult-swim-training): bemelegítés, főrész, levezetés és egyéni úszóedzés-összeállítás.
- [US Masters Swimming – How to Write a Swimming Workout](https://www.usms.org/fitness-and-training/articles-and-videos/articles/how-to-write-a-swimming-workout): edzésrészek és feladathoz igazított pihenők.

Az 56/14 napos frissességi határ, a 20–60 perces keret, az 1000 m-es folyamatossági küszöb, a 30 másodperces pihenő, a 2:1 súly és a 12/24/36/48 órás elhelyezés **verziózott termékdöntések**. A fenti források ezeket együtt nem validálják személyre szabott edzésprotokollként. Az eddigi eredmények és visszajelzések alapján később pontosíthatók.
