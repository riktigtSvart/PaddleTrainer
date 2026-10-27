# P2.4C8.3 – Tervezett edzések időpontjának módosítása

Alap: `698882bbe5b5a154ab207fb7edec36f45221e4ae`, tiszta main és origin/main, a C8.2 + R1 után.

## Felület

Az 1 és 7 napos nézetben a még nem teljesített és nem véglegesített edzéskártya belseje egérrel vagy tollal másik időpontra / napra húzható. A húzás ugyanazt a mért oszlopgeometriát és 5 perces lépést használja, mint a napirendi idősávok. A meglévő másodpercérték megmarad. A tervek nem kapnak időtartamot módosító szélfogantyút: az edzésadag módosítása más feladat.

A kattintás továbbra is részleteket nyit. A részletek **Edzés áthelyezése…** gombja pontos dátum- és időmezőket ad. Ez időpont nélküli vagy ismeretlen hosszúságú tervnél, hosszabb nézetben, érintőképernyőn és billentyűzettel is használható. Hiányzó időtartamból nem készül önkényes hosszúságú húzható edzéskártya.

Elengedés után az új időpont először a szerkesztőbe kerül. **Áthelyezés áttekintése → Áthelyezés mentése** véglegesít. Az előnézet a napirendi elfoglaltságokat, a megadott edzéslehetőségeket és időkereteket, másik edzéssel való átfedést, valamint a kapcsolt felkészülési időszak határait vizsgálja. Ismeretlen időadat és személyes időbecslés külön feliratot kap. Az ütközésre figyelmeztetés után a felhasználó dönt a mentésről; a rendszer nem tervez át további edzéseket.

A felső **Visszavonás** a legutóbbi érintett szerkesztést választja. Edzésáthelyezés esetén az előző időpontot újabb előnézet és külön mentés után állítja vissza, új auditrevízióval. Az eredetileg időpont nélküli állapot is visszaállítható. A visszavonás egy szintű, böngészőnként tárolt előzmény; újabb mentési referencia esetén a régi művelet nem írható vissza automatikusan.

## Mentési határ

A művelet kizárólag `PlannedWorkout.date`, `planned_start_time` és `updated_at` mezőket változtat. Távot, időtartamot, intenzitást, blokkstruktúrát, mezociklus-hivatkozást vagy mért teljesítési adatot nem ír át. A kapcsolt teljesítés, illetve lezárt / kihagyott / törölt állapot kizárja az áthelyezést. Az authoritative logikai tervhez kötött források a meglévő tervfelülvizsgálati folyamatban módosíthatók; a naptári művelet ezt nem kerüli meg.

Minden mentés owner-zárral és tervsorzárral történik. A bemenet rögzíti a forrás pillanatfelvételének hash-ét, a legutóbbi áthelyezés referenciáját, az időzónát, a célidőt és az előnézet hash-ét. A szerver mentés előtt újraszámolja az előnézetet. Megváltozott forrás, teljesítési kapcsolat, napirend, edzéslehetőség, ütközési helyzet vagy ciklushatár új áttekintést igényel. A személyes becslés pusztán új lekérdezési időbélyege nem érvényteleníti a változatlan következtetést; az érdemi becslési adatok a hash részei.

Új immutable auditfajta: `calendar_workout_move`. A rekord a kérés mellett a régi forrást, régi és új időpontot, valamint a mentéskor újraellenőrzött teljes előnézetet is megőrzi. A tartós bizonylatot a frontend a saját kéréshez, tulajdonoshoz, identitáshoz és teljes tartalomhash-hez ellenőrzi. A mért edzésidők nem kerülnek ebbe az írási útvonalba.

A pontos kérésbájtok a POST előtt helyi függő rekordba kerülnek. Ismeretlen kimenetelnél a párbeszédablakban és újratöltés után is elérhető a kifejezett újraküldés. Azonos kérés ugyanazt a bizonylatot adja; egy korábbi sikeres kérés visszajátszása nem állítja vissza a terv régi időpontját. Biztos elutasítás után külön elvetés és újraolvasás lehetséges. Böngészőtárhely-hibánál a még nem őrizhető kérés nem indul el.

## Polar

Az appban jóváhagyott időpont helyben érvényes. A Polar naptárának módosítása külön feladat; ezt a szerkesztő jelzi. Egy későbbi target-import megtartja a jóváhagyott appbeli időpontot, miközben a szolgáltatói forrásadatot, állapotot és az edzés többi adatát továbbra is frissítheti. A szolgáltatói target ID és a korábbi teljesítési kapcsolatok megmaradnak. A célforrás korábbi nyers adatainak meglévő archiválása tovább működik. Az importer tervsorzárat használ, a helyi időpont tulajdonlását ellenőrzött áthelyezési előzményből olvassa.

## API

- `GET /planning/calendar/moves/{plan_id}`: tulajdonosi kontextus, forráshash, aktuális / visszaállítható időpont és módosíthatóság.
- `POST /planning/calendar/moves/preview`: forráshoz kötött javaslat és csak olvasó ütközési előnézet.
- `POST /planning/calendar/moves`: javaslat + előnézethash, tranzakciós módosítás és immutable bizonylat.

A zárt frontend proxy csak ezeket a pontos útvonalakat engedi. A kontextushoz nem fogad query paramétereket; a POST az ismert Origin / JSON / bájtkorlát védelmet használja. Új függőség és adatbázis-migráció nem szükséges: az auditfajta meglévő szöveges tárolóra épül.

## Ellenőrzés

A backend HTTP-próbák izolált SQLite-on, valódi alkalmazási / tárolási kóddal futnak; a Polar csak szintetikus szolgáltatói válaszokat ad. A frontend bizonylatpróbák tényleges backendből rögzített kontextust és hash-eket ellenőriznek. A DOM-próba a tényleges React naptárt köti a valódi HTTP- és tárolási folyamathoz stdin/stdout csatornán, ideiglenes adatbázissal. Húzást, kattintást, előnézetet, mentést, felső visszavonást, elveszett válasz utáni újratöltést és ugyanazon kérés megismétlését ellenőrzi. JSDOM-ban a geometria, pointer-capture és dialog kap helyettesítést; ez nem natív böngészős vagy Windows-próba.
