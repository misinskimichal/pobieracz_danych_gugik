# Widoczność w QGIS — NMT i NMTP ściągacz 2.9.0

Wydanie z 26 października 2026 r. [ZIP do instalacji](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-2.9.0.zip).

## Co przywrócono i co zmieniono

Model 3D ponownie korzysta z renderera WebGL 1 z wersji 2.7.0. Three.js wprowadzone w 2.8.0 zostało usunięte z bieżącej paczki. Zachowano wcześniejsze kafle ortofotomapy, lokalny detal punktów, budynki, korony i mechanizm zachowania obiektów zapisanych w poprzedniej scenie. Nie obiecujemy nowej rekonstrukcji fotorealistycznej.

Podstawowy przebieg służy analizie i prezentacji w QGIS. Parametry i algorytm obliczeń widoczności, zasady braków danych, promienie, wysokości wirnika oraz interpretacja procentów pozostają takie same. Domyślnie nie generujemy dodatkowego modelu 3D ani PDF/PNG/HTML podczas analizy. Są opcjonalne. Dane modeli nadal zapisujemy do późniejszego przygotowania prezentacji.

## Instalacja i użycie

1. Zainstaluj ZIP przez **Wtyczki → Zarządzanie i instalacja wtyczek → Zainstaluj z ZIP**. Zamknij i uruchom QGIS ponownie; sprawdź wersję **2.9.0** w tytule okna.
2. Wybierz warstwę turbin, wysokości, promienie i kroki NMT/NMPT oraz foldery. Warstwy dróg, zabudowy i obserwatorów są opcjonalne w zwijanej sekcji **Ważne miejsca**.
3. Kliknij **Utwórz atlas widoczności**. Po zakończeniu wynik trafi do QGIS zgodnie z zaznaczoną opcją; jest również przycisk **Pokaż wynik w QGIS**.
4. **Więcej wyników** to jedno menu zawierające promienie, przekrój, raport i ponowne obliczenia. Pozycje wymagające jeszcze nieutworzonych plików są wyłączone. **Anuluj** pojawia się podczas zadania. Dziennik włączasz w tym samym menu tylko wtedy, gdy go potrzebujesz.
5. Aby wrócić do istniejącej analizy, wybierz **Wczytaj report.json**. Zachowaj cały folder, zwłaszcza modele rastrowe. Wczytanie raportu nie przelicza widoczności.

## Wybór dowolnej warstwy kliknięciem w panelu QGIS

Obok każdego pola wyboru warstwy jest mały przycisk **↖** z opisem **Wskaż warstwę w panelu warstw QGIS**. Dotyczy turbin/obszaru pobierania, dróg, zabudowy/działek, obserwatorów, lasów, punktów drzew i ortofotomapy. Działa też w starszych oknach pobierania i analizy punktowej.

1. Kliknij **↖ przy konkretnym polu**.
2. Okno ustawień schowa się, aby panel warstw był dostępny. Kliknij nazwę odpowiedniej warstwy w panelu QGIS. Można ponownie kliknąć warstwę już aktywną.
3. Wyłącznie wskazane pole otrzyma tę warstwę; okno ustawień wróci. Nie ma synchronizacji wszystkich pól z każdą zmianą aktywnej warstwy.

Niepasujący typ, np. poligon w polu turbin albo raster w polu dróg, jest odrzucany bez zmiany wcześniejszego wyboru. Wskaż poprawną warstwę lub kliknij **Anuluj wybór**. Obsługa działa także z okna zaawansowanego, zwalniając modalną blokadę dostępu do panelu.

## Nazwy wyników i daty

Grupa wyników w panelu QGIS ma format:

`Widoczność · nazwa źródłowej warstwy turbin · RRRR-MM-DD GG:mm:ss CET/CEST`

Przykład: `Widoczność · Turbiny_Północ · 2026-10-26 09:07:06 CET`.

Raport zapisuje nazwę i identyfikator źródła oraz rzeczywisty moment utworzenia (`turbine_layer_name`, `turbine_layer_id`, `created_at`). Czas jest przechowywany z informacją o strefie, a pokazywany dla **Europe/Warsaw**, z uwzględnieniem czasu letniego. Rozdzielczość napisu to jedna sekunda. Tę samą tożsamość mają tytuły raportu, układu wydruku i nowej sceny. Warstwy wynikowe zachowują ją też we właściwości `nmt_nmpt/result_title`.

Ponowne otwarcie lub odświeżenie prezentacji zachowuje datę analizy. Nowe obliczenia tworzą nowy folder i nową datę. Turbiny odtworzone z nowego raportu zachowują pierwotną nazwę źródła przy ponownych obliczeniach.

Starsze raporty mogą nie zawierać nazwy wejściowej warstwy. Nie wymyślamy jej: widoczny jest napis **nazwa niezapisana**; datę odczytujemy ze starego `started_at`. Dla nowej analizy wskaż oryginalną warstwę turbin.

## Zwijana Wizualizacja

