"""
tests/test_metrics.py
---------------------
Unit testy dla modułu fmeda.metrics.
Weryfikacja logiki koszyków awarii ISO 26262 i obliczeń SPFM / LFM.
"""

import math
import pytest
import pandas as pd

from fmeda.metrics import (
    FaultBuckets,
    ArchitecturalMetrics,
    classify_fault_buckets,
    compute_metrics,
    analyse,
    SPFM_TARGETS,
    LFM_TARGETS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_spf_df() -> pd.DataFrame:
    """
    Trzy tryby awarii — jeden bezpieczny, dwa SPF z różnym DC.
    Oczekiwane koszyki:
        SF  = 2.0
        DD  = 6.0 * 0.9 = 5.4   (SPF_A)
        RF  = 6.0 * 0.1 = 0.6   (SPF_A)
        DD += 4.0 * 0.6 = 2.4   (SPF_B)
        RF += 4.0 * 0.4 = 1.6   (SPF_B)
    Total = 2 + 5.4 + 0.6 + 2.4 + 1.6 = 12.0
    """
    return pd.DataFrame(
        {
            "FIT_Mode": [2.0, 6.0, 4.0],
            "Safety_Related": [False, True, True],
            "Is_SPF": [False, True, True],
            "DC_Coverage": [0.0, 0.90, 0.60],
            "DC_Latent": [0.0, 0.0, 0.0],
        }
    )


@pytest.fixture
def simple_mpf_df() -> pd.DataFrame:
    """
    Jeden SPF (DC=0.9) + jeden MPF (DC_Latent=0.8).
    SF  = 0
    DD  = 5.0 * 0.9 = 4.5
    RF  = 5.0 * 0.1 = 0.5
    MPF_D = 3.0 * 0.8 = 2.4
    MPF_L = 3.0 * 0.2 = 0.6
    Total = 8.0
    """
    return pd.DataFrame(
        {
            "FIT_Mode": [5.0, 3.0],
            "Safety_Related": [True, True],
            "Is_SPF": [True, False],
            "DC_Coverage": [0.90, 0.0],
            "DC_Latent": [0.0, 0.80],
        }
    )


@pytest.fixture
def all_safe_df() -> pd.DataFrame:
    """Wszystkie tryby awarii bezpieczne (Safety_Related=False)."""
    return pd.DataFrame(
        {
            "FIT_Mode": [5.0, 3.0, 2.0],
            "Safety_Related": [False, False, False],
            "Is_SPF": [False, False, False],
            "DC_Coverage": [0.0, 0.0, 0.0],
            "DC_Latent": [0.0, 0.0, 0.0],
        }
    )


# ---------------------------------------------------------------------------
# Testy: classify_fault_buckets
# ---------------------------------------------------------------------------


class TestClassifyFaultBuckets:
    def test_sf_bucket(self, simple_spf_df):
        """Bezpieczne usterki (Safety_Related=False) → SF."""
        _, buckets = classify_fault_buckets(simple_spf_df)
        assert buckets.SF == pytest.approx(2.0)

    def test_dd_rf_buckets_spf(self, simple_spf_df):
        """SPF: DD + RF = FIT_Mode, podzielony przez DC_Coverage."""
        _, buckets = classify_fault_buckets(simple_spf_df)
        assert buckets.DD == pytest.approx(5.4 + 2.4, rel=1e-6)
        assert buckets.RF == pytest.approx(0.6 + 1.6, rel=1e-6)

    def test_total_fit_preserved(self, simple_spf_df):
        """SF + DD + RF + MPF_D + MPF_L musi być równe sumie wejściowej FIT."""
        _, buckets = classify_fault_buckets(simple_spf_df)
        assert buckets.Total == pytest.approx(simple_spf_df["FIT_Mode"].sum())

    def test_mpf_buckets(self, simple_mpf_df):
        """MPF: MPF_D + MPF_L = FIT_Mode (wiersze Is_SPF=False, Safety_Related=True)."""
        _, buckets = classify_fault_buckets(simple_mpf_df)
        assert buckets.MPF_D == pytest.approx(2.4)
        assert buckets.MPF_L == pytest.approx(0.6)

    def test_all_safe_faults(self, all_safe_df):
        """Wszystkie usterki SF → DD=RF=MPF=0."""
        _, buckets = classify_fault_buckets(all_safe_df)
        assert buckets.SF == pytest.approx(10.0)
        assert buckets.DD == 0.0
        assert buckets.RF == 0.0
        assert buckets.MPF_D == 0.0
        assert buckets.MPF_L == 0.0

    def test_missing_dc_columns_use_defaults(self):
        """Brak kolumn DC → domyślne 0.0 (brak pokrycia diagnostycznego)."""
        df = pd.DataFrame(
            {
                "FIT_Mode": [10.0],
                "Safety_Related": [True],
                "Is_SPF": [True],
            }
        )
        _, buckets = classify_fault_buckets(df)
        assert buckets.RF == pytest.approx(10.0)   # DC=0 → wszystko w RF
        assert buckets.DD == pytest.approx(0.0)

    def test_dc_out_of_range_raises(self):
        """DC_Coverage > 1.0 → ValueError."""
        df = pd.DataFrame(
            {
                "FIT_Mode": [5.0],
                "Safety_Related": [True],
                "Is_SPF": [True],
                "DC_Coverage": [1.5],
                "DC_Latent": [0.0],
            }
        )
        with pytest.raises(ValueError, match="poza zakresem"):
            classify_fault_buckets(df)

    def test_missing_required_column_raises(self):
        """Brak kolumny Safety_Related → KeyError."""
        df = pd.DataFrame({"FIT_Mode": [1.0], "Is_SPF": [True]})
        with pytest.raises(KeyError, match="Brakujące kolumny"):
            classify_fault_buckets(df)

    def test_output_columns_added(self, simple_spf_df):
        """Wynikowy DataFrame musi zawierać kolumny SF, DD, RF, MPF_D, MPF_L."""
        df_out, _ = classify_fault_buckets(simple_spf_df)
        for col in ("SF", "DD", "RF", "MPF_D", "MPF_L"):
            assert col in df_out.columns


# ---------------------------------------------------------------------------
# Testy: compute_metrics
# ---------------------------------------------------------------------------


class TestComputeMetrics:
    def test_spfm_formula(self, simple_spf_df):
        """SPFM = 1 − RF / (Total − SF)."""
        _, buckets = classify_fault_buckets(simple_spf_df)
        metrics = compute_metrics(buckets)
        expected_spfm = 1 - buckets.RF / (buckets.Total - buckets.SF)
        assert metrics.SPFM == pytest.approx(expected_spfm)

    def test_lfm_formula(self, simple_mpf_df):
        """LFM = 1 − MPF_L / (Total − SF − DD − RF)."""
        _, buckets = classify_fault_buckets(simple_mpf_df)
        metrics = compute_metrics(buckets)
        denom = buckets.Total - buckets.SF - buckets.DD - buckets.RF
        expected_lfm = 1 - buckets.MPF_L / denom
        assert metrics.LFM == pytest.approx(expected_lfm)

    def test_spfm_none_when_no_dangerous_faults(self, all_safe_df):
        """Brak usterek niebezpiecznych → SPFM = None."""
        _, buckets = classify_fault_buckets(all_safe_df)
        metrics = compute_metrics(buckets)
        assert metrics.SPFM is None

    def test_perfect_coverage_gives_spfm_one(self):
        """DC=1.0 (100%) → RF=0 → SPFM=100%."""
        buckets = FaultBuckets(SF=0.0, DD=10.0, RF=0.0, MPF_D=0.0, MPF_L=0.0)
        metrics = compute_metrics(buckets)
        assert metrics.SPFM == pytest.approx(1.0)

    def test_no_coverage_gives_low_spfm(self):
        """DC=0 → RF=FIT → SPFM=0%."""
        buckets = FaultBuckets(SF=0.0, DD=0.0, RF=10.0, MPF_D=0.0, MPF_L=0.0)
        metrics = compute_metrics(buckets)
        assert metrics.SPFM == pytest.approx(0.0)

    def test_lfm_none_when_no_mpf(self):
        """Brak usterek wielopunktowych → LFM = None."""
        buckets = FaultBuckets(SF=2.0, DD=5.0, RF=3.0, MPF_D=0.0, MPF_L=0.0)
        metrics = compute_metrics(buckets)
        assert metrics.LFM is None

    def test_spfm_pct_format(self):
        buckets = FaultBuckets(SF=0.0, DD=9.0, RF=1.0, MPF_D=0.0, MPF_L=0.0)
        metrics = compute_metrics(buckets)
        assert metrics.spfm_pct() == "90.00%"

    def test_check_asil_d_pass(self):
        """SPFM=99.5%, LFM=91% → ASIL D: obie zaliczone."""
        buckets = FaultBuckets(SF=0.0, DD=9.95, RF=0.05, MPF_D=9.1, MPF_L=0.9)
        metrics = compute_metrics(buckets)
        result = metrics.check_asil("ASIL D")
        assert result["SPFM_pass"] is True
        assert result["LFM_pass"] is True

    def test_check_asil_d_fail_spfm(self):
        """SPFM=95% < 99% → ASIL D: SPFM nie zaliczony."""
        buckets = FaultBuckets(SF=0.0, DD=9.5, RF=0.5, MPF_D=5.0, MPF_L=0.0)
        metrics = compute_metrics(buckets)
        result = metrics.check_asil("ASIL D")
        assert result["SPFM_pass"] is False

    def test_to_dict_keys(self, simple_mpf_df):
        """to_dict() musi zawierać wszystkie wymagane klucze."""
        _, buckets = classify_fault_buckets(simple_mpf_df)
        metrics = compute_metrics(buckets)
        d = metrics.to_dict()
        for key in ("SF_FIT", "DD_FIT", "RF_FIT", "MPF_D_FIT", "MPF_L_FIT",
                    "Total_FIT", "SPFM", "SPFM_pct", "LFM", "LFM_pct"):
            assert key in d


# ---------------------------------------------------------------------------
# Testy: analyse (convenience wrapper)
# ---------------------------------------------------------------------------


class TestAnalyse:
    def test_analyse_returns_classified_df_and_metrics(self, simple_mpf_df):
        df_out, metrics = analyse(simple_mpf_df)
        assert isinstance(metrics, ArchitecturalMetrics)
        assert "SF" in df_out.columns
        assert metrics.SPFM is not None
        assert metrics.LFM is not None

    def test_analyse_total_fit_consistent(self, simple_mpf_df):
        """FIT sumujący się z koszyków == suma FIT_Mode wejściowego."""
        _, metrics = analyse(simple_mpf_df)
        assert metrics.buckets.Total == pytest.approx(
            simple_mpf_df["FIT_Mode"].sum()
        )
