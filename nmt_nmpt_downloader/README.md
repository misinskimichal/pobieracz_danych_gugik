# NMT i NMTP ściągacz — Atlas widoczności 2.9.0

Jeden formularz do pobierania NMT/NMPT i tworzenia **map widoczności całych kół wokół turbin**. Obserwatorzy nie są wymagani. Każdy model ma własny promień i krok mapy. Wynik pokazuje liczbę widocznych turbin, trzy wysokości wirnika, niepewność danych i opcjonalnie ekspozycję dróg oraz zabudowy.

## Instalacja

QGIS → **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP** → `NMT i NMTP ściągacz-2.9.0.zip`. Nie rozpakowuj. Zakończ wcześniejsze zadania i uruchom QGIS ponownie po aktualizacji. W razie potrzeby odinstaluj poprzednią wersję i zainstaluj nowy ZIP. Oddzielne foldery danych pozostają na dysku.

QGIS 3.28–3.x, Python >=3.9; sprawdzone QGIS 3.40.6 / Qt5 / GDAL 3.10.3 / Linux. Windows i macOS nie są dostępne tutaj do testów. QGIS 4 nie jest obsługiwany. Biblioteki środowiska QGIS: PyQGIS, GDAL/OGR, NumPy, requests i lxml, bez osobnego serwera, GRASS czy Open3D.

## Atlas krok po kroku

1. Otwórz wtyczkę. Pozostaw tryb **Pobierz potrzebne dane i utwórz atlas widoczności**.
2. Wybierz punktową warstwę turbin, opcjonalnie tylko zaznaczone obiekty. Podaj wysokość piasty nad gruntem i średnicę wirnika albo pola z wartościami w metrach. Puste pole oznacza stałą wartość z lewej.
3. Ustaw oko w otoczeniu, domyślnie 1,7 m ponad gruntem NMT. Mapa odpowiada, skąd widać turbinę na właściwej wysokości; nie jest widokiem z gruntu pod turbiną.
4. NMT i NMPT włączasz osobno. Każdy ma własny **promień koła** i **krok mapy [m]**. Domyślnie NMT 20000 m / 10 m, NMPT 1000 m / 1 m. NMPT może mieć np. 650, 1000, 1500 m lub własną wartość; krok od 0,5 m. NMT ustala też poziom gruntu dla NMPT, nawet gdy wyłączysz mapę NMT.
5. Ustaw foldery NMT, NMPT i atlasów tylko raz. Można użyć danych poprzedniej wersji. Ustawienia źródeł po rozwinięciu pozwalają wybrać preferowany piksel danych, tryb ścisły i układ wysokościowy każdego modelu.
6. **Ważne miejsca z projektu** są opcjonalne: drogi, zabudowa/działki i obserwatorzy. Bez nich nadal powstaną pełne mapy kół. Służą do oceny ekspozycji i prezentacji; wysokości przeszkód pochodzą z modeli, nie z samego obrysu działki.
7. Automatyczne pobieranie wybiera dostępne dane i ponownie używa zgodnych kafli. Odznacz je dla pracy tylko na lokalnych folderach. Na pierwszą próbę wybierz jedną turbinę i małe koła, np. NMT 1000 m / 5 m i NMPT 650 m / 1 m, szczególnie bez cache.
8. Kliknij **Utwórz atlas widoczności**. Postęp obejmuje pliki, MB, prędkość, szacowane pozostałe MB/ETA, bieżącą turbinę i wysokość wirnika. Zamknięcie okna pozwala pracować dalej. **Anuluj** zachowuje ukończone pliki; aktywne połączenie może czekać do 90 s.
9. Po zakończeniu atlas pojawi się w projekcie, jeśli pozostawisz tę opcję. Domyślnie widoczny jest NMPT; przełącz grupę na NMT do porównania. W grupie jest też początkowo wyłączona warstwa zakresu widocznego wirnika. Opcjonalny PDF/PNG/HTML zawiera stronę każdego modelu, legendę, skalę, granice i podsumowanie. Korzysta z widocznych podkładów projektu, np. ortofotomapy; bez nich z cieniowania terenu.

## Znaczenie map

