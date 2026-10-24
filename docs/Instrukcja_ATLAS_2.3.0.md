# NMT i NMTP ściągacz 2.3.0 — ortofotomapa i widok z poziomu oczu

Wydanie poprawia przygotowanie tekstury i dodaje kamerę umieszczoną w konkretnym miejscu nad gruntem. Można odświeżyć samą prezentację na podstawie zapisanych rastrów, bez ponownego pobierania NMT/NMPT i liczenia widoczności.

## Instalacja

[Pobierz ZIP 2.3.0](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-2.3.0.zip). QGIS → **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP**. Po aktualizacji uruchom QGIS ponownie.

ZIP ma 131451 bajtów; SHA-256: `877cf9bb213e230c84805d6a0d74a4be19c0ba7f0e38a44f08ef7b58c3c58c51`.

Wymagania bez zmian: QGIS 3.28–3.x, Python ≥3.9 i biblioteki środowiska QGIS. Scena z ortofotomapą i kamerą z oczu wymaga WebGL w przeglądarce. Lekki podgląd Canvas ma teraz wyraźne oznaczenie, że nie oferuje tych funkcji, oraz odnośnik do pełnej sceny. Testowano QGIS 3.40.6 / Qt5 / GDAL 3.10.3 na Linux; nie deklarujemy bezpośredniego testu Windows/macOS.

## Jak poprawić istniejący wynik

1. Otwórz wtyczkę i kliknij **Wczytaj report.json** z dotychczasowego katalogu atlasu. Zachowaj cały ten katalog, w tym rastry w podfolderach `NMT`/`NMPT`.
2. W części 3D zaznacz **Nałóż ortofotomapę na model 3D**.
3. Wybierz źródło:
   - **Geoportal · ortofotomapa online** — wtyczka pobiera obraz z publicznej usługi GUGiK.
   - **Wybrana warstwa rastrowa QGIS** — wskaż konkretną ortofotomapę, WMS, WMTS, XYZ lub lokalny raster zdjęciowy. W tym trybie pozostałe warstwy projektu nie zasłonią zdjęcia.
   - **Widoczne warstwy projektu · zaawansowane** — zachowuje możliwość utworzenia tekstury z wielu warstw; użytkownik musi zadbać o ich kolejność i widoczność.
4. Pozostaw **Otwórz scenę z poziomu oczu**. Początkowa wysokość pochodzi z pola oka nad NMT, zwykle 1,7 m; w przeglądarce można ją zmieniać niezależnie.
5. Opcjonalnie kliknij **Wskaż miejsce patrzenia w QGIS**, a potem kliknij drogę, działkę lub inne miejsce w mapie. Escape anuluje wybór i przywraca poprzednie narzędzie.
6. Kliknij **Odśwież samą scenę 3D / ortofotomapę · bez przeliczania widoczności**.
7. Otwórz **Scena 3D**. Jeżeli wcześniej otwarta karta pokazuje starszy widok, odśwież ją. Nagłówek nowej sceny podaje wersję 2.3.0.

Stare HTML-e nie aktualizują się od samej instalacji nowego ZIP-a — trzeba je wygenerować ponownie powyższym przyciskiem albo utworzyć nowy atlas.

Odświeżenie korzysta z `terrain.tif` i `elevation.tif` zapisanych w katalogu wyniku. Nie uruchamia silnika pobierania ani algorytmu widoczności. Rastry `count.tif`, `hub.tif`, `bottom.tif`, `quality.tif` i ich statystyki pozostają z poprzednich obliczeń. Tekstura internetowa może wymagać połączenia z siecią. Obraz oraz HTML zostają osadzone lokalnie.

Jeśli dawny atlas nie zawiera wymaganych modeli prezentacji, komunikat poda brakujący plik. Wtedy należy wykonać normalne ponowne przeliczenie, korzystając z lokalnych folderów źródłowych.

## Wybieranie miejsca i patrzenie z oczu

W pełnej scenie jest mapka z ortofotomapą. **Kliknięcie mapki wybiera położenie kamery i włącza widok z oczu.** Czerwony punkt oznacza wybraną turbinę, niebieski miejsce patrzenia. Pozycję można również wskazać wcześniej w QGIS; współrzędne są przeliczane do EPSG:2180.

Wysokość kamery = **grunt NMT w tym miejscu + podana wysokość oka**. Kamera nie jest automatycznie przenoszona na dach ani koronę z NMPT. Przegląd modelu z góry pozostaje oddzielnym trybem.

Sterowanie w widoku z oczu:

- **Oko nad NMT:** wysokość od 0,3 do 100 m, domyślnie 1,7 m.
- Przeciąganie myszą rozgląda się ze stałego miejsca; pozwala patrzeć także w dół i ku górze.
- **Patrz na turbinę** kieruje kamerę na piastę.
- Po kliknięciu sceny strzałki / W A S D przesuwają położenie o 2 m; Shift zwiększa krok do 10 m.
- Kółko myszy zmienia kąt widzenia, bez przesuwania obserwatora w powietrzu.
- Pion jest ustawiony na 1:1, a rzut na perspektywę. Kontrolki mogą być w tym trybie zablokowane celowo.
- **Przywróć kamerę** wraca do przeglądu modelu z góry.

Bez wskazanego punktu program próbuje znaleźć otwarte miejsce wewnątrz sceny. Użytkownik może od razu wybrać własne. Przy wskazanym punkcie nie zastępujemy go ukradkiem innym położeniem. Jeśli brakuje gruntu albo punkt znajduje się poza sceną, pojawia się komunikat. Gdy NMPT umieściłoby oko pod dachem lub koroną, kamera zgłasza konflikt. Można wybrać drogę/otwarte miejsce, zmienić wysokość lub świadomie oglądać sam NMT.

