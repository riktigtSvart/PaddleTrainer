# C21.10.1 – Beragadó adatfrissítés és szervereredmény-ellenőrzés

Kis frontend-javítás C21.10-hez. Az adatbázis és a backend szerződése változatlan; új függőség nincs. A meglévő kérésazonosítóval ellenőrizzük a már elindított adatátvételt.

## A javított elakadás

A fejléc külön tartotta nyilván az eredeti POST-ra várást és a megőrzött frissítési kérést. A háttérben végzett, ellenőrzött GET már visszaadhatta a lezárt eredményt, és törölhette a függő kérést, miközben az eredeti hálózati válasz továbbra sem érkezett meg. A `sending` állapot ilyenkor igaz maradhatott, és a gomb továbbra is „Frissítés…” állapotban volt.

Most az azonos eredeti kéréshez tartozó, tulajdonos- és hash-ellenőrzött lezárt eredmény feloldja az eredeti válaszra várást is. A későn érkező válasz vagy megszakítás nem írja felül ezt az igazolt eredményt, és egy újabb kérést sem oldhat fel véletlenül.

Ez a hiba reprodukálható. A felhasználó által mellékelt napló a sikeres C21.10 tesztkaput mutatta; a náluk futó konkrét Polar-lekérés futásidejű hibáját nem tartalmazta. A javítás ezért a bizonyított felületi elakadást és a végtelen hálózati várakozást kezeli, nem állítja, hogy a Polar minden lekérése sikeres.

## Időkorlátok

- Böngésző: kapcsolati állapot és kérésnyugta legfeljebb **35 másodperc**.
- Böngésző: az adatátvétel eredeti válaszára legfeljebb **220 másodperc**.
- Next közvetítő: olvasás legfeljebb **30 másodperc**, adatátvételi válasz legfeljebb **210 másodperc**.

A határ a teljes válaszra, annak tartalmára is vonatkozik. A puszta fejlécek megérkezése nem hagyhat korlátlan ideig függőben egy JSON-olvasást. A külön várakozásfigyelő akkor is lejár, ha maga a hálózati művelet nem reagál a megszakításra. A szerveroldali adatátvétel meglévő 180 másodperces végrehajtási kerete és 240 másodperces foglalási határa változatlan.

A válaszra várás megszakítása nem bizonyítja a szerveren futó adatátvétel megszakadását. Emiatt az eredeti kérés változatlan bájtjai és azonosítója megmaradnak, és nem történik automatikus POST-ismétlés. Az állapotellenőrzés továbbra is csak olvasás. Az időtúllépés külön 504/`DATA_SYNC_API_TIMEOUT` jelzést kap; az elérhetetlen szerver 502/`DATA_SYNC_API_UNAVAILABLE` marad.

## Felület

Amikor egy korábbi kérés eredménye még tisztázandó, a főgomb **Állapot ellenőrzése** felirattal használható. Megnyitja az állapotpanelt és újraolvassa a mentett állapotot; új adatátvételt nem indít. Az időtúllépés látható hibaüzenetet ad. Egy lejárt kezdeti állapotolvasást a felület nem nevez tovább betöltésnek.

A befejezett, ellenőrzött nyugta helyben is frissíti a megfelelő szolgáltató utolsó futását, így egy korábbról megmaradt „fut” jelzés nem tartja zárolva a gombot egy következő állapotlekérésre várva. Újabb szerverfutást nem írunk felül régebbi nyugtával.

## Telepítés utáni teendő

A mostani böngészőfület hagyd nyitva; ebben maradt meg a függő kérés. A frontend leállítása, a csomag alkalmazása, a frontend tesztkapu és az újraindítás után ebben a fülben **Ctrl+Shift+R**. Az alkalmazás az eredeti kérés eredményét olvassa vissza.

Szükség esetén a fejlécben **Állapot ellenőrzése**, vagy a jobb oldali lenyílóban **Kapcsolati állapot újraolvasása** használható. A már ellenőrzött sikeres/részleges/hibás vagy megszakadt futás után új művelet indítható. Ha még nincs igazolt eredmény, az eredeti kérés megmarad és konkrét állapotüzenet látható.

## Ellenőrzés

- **1447 frontendteszt**, route-típusgenerálás, TypeScript, ESLint és production build sikeres.
- A változatlan backend meglévő adatkapcsolati tesztjei: **48 sikeres teszt**.
- Valódi FastAPI TestClient API-val, elkülönített szintetikus adatbázissal és React StrictMode/JSDOM felülettel ellenőrizve a szerver mentése után visszatartott eredeti válasz: külön a fejlécek és a tartalom elakadása. Mindkettőnél a nyugta olvasása feloldotta a gombot, további POST nélkül.
- Ellenőrizve az eredeti kérés visszaállítása oldal-újranyitáskor: kizárólag GET, automatikus írás nélkül.
- Ellenőrizve az ismeretlen kimenet és a nem válaszoló kezdeti állapotlekérés: a határ lejár, a hiba látszik, a megőrzött kérés nem vész el, és az állapotellenőrzés nem küld új adatátvételt. A hosszú időkorlátokat a próbában gyorsított tesztórával vizsgáltuk.
- A határidő-tesztek a megszakítást figyelmen kívül hagyó hálózatot, a késői választ és a válasz végtelen tartalmát is lefedik. A korábbi tulajdonosi, kérésazonossági, útvonal- és adatvédelmi ellenőrzések átmentek.

Natív böngészős képernyőképes ellenőrzés nem készült. A telepítő a forrásfájlokat menti és frissíti; az adatbázist nem módosítja. A mostani javítás ellenőrzéséhez a frontend kapu elegendő; a teljes backend kapu külön, opcionálisan futtatható.
