# C21.10.21.1 – Saját edzés foglalt időpontban

A kézzel felvett, másolt vagy módosított saját edzés menthető akkor is, ha munkával vagy más elfoglaltsággal ütközik, elérhetetlennek jelölt napra kerül, vagy meghaladja a megadott edzésablakot. A szerkesztő ilyenkor figyelmeztet, de nem kér külön felülbírálást vagy megerősítő pipát.

## Működés

- Az időponttal kapcsolatos figyelmeztetés a már betöltött, saját fiókhoz és időzónához tartozó naptári adatokból készül. Nem indít új tervezést vagy hálózati kérést.
- Ismert, átfedő elfoglaltságnál annak neve és az érintett nap jelenik meg. Az egymáshoz pontosan csatlakozó időszakok nem átfedések. Az éjfélbe nyúló elfoglaltság is felismerhető.
- Ha nincs ismert elfoglaltság, de a teljes edzésidő nem fér a sportághoz, helyszínhez és kezdéshez tartozó ismert keretbe, a felület a két időtartamot mutatja meg.
- Heti ismétlésnél külön jelzés készül minden, a betöltött naptári időszakba eső érintett napról. A be nem töltött időszakra vagy hiányzó időpontra nem állítunk bizonyított ütközésmentességet.
- A figyelmeztetés időpontváltáskor és szerkesztéskor frissül. A mentés engedélyezett marad; a többi tevékenységet nem írja át vagy törli.
- A szakaszokból és a köztes pihenőkből számított teljes idő foglalt időpontban is automatikusan növelhető. A felhasználó által megadott nagyobb teljes idő megmarad.

Az automatikus tervező továbbra is a megadott elérhetőségen belül keres edzést. A foglalt időpont kézi használata nem ad neki általános felhatalmazást az elfoglaltságok figyelmen kívül hagyására.

## Megmaradó ellenőrzések

A hibás időalak, az érvénytelen ismétlés, a támogatott 24 órát meghaladó edzés és a hiányos recept továbbra is javítást igényel. A már teljesített, lezárt vagy védett forrású edzés szerkesztését, a tulajdonos- és változatellenőrzést, valamint a bizonytalan mentések azonos kéréses újrapróbálását ez a módosítás nem lazítja.

Az API és az adatbázisséma változatlan. A naptár a mentett ütközést a meglévő konfliktusjelzésekkel továbbra is megmutatja.

## Ellenőrzés

A kézi szerkesztő regressziói külön ellenőrzik az ismert időkeretből túlnyúló, szabad szöveges, foglalt, éjfélbe nyúló és heti ismétlődő edzéseket, a hiányzó vagy idegen naptári adatokat, illetve az érvénytelen időtartamokat.

Valódi FastAPI-val, izolált adatbázisban és React StrictMode alatt mentett munkabeosztással is kipróbáltuk az ütköző saját edzés felvételét, heti ismétlését, módosítását és másolását. A próba ellenőrzi, hogy megmarad a munkabeosztás és a naptári konfliktus, nincs külön megerősítő pipa vagy új hálózati kérés az időpont helyi ellenőrzéséhez, és a közben rögzített teljesítés továbbra is megakadályozza az edzés felülírását.

A teljes frontend-regresszió, a Next típuskészítés, a TypeScript, az ESLint és az éles build a `python tools/run_c21_10_21_checks.py --frontend-only --full-frontend` paranccsal futtatható. Változatlan backend mellett nem szükséges újrafuttatni a korábban sikeres backendkaput. Natív Windows-próba nem történt.
