# P2.4C8.1R1 — Személyes naptári időbecslés

A javítás a 06:00-kor kezdődő, csak távolsággal megadott 6 km-es edzés esetét kezeli. Hiányzó tervidő miatt korábban a későbbi munkakezdés is ugyanabba a figyelmeztető összesítőbe került, mint a valódi átfedés.

## Megjelenítés és forrás

Az egyszerű távos tervhez külön `duration_estimate` olvasási vetület készülhet. A kártyán `~` időtartam és becsült végidő jelenik meg; a részletekben a tartomány, a felhasznált megfigyelések száma és a saját teljesítésekre mutató hivatkozások látszanak. A referenciaeset 6 km / 33 perc 20 másodperces saját megfigyelése alapján a terv `~33 p`, 06:00–~06:33, 30–37 perces tájékozódási tartománnyal. A tényleges érték mindig az adott sportoló tárolt előzményeiből származik.

A `PlannedWorkout.duration_sec`, minden eredeti tervmező, a teljesítés és a szolgáltatói nyers adatok változatlanok. A megadott nulla időtartam sem válik ismeretlenné. Nincs migráció, új auditfajta, szolgáltatói lekérés, visszaírás vagy automatikus áthelyezés. A becslés nem kerül mért eredményként a tanulási / validációs folyamatokba, és nem ad terhelési döntési jogosultságot.

## V1 módszer

Séma: `calendar-duration-estimate-v0.1`; módszer: `personal_similar_distance_median_v1`.

- Csak pozitív, strukturált táv és hiányzó időtartam esetén. Nem olvasunk ki céltávot az edzés nevéből.
- Saját sportoló, azonos sportág; a céltáv 80–125%-a közötti mért táv. OTHER és STRENGTH nem kap táv/tempó becslést.
- Legfeljebb 90 napnyi előzmény, a lekérdezés és az adott tervezett kezdés közül a korábbiig befejezett mérésekkel. Ismeretlen kezdésnél a terv helyi napjának kezdete a konzervatív határ. Későbbi vagy még folyamatban lévő teljesítés nem becsüli vissza saját korábbi tervét.
- Érvényes kezdés/befejezés esetén az eltelt időt használjuk, a szünetekkel együtt. Máskülönben pozitív rögzített időtartam használható, külön forrásjelöléssel.
- A legutóbbi legfeljebb 12 megfelelő jelölt idejét a céltávra arányosítjuk; középértékük medián.
- Két, 1,75-szörösnél jobban eltérő jelöltből nem adunk becslést. Legalább három jelöltnél a mediántól `max(25% × medián, 3 × medián abszolút eltérés)` értéknél jobban eltérő idő kimarad a középértékből. A jelölt a forráslistában megmarad `used: false` jelöléssel; az eredeti megfigyelést nem töröljük.
- A felhasznált idők minimumának 90%-a és maximumának 110%-a adja a percenként kifelé kerekített tájékozódási tartományt. Ez alkalmazáspolitika, nem kalibrált statisztikai konfidenciaintervallum: `range_is_calibrated: false`.
- A teljes tartomány legfeljebb 24 óra. Összetett szakaszos, ismétléses vagy pihenős tervre nem vetítünk át egész edzésből származó tempót. Üres szakaszlista vagy egyetlen egyszerű, a teljes céltávot lefedő WORK távsza­kasz támogatható.

A tulajdonosra, sportágra és időszakra szűrt olvasás legfeljebb 4000 történelmi sort enged. Túllépéskor nem becslünk csendesen csonkolt történetből; az eredeti naptár továbbra is megjelenik. Az `as_of` az összehasonlítható mérések időbeli határa, nem történeti döntési vagy tartós elérhetőségi bizonylat. A vetület új szinkronizált / javított mérések alapján változhat.

## Ütközéskezelés

A naptár és a korlátok előnézete azonos becslési kódot használ. Ha a tartomány felső vége is a munkakezdés előtt van, arra nincs átfedési jelzés. A 06:35-kor kezdődő elfoglaltságnál a 30–37 perces tartomány már lehetséges átfedést jelez, kifejezetten becslésként. Az elfoglaltságon belüli ismert edzéskezdés továbbra is egyeztetendő.

Az edzésablakba illeszkedés a tartomány felső határát és a megadott perc- / napi kereteket használja; a becslési bizonytalanság elkülönül a megadott időhatároktól. Több edzés összesített napi terhelésére ez nem ad elfogadási döntést. Az előző napon induló, a látható napra átnyúló terv is vizsgálható, fél-nyílt határkezeléssel.

A konkrét átfedés, a becslés alapján lehetséges átfedés és az adathiány három külön csoportban látszik, az előnézetben is. A `PLAN_END_UNKNOWN`, `PLAN_TIME_UNKNOWN`, stb. semleges **Hiányzó időadat** összesítőt ad; önmagában nem tesz valódi ütközésikont az edzésre.

## Ellenőrzés

Az új backendtesztek lefedik a személyes 6 km-es példát, összehasonlíthatóságot, skálázást, szüneteket, kilógó időt, tulajdonosi szűrést, nulla / hiányzó adat különbségét, jövőbeli mérések kizárását, összetett tervek visszatartását, kereteket és éjfélen átnyúlást. Valódi izolált SQLAlchemy-olvasással ellenőrizzük a forrásadatok változatlanságát.

A frontend valódi szintetikus backend-válaszokat ellenőriz, és jelöli a becslés eredetét. A React DOM-próbák valódi FastAPI / ideiglenes SQLite folyamatból kapják az adatokat stdin/stdout hídon. A natív dialog JSDOM-helyettesítést kap; ez nem valós böngészős pixel- vagy Windows-teszt. A futási eredmények a javítócsomag ellenőrzési mellékleteiben találhatók.
