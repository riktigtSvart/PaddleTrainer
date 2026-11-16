# C21 · Alkalmazáskeret és vezetett adatfelvétel

A módosítás a négy fő terület köré rendezi az alkalmazást, és az adatfelvétel befejezéséhez kapcsolja a tartós, kikapcsolható automatikus edzéstervezést.

## Használati útvonal

1. Az alapnézet a **Naptár**. Mentett profil nélkül az első megnyitás a vezetett adatfelvételre irányít.
2. Az **Alapadatok / tervezési adatok** hat lépése: személyes adatok → sportelőélet → célok és felkészülés → helyszínek → edzésrend → állapotfelmérés.
3. Az állapotfelmérés részei: kérdések és jártasság; már ismert mérések és órás előzmények; gyakorlati felmérés. A próba eredménymezői a vezetett erőfelmérésben, az indítás és a bemelegítés visszaigazolása után nyílnak meg.
4. A befejező gomb a mentett előfeltételek alapján engedélyezi és elindítja az automatikus tervezést, majd megnyitja a naptárat. A hiányzó lépések külön megnevezve láthatók.
5. A naptár állapotkártyája jelzi az automatikus tervezés helyzetét, az új edzések számát vagy a megmaradt akadályokat. A beállítás az adatfelvétel végén kikapcsolható.

## Megvalósítási térkép

| Kérés | C21 viselkedés |
|---|---|
| Filigrán, állandó fejléc | Saját, 44 px magas sor; a tartalom alatta görgethető. A bal menü is saját, állandó oszlopban marad. |
| Téma és alapértelmezett frissítés | A meglévő működő vezérlők kompakt változata; a frissítés menüje megmarad. |
| Bevásárlólista és nyelv | Megjelölt, inaktív későbbi vezérlők. A böngésző nyelvét a fejléc jelzi; a felület jelenleg magyar. |
| Négy főmenüpont | Naptár; Alapadatok / tervezési adatok; Táplálkozási opciók; Általános beállítások. |
| Testméretek | Közvetlen testsúly-, magasság- és mérésidátum-mező, pontos tizedesjegyekkel. A régi profilok változtatás nélkül olvashatók. |
| Sportelőélet | Szabadon beírható sportág, legmagasabb és jelenlegi szint, fő/kiegészítő/szabadidős/szünetelő szerep. A korábbi szintadat a legmagasabb elért szint mezőjében marad. |
| Célok és dátumok | A meglévő felkészülés- és cikluskezelő, versenyekkel és képességszerepekkel. A rekreáció egészségmegőrzési célhoz is választható. |
| Helyszín szerkesztése | A kiválasztott helyszín saját kártyájában nyílik meg. Új helyszín külön szerkesztőkártyát kap. |
| Általános órarend | Helyszínekre épülő meglévő órarend; ugyanitt külön lenyitható a következő hét napi kivételeinek kezelése. |
| Felmérés naptárba helyezése | Felmérési időfoglalás szerkeszthető dátummal és idővel. Elfoglaltságként lefoglalja az időt; nem válik előírt vagy teljesített edzéssé. |
| Naptári hover | A meglévő részletesebb gyorsnézet megmarad. |
| Naptári kattintás | Edzésrészlet-ablak; teljesítésnél a mérési elemzőfelület, tervnél a meglévő tervadatok és leírás. A teljes adatlap külön oldalon is megnyitható. |
| Alternatív edzések | A saját felkészüléshez igazoltan kapcsolt, jövőbeli alkalmazástervek részletablakából érhetők el a meglévő gördülő terv változatai és az áttekinthető módosítások. |
| Naptári rétegek | Tervezett edzések és teljesítések külön; edzéslehetőségek; elfoglaltságok; felkészülési időszakok; ismert állapotadatok. Párosított terv/teljesítés esetén a külön kapcsolt oldal önállóan is megmarad. |
| Edzésnapló és elemzés | A naptárból külön elérhető az edzésnapló és a személyes válaszadatok. A korábbi közvetlen oldalcímek továbbra is működnek. |
| Általános beállítások | Téma és működő órás kapcsolatvezérlő; naptárkapcsolatok és nyelv későbbi lehetőségként megnevezve. |
| Táplálkozási beállítások | Későbbi modul: étrend, érzékenységek, preferenciák, testtömegcél, kötelező boltválasztás és opcionális márkák helye megjelenik. |