- **Ile turbin widać:** liczba turbin, dla których widoczny jest najwyższy punkt zasięgu łopaty; 0 to brak potwierdzonej widoczności, 65535 poza analizą.
- **Zakres wirnika:** brak / górny zasięg łopaty / także piasta / także dolny zasięg / nierozstrzygnięte. To trzy punkty, nie procent widocznej powierzchni łopat.
- **Jakość:** niepewna trasa, brak danych w miejscu obserwacji, oko pod dachem/koroną albo model kompletny. Przy niepewności liczba potwierdzonych turbin jest dolnym ograniczeniem.
- **Drogi:** odcinki do 50 m pokolorowane według udziału próbek z widocznością. **Zabudowa/działki:** próbki obrysu odsuniętego o 2 m, aby nie badać punktu pod dachem. **Obserwatorzy:** próbki geometrii. Nie jest to ocena każdego miejsca elewacji lub działki.

Braki nie są znanym terenem o wysokości 0 i nie zatrzymują pozostałych kół. NMPT jest nieprzezroczystym modelem górnej powierzchni 2,5D; nie opisuje prześwitów pod koronami ani brył 3D. NMT nie uwzględnia drzew i zabudowy. Modele są oddzielnymi produktami.

## Pliki i wydajność

`atlas_DATA_ID/`: `atlas.gpkg`, `ekspozycja.csv`, `report.json`, `report.md`, `events.jsonl`, podfoldery NMT/NMPT z GeoTIFF i stylami QML. Po eksporcie także `atlas.pdf`, `atlas.png` / `atlas_2.png`, `atlas.html`. Zachowaj cały folder dla HTML bez internetu. Raporty transferów mają własne podfoldery.

Rastry: `count.tif`, `hub.tif`, `bottom.tif`, `unknown.tif`, `scope.tif`, `rotor.tif`, `quality.tif`, opcjonalnie `hillshade.tif`. Indeksy obserwują źródłowe foldery. Zmiana danych nie przelicza samoczynnie zakończonego atlasu — uruchom nowe zadanie.

Krok mapy jest niezależny od piksela źródłowego. Przy większym kroku przeszkody agregowane są maksimum, aby nie uśrednić dachów i grzbietów. Źródło może być znacznie większe od wyniku. Interfejs pokazuje orientacyjny transfer; NMPT 20 km przy 0,5 m to bardzo duży obszar. Transfer jest strumieniowy, kafle deduplikowane, turbiny analizowane kolejno, wyniki zbiorcze zapisywane blokami. Limity ochronne: 40 mln komórek na koło, 400 mln w rastrze zbiorczym i 1000 turbin na zadanie. To limity, nie gwarancja szybkiego wykonania największego zadania.

GDAL korzysta z wzajemności linii widzenia, rzeczywistej wysokości turbiny i oka nad NMT. Domyślnie uwzględnia krzywiznę i refrakcję 6/7. Braki są analizowane w wariancie optymistycznym i pesymistycznym; rozbieżność daje niepewność. Maska jakości zachowuje także małe dziury NoData po zmianie kroku. Nie ma automatycznej transformacji EVRF2007 ↔ KRON86; analiza NMPT używa NMT w tym samym pionie, bez cichego zamiennika.

## Samo pobieranie

Przełącz tryb na **Tylko pobierz NMT / NMPT dla bufora warstwy**. Wskaż dowolną warstwę wektorową, bufor, zasoby i foldery w tym samym oknie. Każdy zasób ma preferowany piksel źródłowy, najbliższy dostępny zamiennik / tryb ścisły i układ wysokościowy. Drugi układ można dopuścić w tym trybie; nie oznacza to transformacji. Po pobraniu można dodać rastry; indeksy folderów reagują na dodanie/usunięcie plików.

WCS GUGiK dostarcza numeryczny ASCII, lokalnie kompresowany do GeoTIFF Float32 w EPSG:2180. Sprawdzone TIFF-y tych usług zwracały Byte, dlatego nie zastępują numerycznych wysokości. Cache sprawdza żądanie i odczyt; nie rozpoznaje sam nowszej epoki źródła.

