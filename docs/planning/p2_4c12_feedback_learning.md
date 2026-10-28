# P2.4C12 — visszajelzések a személyes terhelés–válasz adatfolyamban

A C11 változatlan auditbejegyzései két helyre kapcsolódnak: a napi sportolói állapot megfigyeléseihez, illetve a meglévő P1.8 → P2.1 → P2.2 bizonyíték- és személyes elemzési lánchoz. A kapcsolat visszakövethető és időbeli információs korláttal újrajátszható. Ez adatbekötés, nem új prediktív modell, automatikus edzésterv-módosítás vagy bizonyított edzéshatás.

## Kiválasztás

A `feedback_learning.select_revisions` sportolónként, edzésenként és időzítésenként a legutóbbi, az információs határidőig ismert revíziót választja ki. A teljes hash-láncot ellenőrzi. A kiválasztás megelőzi a megfigyelési dátum szerinti szűrést: ha egy javítás más napra helyezi a megfigyelést vagy törli az összes pontszámot, a régebbi válasz nem éledhet újra.

Az adat legkorábbi elérhetősége a következők maximuma:

- a felhasználó megfigyelési időpontja;
- a bejegyzés szerveroldali beküldési ideje;
- az auditbejegyzés adatbázis által kiadott tartósítási ideje.

A beküldés és a megfigyelés pontos időpontja külön megmarad. A kijelzett kitöltési késés egész másodpercben, lefelé kerekítve szerepel. Ez az utólagos kitöltés leírása; nem állítjuk, hogy egy visszatekintő önbevallás ugyanannyira megbízható, mint az azonnal kitöltött. Nincs önkényes óraszám szerinti automatikus kizárás vagy megbízhatósági súly. A későbbi modell külön kezelheti ezt a kontextust.

Az edzés utáni és a másnap reggeli csoport külön marad. Az öt mérőszám: `self_reported_rpe_score`, `self_reported_fatigue_score`, `self_reported_soreness_score`, `self_reported_recovery_score`, `self_reported_energy_score`. A nulla KNOWN érték, az üres mező UNKNOWN/null. Az RPE szubjektív nehézség, nem mért fiziológiai terhelés. A megjegyzés szövegét nem alakítjuk át pontszámmá vagy modelljellemzővé; a forrás hash-e a megjegyzést is köti.

A kiválasztás tulajdonoshoz kötött, a forrásolvasás legfeljebb 20 000 C11 revíziót enged egy lekérésben. Túllépésnél megáll, nem ad csendesen csonkított tanulási adatot. Nagyobb állományhoz később indexelt, lapozott kiválasztás szükséges.

## Napi sportolói állapot

A meglévő `get_daily_response_observations` a C11 forrásból is visszaad megfigyeléseket. A napi információs határidő az adott helyi nap vége és a jelenlegi idő közül a korábbi. A később bevitt, visszadátumozott válasz ezért nem szivárog be egy korábbi napi állapotba. A hagyományos `AthleteResponse` soroknál a létrehozási idő is szűrt.

Ha ugyanahhoz az edzéshez és időzítéshez ismert C11 revízió tartozik, az azonos csoport régi `AthleteResponse` sora nem növeli meg a megfigyelések számát. Más időzítésű és nem kapcsolt régi megfigyelések megmaradnak. A forrásokat nem írjuk át és nem hozunk létre másolatként új `AthleteResponse` sort.

A napi visszaadott megfigyelés tartalmazza az eredeti visszajelzés azonosítóját, hash-ét, revízióját, elérhetőségét és a beküldési késést. Egy változatlanul megőrzött történeti elemzéshez továbbra is rögzített információs határidőt kell használni.

## Tudományos bizonyítékbekötés

A `LockedSessionFeedbackSource` a meglévő `LockedTrainingResponseSourceProvider` szerződését valósítja meg. Tulajdonosi és edzéssorzárolás mellett egy **explicit auditazonosító + hash** által kijelölt, változatlan revízióból készít forráscapture-t. UUID5 forrásazonosítója sportoló- és revíziófüggő, nem azonos a felhasználó kérésazonosítójával. A hash, az öt mérőszám státusza, a valódi megfigyelési/elérhetőségi idő és a C11 auditazonosító bekerül a meglévő authoritative response freeze-be.

A materializálás a már meglévő `ingest_authoritative_training_response` szolgáltatást és tartós EvidenceItem-projekcióját használja. Ehhez szükséges az adott edzés **már létező, ellenőrzött authoritative executed-training auditja**. Egy naptári Polar-párosítás vagy a szöveges edzésnév önmagában nem hoz létre ilyen bizonyítékot. Ennek hiányában az önbevallás napi állapotadatként elérhető, a szigorúbb elemzési bekötés `waiting_for_execution` állapotot jelez.

