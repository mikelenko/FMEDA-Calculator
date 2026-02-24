"""
metrics.py
----------
Obliczanie metryk architektonicznych ISO 26262 Part 5 / Part 10:
    - SPFM  – Single-Point Fault Metric
    - LFM   – Latent Fault Metric

Logika klasyfikacji koszyków awarii:
┌─────────────────────────────────┬─────────────────────────────────────┐
│ Warunek                         │ Wynik                               │
├─────────────────────────────────┼─────────────────────────────────────┤
│ Safety_Related == False         │ →  SF  (Safe Fault)                 │
│ Safety_Related=T, Is_SPF=True   │ →  DD  = FIT × DC_Coverage          │
│                                 │ →  RF  = FIT × (1 − DC_Coverage)   │
│ Safety_Related=T, Is_SPF=False  │ →  MPF_D = FIT × DC_Latent          │
│                                 │ →  MPF_L = FIT × (1 − DC_Latent)   │
└─────────────────────────────────┴─────────────────────────────────────┘

Metryki (ISO 26262 Part 5, Table 4 & 5):
    SPFM = 1 − (ΣRF / (Total_FIT − ΣSF))
    LFM  = 1 − (ΣMPF_L / (Total_FIT − ΣSF − ΣDD − ΣRF))

Wartości docelowe (przykładowo dla ASIL D):
    SPFM ≥ 99%,  LFM ≥ 90%
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


# ---------------------------------------------------------------------------
# Stałe — wymagania normowe per ASIL (ISO 26262-5:2018, Table 4 & 5)
# ---------------------------------------------------------------------------

SPFM_TARGETS: dict[str, float] = {
    "ASIL B": 0.90,
    "ASIL C": 0.97,
    "ASIL D": 0.99,
}

LFM_TARGETS: dict[str, float] = {
    "ASIL B": 0.60,
    "ASIL C": 0.80,
    "ASIL D": 0.90,
}


# ---------------------------------------------------------------------------
# Wynik — dataclass dla czytelności
# ---------------------------------------------------------------------------


@dataclass
class FaultBuckets:
    """Sumy FIT per koszyk awarii (ISO 26262)."""

    SF: float = 0.0      # Safe Faults (nieistotne bezpieczeńściowo)
    DD: float = 0.0      # Dangerous Detected
    RF: float = 0.0      # Residual Faults (niebezpieczne, niewykryte, SPF)
    MPF_D: float = 0.0   # Multi-Point Fault – Detected
    MPF_L: float = 0.0   # Multi-Point Fault – Latent (niewidoczne)
    Total: float = field(init=False)

    def __post_init__(self) -> None:
        self.Total = self.SF + self.DD + self.RF + self.MPF_D + self.MPF_L


@dataclass
class ArchitecturalMetrics:
    """Wyniki metryk architektonicznych ISO 26262."""

    buckets: FaultBuckets
    SPFM: float | None         # Single-Point Fault Metric [0..1]
    LFM: float | None          # Latent Fault Metric [0..1]

    def spfm_pct(self) -> str:
        return f"{self.SPFM * 100:.2f}%" if self.SPFM is not None else "N/A"

    def lfm_pct(self) -> str:
        return f"{self.LFM * 100:.2f}%" if self.LFM is not None else "N/A"

    def check_asil(self, asil: str = "ASIL D") -> dict[str, bool | None]:
        """Sprawdza, czy metryki spełniają wymagania dla danego ASIL."""
        spfm_ok = (
            self.SPFM >= SPFM_TARGETS[asil]
            if self.SPFM is not None and asil in SPFM_TARGETS
            else None
        )
        lfm_ok = (
            self.LFM >= LFM_TARGETS[asil]
            if self.LFM is not None and asil in LFM_TARGETS
            else None
        )
        return {"SPFM_pass": spfm_ok, "LFM_pass": lfm_ok}

    def to_dict(self) -> dict:
        """Eksport do słownika (np. dla pandas)."""
        return {
            "SF_FIT": round(self.buckets.SF, 4),
            "DD_FIT": round(self.buckets.DD, 4),
            "RF_FIT": round(self.buckets.RF, 4),
            "MPF_D_FIT": round(self.buckets.MPF_D, 4),
            "MPF_L_FIT": round(self.buckets.MPF_L, 4),
            "Total_FIT": round(self.buckets.Total, 4),
            "SPFM": self.SPFM,
            "SPFM_pct": self.spfm_pct(),
            "LFM": self.LFM,
            "LFM_pct": self.lfm_pct(),
        }


# ---------------------------------------------------------------------------
# Klasyfikacja koszyków
# ---------------------------------------------------------------------------


def classify_fault_buckets(
    df: pd.DataFrame,
    *,
    fit_col: str = "FIT_Mode",
    safety_col: str = "Safety_Related",
    spf_col: str = "Is_SPF",
    dc_col: str = "DC_Coverage",
    dc_latent_col: str = "DC_Latent",
    dc_default: float = 0.0,
    dc_latent_default: float = 0.0,
) -> tuple[pd.DataFrame, FaultBuckets]:
    """
    Klasyfikuje tryby awarii do koszyków ISO 26262 i oblicza sumy FIT.

    Parametry
    ----------
    df : pd.DataFrame
        Tabela trybów awarii z wymaganymi kolumnami.
    fit_col : str
        Kolumna z wartością FIT dla trybu awarii.
    safety_col : str
        Kolumna logiczna: True = usterka bezpieczościowo istotna.
    spf_col : str
        Kolumna logiczna: True = usterka jednopunktowa (Single Point Fault).
    dc_col : str
        Pokrycie diagnostyczne dla SPF [0..1].
    dc_latent_col : str
        Pokrycie diagnostyczne dla usterek latentnych (MPF) [0..1].
    dc_default : float
        Wartość DC_Coverage, gdy kolumna nie istnieje lub jest NaN.
    dc_latent_default : float
        Wartość DC_Latent, gdy kolumna nie istnieje lub jest NaN.

    Zwraca
    -------
    tuple[pd.DataFrame, FaultBuckets]
        - DataFrame z nowymi kolumnami: SF, DD, RF, MPF_D, MPF_L
        - FaultBuckets z sumami FIT per koszyk
    """
    required = {fit_col, safety_col, spf_col}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"Brakujące kolumny w DataFrame: {missing}")

    df = df.copy()

    # Obsługa brakujących kolumn DC
    if dc_col not in df.columns:
        df[dc_col] = dc_default
    else:
        df[dc_col] = df[dc_col].fillna(dc_default)

    if dc_latent_col not in df.columns:
        df[dc_latent_col] = dc_latent_default
    else:
        df[dc_latent_col] = df[dc_latent_col].fillna(dc_latent_default)

    # Walidacja zakresów
    for col in (dc_col, dc_latent_col):
        if not df[col].between(0.0, 1.0).all():
            raise ValueError(
                f"Kolumna '{col}' zawiera wartości poza zakresem [0, 1]."
            )

    # --- Vectorized classification ---
    fit = df[fit_col]
    is_safe = ~df[safety_col].astype(bool)          # SF: nie istotne bepiecz.
    is_spf = df[spf_col].astype(bool)                # SPF: jednopunktowe
    is_mpf = df[safety_col].astype(bool) & ~is_spf  # MPF: wielopunktowe

    df["SF"] = fit.where(is_safe, 0.0)
    df["DD"] = (fit * df[dc_col]).where(is_spf, 0.0)
    df["RF"] = (fit * (1 - df[dc_col])).where(is_spf, 0.0)
    df["MPF_D"] = (fit * df[dc_latent_col]).where(is_mpf, 0.0)
    df["MPF_L"] = (fit * (1 - df[dc_latent_col])).where(is_mpf, 0.0)

    buckets = FaultBuckets(
        SF=float(df["SF"].sum()),
        DD=float(df["DD"].sum()),
        RF=float(df["RF"].sum()),
        MPF_D=float(df["MPF_D"].sum()),
        MPF_L=float(df["MPF_L"].sum()),
    )
    return df, buckets


# ---------------------------------------------------------------------------
# Obliczanie metryk
# ---------------------------------------------------------------------------


def compute_metrics(buckets: FaultBuckets) -> ArchitecturalMetrics:
    """
    Oblicza SPFM i LFM na podstawie koszyków awarii ISO 26262.

    Wzory (ISO 26262-5, Annex D):
        SPFM = 1 − (ΣRF / (Total − ΣSF))
        LFM  = 1 − (ΣMPF_L / (Total − ΣSF − ΣDD − ΣRF))

    Parametry
    ----------
    buckets : FaultBuckets
        Sumy FIT per koszyk awarii.

    Zwraca
    -------
    ArchitecturalMetrics
        Obiekt z SPFM, LFM i koszykami.
    """
    # SPFM — mianownik: wszystkie usterki niebezpieczne (Total − SF)
    spfm_denominator = buckets.Total - buckets.SF
    if spfm_denominator > 0:
        spfm = 1.0 - (buckets.RF / spfm_denominator)
    else:
        spfm = None  # brak usterek niebezpiecznych → N/A

    # LFM — mianownik: usterki latentne = Total − SF − DD − RF
    lfm_denominator = buckets.Total - buckets.SF - buckets.DD - buckets.RF
    if lfm_denominator > 0:
        lfm = 1.0 - (buckets.MPF_L / lfm_denominator)
    else:
        lfm = None  # brak usterek latentnych → N/A

    return ArchitecturalMetrics(buckets=buckets, SPFM=spfm, LFM=lfm)


# ---------------------------------------------------------------------------
# Convenience: jeden wywołanie dla całego pipeline'u
# ---------------------------------------------------------------------------


def analyse(
    df: pd.DataFrame,
    **classify_kwargs,
) -> tuple[pd.DataFrame, ArchitecturalMetrics]:
    """
    Skrót: klasyfikacja koszyków + obliczenie metryk w jednym wywołaniu.

    Zwraca
    -------
    tuple[pd.DataFrame, ArchitecturalMetrics]
        - DataFrame z kolumnami SF/DD/RF/MPF_D/MPF_L
        - ArchitecturalMetrics z SPFM i LFM

    Przykład
    --------
    >>> df_classified, metrics = analyse(df_fmeda)
    >>> print(f"SPFM = {metrics.spfm_pct()},  LFM = {metrics.lfm_pct()}")
    """
    df_classified, buckets = classify_fault_buckets(df, **classify_kwargs)
    metrics = compute_metrics(buckets)
    return df_classified, metrics
