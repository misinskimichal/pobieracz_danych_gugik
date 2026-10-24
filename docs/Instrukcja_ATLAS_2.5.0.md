# NMT i NMTP ściągacz 2.5.0 — WMS do lokalnej ortofotomapy i czytelnego 3D

Wydanie z 24 października 2026 r. [Pobierz ZIP do QGIS](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-2.5.0.zip). Instalacja: **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP**, następnie restart QGIS.

ZIP: 142775 bajtów; SHA-256: `72d18ef6bbd4896eb6ef3b219251005e4eac991357b26419aaab9c47a40ec581`.

## Wnioski z dostarczonego raportu

Raport zakończył się stanem `completed`, bez błędów eksportu zdjęcia. Zapisał podgląd 2048×2048 o pełnym pokryciu i zróżnicowanych barwach. Scena NMPT zawierała 2000 symboli koron oraz 20 brył budynków; pięć obrysów zostało pominiętych. To potwierdza przygotowanie tych danych, ale sam JSON nie zawiera pikseli ani stanu przeglądarki i nie rozstrzyga wyglądu konkretnego HTML.

Poprzednia wersja używała tego samego pojedynczego obrazu 2048 do mapki oraz całego modelu. Na kole o promieniu 1 km dawało to około 1 m/px. Przy niskiej kamerze obraz był mocno rozciągany, także na stromych zboczach powierzchni koron. Brak mipmap/anizotropii i dodatkowe cieniowanie pogarszały czytelność. Ciągła powierzchnia NMPT przykrywała część osobnych symboli drzew. Wydanie 2.5.0 zmienia oba mechanizmy; nie przypisuje nieudostępnionemu HTML błędu GPU bez dowodu.

## Jak użyć swojego WMS

1. Wczytaj poprzedni `report.json` we wtyczce. Zachowaj cały folder atlasu z modelami NMT/NMPT.
2. Wybierz **Wybrana warstwa rastrowa QGIS** oraz swoją ortofotomapę. Obsługiwane są WMS/WMTS/XYZ renderowane przez QGIS oraz rastry lokalne. Alternatywą pozostaje Geoportal online. Nie musisz sam pobierać dodatkowego rastra.
3. Ustaw **Zdjęcie WMS → lokalne kafle**. Domyślny cel to **0,25 m/px**, do wyboru także 0,10 / 0,50 / 1 m/px. Program pokazuje rzeczywistą rozdzielczość zapisanego obrazu. Dla bardzo dużego zasięgu lub celu 0,10 m/px budżet 64 MP może wymagać rzadszego obrazu; mniejszy promień samej sceny pozwala zachować większą szczegółowość.
4. Pozostaw lub wskaż warstwy lasów, punktów drzew i obrysów budynków. Limit ilustracyjnych koron lasów wynosi 2000 / 5000 / 10000, domyślnie 5000. Zwiększenie limitu nie zamienia próbek w inwentaryzację drzew.
5. Kliknij **Odśwież samą scenę 3D / ortofotomapę** lub **Scena 3D**. Zostaną wykorzystane istniejące modele, a zdjęcie zostanie pobrane przez WMS/WMTS i zapisane lokalnie. Status podaje model, numer obrazu i rozdzielczość. Renderowanie oraz końcowy zapis działają w tle; mapy widoczności nie są liczone ponownie.
6. W HTML wybierz **Zdjęcie z góry**, aby ocenić dopasowanie i rzeczywiste kolory zdjęcia na modelu. Potem kliknij mapkę, skąd chcesz patrzeć z oczu. **Cieniuj zdjęcie** jest domyślnie wyłączone; barwy zdjęcia nie są dodatkowo przygaszane sztucznym światłem.
7. **Pokaż korony zamiast powierzchni lasu** jest domyślnie włączone, jeśli istnieją korony i maska lasu. Wyłącz ten checkbox, aby porównać pełny NMPT. **NMT + obiekty BDOT** nadal pozwala obejrzeć wszystkie uproszczone bryły nad samym gruntem.

Sama aktualizacja ZIP nie zmienia wcześniejszego HTML ani już otwartej karty. Scenę trzeba odświeżyć we wtyczce. Użytkownik nie musi pobierać ponownie NMT/NMPT wyłącznie na potrzeby poprawy zdjęcia.