Kod: `workspace_dialog.py` — jedyny formularz; `atlas.py` — koła i rastry; `atlas_context.py` — ekspozycja; `atlas_presentation.py` — style i eksport; `engine.py`/`core.py`/`catalog.py` — transfer; `coverage.py` — indeksy. Starsze moduły linii pozostają pomocniczo w kodzie, lecz ich okno nie jest rejestrowane w menu.

Licencja GPL-3.0. Pełna instrukcja i walidacja: `docs/Instrukcja_ATLAS_2.9.0.md` w repozytorium.


## Nowości 2.1.0: promienie, przekrój i scena 3D

- **Wysokości + promienie** przełącza mapę na wysokość: zielony nisko, czerwony wysoko, z odcinkami widoczności. Promienie piasty: zielony widoczna, czerwony zasłonięta, fioletowy niepewna, szary oko pod powierzchnią. Alternatywne style warstwy pokazują koniec łopaty i dolny zasięg. Atrybuty `turbina`, `azymut`, `od_m`, `do_m` pozwalają wybrać trasę i zakres.
- Odstęp promieni domyślnie 10°; raster nadal analizuje wszystkie komórki. Limit 200 000 odcinków/model jest raportowany, nie ogranicza obliczeń mapy.
- **Przekrój 2D** pokazuje teren, powierzchnię i trzy przerywane linie widzenia. Wybierz numer turbiny w zestawie i kierunek od niej do obserwatora na brzegu koła, 0° północ siatki, 90° wschód. Warstwa obserwatorów nie jest potrzebna.
- **Scena 3D** otwiera lokalny HTML z terenem, NMPT, turbiną i liniami. Obrót myszą, nachylenie, powiększenie i pion ×1–5. W 2.2.0 siatka jest wybierana do 1025×1025 wierzchołków, a lekki podgląd ma do 129×129; analiza i przekrój zachowują oryginalny krok. Jest to prezentacja powierzchni 2,5D w 3D, bez pełnego ray tracingu brył. Przy pion ×1 proporcje metrów są zachowane.
- `widoczne_pct` oznacza procent próbek z potwierdzoną widocznością ≥1 turbiny. 80% = np. 8 z 10 badanych miejsc. To nie procent wirnika ani działki. `niepewne_pct` to udział próbek z niepewnością / okiem pod powierzchnią; może nakładać się z widocznością innych turbin.
- Renderowanie map do atlasu działa asynchronicznie przez mechanizm QGIS. Okno pokazuje etap i bieżący czas także po pobraniu. Statystyki i piramidy modeli powstają w zadaniu roboczym. Końcowe składanie gotowych obrazów w PDF/PNG odbywa się w interfejsie i może spowodować krótką pauzę. **Anuluj** podczas renderowania zachowuje obliczone pliki.
- Aby uzyskać nowe warstwy dla wcześniejszego wyniku, uruchom analizę na tych samych folderach. Możesz wyłączyć automatyczne pobieranie. Stary raport nie zawiera wyników oddzielnych turbin potrzebnych do promieni.

Pliki dodatkowe w folderze atlasu: `promienie.gpkg`, `profil_NMT.svg`, `profil_NMPT.svg`, `scena_3d_NMT.html`, `scena_3d_NMPT.html`, `mapy_atlasu/`. Zachowaj folder obrazów, jeśli chcesz ponownie eksportować układ zapisany w projekcie QGIS. Podglądy i raporty są lokalne i nie korzystają z CDN ani zewnętrznej usługi 3D.


## Wydanie 2.2.0

