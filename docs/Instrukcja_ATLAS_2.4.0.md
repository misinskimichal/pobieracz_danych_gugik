# NMT i NMTP ściągacz 2.4.0 — ortofotomapa, budynki i drzewa w 3D

Wydanie z 24 października 2026 r. [Pobierz ZIP do QGIS](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-2.4.0.zip). Instalacja: **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP**, następnie restart QGIS.

ZIP: 135935 bajtów; SHA-256: `8b4d271f9ecee3164863fef7441e29fea3ab10c8e00b810592a388762fa41682`.

## Co wynikało ze zrzutu ekranu

Zdjęcie było widoczne na mapce, komunikat potwierdzał jego wczytanie, a paleta modelu wskazywała „Pokrycie / BDOT”. W 2.3.1 wybranie tej palety wyłączało teksturę na modelu; komunikat nie odróżniał dekodowania zdjęcia od jego używania w 3D. W tej wersji można było ręcznie wrócić do „Kolory → Tekstura mapy”. W 2.4.0 przełącznik zdjęcia jest oddzielny od palety.

„0 symboli drzew” oznaczało brak dodatkowych symboli, nie brak wysokości roślinności w NMPT. Ciągła powierzchnia NMPT pokazuje dachy i korony jako wypukłości, bez rozpoznawania domów oraz pojedynczych drzew. Wcześniej nie było generowania osobnych brył budynków.

## Aktualizacja istniejącego atlasu

1. Po zainstalowaniu ZIP i restarcie otwórz wtyczkę. W razie potrzeby **Wczytaj poprzedni atlas · report.json**. Zachowaj cały folder atlasu z modelami.
2. Wybierz warstwę ortofotomapy, która działa w QGIS, albo źródło Geoportal online.
3. Opcjonalnie w ustawieniach sceny wskaż **Lasy / zadrzewienia**, **Drzewa — punkty** oraz nowe pole **Obrysy budynków do brył 3D (nie działki)**. Mogą to być warstwy BDOT10k lub własne warstwy o właściwej geometrii i CRS. Program nie pobiera ich automatycznie i nie rozpoznaje obiektów ze zdjęcia.
4. Kliknij **Odśwież samą scenę 3D / ortofotomapę** albo **Scena 3D**. Przy starszej wersji lub zmianie ustawień scena aktualizuje się przed otwarciem. Widoczność nie jest liczona ponownie; odczytujemy zapisane modele. Sieć może być użyta do samego zdjęcia.
5. W HTML sprawdź **Ortofotomapa na modelu**. Powinien być stan **NAŁOŻONA NA MODEL 3D**. Paleta wysokości/pokrycia nie wyłącza zdjęcia. **Pokaż ortofotomapę** przywraca je jednym kliknięciem.
6. Przejdź do sceny **NMPT**. **NMT + obiekty BDOT** wyłącza ciągłą powierzchnię NMPT, zachowując zmierzone wysokości uproszczonych brył nad gruntem NMT. Dzięki temu symbole nie chowają się wewnątrz powierzchni. Włącz **Powierzchnia NMPT**, aby wrócić do modelu powierzchni. Osobne checkboxy ukrywają symbole drzew i bryły budynków.
7. Kliknij mapkę, aby wybrać miejsce patrzenia z poziomu oczu. Zasady sterowania opisuje [instrukcja 2.3.0](Instrukcja_ATLAS_2.3.0.md). Kamera przy widocznych obiektach nadal sprawdza oryginalną powierzchnię NMPT, aby nie ustawić oka wewnątrz dachu/korony.

Mapa w rogu ma niezależny podgląd zdjęcia. Stan **WYŁĄCZONA NA MODELU** oznacza wyłączony checkbox zdjęcia, nawet jeśli mapka nadal je pokazuje. Gdy zapisano PNG, można je otworzyć z formularza QGIS lub pobrać z HTML. Eksport i błędy WebGL pozostają diagnozowane jak w [2.3.1](Instrukcja_ATLAS_2.3.1.md).

## Skąd biorą się budynki

Używamy wyłącznie wybranych obrysów budynków. Osobne pole zapobiega użyciu działki jako obrysu domu. Dla każdego poligonu odczytujemy próbki NMT i NMPT wewnątrz obrysu; próbki dziedzińca są wykluczone. Minimum NMT jest podstawą, maksimum NMPT wysokością płaskiego dachu. To prosty model prezentacji: nie odtwarza spadków dachu, elewacji, okien ani konstrukcji. Maksimum może obejmować komin lub drzewo nad dachem. Różnice terminów pozyskania warstw mogą powodować niezgodność.

Dach jest dzielony na trójkąty przez `QgsTessellator`, z zachowaniem wklęsłości i otworów. Zdjęcie jest nakładane na dach według tych samych współrzędnych co teren; ściany mają neutralny kolor, ponieważ zdjęcie z góry nie zawiera ich fotografii. Przesunięcie dachu o 5 cm jest wyłącznie zabiegiem rysowania przeciw migotaniu pokrywających się powierzchni.