## Co zostaje zapisane lokalnie

| Plik | Zastosowanie |
|---|---|
| `ortofoto_NMPT/kafel_NNN.png` | Pełna rozdzielczość obrazów, do 64/model; analogiczny folder NMT. |
| `*.pgw`, `*.png.aux.xml` | Georeferencja i EPSG:2180 pojedynczych obrazów. |
| `ortofoto_NMPT.vrt` | Lokalna mozaika wszystkich poprawnych kafli do otwarcia w QGIS; analogicznie NMT. |
| `tekstura_NMPT.png` | Podgląd do 2048 px dla mapki i awaryjnego wyświetlania; nie jest pełną rozdzielczością zdjęcia. |
| `scena_3d_NMPT.html` | Samodzielny HTML zawierający kopię zdjęcia i szczegółowych kafli. |
| `report.json` | Rozdzielczość, rozmiar mozaiki, ścieżki kafli, braki i przyczyny. |

Przycisk **Dodaj pobraną ortofotomapę do QGIS** dodaje mozaikę VRT jako lokalny raster. Zachowaj VRT razem z folderem PNG i plikami towarzyszącymi; ścieżki w VRT są względne, więc cały zestaw można przenieść razem. HTML ma własną kopię obrazów i po ukończeniu eksportu nie potrzebuje zapytań WMS. Dostęp do sieci jest potrzebny podczas przygotowania zdjęcia z usługi.

Cel eksportu 0,10 czy 0,25 m/px nie gwarantuje takiego natywnego GSD fotografii. Dowolny WMS może udostępniać starsze, rzadsze lub inaczej przetworzone zdjęcie. Nie dokładamy sztucznej informacji przestrzennej. Przy 2 km szerokości i celu 0,25 m/px mozaika może mieć około 8000 pikseli na bok zamiast poprzednich 2048, o ile źródło dostarcza odpowiedni szczegół. Budżet obrazu nie zwiększa liczby wierzchołków modelu — rzeczywisty krok 3D nadal podaje nagłówek sceny.

## Dlaczego drzewa są teraz widoczne

W 2.4.0 osobne korony mogły znajdować się wewnątrz ciągłej powierzchni lasu z NMPT. Nowy wariant prezentacji zastępuje tę powierzchnię gruntem **tylko w masce wybranych lasów**, a nad nim rysuje korony o wysokościach NMPT−NMT. Pozostała powierzchnia NMPT, w tym zabudowa poza lasem, pozostaje widoczna. Wyłączenie symboli lub wariantu lasu przywraca pełny model. Oryginalne tablice wysokościowe nie są zmieniane, otwory NoData pozostają otworami, a ustawienie oka nadal sprawdza oryginalny NMPT.

To umowna prezentacja roślinności. Rozmieszczenie koron z poligonów lasu nie odpowiada pojedynczym zmierzonym drzewom; szerokość i kształt koron są ilustracyjne. Odstępy między symbolami nie potwierdzają prześwitów ani widoczności przez las. Wynik rastrów widoczności pozostaje oparty na wybranym modelu obliczeniowym. Dokładne drzewa, elewacje i prześwity wymagają dodatkowych danych LAS/LAZ/LoD2/mesh, zgodności terminów oraz osobnego modelowania.

## Rozwiązania techniczne i Qgis2threejs