- Szczegółowe **WebGL**: siatki do 129/257/513/1025 punktów na bok, domyślnie 513. Mniejszy promień samej sceny daje drobniejszy krok bez zwiększania ciężaru całego koła analizy. Nagłówek zawsze podaje rzeczywisty krok. Przy analizie 1 m, promieniu sceny 500 m i limicie 1025 można zachować 1 m. Siatka nie jest dokładniejsza niż dane obliczeniowe.
- Kamera perspektywiczna lub równoległa, kąt widzenia, kierunek oświetlenia, PNG. Lekki HTML bez WebGL pozostaje dostępny jako osobny plik. To nadal model powierzchni 2,5D, bez pełnego ray tracingu brył.
- Opcjonalna **tekstura z widocznych warstw projektu**, np. ortofotomapy: renderowana w tle i osadzona w HTML. WMS/XYZ mogą połączyć się z siecią przy przygotowaniu tekstury; gotowa scena działa offline.
- Opcjonalne poligony lasów i punkty drzew z BDOT/własnych danych. Las określa materiał, wysokości pozostają z NMT/NMPT. Symbole drzew korzystają z różnicy NMPT−NMT; kształty koron są ilustracyjne. Te dane nie zmieniają wyniku widoczności w tym wydaniu.
- W panelu warstw **Raport HTML i sceny 3D · prawy przycisk** otwiera raport, sceny i profile. Odnośniki i menu są odtwarzane z projektem.
- **Przelicz ponownie · lokalne modele** wykonuje nowy wariant aktualnych parametrów dla tych samych turbin, z pobieraniem modeli wymuszonym na wyłączone. Poprzedni katalog zostaje. Większy promień może ujawnić braki lokalnych danych.
- **Wczytaj report.json** odtwarza zadanie także po zamknięciu QGIS, z punktami i wysokościami z `atlas.gpkg`. Pola `piasta_m` i `srednica_m` mają pierwszeństwo przed stałymi z lewej; wyczyść wybór pola, jeśli chcesz nadpisać je jedną liczbą.
- Cache poprawności źródeł w `<folder atlasów>/.nmt_nmpt_cache/validity` ogranicza ponowne skanowanie pikseli. Zmiana źródła lub jego maski/metadanych unieważnia klucz. Samą widoczność przeliczamy ponownie.

[Dokładna instrukcja i omówienie inspiracji z PDF](../docs/Instrukcja_ATLAS_2.2.0.md). Nowe pliki wyniku: `raport.gpkg`, `scena_3d_lekka_*.html` i opcjonalnie `tekstura_*.png`. Szczegółowa scena zawiera obraz w sobie. Modeli, cache i raportów użytkownika nie ma w ZIP-ie instalacyjnym.


## Historyczne wydanie 2.8.0 — prosty wybór i nowy silnik 3D

W części Wizualizacja wybierz **Model 3D** albo **Fotomontaż**. Jeden przycisk tworzy lub otwiera właściwy wynik. Dodanie zdjęcia automatycznie wybiera fotomontaż. W modelu 3D podstawowe wejścia to ortofotomapa, lasy i obrysy budynków oraz miejsca patrzenia; parametry techniczne są w osobnym oknie. Dziennik jest rozwijany, postęp pokazuje się podczas pracy. W przeglądarce również schowano zaawansowane kontrolki.

Model korzysta z lokalnego Three.js 0.184: tekstury bloków terenu i dachów, oddzielne bryły, instancje koron i automatyczne zarządzanie głębokością. Przy ponownym przygotowaniu można zachować obiekty ze starej sceny, gdy ich warstw brakuje w projekcie. Rozpoznawane nazwy PTLZ/BUBD pomagają ustawić źródła. Brak obrysów nie jest automatyczną rekonstrukcją domów ze zdjęć dachów; ciągła powierzchnia NMPT ma takie ograniczenie także w nowym silniku.

**Dodaj widok Street View z linku** odczytuje konkretną panoramę, położenie i kadr. Bez klucza wskaż plik tego kadru; opcjonalny własny klucz Static API pozwala pobrać 640×480 w tle. Klucz pozostaje tylko w bieżącej sesji. Zwykły link mapy jest odrzucany. Własne zdjęcia i model 3D nie potrzebują usług Google ani PyQtWebEngine. [Instrukcja 2.8.0](../docs/Instrukcja_ATLAS_2.8.0.md) opisuje przebieg tego historycznego wydania.

## Wydanie 2.7.0 — własne zdjęcie z telefonu

