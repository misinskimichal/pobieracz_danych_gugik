# NMT i NMTP ściągacz — Atlas widoczności 2.3.0

Jeden formularz do pobierania NMT/NMPT i tworzenia **map widoczności całych kół wokół turbin**. Obserwatorzy nie są wymagani. Każdy model ma własny promień i krok mapy. Wynik pokazuje liczbę widocznych turbin, trzy wysokości wirnika, niepewność danych i opcjonalnie ekspozycję dróg oraz zabudowy.

## Instalacja

QGIS → **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP** → `NMT i NMTP ściągacz-2.3.0.zip`. Nie rozpakowuj. Zakończ wcześniejsze zadania i uruchom QGIS ponownie po aktualizacji. W razie potrzeby odinstaluj poprzednią wersję i zainstaluj nowy ZIP. Oddzielne foldery danych pozostają na dysku.

QGIS 3.28–3.x, Python >=3.9; sprawdzone QGIS 3.40.6 / Qt5 / GDAL 3.10.3 / Linux. Windows i macOS nie są dostępne tutaj do testów. QGIS 4 nie jest obsługiwany. Biblioteki środowiska QGIS: PyQGIS, GDAL/OGR, NumPy, requests i lxml, bez osobnego serwera, GRASS czy Open3D.

## Atlas krok po kroku

1. Otwórz wtyczkę. Pozostaw tryb **Pobierz potrzebne dane i utwórz atlas widoczności**.
2. Wybierz punktową warstwę turbin, opcjonalnie tylko zaznaczone obiekty. Podaj wysokość piasty nad gruntem i średnicę wirnika albo pola z wartościami w metrach. Puste pole oznacza stałą wartość z lewej.
3. Ustaw oko w otoczeniu, domyślnie 1,7 m ponad gruntem NMT. Mapa odpowiada, skąd widać turbinę na właściwej wysokości; nie jest widokiem z gruntu pod turbiną.
4. NMT i NMPT włączasz osobno. Każdy ma własny **promień koła** i **krok mapy [m]**. Domyślnie NMT 20000 m / 10 m, NMPT 1000 m / 1 m. NMPT może mieć np. 650, 1000, 1500 m lub własną wartość; krok od 0,5 m. NMT ustala też poziom gruntu dla NMPT, nawet gdy wyłączysz mapę NMT.
5. Ustaw foldery NMT, NMPT i atlasów tylko raz. Można użyć danych poprzedniej wersji. Ustawienia źródeł po rozwinięciu pozwalają wybrać preferowany piksel danych, tryb ścisły i układ wysokościowy każdego modelu.
6. **Ważne miejsca z projektu** są opcjonalne: drogi, zabudowa/działki i obserwatorzy. Bez nich nadal powstaną pełne mapy kół. Służą do oceny ekspozycji i prezentacji; wysokości przeszkód pochodzą z modeli, nie z samego obrysu działki.
7. Automatyczne pobieranie wybiera dostępne dane i ponownie używa zgodnych kafli. Odznacz je dla pracy tylko na lokalnych folderach. Na pierwszą próbę wybierz jedną turbinę i małe koła, np. NMT 1000 m / 5 m i NMPT 650 m / 1 m, szczególnie bez cache.
8. Kliknij **Utwórz atlas widoczności**. Postęp obejmuje pliki, MB, prędkość, szacowane pozostałe MB/ETA, bieżącą turbinę i wysokość wirnika. **Ukryj** pozwala pracować dalej. **Anuluj** zachowuje ukończone pliki; aktywne połączenie może czekać do 90 s.
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

Licencja GPL-3.0. Pełna instrukcja i walidacja: `docs/Instrukcja_ATLAS_2.1.0.md` w repozytorium.


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


## Wydanie 2.3.0 — ortofoto i kamera z oczu

Wybór jednego źródła ortofotomapy (warstwa QGIS lub Geoportal online) zapobiega zasłanianiu jej przez NMT/NMPT. Renderer czeka na kafle sieciowe z `RenderBlocking` w zadaniu asynchronicznym; puste i jednolicie szare wyniki są raportowane. Geoportal jest pobierany w tle i dopasowywany do EPSG:2180. W HTML jest osobny komunikat stanu zdjęcia.

**Z poziomu oczu:** wybierz miejsce na mapce w przeglądarce albo przyciskiem **Wskaż miejsce patrzenia w QGIS**. Kamera stoi na gruncie NMT + wysokość oka, domyślnie 1,7 m. Mysz rozgląda się, strzałki/WASD przesuwają, Shift zwiększa krok, kółko zmienia kąt widzenia. Dach/korona na wysokości oka i braki danych są zgłaszane. W tym trybie pion = 1:1. To model 2,5D z obrazem z góry, bez prawdziwych elewacji i prześwitów.

Dla starego wyniku: **Wczytaj report.json → wybierz źródło ortofotomapy → Odśwież samą scenę 3D / ortofotomapę**. Używane są zapisane `terrain.tif` i `elevation.tif`, bez pobierania modeli i liczenia map widoczności. Zmiana kamery/oka w podglądzie nie przelicza analizy. Stare HTML-e wymagają odświeżenia/generacji — instalacja ZIP-a nie zmienia ich automatycznie.

[Instrukcja 2.3.0](../docs/Instrukcja_ATLAS_2.3.0.md) zawiera dokładne kroki i ograniczenia. Pełna scena WebGL obsługuje ortofoto i kamerę z oczu; lekka wersja Canvas ich nie oferuje i ma teraz wyraźny odnośnik do pełnej sceny.
