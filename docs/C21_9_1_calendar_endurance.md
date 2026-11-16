# C21.9.1 – Visszavont tervek és nappali állóképességi lehetőségek

A frissítés a C21.9-re épül. A tervező által visszavont edzések megmaradnak a történetben, de nem jelennek meg aktív tervként a naptárban. A napfénykorlát a ritkán elérhető edzésnapok rangsorolásában is érvényesül, ezért egy megadott nappali kajaklehetőséget nem foglalhatnak el előre az összesített keretből a könnyebben elhelyezhető esti saját erősítőtervek.

## Javítások

1. A naptári feed nem küld vissza `CANCELLED` státuszú tervet az aktív edzések között. A böngésző az esetleg korábban kapott ilyen sorokat sem rajzolja ki. A sorok és elfogadási bizonylataik nem törlődnek az adatbázisból; a teljesítések önállóan megmaradnak.
2. A napok rangsorolása a sportághoz megengedett fényintervallumot, a mintához szükséges minimális időt és a napi/ablak-perckeretet is ellenőrzi. Az esti kajakablak nem számít nappali kajaklehetőségnek a ritkaság meghatározásakor.
3. Aktív, támogatott sportágra vonatkozó napfénykorlátnál a teljes szerkeszthető horizont újraértékelődik. A korábbi, cserélhető saját erősítőtervek nem foglalják le előre az összes jövőbeli alkalmat. Az azonos újraértékelt jelöltek megőrződnek; ismételt frissítés nem hoz létre újabb példányokat.
4. A külön szerkesztett, külső, jóváhagyott és teljesített edzések védelme megmarad. A kihagyottnak jelölt alkalmak megőrzik az eredeti tervezési keretüket. A gördülő heti keret, a ciklusszakasz kerete és a 36 órás meglévő kezdési távolság változatlan. Ez a javítás nem emeli automatikusan az edzésszámot vagy a terhelést.
5. A sportági összegzés megmutatja a megadott lehetőségek, az idő- és fényablakba férő napok, a tényleges jelöltnapok és a saját javaslatok számát. A felületen a **Miért ezek az edzések?** lenyitás magyarázza a kimaradást. A megfelelő időablak nem fiziológiai terhelhetőségi igazolás.
6. A futáshoz továbbra is szükséges a jelenlegi mintának megfelelő saját futóelőzmény. A kajak vagy az erősítés időtartama nem válik futóreferenciává. Ha ez hiányzik, külön magyarázat jelenik meg.
7. Az úszáshoz, kerékpározáshoz és más, még nem támogatott sporthoz nem állítunk kész edzésgenerátort. Ha ilyen lehetőség szerepel a megadott órarendben, a felület kimondja, hogy az automatikus edzésminta még hiányzik. A jelenlegi automatikus családok: kajak, futás, erősítés.

## A mentett erőfelmérés forrása

A C21.9 már megőrizte a felmérés forrását a kizárólag koordinátákat/napfénykorlátot érintő mentéseknél. A böngésző egyik ellenőrzése viszont még az aktuális teljes beállításbizonylattal követelt azonos referenciát. Ez a jogosan megőrzött, korábbi fizikai helyszínforrást is elutasíthatta.

A friss ellenőrzés a saját, hitelesen visszaolvasott bizonylatokat hasonlítja össze. Csak a `coordinates`, `daylight_overrides` és a felső szintű `daylight_rules` mezőket hagyja ki a fizikai összehasonlításból. A név, helyszínazonosság, felszerelés, gyakorlatmegerősítések, sportlehetőségek, heti órarend, kivételek és minden más korábbi mező egyezése továbbra is szükséges. A bizonylat tulajdonosát, lenyomatát, forrásreferenciáját, revíziós sorrendjét és a capture előtti elérhetőségét is ellenőrzi.

Aktív napfényadatcsomagnál a legfrissebb bizonylat már része a tervezési bemenetnek. Kizárólag koordinátát módosító mentésnél a szükséges aktuális bizonylat külön kerül a forrásevidenciába. A régi felmérés és a történeti bizonylatok tartalma változatlan.

## Elveszett visszajelzés

Az automatikus futtatás proxyjának határideje 60 helyett 180 másodperc. Az időtúllépés külön `GOAL_API_TIMEOUT` hibakódot kap, az elérhetetlenség marad `GOAL_API_UNAVAILABLE`. A korábban látott elérhetetlenség pontos élő okát a tesztkapunapló nem bizonyította; a hosszabb határidő nem helyettesít egy működő backendkapcsolatot.

Hálózati hiba után a felület visszaolvassa a mentett automatikus állapotot. Nem küldi újra automatikusan az írást. Ha már új, sikeres futási bizonylat jelent meg, frissíti a naptárt és elengedi a korábbi időtúllépési üzenetet. Változatlan vagy nem olvasható állapotnál a bizonytalanság látható marad.

## Használat

Mindkét kiszolgáló újraindítása után **Naptár → Terv frissítése most**. A már visszavont régi sorok a naptár újraolvasásakor eltűnnek az aktív nézetből. A friss tervezés a megadott nappali időablakokhoz igazodik. Nem talál ki olyan nappali lehetőséget, amely az órarendben nincs megadva.

Új erőfelmérés, böngészőadat-törlés és adatbázis-migráció nem szükséges. A frissítő kizárólag forrásfájlokat módosít; nincs új csomagfüggőség.

## Ellenőrzés

A backend regresszió és a frontend regresszió a `tools/run_c21_9_1_checks.py` kapuban fut, route-típusgenerálással, TypeScripttel, az érintett fájlok ESLint-ellenőrzésével és production builddel. Az új tényleges API-folyamatok ellenőrzik a hétköznap esti és hétvégi nappali lehetőségek közös elhelyezését, a meglévő erősítőtervek újraosztását, a visszavont tervek megőrzését és naptári elrejtését, a védett/mulasztott kereteket, az ismételt futásokat és a koordinátamentés utáni forráskötést.

React StrictMode + valódi FastAPI + naptári `PeriodGrid` folyamatban a frissítés után a régi esti kajak eltűnt, nappali kajak és futás is szerepelt az erősítés mellett. A sikeres szervermentés után szimulált elveszett válaszból a felület újabb írás nélkül állt helyre. Natív böngészős képernyőképes ellenőrzés nem készült.
