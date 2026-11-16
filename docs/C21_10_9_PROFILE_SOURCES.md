# C21.10.9 — profilfrissítés és az erőreferenciák használhatósága

A C21.10.8 utáni képen a helyszíni összehasonlítás már megfelelő volt, az erősítést a `PROFILE` forrásváltozás blokkolta. A képernyőkép a konkrét profilmezőt még nem nevezte meg.

## Javítás

A profil forrásválasztásából kivettük azokat a mezőket, amelyek aktuális tervezési adatot jelentenek, de nem módosítják a korábban megfigyelt gyakorlatot és sorozatot: általános eszközlista, időtartam–iram beállítás, profilmegfigyelések, vizsgált forrásidőszak és kiválasztott adatforrások. A sportelőélet és rendelkezésre álló idő már korábban is ebbe a csoportba tartozott.

A tervező továbbra is az aktuális profilt és aktuális lehetőségeket használja. A konkrét erősítőhelyszín és felszerelés ellenőrzése megmarad; az általános eszközlista frissítése nem teszi elavulttá az ugyanazon helyszínen mért erőeredményeket. A mérési dátum, forrásnyugta, gyakorlat, súly, ismétlésszám és sorozat változatlan.

Az egészségi és mozgási korlátozások, a részvételi állapot, kihagyás utáni visszatérés, hozzáférési igények, állapotmegjegyzések és testadatok továbbra is lényegesek. Ezek változása nem válik automatikusan engedélyezetté. A profil verzióláncát is ellenőrizzük: egy közbenső lényeges változást nem töröl egy későbbi, az eredetivel ismét megegyező profilérték. Ilyenkor külön jelzés segíti a felülvizsgálatot.

## Mit mutat a felület?

A naptári mezociklusablak Maximális erő céljánál és az erőfelmérési összegzésben megjelenik a változott profilmező neve. A felülvizsgálandó mezők külön szerepelnek az egyéb frissítésektől. Például a „Testtömeg” vagy a „Regenerációs és állapotra vonatkozó megjegyzések” már megnevezhető ok; a teljes személyes értéket vagy megjegyzést nem másoljuk a naptári ciklusvégpont válaszába.

A mentett erőfelmérési válaszok közvetlen hivatkozással nyithatók meg. A válaszok és friss források áttekintése, majd mentése önmagában nem ír elő új fizikai tesztet. A tényleges újramérés szükségességét az állapot és a gyakorlatreferenciák határozzák meg, nem egy adatforráslista módosulása.

## Bizonyíték és visszamenőleges olvasás

A `training-plan-policy-v0.13` külön aktuális profilnyugtát és szükség esetén külön profilforrás-nyugtát is ad a felülvizsgálathoz. A `strength-profile-comparison-v0.1` a változott és lényeges mezők neveit, a forráshivatkozás eltérését és az átvétel lehetőségét rögzíti. A böngésző a nyugtákból önállóan újraszámolja ezt, ellenőrzi a tulajdonost, az időbeli elérhetőséget, a forráshivatkozásokat és az aktuális profil teljes tartalmát.

A régebbi felülvizsgálatok a korábbi összehasonlítási szabályukkal olvashatók. A történeti felmérések és forrásnyugták nem módosulnak. A C21.10.8 időbeli elosztása és a naptár színei megmaradnak.

Ellenőrzések: valódi API-felülvizsgálatok aktuális eszközlista, forrásidőszak, megfigyelések és kiválasztott források változtatása után; ismételt elfogadás; tényleges egészségi, testadat- és közbenső állapotváltozás; régi sorozatok változatlan átvétele kézi felülvizsgálatkor. A felületi ellenőrzés tartalmazza az önálló bizonyítékellenőrzést, manipulált profiladatok elutasítását és a konkrét mezőnevek megjelenítését.

Telepítés után a backend és frontend újraindítása, **Ctrl+Shift+R**, majd **Terv frissítése most** szükséges. A telepítés nem módosít adatbázist. Ellenőrző kapu: `python tools/run_c21_10_9_checks.py`.
