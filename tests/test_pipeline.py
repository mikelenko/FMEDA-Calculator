"""
tests/test_pipeline.py
----------------------
Unit testy dla klasy FMEDAPipeline.
Używają syntetycznych danych (nie wymagają pliku Excel).
"""

from __future__ import annotations

import warnings

import pandas as pd
import pytest

from fmeda.pipeline import FMEDAPipeline


# ---------------------------------------------------------------------------
# Fixtures — syntetyczne dane testowe
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_fit_db() -> pd.DataFrame:
    """Prosta baza FIT z dwoma typami komponentów."""
    return pd.DataFrame(
        {
            "Footprint": ["RESC0402L", "CAPC0603L", "SOT23-3"],
            "Base_FIT": [1.2, 1.5, 5.0],
            "Component_Class": ["Resistor", "Capacitor", "Transistor_MOSFET"],
        }
    )


@pytest.fixture
def minimal_rules_db() -> pd.DataFrame:
    """Reguły bezpieczeństwa dla arkusza '4.1.1'."""
    return pd.DataFrame(
        {
            "SheetNumber": ["4.1.1", "4.1.1"],
            "Component_Class": ["Resistor", "Transistor_MOSFET"],
            "Safety_Related": [True, True],
            "Is_SPF": [True, False],
            "DC_Coverage": [0.90, 0.0],
        }
    )


@pytest.fixture
def single_component_bom() -> pd.DataFrame:
    """BOM z jednym rezystorem na jednym arkuszu."""
    return pd.DataFrame(
        {
            "Designator": ["R1"],
            "Footprint": ["RESC0402L"],
            "Comment": ["10k 1% 0402"],
            "SheetNumber": ["4.1.1"],
        }
    )


@pytest.fixture
def multi_designator_bom() -> pd.DataFrame:
    """BOM: jeden wiersz z CSV designatorami (jak w prawdziwym BOM)."""
    return pd.DataFrame(
        {
            "Designator": ["R1_1, R1_2, R1_3"],
            "Footprint": ["RESC0402L"],
            "Comment": ["10k 1% 0402"],
            "SheetNumber": ["4.1.1"],
        }
    )


@pytest.fixture
def multi_sheet_bom() -> pd.DataFrame:
    """BOM: jeden wiersz z CSV SheetNumbers."""
    return pd.DataFrame(
        {
            "Designator": ["R1_1, R1_2"],
            "Footprint": ["RESC0402L"],
            "Comment": ["10k"],
            "SheetNumber": ["4.1.1, 4.2.1"],
        }
    )


@pytest.fixture
def multi_component_bom() -> pd.DataFrame:
    """BOM z dwoma różnymi typami komponentów, dwoma arkuszami."""
    return pd.DataFrame(
        {
            "Designator": ["R1_1, R1_2", "C1_1, C1_2"],
            "Footprint": ["RESC0402L", "CAPC0603L"],
            "Comment": ["10k", "47n"],
            "SheetNumber": ["4.1.1", "4.1.1"],
        }
    )


def build_pipeline(bom, fit_db, rules_db, temp=65.0) -> FMEDAPipeline:
    rules = rules_db.copy()
    rules["Local_Temp"] = temp
    return FMEDAPipeline(
        bom_df=bom,
        fit_db=fit_db,
        rules_db=rules,
    )


# ---------------------------------------------------------------------------
# Testy: walidacja wejścia
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_missing_bom_column_raises(self, minimal_fit_db, minimal_rules_db):
        bad_bom = pd.DataFrame({"Designator": ["R1"], "Footprint": ["RESC0402L"]})
        with pytest.raises(KeyError, match="SheetNumber"):
            FMEDAPipeline(bad_bom, minimal_fit_db, minimal_rules_db)

    def test_missing_fit_db_column_raises(self, single_component_bom, minimal_rules_db):
        bad_fit = pd.DataFrame({"Footprint": ["RESC0402L"], "Base_FIT": [1.2]})
        with pytest.raises(KeyError, match="Component_Class"):
            FMEDAPipeline(single_component_bom, bad_fit, minimal_rules_db)

    def test_missing_rules_db_column_raises(self, single_component_bom, minimal_fit_db):
        bad_rules = pd.DataFrame({"SheetNumber": ["4.1.1"], "Component_Class": ["Resistor"]})
        with pytest.raises(KeyError, match="Safety_Related"):
            FMEDAPipeline(single_component_bom, minimal_fit_db, bad_rules)


# ---------------------------------------------------------------------------
# Testy: Krok 1 — explode Designators
# ---------------------------------------------------------------------------


