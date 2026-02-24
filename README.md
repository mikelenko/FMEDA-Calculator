# FMEDA Calculator

Profesjonalne narzędzie do analizy **FMEDA (Failure Mode, Effects and Diagnostic Analysis)** dla systemów elektronicznych, opracowane zgodnie z międzynarodowymi normami bezpieczeństwa funkcjonalnego.

## Główne Funkcje

- **SN 29500 (Arrhenius)**: Automatyczne obliczanie rzeczywistych wskaźników awaryjności (λ_real) na podstawie temperatury pracy.
- **IEC 61709 (Failure Modes)**: Dystrybucja FIT na poszczególne tryby awarii (zwarcie, przerwa, dryft) dla różnych klas komponentów.
- **ISO 26262 (Architectural Metrics)**: Obliczanie metryk **SPFM** (Single-Point Fault Metric) oraz **LFM** (Latent Fault Metric) wraz z weryfikacją wymagań dla poziomów ASIL B/C/D.
- **Automatyczny Pipeline**: Przetwarzanie całych projektów na podstawie plików BOM (Excel), z obsługą arkuszy schematów i reguł bezpieczeństwa.

## Struktura Projektu

- `fmeda/`: Rdzeń obliczeniowy (moduły FIT, Failure Modes, Metrics, Pipeline).
- `tests/`: Kompleksowe testy jednostkowe (75 testów).
- `main.py`: Demo end-to-end wykorzystujące dane z pliku Excel.
- `RAPORT.md`: Dokumentacja techniczna i opis teoretyczny.

## Szybki Start

### Wymagania
- Python 3.8+
- pandas
- openpyxl (do obsługi plików Excel)

### Instalacja i uruchomienie demo
```bash
pip install pandas openpyxl pytest
python main.py
```

### Uruchamianie testów
```bash
pytest tests/ -v
```

## Przykładowy Wynik Pipeline
```text
Arkusz                    | SPFM       | LFM        | Status
-----------------------------------------------------------------
4.1.1                     | 99.88%     | 82.50%     | ✅ ASIL D OK
3.3.1                     | 97.40%     | 65.00%     | ⚠ Low LFM
```

---
**Autor:** Antigravity AI
