# Local Transcripter

készítette: szarkabalint.hu

Ingyenes, MIT licencű macOS-alkalmazás magyar és angol hangfelvételek helyi átírásához. A Whisper large-v3 modellt MLX-szel, az Apple GPU-n futtatja. A hangot és a leiratot nem küldi felhős feldolgozásra.

## Követelmények

- Apple Silicon Mac; Intel Mac nem támogatott.
- macOS 27.0 vagy újabb.
- Legalább 8 GB szabad tárhely a modellhez és a helyi futásokhoz.
- Internet az egyszeri modellletöltéshez; utána az átírás offline is működik.

A kipróbált gép Apple M5, 32 GB memória, macOS 27.0.1. Más hardveren a feldolgozás ideje és memóriaigénye eltérhet.

## Letöltés és telepítés

A Local Transcripter DMG-telepítője a [GitHub kiadásoknál](https://github.com/szarkab/local-transcripter/releases/latest) tölthető le.

1. Nyisd meg a `Local-Transcripter-0.4.1-apple-silicon-local.dmg` fájlt.
2. Húzd a **Local Transcripter** alkalmazást az **Applications** mappába.
3. Indítsd el a bemásolt appot, majd válaszd le a DMG-t.
4. Első használatkor a felületen töltsd le a kb. 3,2 GB-os alapmodellt. Az opcionális beszélőmodellek további kb. 108 MB-ot foglalnak.

A jelenlegi 0.4.1-es DMG még nincs Apple-notarizálva, ezért a macOS első indításkor figyelmeztetést adhat. A sikertelen indítás után a **Rendszerbeállítások → Adatvédelem és biztonság → Megnyitás mindenképpen** lehetőséggel nyitható meg. [Apple útmutató](https://support.apple.com/en-us/102445)

## Használat

1. A **Felvétel nyelve** mezőben válassz **Magyar** vagy **Angol** értéket. Minden új indításkor Magyar az alapérték; a választás az adott használat alatt megmarad.
2. Válassz M4A-, MP3- vagy WAV-hangfelvételt. A választott nyelv a felvétel fő nyelve legyen; az app nem fordítja le az elhangzott beszédet.
3. Igény szerint kapcsold be a **Beszélők elkülönítése** checkboxot. A létszámbecslés automatikus.
4. Kövesd az aktuális feldolgozási lépést és felismeréskor a feldolgozott hangidőt. A **Megszakítás** leállítja a munkát; részleges leirat nem menthető teljesként.
5. Válassz **TXT** vagy **Markdown** formátumot, majd mentsd a leiratot.

Az új ablak külön mutatja a beállításokat, a hangfelvételt és a feldolgozás állapotát. A fejlécben és az appikonon hangbuborékjel látható. A felület a macOS saját megjelenését használja.

Az export UTF-8 szöveg, időbélyegekkel. A felismert szöveget nem fogalmazza át. A beszélők névtelen címkéket kapnak. Az elakadt felismerés legfeljebb egyszer indul újra; szöveges ismétlésgyanú nem indít újabb teljes átírást és nem töröl elhangzott ismétlést. A választó nem ígér megbízható mondatonkénti nyelvváltást vegyes nyelvű hangon.

## Adatkezelés és korlátok

A modell-előkészítés nyilvános Hugging Face és Sherpa-ONNX letöltést végez, bejelentkezés és API-kulcs nélkül. Nincs beépített analitika vagy felhős tartalék.

A `~/Library/Application Support/Helyi leirat/` mappában találhatók a modellek és a futások. A Local Transcripter a korábbi néven létrehozott mappát tovább használja, így a névváltás nem igényel új modellletöltést. A `runs/` mappa hangmásolatokat, leiratokat és helyi naplókat őriz; tartalma személyes adat lehet és nem törlődik automatikusan. Bezárt app mellett a már nem szükséges futások törölhetők, miután a kívánt exportokat elmentetted. A `models/` törlése új modellletöltést igényel. A frissítés megőrzi ezeket az adatokat.

A felismerés hibázhat: félrehallás, kihagyás, kitalált szöveg és pontatlan időbélyeg is előfordulhat. A beszélőcímkék becsült hangcsoportok. Az ellenőrizendő szó és egyszerre beszélés jelölése kísérleti segítség; hiánya nem bizonyít hibátlan leiratot. Megbízható automatikus érthetetlenség-felismerés nincs. Fontos tartalomnál hallgasd vissza a hangot.

## Licenc

A saját forráskód [MIT licencű](LICENSE). A csomagolt könyvtárak és külön letöltött modellek a saját licenceik alatt maradnak; részletek: [THIRD_PARTY.md](THIRD_PARTY.md). Az FFmpeg LGPL-2.1-or-later licencű; eredeti forrása és fordítási receptje az app **Licencek és források…** menüjéből is elérhető.
