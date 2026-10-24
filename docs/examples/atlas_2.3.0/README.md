# Przykład 2.3.0 — widok z oczu, dane syntetyczne

Cały model, lasy i podkład są sztuczne. To demonstracja funkcji, nie rzeczywista inwestycja i nie dane użytkownika. Nie zawiera zdjęcia Geoportalu z prób sieciowych.

`scena_3d_NMPT.html` to wynik generatora z osadzonym syntetycznym podkładem. Otwórz lokalnie w przeglądarce z WebGL. Kliknięcie mapki zmienia miejsce. Kamera początkowa jest na NMT +1,7 m, 300 m na północ od wybranej turbiny. Wysokość gruntu w tym położeniu to około 135,03 m modelu, oka około 136,73 m. Parametry turbiny: piasta 55 m, średnica 40 m.

PNG pokazuje rzeczywisty wynik tych samych shaderów i buforów przy kamerze z oczu, odtworzony przez Mesa/EGL. Nie jest fotomontażem ani zrzutem rzeczywistego krajobrazu. Obwiednia sceny ma promień 650 m, siatka 434×434 i krok 3 m; analiza źródłowa była co 1 m.

Lekki plik Canvas nie obsługuje ortofotomapy i oczu; zawiera odnośnik do pełnej sceny. Zachowaj pliki HTML i SVG obok siebie, aby odnośniki działały. Podgląd kamery jest niezależny od starego przekroju; linie przekroju domyślnie są wyłączone w widoku z oczu.
