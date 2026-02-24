"""
fit_calculator.py
-----------------
Obliczanie rzeczywistego wskaźnika awaryjności λ_real zgodnie z normą SN 29500
przy użyciu uproszczonego modelu temperaturowego Arrheniusa.

Wzór:
    λ_real = λ_ref · π_T

    π_T = exp[ (E_a / k) · (1/T_ref − 1/T_real) ]

Gdzie:
    λ_ref  – bazowy wskaźnik FIT z normy SN 29500 [FIT = failures per 10^9 hours]
    E_a    – energia aktywacji [eV], typowo 0.4 eV dla układów scalonych
    k      – stała Boltzmanna = 8.617 × 10⁻⁵ eV/K
    T_ref  – temperatura referencyjna [K], domyślnie 40°C → 313.15 K
    T_real – rzeczywista temperatura pracy [K]
"""

import math

# ---------------------------------------------------------------------------
# Stałe fizyczne
# ---------------------------------------------------------------------------

BOLTZMANN_K: float = 8.617e-5  # eV/K — stała Boltzmanna

# ---------------------------------------------------------------------------
# Funkcje pomocnicze
# ---------------------------------------------------------------------------


def celsius_to_kelvin(t_celsius: float) -> float:
    """Konwertuje temperaturę z °C na K."""
    return t_celsius + 273.15


def calculate_pi_t(
    t_real_celsius: float,
    t_ref_celsius: float = 40.0,
    e_a: float = 0.4,
) -> float:
    """
    Oblicza współczynnik temperaturowy π_T ze wzoru Arrheniusa (SN 29500).

    Parametry
    ----------
    t_real_celsius : float
        Rzeczywista temperatura pracy komponentu [°C].
    t_ref_celsius : float, opcjonalnie
        Temperatura referencyjna z normy SN 29500 [°C]. Domyślnie 40.0 °C.
    e_a : float, opcjonalnie
        Energia aktywacji [eV]. Domyślnie 0.4 eV (typowa dla IC wg SN 29500).

    Zwraca
    -------
    float
        Współczynnik temperaturowy π_T (bezwymiarowy).

    Przykład
    --------
    >>> pi_t = calculate_pi_t(t_real_celsius=85.0)
    >>> print(pi_t)   # ≈ 5.28
    """
    t_real_k = celsius_to_kelvin(t_real_celsius)
    t_ref_k = celsius_to_kelvin(t_ref_celsius)

    exponent = (e_a / BOLTZMANN_K) * ((1.0 / t_ref_k) - (1.0 / t_real_k))
    return math.exp(exponent)


# ---------------------------------------------------------------------------
# Funkcja główna
# ---------------------------------------------------------------------------


def calculate_lambda_real(
    lambda_ref: float,
    t_real_celsius: float,
    t_ref_celsius: float = 40.0,
    e_a: float = 0.4,
) -> float:
    """
    Oblicza rzeczywisty wskaźnik awaryjności λ_real [FIT] wg SN 29500.

    Używa uproszczonego modelu temperaturowego Arrheniusa:
        λ_real = λ_ref · π_T

    Parametry
    ----------
    lambda_ref : float
        Bazowy wskaźnik awaryjności z normy SN 29500 [FIT].
        1 FIT = 1 awaria na 10⁹ godzin pracy.
    t_real_celsius : float
        Rzeczywista temperatura pracy komponentu [°C].
    t_ref_celsius : float, opcjonalnie
        Temperatura referencyjna z normy SN 29500 [°C]. Domyślnie 40.0 °C.
    e_a : float, opcjonalnie
        Energia aktywacji [eV]. Domyślnie 0.4 eV (typowa dla IC wg SN 29500).

    Zwraca
    -------
    float
        Obliczona wartość λ_real zaokrąglona do 2 miejsc po przecinku [FIT].

    Przykład
    --------
    >>> result = calculate_lambda_real(lambda_ref=2.0, t_real_celsius=85.0)
    >>> print(result)   # ≈ 10.56
    """
    pi_t = calculate_pi_t(
        t_real_celsius=t_real_celsius,
        t_ref_celsius=t_ref_celsius,
        e_a=e_a,
    )
    lambda_real = lambda_ref * pi_t
    return round(lambda_real, 2)
