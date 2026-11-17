# C21.12 – Étkezési időpontok, napló, visszajelzések és felmérési adatfogadás

A C21.11 receptalapú étrendjének bővítése. Előfeltétel a C21.11.1 sikeres telepítése és az eredeti projektben működő Next.js 16.4.6. A frissítés nem módosít csomagfüggőséget, Next-konfigurációt vagy korábbi étrendbizonylatot.

## Használat

- Az étkezési kártya fejlécében a tervezett időpont szerepel. Az elkészítési idő az **Alapanyagok és elkészítés** részbe került. A korábban ismeretlen időpont ismeretlen marad.
- Az időpontok külön a kártyán és közös szokásos időpontként is beállíthatók, másodperc pontossággal. **Időpontok, napló és felmérés mentése** őrzi meg őket. A bevásárlási mennyiséget egy időpontváltoztatás nem érinti.
- **Megettem**: aznapi, elmentett étkezéshez egy saját tervezett adag tényleges elfogyasztását rögzíti az aktuális idővel. Nyolcfős menünél is egy személy adagjáról van szó. Egyéb időpont vagy részadag a **Más adag / időpont** gombbal adható meg. Korábbi napnál a tényleges időpontot át kell nézni és meg kell adni.
- **Kihagytam**: kifejezett kihagyás. A jövőbeli terv nem lesz ettől múltbeli fogyasztás. Az üres napló ismeretlen bevitel, nem nulla étel.
- **Étkezés hozzáadása**: terven kívüli étel vagy ital, időponttal, mennyiséggel és mértékegységgel. Saját ételnév is használható. A recepttől független ételhez nem találunk ki tápanyagértéket.
- A **Rögzített étkezések** részben a bejegyzés javítható vagy a jelenlegi piszkozatból eltávolítható, majd menthető. A korábbi mentett változat megmarad az audit-előzményben. A naplóbejegyzés forrása egy korábbi menüverzió is lehet; későbbi menücsere nem írja át a régi étkezést.
- Az 1–5-ös visszajelzés opcionális. **Ételjavaslatok a visszajelzéseim alapján** helyben készít új menütervezetet a mentett tényleges étkezések pozitív/negatív ételértékeléseiből. Megőrzi az adagokat, személyszámot és az összes kötelező étrendi/allergénszűrést. Áttekintés és mentés után lesz az új terv a mentett menü.
- Legalább három valódi, azonos étkezéstípushoz kapcsolt bejegyzésből jellemző étkezési időpont javasolható. Átvétele külön gomb; az alkalmazás nem írja át automatikusan a megszokott időket. Ez szokásfelismerés, nem személyes energiaigény mérése vagy validált tanult élettani modell.
- Az izomtömeg megőrzése/növelése és az erő/állóképesség/jóllét hangsúlya külön megadható. A testsúlyirány továbbra is az egyetlen közös **Testsúlycél és testtömeg** részen található.

## Felmérés és mikrotápanyagok: mit lehet megtudni?

A napi bevitel, a szervezet aktuális ellátottsága és egy személy élettani szükséglete különböző fogalmak. A személyre szabott megítélésben a szokásos étrend, életkor és életszakasz, terhelés, egészségi körülmények, gyógyszerek/kiegészítők, valamint indokolt esetben célzott vizsgálatok együtt számítanak. Egyetlen laborpanel nem méri meg minden vitamin és ásványi anyag napi szükségletét.

Példák a célzott állapotfelmérésre, nem mindenkinek kötelező vizsgálati csomagként:

| Példa | Mit segít megítélni? | Fontos értelmezési körülmény |
| --- | --- | --- |
| Ferritin, szükség szerint kapcsolódó vizsgálatok | Vasraktárak/vasállapot | A gyulladás befolyásolhatja a ferritint; önmagában nem napi vasadag. |
| Össz- vagy aktív B12, egyes esetekben további marker | B12-ellátottság gyanújának vizsgálata | Tünetek, kockázati tényezők és korábbi pótlás is számítanak. |
| 25-OH-D | D-vitamin-státusz vizsgálata | A tünetmentes felnőttek általános szűrésének hasznára nincs elegendő bizonyíték; ez nem mindenkinél szükséges rutinpanel. |

Az appban rögzíthető a leleten szereplő megnevezés, pontos tizedes érték, `<`/`>` jelölés, mértékegység, mintavételi dátum, labor/dokumentum, referencia-tartomány és a szakmai értékelés. A referencia-tartomány koncentrációegységét nem alakítjuk napi beviteli egységgé. A bejegyzés felhasználó által rögzített adat; a program nem igazolja a lelet hitelességét és nem állít fel diagnózist.

