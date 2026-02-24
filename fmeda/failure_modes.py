"""
failure_modes.py
----------------
Rozkład trybów awarii (Failure Mode Distribution) komponentów elektronicznych
zgodnie z normą IEC 61709.

Moduł "rozmnaża" wiersze BOM tak, aby jeden komponent o całkowitym FIT
został podzielony na kilka wierszy odpowiadających jego trybom awarii,
z proporcjonalnym rozdziałem wartości FIT.
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Domyślne rozkłady trybów awarii (IEC 61709)
# ---------------------------------------------------------------------------

DEFAULT_FAILURE_MODES: dict[str, dict[str, float]] = {
    "Resistor": {
        "Open Circuit": 0.60,
        "Short Circuit": 0.10,
        "Drift": 0.30,
    },
    "Capacitor_Ceramic": {
        "Short Circuit": 0.70,
        "Open Circuit": 0.15,
        "Drift": 0.15,
    },
    "Capacitor_Electrolytic": {
        "Short Circuit": 0.50,
        "Open Circuit": 0.30,
        "Drift": 0.20,
    },
    "Capacitor": {
        "Short Circuit": 0.50,
        "Open Circuit": 0.30,
        "Drift": 0.20,
    },
    "IC_Digital": {
        "Loss of Function": 0.50,
        "Incorrect Output": 0.30,
        "Short Circuit": 0.20,
    },
    "IC_Analog": {
        "Drift": 0.40,
        "Loss of Function": 0.35,
        "Short Circuit": 0.25,
    },
    "Transistor_MOSFET": {
        "Short Circuit": 0.55,
        "Open Circuit": 0.30,
        "Drift": 0.15,
    },
    "Diode": {
        "Short Circuit": 0.50,
        "Open Circuit": 0.35,
        "Drift": 0.15,
    },
    "Inductor": {
        "Open Circuit": 0.55,
        "Short Circuit": 0.25,
        "Drift": 0.20,
    },
    "Connector": {
        "Open Circuit": 0.70,
        "Short Circuit": 0.20,
        "Intermittent Contact": 0.10,
    },
    "Crystal_Oscillator": {
        "No Oscillation": 0.60,
        "Frequency Drift": 0.30,
        "Short Circuit": 0.10,
    },
}


# ---------------------------------------------------------------------------
# Walidacja
# ---------------------------------------------------------------------------


def validate_failure_modes(
    failure_modes: dict[str, dict[str, float]],
    tolerance: float = 1e-6,
) -> None:
    """
    Sprawdza, czy rozkłady procentowe sumują się do 1.0 dla każdego typu.

    Parametry
    ----------
    failure_modes : dict
        Słownik {Component_Type: {Mode: ratio, ...}}.
    tolerance : float
        Dopuszczalna tolerancja przy porównaniu sumy do 1.0.

    Rzuca
    ------
    ValueError
        Gdy suma udziałów nie wynosi 1.0 (±tolerance).
    """
    for comp_type, modes in failure_modes.items():
        total = sum(modes.values())
        if abs(total - 1.0) > tolerance:
            raise ValueError(
                f"Rozkład dla '{comp_type}' sumuje się do {total:.6f}, "
                f"a powinien wynosić 1.0 (tolerancja={tolerance})"
            )


# ---------------------------------------------------------------------------
# Główna funkcja
# ---------------------------------------------------------------------------


def distribute_failure_modes(
    df_bom: pd.DataFrame,
    failure_modes: dict[str, dict[str, float]] | None = None,
    *,
    designator_col: str = "Designator",
    type_col: str = "Component_Type",
    fit_col: str = "Total_FIT",
) -> pd.DataFrame:
    """
    Rozmnaża wiersze BOM na tryby awarii z proporcjonalnym podziałem FIT.

    Jeden komponent (np. 'R1' z Total_FIT=10.0) jest dzielony na N wierszy,
    po jednym na każdy tryb awarii, z kolumną FIT_Mode = Total_FIT × udział%.

    Parametry
    ----------
    df_bom : pd.DataFrame
        Tabela BOM z kolumnami [Designator, Component_Type, Total_FIT]
        (nazwy kolumn konfigurowalne).
    failure_modes : dict, opcjonalnie
        Słownik rozkładów {Component_Type: {Mode: ratio, ...}}.
        Domyślnie używa DEFAULT_FAILURE_MODES (IEC 61709).
    designator_col : str
        Nazwa kolumny z identyfikatorem komponentu.
    type_col : str
        Nazwa kolumny z typem komponentu.
    fit_col : str
        Nazwa kolumny z całkowitym FIT.

    Zwraca
    -------
    pd.DataFrame
        Nowy DataFrame z kolumnami:
        [Designator, Component_Type, Total_FIT, Failure_Mode, Mode_Ratio, FIT_Mode]

    Rzuca
    ------
    KeyError
        Gdy typ komponentu nie istnieje w słowniku failure_modes.
    ValueError
        Gdy sumy procentowe w failure_modes nie wynoszą 1.0.

    Przykład
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     'Designator': ['R1'],
    ...     'Component_Type': ['Resistor'],
    ...     'Total_FIT': [10.0],
    ... })
    >>> result = distribute_failure_modes(df)
    >>> print(result[['Designator', 'Failure_Mode', 'FIT_Mode']])
      Designator  Failure_Mode  FIT_Mode
    0         R1  Open Circuit       6.0
    1         R1  Short Circuit      1.0
    2         R1          Drift      3.0
    """
    if failure_modes is None:
        failure_modes = DEFAULT_FAILURE_MODES

    # Waliduj rozkłady
    validate_failure_modes(failure_modes)

    # Sprawdź, czy wymagane kolumny istnieją
    required = {designator_col, type_col, fit_col}
    missing = required - set(df_bom.columns)
    if missing:
        raise KeyError(f"Brakujące kolumny w DataFrame: {missing}")

    # Sprawdź, czy wszystkie typy komponentów mają zdefiniowane rozkłady
    bom_types = set(df_bom[type_col].unique())
    known_types = set(failure_modes.keys())
    unknown = bom_types - known_types
    if unknown:
        raise KeyError(
            f"Brak rozkładu trybów awarii dla typów: {unknown}. "
            f"Dodaj je do słownika failure_modes. "
            f"Dostępne typy: {sorted(known_types)}"
        )

    # --- Vectorized approach via merge ---
    # 1. Budujemy DataFrame z rozkładami trybów awarii
    modes_records = []
    for comp_type, modes in failure_modes.items():
        for mode_name, ratio in modes.items():
            modes_records.append(
                {
                    type_col: comp_type,
                    "Failure_Mode": mode_name,
                    "Mode_Ratio": ratio,
                }
            )
    df_modes = pd.DataFrame(modes_records)

    # 2. Merge BOM × tryby awarii (inner join — filtruje do istniejących typów)
    df_result = df_bom.merge(df_modes, on=type_col, how="inner")

    # 3. Oblicz FIT per tryb awarii
    df_result["FIT_Mode"] = (df_result[fit_col] * df_result["Mode_Ratio"]).round(2)

    # 4. Sortowanie dla czytelności
    df_result = df_result.sort_values(
        [designator_col, "FIT_Mode"], ascending=[True, False]
    ).reset_index(drop=True)

    return df_result