Wysokość pod kamerą jest obliczana z **tego samego trójkąta siatki, który jest rysowany**. Nie używamy interpolacji biliniowej, która w siodle pomiędzy czterema punktami mogłaby umieścić oko poniżej widocznej powierzchni. Bliska płaszczyzna kamery w tym trybie wynosi około 0,1 m, aby nie wycinać gruntu kilka metrów przed obserwatorem.

Jeśli punkt wskazany w QGIS leży poza dotychczasowym małym zasięgiem sceny, ale wewnątrz obliczonego koła, scena może zostać rozszerzona, aby go objąć. Jej rzeczywisty krok podaje nagłówek — większy zasięg przy tej samej liczbie punktów może być rzadszy. Punkt poza obliczonym kołem wymaga większego zasięgu analizy lub bliższego miejsca; samo odświeżenie nie pobiera nowych modeli.

## Dlaczego wcześniej mogło być szaro

Kod 2.2.0 zbierał do tekstury wszystkie widoczne warstwy projektu. Raster wysokości lub cieniowania mógł więc zasłonić zdjęcie. Renderer nie miał też wymuszonego oczekiwania na kafle sieciowe; w niektórych konfiguracjach mógł zapisać obraz zanim dotarły. Bez raportu konkretnego uruchomienia nie rozstrzygamy, która przyczyna wystąpiła na komputerze użytkownika.

W 2.3.0:

1. Można wskazać jedną warstwę zdjęciową, niezależnie od pozostałych warstw.
2. Renderer używa `RenderBlocking`, ale działa asynchronicznie — czeka na kafle bez blokowania interfejsu QGIS.
3. W trybie pojedynczej warstwy używany jest jej klon z wyłączonym ograniczeniem skali i pełną nieprzezroczystością. Ustawienia oryginalnej warstwy w projekcie pozostają nienaruszone.
4. Tło renderowania jest przezroczyste. Pusty/przezroczysty lub jednolicie szary/biały wynik jest odrzucany z komunikatem; nie zapisujemy go jako rzekomo poprawnej ortofotomapy. Jednolicie jasne prawdziwe zdjęcie może wymagać wybrania innego źródła lub terminu.
5. HTML wyraźnie pokazuje, czy ortofotomapa została wczytana, nie istnieje czy wystąpił błąd. Nie ma już cichego przejścia do szarego zastępnika.
6. Części przezroczystego obrazu są mieszane z kolorem modelu, zamiast zamieniać brak obrazu w czarną powierzchnię.

Tryb Geoportalu używa publicznego WMS `ORTO/WMS/StandardResolution`, warstwy `Raster`. Pobiera obraz w EPSG:3857 z krótką, zaokrągloną na zewnątrz obwiednią, a następnie przelicza go do **dokładnej obwiedni sceny w EPSG:2180**. To zachowuje dopasowanie zdjęcia do modelu. Zadanie ma limit wielkości odpowiedzi, timeouty i anulowanie. Nie zapisuje loginów, haseł ani źródłowego URI prywatnej warstwy w danych tekstury.

W `details[].texture_info` są wymiary, tryb i udział pokrycia obrazu; `texture_layers` wskazuje nazwę źródła. `scene_texture_error` zapisuje problem pobierania/renderowania. Dostępność i pokrycie zewnętrznego źródła nie są gwarantowane — można wybrać inną warstwę lub lokalne zdjęcie.

## Co oznacza taki podgląd

To kamera w modelu powierzchni NMT/NMPT z nałożoną ortofotomapą. Zdjęcie z góry nie odtworzy prawdziwych elewacji budynków, spodów koron i prześwitów. NMPT pozostaje modelem 2,5D, więc na stromych bokach obiektów tekstura może być rozciągnięta. Nie jest to Street View ani pełna rekonstrukcja fotogrametryczna.

Zmiana miejsca i oka w przeglądarce **nie przelicza map widoczności**. Linie profilu dotyczą pierwotnego obserwatora przekroju i są domyślnie wyłączone przy wejściu do widoku z oczu, aby nie pomylić ich z nową pozycją. Do nowej analizy z inną wysokością oka służy **Przelicz ponownie · lokalne modele**. Podgląd kamery jest lokalny i płaski; wynik analizy i przekrój zachowują wybraną korektę krzywizny/refrakcji.

## Weryfikacja

73 testy Python/QGIS obejmują opóźniony serwer XYZ, oczekiwanie na zdjęcie z działającym timerem GUI, ignorowanie szarego rastra powyżej ortofotomapy, zachowanie przezroczystości i ograniczeń skali oryginału, odrzucanie pustego/szarego obrazu, reprojekcję Geoportalu, odświeżenie bez zmiany hashów wyników analizy, wskazanie punktu QGIS z przywróceniem narzędzia oraz wysokość kamery na trójkącie siatki. JavaScript sprawdza również wybór z mapki, ruch, patrzenie w dół, niezmienność położenia podczas rozglądania i komunikaty ładowania obrazu. Zweryfikowano shadery GLSL ES 1.00 oraz pełne pobranie i dopasowanie rzeczywistej ortofotomapy Geoportalu 2048×2048 na publicznym obszarze testowym.

Zasady pozostałych map, procentów i wariantów obliczeń opisują [instrukcja 2.2.0](Instrukcja_ATLAS_2.2.0.md) i [pełna dokumentacja](NMT_i_NMTP_sciagacz_dokumentacja_i_rozwoj.md).