Külön rögzíthető egy szakembertől kapott napi étrendi cél: tápanyag, alsó/felső cél, egység, élelmiszerekből vagy teljes bevitelből értendő hatókör, forrás, dátum, felülvizsgálati határ és opcionális kapcsolat a felméréssel. A laboreredmény nem hoz létre automatikusan ilyen célt. Egy lejárt cél megmarad előzménynek; a felület jelzi a felülvizsgálat igényét. Órarend-, helyszín- vagy menüváltoztatás nem érvényteleníti a felmérést.

Felmérés hiányában a recepttervezés továbbra is használható, általános egészséges étrendi háttérrel. Célzott vizsgálat indokoltságáról tünetek/kockázatok esetén szakemberrel érdemes egyeztetni; a funkció nem kéri mindenkitől ugyanazt a laborcsomagot.

## Pontos funkcionális határ

**Ez a kiadás nem számít automatikus személyes energia-/makrotápanyag-célt, nem becsüli újra az edzések energiafelhasználását, és nem optimalizál számszerű mikrotápanyag-célokra.** A C21.11 katalógusa nem tartalmaz teljes, forrással alátámasztott tápanyag-összetételt. A felmérési adatok és célok fogadása elkészült; a későbbi, ezek alapján történő számszerű étrendfinomításhoz ezt az alapanyag-adatbázist és az ellenőrzött számítási szabályokat kell hozzáadni. A hiányzó tápanyagadat nem válik nullává vagy igazolt megfelelőséggé. A szakmai cél rögzítése nem igazolja annak teljesülését.

## Működés és adatmegőrzés

- `GET/POST /api/v1/planning/nutrition/journal`: külön, konfigurált tulajdonoshoz kötött végpont. Csak pontos GET/POST útvonal, az eredeti origin-, méret-, query- és credentialvédelem mellett.
- Új `nutrition_journal` auditfajta, meglévő tárolóban, migráció nélkül. Atomi, előző verzióhoz és kérésazonosítóhoz kötött mentés. Másik ablakból érkező változást nem ír felül csendben.
- Válaszvesztésnél a böngésző az eredeti mentési kérést őrzi meg. Az ellenőrző újrapróbálás azonos bájtokat használ, nem hoz létre dupla étkezést. POST nem ismétlődik automatikusan.
- Az étrend és a napló külön menthető. Egyik piszkozatát a másik mentése nem törli. A napló opcionális paneljének hibája nem rejti el a menüt.
- A kártya megnyitása, időpontszerkesztés, nézetváltás, statisztika és ételértékelési javaslat helyi művelet. Nem hívja a Polart vagy az edzéstervezőt.
- Az óraátállítás nem létező helyi idejét elutasítja; az ismétlődő órában a két előfordulás közül választani kell. A korábbi bejegyzés saját időzónája megmarad.
- A jelenlegi naplóállapot legfeljebb 500 bejegyzést, 100 felmérést és 50 étrendi célt fogad. A régi verziók megmaradnak. Nagyobb naplóhoz külön lapozott történeti végpont szükséges; a rendszer nem csonkolja csendben az adatokat.

## Források

Ellenőrizve: 2026. november 17.

- EFSA: https://www.efsa.europa.eu/en/topics/topic/dietary-reference-values – populációs referenciaértékek és egyéni szükséglet különbsége.
- WHO: https://www.who.int/publications/i/item/9789240000124 – ferritin, vasállapot és értelmezési körülmények.
- NICE NG239: https://www.nice.org.uk/guidance/ng239/chapter/Recommendations – célzott B12-vizsgálat és az eredményt befolyásoló tényezők.
- USPSTF: https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/vitamin-d-deficiency-screening – tünetmentes felnőttek D-vitamin-szűrésének bizonyítékai.
- WHO: https://www.who.int/news-room/fact-sheets/detail/healthy-diet – általános egészséges étrendi háttér.

## Ellenőrzés

`python tools/run_c21_12_checks.py`: releváns backendregressziók, teljes aktuális frontendtesztsor, TypeScript, ESLint, buildőr és valóban elkészült éles build ellenőrzése.

Külön valódi FastAPI + React StrictMode próba ellenőrzi a személyes adagot, terven kívüli étkezést, felmérési egységeket, külön étrendi célt, válaszvesztés azonos újrapróbálását, piszkozatmegőrzést és újranyitást. A gépi kódellenőrzés nem klinikai validálás.
