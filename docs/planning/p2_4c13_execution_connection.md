# P2.4C13 — végrehajtási bizonyíték bekötése

A C12-ben „edzésbizonyítékra vár” állapotban lévő visszajelzéshez a meglévő tervátvételi, terv–teljesítés-azonosítási és executed-training bizonyítékláncot kapcsolja hozzá. Az alkalmazás nem talál ki korabeli tervváltozatot, időbeli párosítást vagy teljesített szakaszhatárokat.

## Felhasználói folyamat

A **Saját visszajelzés → Tanulási kapcsolat** részben a **Terv és teljesítés ellenőrzése** gomb előnézetet kér. A gomb csak olvas; nincs átvétel vagy bizonyítéklétrehozás a lap megnyitásától.

Az előnézet a teljesítés nevét/kezdetét, a tárolt terv nevét/napját, a profil időzónáját és a kapcsolat alapját mutatja. Elfogadható alap:

- a két tárolt Polar-forrásban egyező célazonosító, azonos sportolóval/sporttal és nem ellentmondó tervhivatkozással;
- egy korábban explicit `MANUAL_CONFIRMED` jelölést kapott, az adott tervre mutató kapcsolat.

A puszta `planned_workout_id`, egy `AUTO_MATCHED` jelölés, a név vagy időpont közelsége nem elég. A szolgáltatói azonosítóütközést nem írja felül a kézi jelölés. Hiányzó, más sportolóhoz tartozó vagy nem támogatott forrásnál az előnézet elutasítási okot ad. Ez a lépés nem kínál önkényes újrapárosítást vagy naptári keresést.

Két külön megerősítés szükséges a felületen: a most ismert tervállapot használata nem igazol visszamenőleg tervváltozatot; a terv és teljesítés összetartozása nem igazolja a szakaszok teljesítését. Ezek után a **Kapcsolat és bizonyíték rögzítése** indítja az írást.

## Meglévő szerződések újrahasználata

Ha még nincs authoritative tervazonosság, a jelenlegi terv a meglévő `prepare_current_state_adoption` útvonalon kap új, planning-owned alapváltozatot. Ez `CURRENT_STATE_BASELINE_ONLY`, most kezdődő authority-ablakkal. Polar-forrásnál a meglévő provider–ORM egyeztetés és annak tartós auditja is szükséges. Az eredeti provider- vagy capture-azonosítókat nem emeljük planning-owned azonosítóvá.

Ha a tervnek már van ellenőrzött alapváltozata, azt újabb átvétel helyett újrahasználjuk. A `resolve_execution_link_basis` és `finalize_authoritative_plan_execution_link` a már meglévő, szigorú azonossági szabályokat alkalmazza. A végrehajtási auditot a meglévő `assemble_authoritative_executed_training_with_repository`, a generic evidence-et a meglévő executed-training projector hozza létre. Az előzetesen meglévő, de azóta forrásváltozást elszenvedett execution linket nem írjuk át.

A rögzített bizonyíték `plan_content_at_execution_status=unverified` állapotú. Az occurrence-, phase-, provider-event-, clock- és tényleges szakaszhatár-igazolást nem állítjuk be. A tervazonosság nem azonos a terv szerinti teljesítés vagy edzéshatás bizonyításával.

## Egy tranzakció és visszakövethető nyugta

Egy megerősített kérés egy tranzakcióban rögzíti a szükséges tervátvételt, a Polar reconciliation auditot, az execution linket, az authoritative executed-training auditot, annak generic evidence-projekcióját és a `SESSION_EXECUTION_CONNECTION` nyugtát. Bármelyik lépés hibája az összes új írást visszagörgeti. A meglévő belső repository-k flush-olnak; a külső workflow egyszer commitol.

A nyugta tulajdonoshoz és UUID kérésazonosítóhoz kötött; tárolja a megerősített előnézet hash-ét, a forráshasheket, a terv-, execution-link- és execution-evidence referenciákat, valamint a korlátozott authority-jelzéseket. A mentett tartalmat commit előtt visszaolvassuk és ellenőrizzük. Csak sikeres commit után adunk `committed=true` választ. A commit-visszaigazolás elveszhet: ugyanazzal a kérésazonosítóval és törzzsel a már tartós nyugta visszakapható, új tervváltozat nélkül.

Az előnézet hash-e a releváns forrásokat, a profil időzónáját, a meglévő tervreferenciát és a kapcsolati feltételeket köti, nem egy új olvasás véletlen capture-azonosítóját. A POST újraolvassa és zárolja a forrásokat. Eltéréskor új előnézet kell; nincs automatikus újraelfogadás.