W tej samej wtyczce znajdziesz **Zdjęcie z telefonu · fotomontaż turbin**. Kliknij **Dodaj zdjęcie na mapie**, przeciągnij od miejsca aparatu w kierunku kadru (lub kliknij te dwa miejsca), a następnie wybierz oryginalny JPG/PNG. W formularzu pojawi się plik, podgląd i parametry aparatu. Miejsce i kierunek pojawiają się jako warstwy w projekcie. Po wykonaniu lub wczytaniu atlasu kliknij **Przygotuj wizualizację na zdjęciu**; korzysta z zapisanych NMT/NMPT, bez ponownego pobierania i analizy.

HTML pozwala dopasować kierunek, pochylenie, przechylenie i kąt widzenia, włączyć zasłanianie NMT/NMPT, namalować ręczną maskę pierwszego planu oraz pobrać pełnowymiarowy PNG i dopasowanie JSON. JSON wczytasz ponownie we wtyczce. Model turbiny używa pozycji i wymiarów z atlasu; kształt i ustawienie łopat są uproszczone. To fotomontaż z jednego stanowiska, nie swobodne przemieszczanie się po zdjęciu. Nie obsługuje panoram 360° ani HEIC bez konwersji.

Do 24 zdjęć i 200 najbliższych turbin. Roboczy obraz do 6000 px / 24 MP; oryginał zachowany. Profile zasłaniania są przybliżeniem, a nie zastępstwem rastrów widoczności; braki i niezgodność położenia oka z NMPT są zgłaszane. Przycisk **Otwórz Street View** otwiera Google Maps dla stanowiska i kierunku w przeglądarce, bez pobierania zdjęć Google do fotomontażu. Nie wymaga klucza API ani QtWebEngine.

Pliki `zdjecia_punkty.geojson`, `zdjecia_kierunki.geojson` oraz `zdjecia_terenowe/ID/` są częścią atlasu; listę i ustawienia zachowuje `report.json`. [Instrukcja 2.7.0](../docs/Instrukcja_ATLAS_2.7.0.md) opisuje przygotowanie zdjęcia, dopasowanie, zapis, ograniczenia i testy.

## Wydanie 2.6.0 — punkty z mapy i szczegółowy widok z gruntu

Wczytaj istniejący atlas i kliknij **Klikaj punkty wizualizacji na mapie**. Każde kliknięcie dodaje wiersz do tabeli oraz punkt w projekcie; małe okno pokazuje liczbę zebranych miejsc. Prawy przycisk / Escape / Zakończ wraca do formularza. Do 12 punktów, z nazwą i wysokością oka. **Przygotuj widoki punktów** odświeża prezentację bez ponownego liczenia widoczności. Punkty muszą mieścić się w obszarze zapisanych modeli; problem jednego punktu jest raportowany i nie zatrzymuje pozostałych.

W HTML wybierasz **Miejsce** z listy. W trybie wybranych punktów tło ma do 513×513 wierzchołków i zdjęcie z celem co najmniej 0,5 m/px. Wokół każdego punktu przygotowywany jest fragment z istniejącego modelu obliczeniowego, do 513×513 i z celem zdjęcia 0,10 m/px, do 16 dodatkowych obrazów. Domyślny promień szczegółowego otoczenia: 120 m (30–250 m). GPU utrzymuje tylko aktywny lokalny detal. Rzeczywisty krok zależy od dostępnych danych i limitu siatki; nie odtwarzamy utraconych szczegółów przez samo zagęszczanie.

Bliski las ma gęstsze, nieregularne próbki i teksturowane sylwetki z listowiem. Dalszy zachowuje ciągłą powierzchnię NMPT. Elewacje i okna, listowie, poszycie oraz miękkie cienie są poglądowe. Dachy korzystają z dokładnych kafli zdjęcia; spadki dopasowujemy do NMPT, gdy dane wystarczają, z płaskim modelem awaryjnym. Zdjęcie z góry nie daje fotograficznych elewacji.

Punkty: `punkty_wizualizacji.geojson`. Dokładne lokalne zdjęcia: `ortofoto_NMPT_punkt_NN.vrt` i wspólny folder PNG. Wybierz wiersz w tabeli i **Dodaj pobraną ortofotomapę do QGIS**, aby dodać zdjęcie tego punktu. Cały HTML działa offline po eksporcie. Szczegóły i przykłady: [instrukcja 2.6.0](../docs/Instrukcja_ATLAS_2.6.0.md).