class TestExplodeDesignators:
    def test_csv_designators_explode(self, multi_designator_bom, minimal_fit_db, minimal_rules_db):
        """CSV 'R1_1, R1_2, R1_3' → 3 oddzielne wiersze."""
        p = build_pipeline(multi_designator_bom, minimal_fit_db, minimal_rules_db)
        p.run_pipeline()
        assert len(p.df_exploded) == 3

    def test_single_designator_unchanged(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        """Pojedynczy designator → 1 wiersz."""
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db)
        p.run_pipeline()
        assert len(p.df_exploded) == 1

    def test_designators_stripped(self, multi_designator_bom, minimal_fit_db, minimal_rules_db):
        """Białe znaki wokół designatora usunięte."""
        p = build_pipeline(multi_designator_bom, minimal_fit_db, minimal_rules_db)
        p.run_pipeline()
        for des in p.df_exploded["Designator"]:
            assert des == des.strip()


# ---------------------------------------------------------------------------
# Testy: Krok 2 — merge FIT DB
# ---------------------------------------------------------------------------


class TestMergeFitDB:
    def test_base_fit_added(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db)
        p.run_pipeline()
        assert "Base_FIT" in p.df_with_fit.columns

    def test_unknown_footprint_warning(self, minimal_fit_db, minimal_rules_db):
        """Footprint bez odpowiednika w fit_db → UserWarning."""
        bom = pd.DataFrame({
            "Designator": ["X1"],
            "Footprint": ["UNKNOWN_FP"],
            "Comment": ["?"],
            "SheetNumber": ["4.1.1"],
        })
        p = build_pipeline(bom, minimal_fit_db, minimal_rules_db)
        with pytest.warns(UserWarning, match="Brak Base_FIT"):
            with pytest.raises(ValueError):  # brak komponentów → ValueError
                p.run_pipeline()


# ---------------------------------------------------------------------------
# Testy: Krok 3 — Arrhenius
# ---------------------------------------------------------------------------


class TestArrhenius:
    def test_real_fit_above_base_fit_at_high_temp(
        self, single_component_bom, minimal_fit_db, minimal_rules_db
    ):
        """Real_FIT > Base_FIT przy T=85°C (powyżej T_ref=40°C)."""
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db, temp=85.0)
        p.run_pipeline()
        # Total_FIT w df_failure_modes pochodzi z Real_FIT
        assert p.df_with_fit["Real_FIT"].iloc[0] > minimal_fit_db["Base_FIT"].iloc[0]

    def test_real_fit_equals_base_fit_at_ref_temp(
        self, single_component_bom, minimal_fit_db, minimal_rules_db
    ):
        """Real_FIT ≈ Base_FIT przy T=40°C (punkt referencyjny)."""
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db, temp=40.0)
        p.run_pipeline()
        base = float(minimal_fit_db.loc[minimal_fit_db["Footprint"] == "RESC0402L", "Base_FIT"].iloc[0])
        real = p.df_with_fit["Real_FIT"].iloc[0]
        assert abs(real - base) < 0.02


# ---------------------------------------------------------------------------
# Testy: Krok 4 — Failure Mode Distribution
# ---------------------------------------------------------------------------


class TestFailureModeExpansion:
    def test_resistor_three_modes(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        """Jeden rezystor → 3 tryby awarii (Open, Short, Drift)."""
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db)
        p.run_pipeline()
        assert len(p.df_failure_modes) == 3

    def test_fit_preserved_after_distribution(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        """Suma FIT_Mode ≈ Real_FIT (zachowanie FIT)."""
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db, temp=40.0)
        p.run_pipeline()
        real_fit = p.df_with_fit["Real_FIT"].sum()
        mode_sum = p.df_failure_modes["FIT_Mode"].sum()
        assert abs(mode_sum - real_fit) < 0.05  # tolerancja zaokrągleń

    def test_unknown_class_warning(self, minimal_fit_db, minimal_rules_db):
        """Komponent z nieznanym Component_Class → UserWarning."""
        fit_db_unknown = minimal_fit_db.copy()
        fit_db_unknown.loc[len(fit_db_unknown)] = ["RESC0402L", 1.2, "UnknownClass"]
        bom = pd.DataFrame({
            "Designator": ["R1"],
            "Footprint": ["RESC0402L"],
            "Comment": ["10k"],
            "SheetNumber": ["4.1.1"],
        })
        # Podmień typ na nieznany
        fit_db_only_unknown = pd.DataFrame({
            "Footprint": ["RESC0402L"],
            "Base_FIT": [1.2],
            "Component_Class": ["UnknownClass"],
        })
        p = build_pipeline(bom, fit_db_only_unknown, minimal_rules_db)
        with pytest.warns(UserWarning, match="Brak rozkładu"):
            with pytest.raises(ValueError):
                p.run_pipeline()


# ---------------------------------------------------------------------------
# Testy: Krok 5 — Explode SheetNumber
# ---------------------------------------------------------------------------


