# NMT i NMTP ściągacz 2.3.1 — ortofotomapa w HTML 3D

Wydanie z 24 października 2026 r. Poprawia aktualizowanie sceny po wyborze zdjęcia i ułatwia rozpoznanie, na którym etapie obraz znika. Kamera z poziomu oczu oraz wskazywanie miejsca pozostają zgodne z [instrukcją 2.3.0](Instrukcja_ATLAS_2.3.0.md).

ZIP: 132536 bajtów; SHA-256: `b6b872d981f68fc4e165ea2c18a2364523b96bda269b9c1dceba7fa3bab4b207`.

## Instalacja i aktualizacja istniejącego wyniku

[Pobierz ZIP 2.3.1](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-2.3.1.zip). W QGIS: **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP**. Po instalacji uruchom QGIS ponownie.

1. Otwórz wtyczkę i użyj **Wczytaj poprzedni atlas · report.json**, jeśli poprzedniego wyniku nie ma już w formularzu. Zachowaj cały folder atlasu z modelami terenu i powierzchni.
2. W ustawieniach szczegółowej sceny wybierz **Wybrana warstwa rastrowa QGIS** i wskaż ortofotomapę, która działa w zwykłym widoku. Wybór warstwy automatycznie zaznacza **Nałóż ortofotomapę na model 3D**. Alternatywnie wybierz źródło Geoportal online.
3. Kliknij **Scena 3D**. Po zmianie źródła lub innych ustawień sceny przycisk najpierw przygotuje aktualny HTML, a dopiero po ukończeniu otworzy przeglądarkę. Etap jest widoczny w formularzu. **Odśwież samą scenę 3D / ortofotomapę** nadal działa jako osobna operacja.
4. W otwartym HTML powinna pojawić się informacja **Ortofotomapa … wczytana** oraz zdjęcie na mapce i na modelu. Kliknij mapkę, aby wybrać miejsce patrzenia; oko domyślnie znajduje się 1,7 m nad gruntem NMT.

Odświeżenie czyta zapisane modele. Nie pobiera ponownie NMT/NMPT i nie uruchamia obliczeń widoczności. Może pobrać samo zdjęcie ze źródła sieciowego. Zmiana opcji sceny nie zmienia zapisanych rastrów analizy. Odczyt wcześniejszego raportu zachowuje jego opcję włączenia/wyłączenia zdjęcia; dopiero świadomy wybór nowego źródła je włącza.

## Co zostało poprawione

W poprzednim kodzie wybór warstwy w formularzu nie przebudowywał istniejącego pliku HTML, a **Scena 3D** otwierała poprzedni plik. Teraz zmiany źródła, punktu kamery, oka, promienia i gęstości siatki są śledzone. Otwarcie sceny ze starszej wersji również uruchamia jej odświeżenie. Przy niezmienionych ustawieniach gotowy HTML jest otwierany od razu.

Zapisany HTML pozostaje samodzielnym plikiem ze zdjęciem osadzonym jako PNG. Wcześniej otwarta karta przeglądarki nie zmienia treści automatycznie — należy użyć przycisku we wtyczce, aby otworzyć aktualną scenę, lub odświeżyć tę kartę po zakończeniu eksportu. Akcje w panelu warstw QGIS otwierają ostatnio zapisane pliki; ustawienia należy aktualizować w formularzu.

## Rozpoznanie problemu ze zdjęciem

Formularz ma informację, czy obraz został osadzony w HTML, oraz przycisk **Pokaż wyeksportowane zdjęcie PNG**. Pozwala to sprawdzić wynik eksportu bez WebGL.

| Objaw | Co oznacza i co sprawdzić |
|---|---|
| Eksport zdjęcia nie powiódł się | Komunikat podaje błąd źródła/renderowania. Sprawdź wybór warstwy i jej pokrycie dla całego obszaru sceny; można wybrać lokalny raster lub Geoportal. |
| HTML nie zawiera ortofotomapy | Zdjęcie nie zostało osadzone. Włącz nakładanie zdjęcia, wskaż źródło i odśwież scenę. |
| PNG jest poprawne, a HTML nie pokazuje zdjęcia nawet na mapce | Sprawdź komunikat dekodowania obrazu i czy otwierasz nowo zapisany HTML. |
| Zdjęcie jest na mapce, ale brak go na modelu | Dekodowanie się udało; komunikat podaje problem nakładania przez WebGL/kartę graficzną. PNG nadal można pobrać z HTML. |

Przeglądarka ogranicza wielkość tekstury do `MAX_TEXTURE_SIZE` urządzenia. Jeżeli osadzony obraz jest większy, przed wysłaniem do WebGL zostaje zmniejszony z zachowaniem proporcji. Ta operacja nie zmienia pliku PNG ani siatki terenu. Odczytane zdjęcie jest używane na mapce także wtedy, gdy przesłanie do WebGL zgłosi błąd. Błędy wcześniejszego rysowania są oddzielane od błędu wysyłania tekstury. Brak WebGL nadal kieruje do lekkiego podglądu, który nie obsługuje ortofotomapy ani kamery z oczu.

Sam fakt, że warstwa działa w QGIS 2D, nie rozstrzyga, czy błąd konkretnego HTML powstał przy eksporcie, dekodowaniu czy nakładaniu obrazu. Wydanie naprawia potwierdzony problem otwierania nieaktualnego HTML i dodaje diagnostykę pozostałych etapów; nie deklaruje rozpoznania nieudostępnionego pliku użytkownika.

## Weryfikacja

75 testów Python/QGIS oraz trzy zestawy testów JavaScript. Nowy test przechodzi przez odczyt wcześniejszego raportu, wybór lokalnego RGB, kliknięcie **Scena 3D**, asynchroniczny eksport, osadzenie PNG i otwarcie dopiero gotowego HTML. Sprawdza niezmienione hashe rastrów widoczności oraz brak ponownej analizy. Drugi test potwierdza czytelny błąd przy braku wybranego zdjęcia i brak automatycznego otwarcia starego HTML. JavaScript sprawdza limit rozmiaru tekstury, pobranie PNG, odrębne raportowanie błędów GPU oraz zachowanie zdjęcia na mapce po nieudanym nałożeniu. Shadery zostały również skompilowane i połączone w rzeczywistym kontekście OpenGL ES (Mesa/EGL).

Środowisko: QGIS 3.40.6 / Qt5 / GDAL 3.10.3 / Linux. Testy sterowania JavaScript korzystają z symulowanego DOM i WebGL; test kompilacji shaderów korzysta z rzeczywistego OpenGL ES. Nie wykonano testu w przeglądarce na komputerze użytkownika ani testów Windows/macOS.
