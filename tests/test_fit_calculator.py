"""
tests/test_fit_calculator.py
----------------------------
Unit testy dla modułu fmeda.fit_calculator.
Sprawdzamy poprawność wzoru Arrheniusa i funkcji obliczających λ_real.
"""

import math
import pytest
from fmeda.fit_calculator import (
    BOLTZMANN_K,
    celsius_to_kelvin,
    calculate_pi_t,
    calculate_lambda_real,
)


# ---------------------------------------------------------------------------
# Testy: celsius_to_kelvin
# ---------------------------------------------------------------------------


class TestCelsiusToKelvin:
    def test_zero_celsius(self):
        assert celsius_to_kelvin(0.0) == pytest.approx(273.15)

    def test_negative_celsius(self):
        assert celsius_to_kelvin(-273.15) == pytest.approx(0.0)

    def test_standard_ref_temp(self):
        """Temperatura referencyjna SN 29500 = 40°C → 313.15 K."""
        assert celsius_to_kelvin(40.0) == pytest.approx(313.15)


# ---------------------------------------------------------------------------
# Testy: calculate_pi_t
# ---------------------------------------------------------------------------


class TestCalculatePiT:
    def test_pi_t_equals_one_at_reference_temperature(self):
        """Gdy T_real = T_ref, π_T musi wynosić dokładnie 1.0 (brak stresu)."""
        pi_t = calculate_pi_t(t_real_celsius=40.0, t_ref_celsius=40.0)
        assert pi_t == pytest.approx(1.0, rel=1e-6)

    def test_pi_t_greater_than_one_above_reference(self):
        """Przy T_real > T_ref wskaźnik awaryjności wzrasta → π_T > 1."""
        pi_t = calculate_pi_t(t_real_celsius=85.0, t_ref_celsius=40.0)
        assert pi_t > 1.0

    def test_pi_t_less_than_one_below_reference(self):
        """Przy T_real < T_ref wskaźnik awaryjności spada → π_T < 1."""
        pi_t = calculate_pi_t(t_real_celsius=25.0, t_ref_celsius=40.0)
        assert pi_t < 1.0

    def test_pi_t_85c_default_params(self):
        """
        Ręczna kalkulacja dla T_real=85°C, T_ref=40°C, E_a=0.4 eV:
            exp( (0.4 / 8.617e-5) · (1/313.15 − 1/358.15) )
        """
        e_a = 0.4
        t_ref_k = 313.15
        t_real_k = 358.15
        expected = math.exp((e_a / BOLTZMANN_K) * (1 / t_ref_k - 1 / t_real_k))
        pi_t = calculate_pi_t(t_real_celsius=85.0)
        assert pi_t == pytest.approx(expected, rel=1e-6)

    def test_pi_t_125c(self):
        """Dla T_real=125°C π_T musi być > π_T(85°C)."""
        pi_t_85 = calculate_pi_t(t_real_celsius=85.0)
        pi_t_125 = calculate_pi_t(t_real_celsius=125.0)
        assert pi_t_125 > pi_t_85

    def test_pi_t_custom_activation_energy(self):
        """Wyższa energia aktywacji → silniejszy efekt temperatury."""
        pi_t_low_ea = calculate_pi_t(t_real_celsius=85.0, e_a=0.3)
        pi_t_high_ea = calculate_pi_t(t_real_celsius=85.0, e_a=0.7)
        assert pi_t_high_ea > pi_t_low_ea


# ---------------------------------------------------------------------------
# Testy: calculate_lambda_real
# ---------------------------------------------------------------------------


class TestCalculateLambdaReal:
    def test_lambda_unchanged_at_reference_temperature(self):
        """Przy T_real = T_ref, λ_real ≈ λ_ref (z uwzględnieniem zaokrąglenia)."""
        result = calculate_lambda_real(lambda_ref=2.0, t_real_celsius=40.0)
        assert result == pytest.approx(2.0, abs=0.01)

    def test_lambda_real_85c(self):
        """
        Przykład z dokumentacji:
            λ_ref=2.0, T_real=85°C → λ_real ≈ 10.56
        """
        result = calculate_lambda_real(lambda_ref=2.0, t_real_celsius=85.0)
        # Weryfikacja ręczna: 2.0 × π_T(85°C)
        expected = round(2.0 * calculate_pi_t(85.0), 2)
        assert result == expected

    def test_lambda_real_increases_with_temperature(self):
        """λ_real musi rosnąć wraz z temperaturą."""
        l_40 = calculate_lambda_real(lambda_ref=1.0, t_real_celsius=40.0)
        l_85 = calculate_lambda_real(lambda_ref=1.0, t_real_celsius=85.0)
        l_125 = calculate_lambda_real(lambda_ref=1.0, t_real_celsius=125.0)
        assert l_40 <= l_85 <= l_125

    def test_lambda_real_proportional_to_lambda_ref(self):
        """Podwojenie λ_ref powinno podwoić λ_real."""
        l1 = calculate_lambda_real(lambda_ref=1.0, t_real_celsius=85.0)
        l2 = calculate_lambda_real(lambda_ref=2.0, t_real_celsius=85.0)
        assert l2 == pytest.approx(2 * l1, abs=0.01)

    def test_return_type_is_float(self):
        result = calculate_lambda_real(lambda_ref=1.5, t_real_celsius=70.0)
        assert isinstance(result, float)

    def test_rounding_to_two_decimal_places(self):
        """Wynik musi być zaokrąglony do 2 miejsc po przecinku."""
        result = calculate_lambda_real(lambda_ref=1.0, t_real_celsius=75.0)
        # Sprawdź, że zaokrąglenie jest prawidłowe
        assert result == round(result, 2)