## Wydanie 2.5.0 — lokalna ortofotomapa WMS w szczegółowych kaflach

WMS/WMTS może być źródłem zdjęcia. Eksport zapisuje w folderze atlasu do 64 georeferencyjnych kafli/model i lokalną mozaikę `ortofoto_NMPT.vrt` (analogicznie NMT). Cel domyślny: 0,25 m/px, do wyboru 0,10 / 0,25 / 0,50 / 1 m/px; rzeczywistą rozdzielczość ograniczają źródło oraz budżet 64 MP/model i podaje ją raport. Każdy blok ma do 1024×1024 px. PNG 2048 pozostaje małym podglądem mapki; model korzysta z pełnych kafli. HTML zawiera ich kopię i działa bez dalszych zapytań WMS. Przycisk w QGIS dodaje lokalne zdjęcie do projektu. Zachowaj VRT razem z folderem PNG/plikami georeferencji.

Własny renderer wiąże teksturę i jej współrzędne dla każdego bloku osobno, tworzy mipmapy i korzysta z filtrowania anizotropowego, jeśli urządzenie je obsługuje. Zdjęcie domyślnie zachowuje barwy bez dodatkowego cieniowania. **Zdjęcie z góry** pozwala sprawdzić dopasowanie, a **Zapisz diagnostykę widoku** zapisuje informacje z rzeczywistego WebGL, brakujące kafle i stany przełączników.

Gdy przygotowano korony i lasy, **Pokaż korony zamiast powierzchni lasu** jest domyślnie włączone: usuwa przykrywającą symbole powierzchnię NMPT tylko w lasach, pozostawiając tam grunt i korony. Wyłączenie wraca do pełnego NMPT. Wysokości źródłowe, braki i sprawdzanie położenia oka pozostają zachowane. To wariant prezentacji; odstępy między koronami nie są wynikiem analizy. Limit koron lasu: 2000 / 5000 / 10000, domyślnie 5000.

Opis wdrożenia, ograniczeń, wykorzystanych wzorców Qgis2threejs i testów: [instrukcja 2.5.0](../docs/Instrukcja_ATLAS_2.5.0.md).

## Wydanie 2.4.0 — zdjęcie niezależne od palety, budynki i lasy

**Ortofotomapa na modelu** jest osobnym przełącznikiem w HTML. Zmiana palety wysokości/pokrycia jej nie wyłącza. Komunikat odróżnia zdjęcie nałożone na model od samego podglądu na mapce. Przycisk **Pokaż ortofotomapę** przywraca nakładanie jednym kliknięciem.

W QGIS wybierz opcjonalnie obrysy budynków, lasy i punkty drzew. Budynki stają się uproszczonymi bryłami z płaskim dachem na wysokości maksimum NMPT w obrysie, z teksturą zdjęcia na dachu. Ściany mają neutralny kolor. Wysokości drzew pochodzą z NMPT−NMT; bez punktów drzew warstwa lasów daje ilustracyjne próbki koron wewnątrz poligonów, nie inwentaryzację pojedynczych drzew. Brak takich danych jest opisany w HTML. Warstwa działek nie jest źródłem obrysów budynków.

**NMT + obiekty BDOT** pokazuje bryły i korony nad samym gruntem, aby nie chowały się wewnątrz ciągłej powierzchni NMPT. To wariant prezentacji; przerwy między symbolami nie oznaczają prześwitów ani potwierdzonej widoczności. Włącz **Powierzchnia NMPT**, aby wrócić do modelu powierzchni. Wybór miejsca kamery przy widocznych obiektach nadal sprawdza oryginalną powierzchnię NMPT. Żaden z tych przełączników nie przelicza analizy. Aktualizacja istniejącego wyniku wymaga **Odśwież samą scenę 3D / ortofotomapę** lub **Scena 3D** po zmianie ustawień/wersji.

[Instrukcja 2.4.0](../docs/Instrukcja_ATLAS_2.4.0.md) opisuje konfigurację, ograniczenia i weryfikację.

## Wydanie 2.3.1 — aktualny HTML po wyborze zdjęcia

