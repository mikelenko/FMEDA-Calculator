"""
tests/test_failure_modes.py
---------------------------
Unit testy dla modułu fmeda.failure_modes.
"""

import pandas as pd
import pytest

from fmeda.failure_modes import (
    DEFAULT_FAILURE_MODES,
    distribute_failure_modes,
    validate_failure_modes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def single_resistor_bom() -> pd.DataFrame:
    """BOM z jednym rezystorem R1, Total_FIT = 10.0."""
    return pd.DataFrame(
        {
            "Designator": ["R1"],
            "Component_Type": ["Resistor"],
            "Total_FIT": [10.0],
        }
    )


@pytest.fixture
def multi_component_bom() -> pd.DataFrame:
    """BOM z kilkoma komponentami różnych typów."""
    return pd.DataFrame(
        {
            "Designator": ["R1", "R2", "C1", "U1"],
            "Component_Type": ["Resistor", "Resistor", "Capacitor", "IC_Digital"],
            "Total_FIT": [10.0, 5.0, 8.0, 20.0],
        }
    )


@pytest.fixture
def custom_failure_modes() -> dict:
    return {
        "Resistor": {"Open Circuit": 0.60, "Short Circuit": 0.10, "Drift": 0.30},
        "Capacitor": {"Short Circuit": 0.50, "Open Circuit": 0.30, "Drift": 0.20},
    }


# ---------------------------------------------------------------------------
# Testy: validate_failure_modes
# ---------------------------------------------------------------------------


class TestValidateFailureModes:
    def test_default_modes_are_valid(self):
        """Domyślne rozkłady IEC 61709 muszą się sumować do 1.0."""
        validate_failure_modes(DEFAULT_FAILURE_MODES)  # nie rzuca wyjątku

    def test_invalid_modes_raise_error(self):
        bad_modes = {"Resistor": {"Open": 0.5, "Short": 0.3}}  # suma = 0.8
        with pytest.raises(ValueError, match="sumuje się do"):
            validate_failure_modes(bad_modes)

    def test_valid_custom_modes(self):
        valid = {"TestType": {"ModeA": 0.7, "ModeB": 0.3}}
        validate_failure_modes(valid)  # nie rzuca wyjątku


# ---------------------------------------------------------------------------
# Testy: distribute_failure_modes — pojedynczy komponent
# ---------------------------------------------------------------------------


class TestDistributeSingleComponent:
    def test_resistor_produces_three_rows(self, single_resistor_bom):
        result = distribute_failure_modes(single_resistor_bom)
        assert len(result) == 3  # Open, Short, Drift

    def test_resistor_fit_values(self, single_resistor_bom):
        """R1: Total_FIT=10 → Open=6.0, Short=1.0, Drift=3.0."""
        result = distribute_failure_modes(single_resistor_bom)
        fit_by_mode = dict(
            zip(result["Failure_Mode"], result["FIT_Mode"])
        )
        assert fit_by_mode["Open Circuit"] == pytest.approx(6.0)
        assert fit_by_mode["Short Circuit"] == pytest.approx(1.0)
        assert fit_by_mode["Drift"] == pytest.approx(3.0)

    def test_fit_mode_sums_to_total(self, single_resistor_bom):
        """Suma FIT_Mode musi być równa Total_FIT."""
        result = distribute_failure_modes(single_resistor_bom)
        assert result["FIT_Mode"].sum() == pytest.approx(10.0)

    def test_all_rows_have_same_designator(self, single_resistor_bom):
        result = distribute_failure_modes(single_resistor_bom)
        assert (result["Designator"] == "R1").all()


# ---------------------------------------------------------------------------
# Testy: distribute_failure_modes — wiele komponentów
# ---------------------------------------------------------------------------


class TestDistributeMultiComponent:
    def test_row_count(self, multi_component_bom):
        """R1(3) + R2(3) + C1(3) + U1(3) = 12 wierszy."""
        result = distribute_failure_modes(multi_component_bom)
        assert len(result) == 12

    def test_total_fit_preserved(self, multi_component_bom):
        """Suma FIT_Mode == suma Total_FIT (= 10 + 5 + 8 + 20 = 43)."""
        result = distribute_failure_modes(multi_component_bom)
        assert result["FIT_Mode"].sum() == pytest.approx(43.0)

    def test_per_component_fit_preserved(self, multi_component_bom):
        """Suma FIT_Mode per komponent == jego Total_FIT."""
        result = distribute_failure_modes(multi_component_bom)
        grouped = result.groupby("Designator")["FIT_Mode"].sum()
        assert grouped["R1"] == pytest.approx(10.0)
        assert grouped["R2"] == pytest.approx(5.0)
        assert grouped["C1"] == pytest.approx(8.0)
        assert grouped["U1"] == pytest.approx(20.0)

    def test_output_columns(self, multi_component_bom):
        result = distribute_failure_modes(multi_component_bom)
        expected_cols = {
            "Designator",
            "Component_Type",
            "Total_FIT",
            "Failure_Mode",
            "Mode_Ratio",
            "FIT_Mode",
        }
        assert expected_cols.issubset(set(result.columns))


# ---------------------------------------------------------------------------
# Testy: obsługa błędów
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_unknown_component_type_raises_key_error(self):
        df = pd.DataFrame(
            {
                "Designator": ["X1"],
                "Component_Type": ["UnknownWidget"],
                "Total_FIT": [5.0],
            }
        )
        with pytest.raises(KeyError, match="UnknownWidget"):
            distribute_failure_modes(df)

    def test_missing_column_raises_key_error(self):
        df = pd.DataFrame({"Designator": ["R1"], "Total_FIT": [10.0]})
        with pytest.raises(KeyError, match="Brakujące kolumny"):
            distribute_failure_modes(df)

    def test_custom_failure_modes(self, custom_failure_modes):
        df = pd.DataFrame(
            {
                "Designator": ["R1", "C1"],
                "Component_Type": ["Resistor", "Capacitor"],
                "Total_FIT": [10.0, 8.0],
            }
        )
        result = distribute_failure_modes(df, failure_modes=custom_failure_modes)
        assert len(result) == 6  # 3 + 3
        assert result["FIT_Mode"].sum() == pytest.approx(18.0)
