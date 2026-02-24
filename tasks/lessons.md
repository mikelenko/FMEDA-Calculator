# Lessons Learned

## CustomTkinter Compatibility (2026-02-24)

### Problem
Próba użycia parametru `segmented_button_align` w konstruktorze `ctk.CTkTabview` zakończyła się błędem:
`ValueError: ['segmented_button_align'] are not supported arguments.`
Wystąpiło to w wersji `customtkinter == 5.2.2`.

### Przyczyna
Parametr ten (lub jego nazwa) może być specyficzny dla nowszych wersji biblioteki lub został pomylony z parametrami innych widgetów (np. `CTkSegmentedButton` obsługuje podobne wyrównania).

### Rozwiązanie
Zastąpienie `ctk.CTkTabview` własną implementacją opartą na `ctk.CTkSegmentedButton` oraz `ctk.CTkFrame`. Pozwala to na pełną kontrolę nad wyrównaniem przycisków zakładek (np. do lewej strony) oraz uniknięcie błędów braku wsparcia dla argumentów `**kwargs`.

---
*Zasada: Jeśli widget wysokopoziomowy (jak TabView) ogranicza layout, przejdź na kompozycję z widgetów niskopoziomowych (SegmentedButton + Frame).*