Obiekty są pomijane, jeśli nie mieszczą się w kole/modelu, są niepoprawne geometrycznie, nie mają dostatecznych próbek lub różnicy wysokości 2–150 m. Wymagamy poprawnych wysokości dla co najmniej 80% próbek poligonu. Nie dopisujemy umownych wysokości do braków. Limit podglądu: do 500 części budynków, do 512 punktów obrysu jednej części. Próbkowanie bardzo dużego pojedynczego obrysu jest ograniczone do około 256 punktów na bok; może nie uchwycić drobnego szczegółu. Warstwa powinna zawierać budynki, nie dowolne poligony.

## Skąd biorą się drzewa

Gdy wybierzesz punkty drzew, każdy poprawny punkt uzyskuje wysokość z różnicy NMPT−NMT. Obiekty poza kołem, z brakami lub różnicą spoza 2–80 m są pomijane. Nie zakładamy, że każde drzewo ma tę samą wysokość. Korona jest uproszczoną zaokrągloną bryłą, a jej szerokość jest ilustracyjna.

Jeśli wybierzesz lasy bez punktów drzew, program tworzy regularne ilustracyjne próbki koron **wewnątrz poligonów lasu**, mniej więcej co najmniej 8 m, z wysokościami NMPT−NMT. Obecność wybranej warstwy punktów wyłącza takie próbkowanie. Limit wynosi 2000 symboli, przy większym obszarze wybieranych równomiernie z dostępnych próbek. Nie są to wykryte pojedyncze drzewa, a licznik symboli nie jest liczbą drzew w lesie.

**NMT + obiekty BDOT to podgląd uproszczony. Przerwy pomiędzy symbolami nie potwierdzają widoczności, prześwitów ani możliwości patrzenia pod koronami.** Rastry analizy nadal używają pełnej wybranej powierzchni. Przy braku danych o budynkach/drzewach HTML podaje odpowiednią informację. Raport sceny przechowuje liczbę przyjętych/pominiętych obiektów i informację o osiągniętych limitach; nie ma automatycznego przeliczania map widoczności.

## Rozwiązania w kodzie

- `scene_webgl.js`, `scene3d.html`: osobny stan zdjęcia, komunikat faktycznego nakładania, bryły ścian/dachów, zaokrąglone korony, widok obiektów na NMT i przełączniki.
- `scene_context.py`: transformacja obrysów do EPSG:2180, filtrowanie zasięgiem, odczyt wysokości, teselacja dachów i ograniczone próbkowanie koron. Brak nowych bibliotek wymaganych u użytkownika; używamy PyQGIS, GDAL i NumPy.
- `atlas_details.py`: obiekty i źródła w samodzielnym HTML; opis pochodzenia i liczby obiektów.
- `workspace_dialog.py`: osobny wybór obrysów budynków i zapis warstw sceny w `scene_view_options.scene_context_layer_ids`, odtwarzany po wczytaniu raportu.
- `atlas.py`: warstwy budynków 3D/lasów/drzew trafiają do prezentacji, niezależnie od warstw analizy ekspozycji.

Pełny realizm wymagałby dodatkowego etapu: segmentacji sklasyfikowanej chmury LAS/LAZ lub gotowych modeli LoD2/mesh, zgodności dat i tekstur elewacji. Bieżący wariant poprawia czytelność i prezentację istniejących danych, ale nie tworzy takich danych ze zwykłej ortofotomapy.

## Weryfikacja i przykład

79 testów Python/QGIS oraz trzy zestawy JavaScript. Nowe przypadki obejmują zachowanie dziedzińca w dachu, odrzucenie braku wysokości, korony ograniczone do lasu i rzeczywistych różnic wysokości, brak zmiany rastrów widoczności oraz odtworzenie warstw po odświeżeniu/wczytaniu raportu. JavaScript sprawdza, że paleta pokrycia nie wyłącza tekstury (`uUseTexture`), że checkbox i przycisk działają, dach jest teksturowany, ściany pozostają neutralne, a wariant NMT zachowuje obiekty.

Na syntetycznej scenie wykonano rzeczywisty render Mesa/EGL z teksturą i bez niej: obrazy różnią się w ponad 190 tys. pikseli. [Przykład podglądu NMT + obiekty](examples/atlas_2.4.0/podglad_syntetyczny.png) pokazuje uproszczone bryły oraz teksturę pól. To dane w całości syntetyczne; obraz nie przedstawia projektu użytkownika i nie jest zrzutem jego przeglądarki. [Samodzielny HTML przykładu](examples/atlas_2.4.0/scena_3d_NMPT.html) można zapisać i otworzyć lokalnie.

Środowisko testowe: QGIS 3.40.6 / Qt5 / GDAL 3.10.3 / Linux. Sterowanie JavaScript sprawdzono w symulowanym DOM/WebGL, render geometryczny w rzeczywistym Mesa/EGL. Testów na komputerze użytkownika ani Windows/macOS nie wykonano. Linki do wcześniejszych funkcji, algorytmów analizy i planów rozwoju zawiera [pełna dokumentacja](NMT_i_NMTP_sciagacz_dokumentacja_i_rozwoj.md).
