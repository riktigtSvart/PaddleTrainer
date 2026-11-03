# C18.4R1 — Konkrét profilindokok és azonosítható teljesítések

A valós felületi próbán a tervező általános „sportolói felmérést ki kell
egészíteni” üzenetet mutatott hét napon át, miközben az értékelés már
tartalmazta a részletes `entry_review` állapotot és indokkódokat. A teljesítési
lista a teljesített edzéseknél pusztán státuszokat ismételt.

## Javítás

- A **Mi állítja meg a tervkészítést?** blokk megjeleníti az adott értékelés
  tényleges profilindokait és a hozzájuk tartozó mezőket. A felmérés közvetlen
  linkkel megnyitható; mentés után újraértékelés kérhető.
- A hiányzó profil, a hiányos mező, a kifejezett szünet, a szakmai felülvizsgálat
  és az alkalmazkodást igénylő keret külön magyarázatot kap. Az adaptált profil
  akkor is értelmezhető, ha a korábbi általános indoklista üres.
- Az azonos ok miatt javaslat nélkül maradó napok egy dátumtartományba kerülnek;
  a széttagolt napokat a megjelenítés nem tünteti fel összefüggő tartományként.
- A teljesítések és lejárt tervek státuszcsoportokban, darabszámmal látszanak.
  Az egyes edzések helyi dátummal és idővel, névvel vagy ismert sportnévvel,
  valamint a részletes edzéshez vezető hivatkozással jelennek meg.
- A C18.1 olvasási pillanatkép a tárolt edzésnevet is átadja. Az eseményekhez
  név, sport, kezdőidő és helyi nap kerül. Név nélküli, kapcsolt teljesítésnél
  a kapcsolt terv címe a tartalék megnevezés.
- A korábban mentett értékelések a saját rögzített forrásaikból kapnak dátumot
  és nevet/sportot; a megjelenítés nem igényli a korábbi auditok átírását.

A tervkészítési feltételek, a dózisok, az elfogadás és a kihagyás kezelésének
szabályai változatlanok. Az R1 a tényleges blokkoló okot láthatóvá teszi;
hiányzó személyes adatot nem talál ki, és nem ad automatikusan terhelési engedélyt.

A javítás a telepített C18.4 fájljaira épül. Új migráció és függőség nincs.
A meglévő GET pillanatképséma bővítése additív; a régi bizonylatok olvashatók.
Friss forrásból történő újraértékelés új hash-t adhat az edzésnevek és az
eseményazonosító adatok miatt, ezért egy régi, megnyitott javaslatot mentés
előtt újra kell értékelni.

## Ellenőrzés

A C18-as célzott tesztkapu: 80 backend- és 57 frontendteszt, Next típusgenerálás,
TypeScript és ESLint. A régi profilkapu és mentési invariánsok is megmaradnak.
A megjelenítési tesztek hiányos profilokat, adaptált keretet, régi bizonylatot,
név nélküli teljesítést, HTML-ként nem értelmezhető megjegyzéseket és hét
ismételt indok összevonását ellenőrzik.

PowerShell-szkriptek futtatási engedélyétől függetlenül indítható tesztkapu:

```powershell
Set-Location 'C:\Users\gyula\OneDrive\Dokumentumok\PaddleTrainerProject'
& .\.venv\Scripts\python.exe .\tools\run_c18_4_checks.py
```

Sikeres zárósor: `C18.4R1 TESZTKAPU OK`. A futtató a backend parancsokat az
`apps/api`, a frontend parancsokat az `apps/web` mappában indítja, az első
hibánál megáll. A korábbi `.ps1` tesztkapu megmarad.