class TestExplodeSheets:
    def test_csv_sheets_duplicated_per_sheet(
        self, multi_sheet_bom, minimal_fit_db, minimal_rules_db
    ):
        """Komponent na 2 arkuszach → wyniki dla 2 kluczy w dict."""
        p = build_pipeline(multi_sheet_bom, minimal_fit_db, minimal_rules_db)
        results = p.run_pipeline()
        assert "4.1.1" in results
        assert "4.2.1" in results


# ---------------------------------------------------------------------------
# Testy: Krok 6 — Rules Engine
# ---------------------------------------------------------------------------


class TestRulesEngine:
    def test_safety_related_from_rules(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        """Rezystor na arkuszu 4.1.1 ma regułę Safety_Related=True."""
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db)
        p.run_pipeline()
        sr_values = p.df_classified["Safety_Related"]
        assert sr_values.any()  # przynajmniej jeden wiersz Safety_Related=True

    def test_default_safety_false_without_rule(self, minimal_fit_db):
        """Komponent bez reguły → domyślnie Safety_Related=False."""
        bom = pd.DataFrame({
            "Designator": ["C1"],
            "Footprint": ["CAPC0603L"],
            "Comment": ["47n"],
            "SheetNumber": ["99.9"],  # arkusz bez reguły
        })
        empty_rules = pd.DataFrame({
            "SheetNumber": pd.Series([], dtype=str),
            "Component_Class": pd.Series([], dtype=str),
            "Safety_Related": pd.Series([], dtype=bool),
            "Is_SPF": pd.Series([], dtype=bool),
            "DC_Coverage": pd.Series([], dtype=float),
        })
        p = FMEDAPipeline(bom, minimal_fit_db, empty_rules)
        p.run_pipeline()
        assert not p.df_classified["Safety_Related"].any()

    def test_dc_coverage_applied(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        """DC_Coverage z reguł = 0.90 dla rezystora na 4.1.1."""
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db)
        p.run_pipeline()
        # Rezystor ma Safety_Related=True & Is_SPF=True & DC_Coverage=0.90
        spf_rows = p.df_classified[p.df_classified["Is_SPF"]]
        if not spf_rows.empty:
            assert (spf_rows["DC_Coverage"] - 0.90).abs().max() < 1e-6


# ---------------------------------------------------------------------------
# Testy: Krok 7 — Block-Level Metrics
# ---------------------------------------------------------------------------


class TestBlockMetrics:
    def test_result_is_dict(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db)
        result = p.run_pipeline()
        assert isinstance(result, dict)

    def test_result_keys_are_sheet_names(self, multi_sheet_bom, minimal_fit_db, minimal_rules_db):
        p = build_pipeline(multi_sheet_bom, minimal_fit_db, minimal_rules_db)
        result = p.run_pipeline()
        assert set(result.keys()) == {"4.1.1", "4.2.1"}

    def test_result_has_required_metric_keys(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db)
        result = p.run_pipeline()
        sheet_result = list(result.values())[0]
        for key in ("Total_FIT", "SPFM_pct", "LFM_pct", "n_modes"):
            assert key in sheet_result, f"Missing key: {key}"

    def test_total_fit_positive(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db)
        result = p.run_pipeline()
        total = list(result.values())[0]["Total_FIT"]
        assert total > 0.0

    def test_multi_component_metrics(self, multi_component_bom, minimal_fit_db, minimal_rules_db):
        """Pipeline dla dwóch typów komponentów na tym samym arkuszu."""
        p = build_pipeline(multi_component_bom, minimal_fit_db, minimal_rules_db)
        result = p.run_pipeline()
        assert "4.1.1" in result

    def test_spfm_and_lfm_format(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        """Sprawdza, że SPFM_pct i LFM_pct to stringi z %."""
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db)
        result = p.run_pipeline()
        sheet = list(result.values())[0]
        spfm_pct = sheet["SPFM_pct"]
        assert isinstance(spfm_pct, str)
        assert "%" in spfm_pct or spfm_pct == "N/A"

    def test_properties_accessible_after_run(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        """Właściwości df_exploded, df_with_fit, df_failure_modes, df_classified dostępne po run."""
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db)
        p.run_pipeline()
        assert p.df_exploded is not None
        assert p.df_with_fit is not None
        assert p.df_failure_modes is not None
        assert p.df_classified is not None

    def test_properties_raise_before_run(self, single_component_bom, minimal_fit_db, minimal_rules_db):
        """Właściwości rzucają RuntimeError przed wywołaniem run_pipeline()."""
        p = build_pipeline(single_component_bom, minimal_fit_db, minimal_rules_db)
        with pytest.raises(RuntimeError, match="run_pipeline"):
            _ = p.df_exploded
