# NMT i NMTP ściągacz 2.6.0 — szczegółowe wizualizacje z wybranych punktów

Wydanie z 24 października 2026 r. [Pobierz ZIP do QGIS](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-2.6.0.zip). Instalacja: **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP**, następnie restart QGIS.

ZIP: 157738 bajtów; SHA-256: `3a77d083655240819510339bf8f659e9cecfdb1306d2b3c6be990e4d37b83919`.

## Co zmienia tryb punktowy

W 2.5.0 limit drzew był rozdzielany po całym kole, a korony były prostymi bryłami. Z bliska las mógł wyglądać jak rzadko rozstawione symbole. Budynki miały uproszczoną geometrię i jednolite ściany, a dachy korzystały z małego wspólnego podglądu zdjęcia.

Teraz budżet szczegółów jest przeznaczany na konkretne miejsca patrzenia. Wokół każdego punktu przygotowujemy lokalny fragment modelu, dokładniejsze zdjęcie oraz gęstsze listowie. Dalszy teren pozostaje lżejszy. W jednym HTML można przełączać miejsca; przeglądarka utrzymuje lokalny detal aktywnego punktu. Dalszy las zachowuje ciągłą powierzchnię NMPT, więc brak osobnych drzew w tle nie tworzy pustego terenu.

To wyraźna poprawa prezentacji danych NMT/NMPT i obrysów. Elewacje, okna, listowie, poszycie i miękkie cienie pod koronami są materiałami poglądowymi. Wtyczka nie tworzy prawdziwych fotografii ścian ze zdjęcia dachów i nie udaje, że ilustracyjne korony są pomierzonymi pojedynczymi drzewami.

## Przygotowanie punktów w QGIS

1. Po aktualizacji wczytaj dotychczasowy `report.json`. Zachowaj cały folder atlasu, w szczególności `terrain.tif`, `elevation.tif` i dane źródłowe. Dla istniejącego atlasu nie trzeba ponownie liczyć widoczności wyłącznie na potrzeby prezentacji.
2. Pozostaw wybraną ortofotomapę WMS/WMTS, lasy i obrysy budynków. Opcjonalne punkty drzew zastępują automatyczne próbkowanie lasów. Wybrane źródła muszą być dostępne w projekcie podczas przygotowania HTML.
3. Kliknij **Klikaj punkty wizualizacji na mapie**. Formularz odsuwa się, a małe okno pokazuje liczbę i ostatnie dodane miejsca. Każde lewe kliknięcie dodaje punkt do tabeli oraz do warstwy **Punkty wizualizacji 3D** w projekcie. Współrzędne są przeliczane z CRS mapy do EPSG:2180.
4. **Prawy przycisk, Escape lub Zakończ** kończy zbieranie i przywraca formularz oraz poprzednie narzędzie mapy. Zebrane punkty pozostają w tabeli.
5. Zmień nazwy i wysokości oka, jeśli potrzeba. Współrzędne są tylko do odczytu. **Wskaż jedno miejsce / zmień wybrany punkt** może poprawić wybrany wiersz, a **Usuń wybrany punkt** usuwa go z zestawu. Dozwolone jest do 12 miejsc; na pierwszą próbę zalecamy 2–3.
6. Ustaw **Szczegółowe otoczenie każdego punktu**, domyślnie 120 m, zakres 30–250 m. Mniejszy zasięg ułatwia zachowanie najdrobniejszego kroku istniejących danych i zmniejsza rozmiar lokalnego zdjęcia. Limit ilustracyjnych koron określa budżet bliskiego lasu dla każdego miejsca.
7. Kliknij **Przygotuj widoki punktów · bez przeliczania widoczności**. To przycisk odświeżenia prezentacji istniejącego atlasu. Program odczyta zapisane modele i pobierze potrzebne obrazy z WMS. O postępie informują etapy i numer obrazu. Po przygotowaniu warstwa punktów jest podłączana do zapisanego GeoJSON, aby zachować ją przy zapisie i ponownym otwarciu projektu QGIS. Można też użyć dotychczasowego przycisku odświeżania samej sceny.
8. Wybierz **Scena 3D**, a w HTML pole **Miejsce**. Startowy widok odpowiada wybranemu wierszowi tabeli. Pozostałe miejsca przełączysz listą. Każde ma własne oko nad NMT.