A két meglévő zárolt forrásprovider `populate_existing=True` opcióval frissíti az ORM identity mapben már betöltött sorokat. Egy `FOR UPDATE` lekérés így nem használhat a zárolás előtti, elavult Python-attribútumokat a forráshash készítéséhez.

## Bizonytalan kliensoldali eredmény

A böngésző a pontos POST-törzset még a küldés előtt, sportolóhoz és teljesítéshez kötve megőrzi. Ha nem tud tartósítani, nem küld írást. Hálózati/5xx hiba vagy ellenőrizhetetlen válasz után az **Azonos rögzítés újrapróbálása** ugyanazokat a bájtokat küldi. Újratöltéskor akkor is visszaáll ez a kérés, ha a háttérben a végrehajtási bizonyíték már létrejött. Egy másik lapon függő kérés nem írható felül csendben.

A kliens csak az egyező sportolót, teljesítést, megerősítéseket, sémát, hash-t, referenciákat és commitot igazoló nyugtát fogadja el. Határozott 4xx elutasítás után a kérés megszüntethető és új előnézet kérhető. Egy 409 nem jogosítja fel a klienst az adatok automatikus újraelfogadására.

## C12 kapcsolat és időbeliség

A végrehajtási bizonyíték sikeres commitja után a szerver külön tranzakcióban megkísérli a C12 tanulási kapcsolat frissítését. Ennek hibája nem változtatja a már commitolt C13 műveletet sikertelenné. A kapcsolat később idempotensen újraellenőrizhető.

A végrehajtási bizonyíték most rögzített elérhetősége miatt a visszajelzés nem használható tudományos elemzésben úgy, mintha a teljes bizonyítéklánc már korábban is ismert lett volna. Az utólagos kitöltés C12 időpontjai külön megmaradnak. A pipeline változatlanul legfeljebb leíró személyes elemzési bemenetet ad; a modell tanítása, hatásbecslés és tervmódosítás külön jogosultság/lépés.

A meglévő freeze változatlan marad későbbi Polar-frissítéskor is. A később pontosított forrásadat nem írja át automatikusan az első freeze-t vagy a hozzá tartozó auditot; ilyen korrekcióhoz külön, explicit provenance-kezelés szükséges.

## API, tárolás, korlátok

- `GET /planning/calendar/sessions/{UUID}/execution-connection`: tulajdonoshoz kötött, zárolás után visszagörgetett, írásmentes előnézet.
- `POST` ugyanitt: UUID `request_id`, `review_hash`, két explicit JSON boolean `true` megerősítés. Extra mező, numerikus vagy szöveges megerősítés nem engedélyezett.
- Új nyugtafajta: `SESSION_EXECUTION_CONNECTION` a meglévő audit-táblában. Nincs új tábla vagy migráció; a korábbi planning/reconciliation/execution/evidence migrációk szükségesek.
- A Next proxy csak a pontos UUID-s útvonalon enged GET/POST-ot, query nélkül. A meglévő Origin-, bodyméret-, credential- és redirect-korlátok megmaradnak.

A `PlannedWorkout`, `WorkoutBlock`, `WorkoutSession` és Polar nyers adatok tartalmát a bekötés nem módosítja. Nem küld kérést a szolgáltatónak, nem ír vissza a Polarba, és nem változtat edzésterhelést.

## Ellenőrzés

Izolált SQLite HTTP-tesztek ellenőrzik a korábbi manuális és a valódi egyező Polar-célazonosítós utat, a reconciliation auditot, a C12 személyes bemenetekig tartó láncot, a tulajdonosi védelmet, a stale preview-t, a profil időzónaváltását, a nyugták ismétlését, a részleges írások rollbackjét, az elveszett commit-visszaigazolást, a meglévő terv újrahasználatát és az ORM identity-map frissítését. A PostgreSQL valódi párhuzamos sorzárolását a SQLite-próba nem helyettesíti.

A frontend a Python HTTP-fixture-t is ellenőrzi. DOM/JSDOM próbák fedik a két megerősítést, az írás előtti tartósítást, az újratöltés utáni azonos ismétlést, a forrásütközést és a tárhelyhibát. A teljes kapu a korábbi adoption/execution/feedback/elemzési teszteket és a teljes frontend tesztsort, típusellenőrzést, lintet és production buildet is futtatja. Élő alkalmazás-DB-t vagy Polart nem ér el; natív Windows alkalmazáspróbát a helyi teszt nem állít.