Przejrzano [wskazany fork Qgis2threejs](https://github.com/misinskimichal/Qgis2threejs) na rewizji `922f1663e4767361fc98205d005ac63c8cfaa447`, szczególnie:

- [ImageManager](https://github.com/misinskimichal/Qgis2threejs/blob/922f1663e4767361fc98205d005ac63c8cfaa447/core/build/datamanager/image.py): renderowanie warstw QGIS do obrazów o konkretnym zasięgu i rozmiarze.
- [Materiały](https://github.com/misinskimichal/Qgis2threejs/blob/922f1663e4767361fc98205d005ac63c8cfaa447/web/src/material.ts) i [bloki DEM](https://github.com/misinskimichal/Qgis2threejs/blob/922f1663e4767361fc98205d005ac63c8cfaa447/web/src/layer/demlayer.ts): obraz przypisany do materiału poszczególnego bloku.
- [Ustawienia renderera](https://github.com/misinskimichal/Qgis2threejs/blob/922f1663e4767361fc98205d005ac63c8cfaa447/web/src/app.ts): dostosowanie filtrowania anizotropowego do urządzenia.

Te wzorce zastosowano we własnym kodzie, bez dodawania zależności od instalacji Qgis2threejs ani serwera/CDN. Nie zastąpiono całego renderera biblioteki Three.js. Mipmapy i dostępna anizotropia poprawiają oglądanie tekstury pod małym kątem. Każdy blok jawnie wiąże teksturę i otrzymuje transformację UV z georeferencji; obrazy są ładowane po cztery. Obrazy o wymiarach niebędących potęgą dwóch są przeskalowywane do zgodnych wymiarów bufora GPU; ich zasięg geograficzny pozostaje ten sam.

`scene_imagery.py` planuje do 8×8 bloków na granicach komórek siatki; każdy ma do 1024×1024 px, łącznie do 64 MP/model. `scene_texture.py` używa asynchronicznego renderera QGIS z oczekiwaniem na kafle. Korekta do dokładnego zasięgu usuwa różnicę wynikającą z dopasowania proporcji obrazu przez `QgsMapSettings`. Końcowe składanie mapki i HTML działa w `QgsTask`. W trybie Geoportalu blok WMS jest pobierany w EPSG:3857 i przeliczany do dokładnego EPSG:2180.

Awaria jednego obrazu nie zatrzymuje pozostałych. Braki trafiają do `details[].texture_tile_errors`, podsumowania QGIS oraz informacji w HTML. Błędy przeglądarki można zapisać przyciskiem **Zapisz diagnostykę widoku** do `diagnostyka_widoku_3d.json`; zawiera liczbę odczytanych kafli, błędy WebGL, tryb powierzchni i stany przełączników. JSON końcowy QGIS nie zastępuje tej diagnostyki przeglądarki.

## Weryfikacja

83 testy Python/QGIS. Nowe testy sprawdzają limit i podział obrazów na granicach siatki, lokalną mozaikę z prawidłowym CRS/pikselami/alfą, przenoszenie całego zestawu do innego folderu, limit koron, a także **wybraną warstwę WMS** z serwerem GetCapabilities/GetMap. Serwer celowo uszkadza jeden obraz: reszta jest zapisywana, brak raportowany, a mozaika ma większą rozdzielczość niż podgląd 2048. Wykonano też rzeczywiste pobranie i reprojekcję bloku 1024×1024 z publicznego WMS GUGiK.

Trzy zestawy testów JavaScript sprawdzają geometrię, sterowanie i brak modyfikacji oryginalnych wysokości/otworów podczas prezentacji lasów. Shadery zostały skompilowane i połączone w rzeczywistym OpenGL ES. **Dodatkowo wykonano pełny test w prawdziwym Chromium/WebGL (SwiftShader)**: 16 szczegółowych obrazów załadowanych, 0 błędów GL i 0 wyjątków JavaScript. Włączenie/wyłączenie zdjęcia w widoku z oczu zmieniło ponad 160 tys. pikseli obrazu; sprawdzono również przywracanie zdjęcia, tryb koron i widok z góry.

[Przykład z poziomu oczu](examples/atlas_2.5.0/widok_z_oczu.png), [widok z góry](examples/atlas_2.5.0/zdjecie_z_gory.png) i [samodzielny HTML](examples/atlas_2.5.0/scena_3d_NMPT.html) używają w całości syntetycznych modeli i tekstury pól. Są rzeczywistymi zrzutami renderowania testowej przeglądarki, nie projektem użytkownika. Załączony raport oraz geometrie użytkownika nie są publikowane.

Środowisko: QGIS 3.40.6 / Qt5 / GDAL 3.10.3 / Linux. Weryfikacja nie obejmuje Windows/macOS ani konkretnej przeglądarki użytkownika. Przeglądarka może ograniczyć maksymalny rozmiar tekstury; poszczególne obrazy są do niego dostosowywane, a stan można sprawdzić w diagnostyce. Pełne zasady analizy i wcześniejsze funkcje opisują [dokumentacja](NMT_i_NMTP_sciagacz_dokumentacja_i_rozwoj.md) oraz [instrukcja 2.4.0](Instrukcja_ATLAS_2.4.0.md).