Wybór warstwy rastrowej włącza nakładanie zdjęcia i wybiera tryb pojedynczej warstwy. Po zmianie ustawień **Scena 3D** najpierw odświeża prezentację z zapisanych modeli, a dopiero potem otwiera HTML. Nie przelicza widoczności. Przy odczycie raportu zachowywane są zapisane opcje; obrazu nie włączamy wbrew wcześniejszemu wyborowi użytkownika. Zaktualizowany formularz pozwala osobno otworzyć wyeksportowane PNG i pokazuje, czy obraz jest osadzony w HTML.

W HTML można pobrać zdjęcie PNG. Jego podgląd na mapce pozostaje dostępny także przy błędzie przesłania do WebGL. Duże obrazy są dopasowywane do limitu tekstury karty graficznej; błędy eksportu, dekodowania i nakładania mają osobne komunikaty. Szczegóły: [instrukcja 2.3.1](../docs/Instrukcja_ATLAS_2.3.1.md).

## Wydanie 2.3.0 — ortofoto i kamera z oczu

Wybór jednego źródła ortofotomapy (warstwa QGIS lub Geoportal online) zapobiega zasłanianiu jej przez NMT/NMPT. Renderer czeka na kafle sieciowe z `RenderBlocking` w zadaniu asynchronicznym; puste i jednolicie szare wyniki są raportowane. Geoportal jest pobierany w tle i dopasowywany do EPSG:2180. W HTML jest osobny komunikat stanu zdjęcia.

**Z poziomu oczu:** wybierz miejsce na mapce w przeglądarce albo przyciskiem **Wskaż miejsce patrzenia w QGIS**. Kamera stoi na gruncie NMT + wysokość oka, domyślnie 1,7 m. Mysz rozgląda się, strzałki/WASD przesuwają, Shift zwiększa krok, kółko zmienia kąt widzenia. Dach/korona na wysokości oka i braki danych są zgłaszane. W tym trybie pion = 1:1. To model 2,5D z obrazem z góry, bez prawdziwych elewacji i prześwitów.

Dla starego wyniku: **Wczytaj report.json → wybierz źródło ortofotomapy → Odśwież samą scenę 3D / ortofotomapę**. Używane są zapisane `terrain.tif` i `elevation.tif`, bez pobierania modeli i liczenia map widoczności. Zmiana kamery/oka w podglądzie nie przelicza analizy. Stare HTML-e wymagają odświeżenia/generacji — instalacja ZIP-a nie zmienia ich automatycznie.

[Instrukcja 2.3.0](../docs/Instrukcja_ATLAS_2.3.0.md) zawiera dokładne kroki i ograniczenia. Pełna scena WebGL obsługuje ortofoto i kamerę z oczu; lekka wersja Canvas ich nie oferuje i ma teraz wyraźny odnośnik do pełnej sceny.

## Wydanie 2.9.0 — wynik w QGIS i zwijana Wizualizacja

Przywrócono silnik WebGL 1 z 2.7.0 i usunięto Three.js z paczki. Model 3D, zdjęcia i ich parametry są w domyślnie zwiniętej sekcji **Wizualizacja**; w HTML również jest jedno takie menu. Model ma tylko trzy przyciski: patrzenie na turbinę, reset kamery, PNG. Fotomontaż startuje z blokadą przeciągania; kalibracja kamery pozostaje opcjonalna.

Podstawowy przebieg przygotowuje wynik w QGIS, bez automatycznego generowania 3D i PDF/PNG/HTML. Opcję eksportu można włączyć. **Więcej wyników** zastępuje zestaw osobnych przycisków. Obok każdego pola warstwy jest **↖**: kliknij je, a następnie warstwę w panelu QGIS; zmieni się wyłącznie wskazane pole.

Grupa wyników: **Widoczność · nazwa warstwy turbin · RRRR-MM-DD GG:mm:ss CET/CEST**. Nazwa źródła i chwila utworzenia trafiają do raportu; odświeżenie sceny zachowuje datę obliczeń. Interpretacja map i procentów nie zmieniła się. [Instrukcja 2.9.0](../docs/Instrukcja_ATLAS_2.9.0.md).