Punkt musi mieścić się w obszarze zapisanych modeli. Punkty poza zasięgiem, bez NMT/NMPT lub z okiem pod powierzchnią dachu/korony są opisane jako niedostępne; inne miejsca są przygotowywane dalej. Ten tryb nie pobiera automatycznie modelu nowego obszaru poza atlasem. Dla takich miejsc trzeba najpierw powiększyć zakres atlasu lub przygotować nowy zestaw danych. Nie wymagamy punktów do zwykłej analizy koła. Przy pustej tabeli można nadal korzystać z pojedynczego miejsca lub automatycznego widoku startowego.

## Sterowanie i ocena jakości

**Miejsce** przełącza przygotowany punkt i kieruje kamerę na wybraną turbinę. Przeciąganie rozgląda się z tego miejsca, kółko zmienia kąt widzenia. Oko jest liczone ponad gruntem NMT; w trybie z oczu pion wynosi 1:1. Strzałki / W A S D pozwalają przemieścić kamerę jak w poprzedniej wersji. Najwyższy detal dotyczy przygotowanego otoczenia, a nie dowolnego miejsca całego koła.

**Zdjęcie z góry** pozwala porównać dopasowanie ortofotomapy. Zdjęcie ma osobny przełącznik. **Pokaż korony zamiast powierzchni lasu** pokazuje bliskie listowie; wyłączenie przywraca ciągły model powierzchni. Wariant NMT + obiekty zachowuje dalszy las jako tło, jeśli prezentacja koron jest włączona. Gdy chcesz obejrzeć sam grunt, wyłącz prezentację koron lub symbole drzew.

Nagłówek podaje krok tła, a stan sceny dopisuje rzeczywisty krok lokalnego fragmentu dla bieżącego miejsca. Materiały nie zwiększają dokładności pomiaru. **Zapisz diagnostykę widoku** zachowuje aktywny punkt, kroki lokalnych siatek, liczbę obrazów i ewentualne błędy WebGL.

## Skąd bierze się większy detal i oszczędność

| Element | Przygotowanie i ograniczenia |
|---|---|
| Tło po wybraniu punktów | Do 513×513 wierzchołków; zdjęcie z celem nie gęstszym niż 0,5 m/px. Bez wybranych punktów dotychczasowe ustawienia tła pozostają dostępne. |
| Lokalny teren | Okno istniejącego modelu obliczeniowego, do 513×513; zachowuje jego krok, dopóki pozwala na to rozmiar okna. Nie wymyśla dodatkowych wysokości. |
| Lokalne zdjęcie | Cel 0,10 m/px, do 16 dodatkowych obrazów na miejsce. Faktyczny szczegół zależy od WMS i limitów eksportu. Obrazy pozostają georeferencyjne. |
| Bliski las | Około 3,5–4 m odstępu kandydatów na siatce źródłowej, z deterministycznym nieregularnym przesunięciem. Wysokość ponownie odczytywana w ostatecznym położeniu. |
| Budżet koron | Do ustawionego limitu na miejsce i do 30 000 różnych pozycji w jednym zestawie, z deduplikacją nakładających się otoczeń. W rendererze rysujemy tylko bliskie korony. |
| GPU | Zachowuje tło i szczegółowe obrazy aktywnego miejsca; obrazy poprzedniego są usuwane. Pozostałe miejsca pozostają w pliku HTML i można je ponownie wybrać. |

Przykładowo w danych analizowanych co 1 m tło koła o średnicy około 2 km może mieć krok 4 m, a otoczenie punktu zachować 1 m. Zdjęcie tła ma mniej pikseli niż w pełnym wariancie 0,25 m/px, zaś lokalny obraz może mieć cel 0,10 m/px. To przydzielenie zasobów do pierwszego planu. W danych obliczonych co 5 czy 10 m nie odzyskamy drobnych przeszkód samą zmianą opcji podglądu; potrzebny jest dokładniejszy model wejściowy/obliczeniowy.