Wszystkie ustawienia modelu i zdjęć są w domyślnie zwiniętej sekcji **Wizualizacja**. Rozwiń ją tylko wtedy, gdy potrzebujesz HTML. Wybierz model 3D lub zdjęcie; jeden przycisk tworzy albo otwiera wybrany wynik. Szczegółowe parametry są w oknie zaawansowanym dostępnym z tej sekcji. **Ważne miejsca**, krzywizna, wysokość oka i parametry danych mają wpływ na analizę, dlatego pozostają przy analizie.

Nowy HTML modelu ma zamknięte menu **Wizualizacja**. Pozostawiono trzy przyciski: **Patrz na turbinę**, **Przywróć kamerę**, **Zapisz PNG**. Usunięto powtórzony zapis PNG i osobne przyciski robiące to samo co przełączniki. Widok z góry wybiera się z listy widoków, ortofotomapę jednym przełącznikiem, a sposób pokrycia jedną listą: NMPT z obiektami, sama powierzchnia NMPT albo grunt NMT z obiektami. Każdy pozostawiony przycisk przeszedł próbę w rzeczywistej przeglądarce, w tym pobranie pliku PNG.

Pełna scena wymaga WebGL. Łącza prowadzą też do przekroju SVG i lżejszego podglądu Canvas. Ustawienia tego podglądu również są pod menu **Wizualizacja**. Stary HTML na dysku nie zmienia się przez samą instalację: wczytaj raport i utwórz model ponownie, korzystając z zapisanych rastrów.

Budynki i korony potrzebują obrysów lub warstw roślinności. Ortofotomapa nakłada obraz z góry na teren i dachy; nie dostarcza fotografii ścian. Elementy te pozostają poglądowe. Samo NMPT jest powierzchnią 2,5D.

## Zdjęcie i fotomontaż

Fotomontaż pozostaje opcjonalną prezentacją, ukrytą w **Wizualizacji**. Domyślny tryb **Podgląd — bez przesuwania** blokuje przypadkowe przeciąganie kadru i tworzenie masek. Aby świadomie skalibrować aparat, w menu wybierz **Dopasuj kamerę — włącz przeciąganie**. Nie zmienia to współrzędnych ani wysokości turbin; te pochodzą z analizy. Dopasowanie kierunku i kąta widzenia pozostaje ręczną kalibracją fotografii, a nie pomiarem widoczności. Import linków Street View i własnych zdjęć działa jak poprzednio; link Google nie jest samym plikiem zdjęcia.

## Procenty i mapy QGIS

`widoczne_pct = 25%` oznacza np. 5 z 20 sprawdzonych miejsc z potwierdzoną widocznością co najmniej jednej turbiny. Dla drogi sprawdzamy próbki linii, a dla budynku jego otoczenie przy obrysie. Nie jest to 25% powierzchni wirnika. Osobno sprawdź `niepewne_pct` i warstwę jakości. Warstwa **Ile turbin widać** podaje liczbę turbin; **Zakres widocznego wirnika** sprawdza trzy wysokości: koniec łopaty, piastę i dolny zasięg.

## Sprawdzenie

Przeszło 108 testów Python/PyQGIS na QGIS 3.40.6 / Qt5 / GDAL 3.10.3 / Linux. Testy obejmują prawdziwe kliknięcia w `QgsLayerTreeView`, wszystkie osiem pól warstw, odrzucenie niewłaściwej geometrii, anulowanie, dostęp do panelu z okna modalnego, nazwy wyników i strefę czasu, a także dotychczasowe obliczenia i raporty. Przeszły cztery zestawy testów JavaScript.

Test Chromium potwierdził ortofotomapę z poziomu oczu, dwa przełączane punkty i ładowanie lokalnego detalu, trzy sposoby pokrycia, obrót kamery, reset oraz rzeczywisty zapis PNG. Scena kontrolna ma 578 koron i trzy budynki. To dane syntetyczne służące sprawdzeniu renderera, nie dowód dokładności konkretnej inwestycji. Windows/macOS i komputer użytkownika nie były dostępne do prób.


Gotowy ZIP: **40 plików, 195997 bajtów**, SHA-256 `933d1ae66528038f956440fe46e1552e376f640764c34248af2bdf5347298a3d`. Sprawdzenie instalacji rozpakowało właśnie tę paczkę, załadowało ją przez menedżer QGIS i z jej kodu przygotowało model oraz zdjęcie. Sprawdzono pojedynczy zapis PNG, zamkniętą Wizualizację, domyślne wyłączenie eksportu i poprawne wyładowanie wtyczki.

[Domyślny formularz](examples/atlas_2.9.0/formularz.png) · [Rozwinięta Wizualizacja](examples/atlas_2.9.0/wizualizacja.png). Zrzuty wykonano na danych kontrolnych.

Sprawdzono też przywrócony renderer na zapisanych rzeczywistych NMT/NMPT GUGiK i ośmiu kaflach WMS użytych wcześniej, bez nowego pobierania. Porównanie widoku z oczu z ortofotomapą włączoną i wyłączoną zmieniło 1110383 piksele, bez błędów GL. Test fotografii potwierdził blokadę przeciągania, edycję masek i pobranie PNG 2400×1600 oraz JSON. Żaden z tych testów nie stanowi pomiarowej walidacji fotomontażu.