Egy revízió egyszer fagyasztható be; az ismételt kérés a meglevő tartós freeze-t állítja helyre. A hiányzó response EvidenceItem-projekció ugyanehhez az auditforráshoz újra létrehozható. A javítás új forrást és új freeze-t kap, a korábbi történeti bizonyíték nem módosul.

A `RevisionAwareFeedbackEvidenceRepository` az explicit információs határidő szerint kiszűri a már meghaladott C11 freeze-eket, és ugyanebben az edzés/időzítés csoportban a régi megfigyelések dupla beszámítását is megakadályozza. Egy forrás nélkül maradt C12 freeze nem térhet vissza „másik régi adatként”. A közönséges evidence-repository auditcélra továbbra is megőrzi az összes változatot.

A `assemble_feedback_personal_inputs` C12 belépési pont a kiválasztott bizonyítékokkal futtatja a meglévő history-, response-metric rejoin-, referencia-, adatelégség- és személyes asszociációs dataset-építést. **A C12 személyes elemzéshez ezt a belépési pontot, illetve a revíziót szűrő repository-t kell használni; az összes történeti revízió nyers listája nem tanulási mintahalmaz.** A lefagyasztás előtt a generic response evidence sem használható korábbi tudományos elemzésben: annak saját elérhetőségi ideje is érvényes.

A `duration_s` prediktor a már rögzített edzésidőt használhatja, az eredeti ismertségi státusszal és másodperc egységgel. Ez egyszerű expozíciós leíró, nem új terhelésbecslés. Egyéb hiányzó terhelésjellemzőt nem pótolunk. A lefedettség ismeretlen/részleges marad; a referencia- és modellalkalmasság nem lesz automatikusan elegendő néhány visszajelzéstől. A bekötés legfeljebb leíró jogosultságot ad.

## API és felület

- `GET /planning/calendar/sessions/{UUID}/learning`: a két csoport kiválasztása, forrásreferenciái, ismertségi státuszai és bekötési állapota. Az API opcionális, időzónás `information_cutoff_at` paraméterrel korábbi információs állapotot is megmutat; jövőbeli/naiv határidő nem engedélyezett. A webes proxy ezen a végponton csak a jelenlegi, query nélküli olvasást engedi.
- `POST` ugyanitt, `{}` törzzsel: a jelenleg beköthető források idempotens lefagyasztása. A kliens nem adhat meg saját mérőszámot, sportolót vagy mesterséges bizonyítékot.
- `GET /planning/calendar/learning-inputs`: a meglévő személyes elemzési lánc bemeneti assembly-je. Alapértelmezésben az utóbbi 90 nap, opcionálisan `start_date` + `end_date` a sportoló profiljának időzónájában. Olvasási művelet; a prediktív modell nem frissül.

Minden útvonal a meglévő tulajdonosi határon marad. A Next proxy explicit útvonallistája, GET/POST-, Origin-, query-, méret- és credential-korlátai érvényesek.

A C11 visszajelzés sikeres commitja után a szerver megkísérli a bekötést. Ez külön tranzakció: ha a tanulási lépés hibázik, a már elmentett visszajelzés commitolt válasza megmarad, és a kapcsolat később újrapróbálható. Több időzítés bekötése forrásonként idempotens; egy részben sikeres frissítés újrafuttatható. A visszajelzési előzményeket nem görgetjük vissza egy későbbi tanulási hiba miatt.

A **Saját visszajelzés** kártya **Tanulási kapcsolat** részében látható a változat, az időbeli kontextus és az állapot. A „Tanulási kapcsolat frissítése” gomb a korábban mentett C11 visszajelzéseket is bekötheti, ha a szükséges edzésbizonyíték már rendelkezésre áll. A lap megnyitása csak olvas. Egy „bekötve” állapot nem jelenti, hogy már tanítottunk modellt, bizonyítottuk az edzés hatását vagy engedélyeztünk tervmódosítást.

## Tárolás és ellenőrzés

Új adatbázistábla, migráció vagy függőség nincs. A meglévő audit- és evidence-táblák szükségesek. A Polar-adatok, a forrás RPE, a C11 revíziók és a régi `AthleteResponse` sorok változatlanok.

A kapu izolált SQLite HTTP- és tudományos láncteszteket futtat, többek között a nulla/null különbségére, késői bevitelre, korábbi cutoffra, szöveges javításra, megváltozott megfigyelési napra, tulajdonosra, hashhibára, tanulási rollbackre, ismételt materializálásra és hiányzó response-projekció visszaállítására. A frontend a Pythonból előállított szintetikus választ is ellenőrzi. Külön DOM/JSDOM próbák, a teljes frontend tesztsor, TypeScript, ESLint és production build egészítik ki. A Windows asyncio belső socketpair-kivétele megmarad; a kapu nem ér el Polart, alkalmazásszervert vagy alkalmazás-adatbázist.