Ustawienie 0,10 m/px nie gwarantuje takiego natywnego GSD ortofotomapy. WMS może udostępniać fotografię o rzadszym rzeczywistym szczególe. Duże okno, wiele miejsc lub limit siatki również mogą wymagać rzadszego kroku; faktyczne rozdzielczości są zapisane w raporcie.

## Las i budynki — co jest pomiarem, a co materiałem

Lasy pochodzą z wybranych poligonów, wysokości przeszkód z NMT/NMPT. W pobliżu punktu próbkujemy gęściej i preferujemy kandydatów najbliższych obserwatorowi. Pozycje są lekko rozpraszane, ponownie sprawdzane w masce lasu i danych źródłowych. Rozkład nadal jest ilustracyjny. Gdy dostarczysz punkty drzew, używamy ich, bez tworzenia dodatkowego układu z poligonów.

Korona używa kilku przecinających się płaszczyzn z własną teksturą listowia i przezroczystością wycinaną w shaderze. To pozwala pokazać więcej detali przy znacznie mniejszej liczbie trójkątów niż przy poprzednich bryłach. Proceduralne materiały powstają lokalnie, bez pobierania zewnętrznych fotografii czy zależności od CDN. Poszycie i miękkie cienie pod koronami poprawiają czytelność bliskiego planu; nie są danymi o podszycie ani analizą cieni słonecznych. Cienie nie są nakładane na otwory NoData.

Dla budynku próbujemy dopasować płaszczyznę lub dach dwuspadowy do poprawnych próbek NMPT. Dopasowanie wymaga dostatecznej liczby punktów, małego błędu oraz wyraźnej poprawy względem modelu płaskiego. Odrzucamy słabe wyniki; wtedy pozostaje uproszczony dach. Nie rekonstruujemy dowolnych skomplikowanych dachów, facjatek i kominów. Model dopasowany jest aproksymacją NMPT, a nie pełną inwentaryzacją architektoniczną.

Dachy korzystają ze szczegółowych obrazów. Ich trójkąty są przycinane do granic bloków zdjęcia, aby uniknąć rozciągania obrazu z sąsiedniego kafla. Ściany otrzymują poglądowy tynk, okna, drzwi i cokół. Podział na kondygnacje i kolory nie pochodzą z pomiaru elewacji. Przykrywanie ścian przez uproszczoną powierzchnię NMPT jest usuwane w maskach przyjętych obrysów budynków.

**Widok nie służy do oceniania prześwitów przez las.** Przerwy między płaszczyznami liści nie dowodzą widoczności turbiny. Formalne rastry widoczności pozostają oparte na modelu obliczeniowym; materiały i gęstość wizualizacji nie zmieniają ich wyniku. Oko nadal sprawdza oryginalną powierzchnię NMPT. Fotorealistyczny obraz konkretnej ulicy wymagałby zdjęć naziemnych, modeli LoD2/mesh lub chmury LAS/LAZ, odpowiedniego teksturowania i zgodności terminów.

## Pliki i odtwarzanie

- `punkty_wizualizacji.geojson`: nazwane punkty z wysokościami oka, EPSG:2180; obejmuje miejsca wskazane przez użytkownika.
- `report.json` / `scene_view_options.scene_viewpoints`: lista miejsc, wybrany wiersz startowy, promień detalu i ustawienia źródeł. `details[].viewpoints` podaje również powód niedostępności lub krok detalu.
- `ortofoto_NMPT.vrt`: lokalne zdjęcie tła i wspólny folder obrazów.
- `ortofoto_NMPT_punkt_01.vrt`, kolejne numery: pełne lokalne zdjęcie otoczenia konkretnego punktu. Wybór wiersza w tabeli przed **Dodaj pobraną ortofotomapę do QGIS** dodaje tę mozaikę.
- `scena_3d_NMPT.html`: jeden samodzielny plik z listą miejsc, modelami i kopiami zdjęć, działający offline po eksporcie.

VRT trzeba zachować razem z folderem PNG i plikami georeferencji. HTML ma własną kopię obrazów. Wczytanie raportu odtwarza listę punktów i ich parametry; nie trzeba ponownie klikać tych samych miejsc. Przeniesienie danych do innego katalogu wymaga zachowania całej struktury atlasu.