## Saját testsúlyos felmérés

A saját testsúly adottság. A megadott, ismert változatban a szabályos ismétléseket mérjük, nincs elérendő célismétlésszám, és nem kérünk tíz ismétléshez választott terhelést. Az ismert megállási szabályok és az első mérés ismétléskorlátja megmaradnak; a korlát elérése nem maximális ismétlésszám.

Az alapértelmezett eredmény külső súly nélküli saját testsúlyos végrehajtás. A már ténylegesen hozzáadott külső súly külön, opcionális részben rögzíthető. A testsúly ismeretlen értékét nem helyettesítjük nullával.

A korábbi bankkal már megkezdett alkalom megjelenítése is a javított saját testsúlyos utasítást használja. A tartósan mentett eredeti protokoll, annak hash-e és a nyers megfigyelések változatlan auditadatok maradnak. A külső súlyos gyakorlatok rögzített utasítását nem cseréljük le.

## Automatikus tervezés

A befejezés egy tulajdonoshoz és pontos felkészülés-hivatkozáshoz kötött beállítást ment. A bekapcsolás és a kikapcsolás tartós, verziózott, az ismételt kérés ugyanazokat a bájtokat használja. Az új háttérfolyamat a meglévő, percenként futó ellenőrzéshez kapcsolódik, és szerver-újraindítás után is a mentett beállítást olvassa.

A tervezés a meglévő ellenőrzött edzésmintákra, saját referenciákra, helyszínekre, időablakokra, terhelési keretekre és aktuális/következő mentett mezociklusokra támaszkodik. Ugyanazt az ellenőrzött elfogadási tranzakciót használja, mint a kézi jóváhagyás; az automatikus alkalmazás külön megjelölt jogosultsági forrást kap, nem állít emberi áttekintést. A beállítás visszavonását közvetlenül az alkalmazás előtt is ellenőrzi.

A kézzel megadott vagy külső szolgáltatói tervek védelme, az ismeretlen adatok kezelése és a terhelési felső korlátok megmaradnak. Külső óraszolgáltatóhoz nem ír vissza edzést. A véges felkészülés végén leáll; nyitott rekreációs cél esetén a mentett ciklusok elfogyása után új ciklusok szükségesek.

## Határok

- A sportági kérdőív több sportágat kezel, de automatikus edzésminták jelenleg kajakhoz, futáshoz és erősítéshez állnak rendelkezésre. A sportmúltban rögzített szint önmagában nem helyettesít mért terhelhetőséget.
- Végrehajtható gyakorlati tesztvezetés az erőfelméréshez készült. A további képességekhez a meglévő cél-, protokoll- és mérésrögzítés érhető el.
- Táplálkozási tervezés, ételalternatívák, bevásárlási lekérés, külső naptárkapcsolatok, regenerációs javaslatgenerátor és becsült fáradtsági modell még nincs bekötve.
- A felület továbbra is az alkalmazás már meglévő, beállított sportolói fiókját használja; új bejelentkezési vagy felhasználókezelő rendszert ez a frissítés nem vezet be.

## Ellenőrzés

A teljes tervezési backendkészlet, a teljes frontendkészlet, TypeScript, ESLint és production build ellenőrizendő a `python tools/run_c21_checks.py --build` paranccsal.

Külön DOM-interakciós ellenőrzés fedi a személyes/sportelőéleti piszkozat megtartását, a helyszínkártyában nyíló szerkesztőt, a felmérési időfoglalást, a naptári részletablakot, az új profil belépési útját és a felmérés kézi eredménymentési folyamatát.