## Kod i uzasadnienie rozwiązań

- `workspace_dialog.py`: tabela, zbieranie kliknięć z małym oknem postępu, warstwa punktów, odtwarzanie i osobny przycisk przygotowania widoków. Escape/prawy przycisk przywraca poprzednie narzędzie mapy.
- `scene_views.py`: walidacja do 12 miejsc i okna danych przy punktach; brzegi są dopasowane do siatki tła, bez zmiany wejściowych rastrów. Niedostępny punkt nie przerywa innych.
- `scene_context.py`: dokładniejsza maska lasu i budynków, gęste kandydaty blisko punktów, ograniczenie liczby symboli i ponowny odczyt wysokości po przesunięciu.
- `scene_architecture.py`: odporne dopasowanie metodą najmniejszych kwadratów z odrzucaniem odstających reszt; próg błędu i poprawy względem płaskiego dachu. Podział wzdłuż kalenicy zachowuje obrys i dziedzińce.
- `scene_appearance.js`: własne proceduralne listowie i poszycie, przycinanie dachów do bloków tekstury oraz gradient nieba.
- `scene_webgl.js`: materiały, bliski detal, maski prezentacji, kontaktowe cienie, delikatna perspektywa powietrzna i zwalnianie poprzednich obrazów. Transformację UV wykonujemy w shaderze wierzchołków o wysokiej precyzji przed interpolacją — ważne dla szczegółowego zdjęcia przy kamerze z oczu.
- `scene_imagery.py`: wspólne pliki obrazów i mozaiki dla tła oraz poszczególnych punktów. Mały margines rozmiaru nie podwaja całego obrazu wyłącznie dla zysku poniżej 0,5%.

## Weryfikacja i przykłady

87 testów Python/QGIS obejmuje m.in. rozpoznanie dachu dwuspadowego i jednospadowego na danych o znanej geometrii, brak zmiany źródłowych wysokości, lokalny krok 1 m przy rzadszym tle, granice i otwory okien, raport niedostępnego punktu, wiele kliknięć w CRS innym niż EPSG:2180, zapis warstwy i GeoJSON, przywrócenie narzędzia mapy oraz odtworzenie listy z raportu. Hashe rastrów liczby widocznych turbin pozostają niezmienione po przygotowaniu punktów; nowa analiza nie jest uruchamiana.

Testy JavaScript sprawdzają geometrię, materiały, NoData oraz cienie. Shadery są kompilowane i łączone w rzeczywistym OpenGL ES. Test w prawdziwym Chromium/SwiftShader przełącza dwa miejsca i wraca do pierwszego, sprawdza liczbę aktywnych obrazów, brak błędów GL i wyjątków oraz różnicę obrazu po wyłączeniu zdjęcia. Test śledzi też pojedyncze polecenia GL, aby błędy nie zniknęły przy późniejszym ładowaniu obrazu.

[Pierwszy punkt — zabudowa i otwarty widok](examples/atlas_2.6.0/widok_z_oczu.png), [drugi — skraj lasu](examples/atlas_2.6.0/skraj_lasu.png), [widok z góry](examples/atlas_2.6.0/zdjecie_z_gory.png) i [samodzielny HTML](examples/atlas_2.6.0/scena_3d_NMPT.html). Wszystkie dane i tekstury pól w przykładzie są syntetyczne. PNG są rzeczywistymi zrzutami renderowania w Chromium, nie obrazami wygenerowanymi jako obietnica wyglądu. Dane użytkownika nie są publikowane.

Środowisko testowe: QGIS 3.40.6 / Qt5 / GDAL 3.10.3 / Linux; Chromium/WebGL/SwiftShader. Nie wykonano testów na komputerze użytkownika ani Windows/macOS. Dla pierwszej próby warto przygotować kilka miejsc, ocenić czas i dopiero potem rozszerzać zestaw. Zasady pozostałych map i źródeł opisuje [pełna dokumentacja](NMT_i_NMTP_sciagacz_dokumentacja_i_rozwoj.md).
