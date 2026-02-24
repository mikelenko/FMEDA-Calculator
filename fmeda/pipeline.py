"""
pipeline.py
-----------
Zintegrowany pipeline FMEDA łączący wszystkie kroki analizy:

    1. Explode Designators   – CSV string → osobne wiersze per instancja
    2. Merge FIT DB          – dopasowanie Base_FIT po Footprint
    3. Arrhenius             – Base_FIT → Real_FIT wg SN 29500
    4. Failure Mode Dist.    – 1 komponent → N wierszy trybów awarii
    5. Explode SheetNumber   – CSV string → osobne wiersze per arkusz
    6. Rules Engine          – nałożenie Safety_Related/Is_SPF/DC_Coverage
    7. Block-Level Metrics   – SPFM / LFM per SheetNumber

Wymagane kolumny wejściowe
--------------------------
bom_df   : Designator, Footprint, Comment, SheetNumber
fit_db   : Footprint, Base_FIT, Component_Class
rules_db : SheetNumber, Component_Class, Safety_Related, Is_SPF, DC_Coverage
"""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

from .fit_calculator import calculate_lambda_real
from .failure_modes import distribute_failure_modes, DEFAULT_FAILURE_MODES
from .metrics import classify_fault_buckets, compute_metrics, FaultBuckets


# ---------------------------------------------------------------------------
# Stałe domyślne
# ---------------------------------------------------------------------------

_REQUIRED_BOM = {"Designator", "Footprint", "SheetNumber"}
_REQUIRED_FIT = {"Footprint", "Base_FIT", "Component_Class"}
_REQUIRED_RULES = {"SheetNumber", "Component_Class", "Safety_Related", "Is_SPF", "DC_Coverage", "Local_Temp"}


# ---------------------------------------------------------------------------
# Klasa główna
# ---------------------------------------------------------------------------


class FMEDAPipeline:
    """
    Zintegrowany pipeline do analizy FMEDA w pełni wektoryzowany (pandas).

    Parametry
    ----------
    bom_df : pd.DataFrame
        BOM z co najmniej kolumnami: Designator, Footprint, SheetNumber.
        Designator i SheetNumber mogą być listami CSV (np. "R1_1, R1_2").
    fit_db : pd.DataFrame
        Baza FIT z kolumnami: Footprint, Base_FIT, Component_Class.
    rules_db : pd.DataFrame
        Reguły bezpieczeństwa z kolumnami:
        SheetNumber, Component_Class, Safety_Related, Is_SPF, DC_Coverage.
    mission_temp : float
        Temperatura pracy [°C] do obliczenia Real_FIT wg Arrheniusa. Domyślnie 65.0°C.
    failure_modes : dict, opcjonalnie
        Słownik rozkładów trybów awarii {Component_Class: {mode: ratio}}.
        Domyślnie DEFAULT_FAILURE_MODES (IEC 61709).

    Przykład
    --------
    >>> pipeline = FMEDAPipeline(bom_df, fit_db, rules_db, mission_temp=85.0)
    >>> results = pipeline.run_pipeline()
    >>> for sheet, metrics in results.items():
    ...     print(f"{sheet}: SPFM={metrics['SPFM_pct']}, LFM={metrics['LFM_pct']}")
    """

    def __init__(
        self,
        bom_df: pd.DataFrame,
        fit_db: pd.DataFrame,
        rules_db: pd.DataFrame,
        failure_modes: dict[str, dict[str, float]] | None = None,
        *,
        designator_col: str = "Designator",
        footprint_col: str = "Footprint",
        sheet_col: str = "SheetNumber",
        component_class_col: str = "Component_Class",
        base_fit_col: str = "Base_FIT",
    ) -> None:
        self._bom = bom_df.copy()
        self._fit_db = fit_db.copy()
        
        # Obsługa opcjonalnego Local_Temp na wypadek starych plików reguł (kompatybilność wsteczna)
        self._rules_db = rules_db.copy()
        if "Local_Temp" not in self._rules_db.columns:
            self._rules_db["Local_Temp"] = 65.0
            
        self.failure_modes = failure_modes or DEFAULT_FAILURE_MODES

        # Konfigurowalne nazwy kolumn
        self._des_col = designator_col
        self._fp_col = footprint_col
        self._sheet_col = sheet_col
        self._class_col = component_class_col
        self._base_fit_col = base_fit_col

        # Pośrednie DataFrame (dostępne po run_pipeline)
        self._df_exploded: pd.DataFrame | None = None
        self._df_with_fit: pd.DataFrame | None = None
        self._df_failure_modes: pd.DataFrame | None = None
        self._df_classified: pd.DataFrame | None = None

        self._validate_inputs()

    # ------------------------------------------------------------------
    # Walidacja wejścia
    # ------------------------------------------------------------------

    def _validate_inputs(self) -> None:
        """Sprawdza, czy wymagane kolumny istnieją we wszystkich DataFrame."""
        self._check_columns(self._bom, _REQUIRED_BOM, "bom_df")
        self._check_columns(self._fit_db, _REQUIRED_FIT, "fit_db")
        self._check_columns(self._rules_db, _REQUIRED_RULES, "rules_db")

    @staticmethod
    def _check_columns(df: pd.DataFrame, required: set[str], name: str) -> None:
        missing = required - set(df.columns)
        if missing:
            raise KeyError(
                f"DataFrame '{name}' brakuje kolumn: {missing}. "
                f"Dostępne kolumny: {set(df.columns)}"
            )

    # ------------------------------------------------------------------
    # Właściwości dostępu do pośrednich DataFrame (debug/raportowanie)
    # ------------------------------------------------------------------

    @property
    def df_exploded(self) -> pd.DataFrame:
        """DataFrame po explode Designator (jedna instancja = jeden wiersz)."""
        if self._df_exploded is None:
            raise RuntimeError("Wywołaj najpierw run_pipeline().")
        return self._df_exploded

    @property
    def df_with_fit(self) -> pd.DataFrame:
        """DataFrame po dołączeniu Base_FIT i Real_FIT z bazy FIT."""
        if self._df_with_fit is None:
            raise RuntimeError("Wywołaj najpierw run_pipeline().")
        return self._df_with_fit

    @property
    def df_failure_modes(self) -> pd.DataFrame:
        """DataFrame po rozbicu na tryby awarii (jedno wiersz = jeden tryb)."""
        if self._df_failure_modes is None:
            raise RuntimeError("Wywołaj najpierw run_pipeline().")
        return self._df_failure_modes

    @property
    def df_classified(self) -> pd.DataFrame:
        """DataFrame z kolumnami SF/DD/RF/MPF_D/MPF_L po nałożeniu reguł."""
        if self._df_classified is None:
            raise RuntimeError("Wywołaj najpierw run_pipeline().")
        return self._df_classified

    # ------------------------------------------------------------------
    # Kroki pipeline'u
    # ------------------------------------------------------------------

    def _step1_explode_designators(self) -> pd.DataFrame:
        """
        Krok 1: Explode Designators.

        Każdy wiersz z CSV designatorem (np. "R1_1, R1_2, R1_3") jest
        rozbijany na osobne wiersze — jedna instancja komponentu = jeden wiersz.
        """
        df = self._bom.copy()
        df[self._des_col] = df[self._des_col].astype(str).str.split(r"\s*,\s*")
        df = df.explode(self._des_col).reset_index(drop=True)
        df[self._des_col] = df[self._des_col].str.strip()
        return df

    def _step2_merge_fit(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Krok 2: Merge z bazą FIT po Footprint.

        Dociąga Base_FIT i Component_Class. Komponenty bez dopasowania
        w fit_db otrzymują ostrzeżenie i są pomijane.
        """
        merged = df.merge(
            self._fit_db[[self._fp_col, self._base_fit_col, self._class_col]],
            on=self._fp_col,
            how="left",
        )

        # Wykryj i zaraportuj brakujące dopasowania
        missing_mask = merged[self._base_fit_col].isna()
        if missing_mask.any():
            missing_fps = merged.loc[missing_mask, self._fp_col].unique()
            warnings.warn(
                f"Brak Base_FIT dla Footprint: {list(missing_fps)}. "
                f"Wiersze zostaną pominięte.",
                UserWarning,
                stacklevel=3,
            )
            merged = merged[~missing_mask]

        return merged.reset_index(drop=True)

    def _step3_arrhenius(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Krok 3 (logiczny): Obliczenie Real_FIT wg modelu Arrheniusa (SN 29500).

        Dedykowana wartość pobierana jest z 'Local_Temp' per arkusz.
        """
        df = df.copy()
        # Fallback na 65.0 jeśli po mergu nie ma Local_Temp z rules_db
        if "Local_Temp" not in df.columns:
            df["Local_Temp"] = 65.0
        else:
            df["Local_Temp"] = pd.to_numeric(df["Local_Temp"], errors="coerce").fillna(65.0)

        df["Real_FIT"] = df.apply(
            lambda row: calculate_lambda_real(
                lambda_ref=float(row[self._base_fit_col]),
                t_real_celsius=float(row["Local_Temp"]),
            ),
            axis=1
        )
        return df

    def _step4_failure_modes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Krok 4: Rozbicie na tryby awarii wg IEC 61709.

        Używa Component_Class jako klucza do słownika failure_modes.
        Jeśli Component_Class nie pasuje do żadnego klucza,
        komponent jest pomijany ze stosownym ostrzeżeniem.
        """
        # Przekształć failure_modes dict — klucze to Component_Class
        # Kolumna BOM dla distribute_failure_modes musi nazywać się Component_Type
        if self._class_col in df.columns:
            df = df.rename(columns={self._class_col: "Component_Type"})
        df = df.rename(columns={"Real_FIT": "Total_FIT"})

        # Filtruj znane typy
        known_types = set(self.failure_modes.keys())
        unknown = set(df["Component_Type"].unique()) - known_types
        if unknown:
            warnings.warn(
                f"Brak rozkładu trybu awarii dla typów: {unknown}. "
                f"Komponenty zostaną pominięte.",
                UserWarning,
                stacklevel=3,
            )
            df = df[df["Component_Type"].isin(known_types)]

        if df.empty:
            raise ValueError(
                "Brak komponentów ze zdefiniowanymi trybami awarii. "
                "Sprawdź Component_Class w fit_db."
            )

        df_result = distribute_failure_modes(
            df_bom=df,
            failure_modes=self.failure_modes,
            designator_col=self._des_col,
            type_col="Component_Type",
            fit_col="Total_FIT",
        )

        return df_result

    def _step5_explode_sheets(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Krok 5: Explode SheetNumber.

        Komponent na wielu arkuszach (np. "4.1.1, 4.2.1") jest kopiowany
        do każdego arkusza — tworząc osobny wiersz per arkusz.
        """
        df = df.copy()
        df[self._sheet_col] = df[self._sheet_col].astype(str).str.split(r"\s*,\s*")
        df = df.explode(self._sheet_col).reset_index(drop=True)
        df[self._sheet_col] = df[self._sheet_col].str.strip()
        return df

    def _step6_rules_engine(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Krok 6: Rules Engine — nałożenie reguł bezpieczeństwa.

        Używa elastycznego merga: jeśli reguła w pliku ma Component_Type="ALL" lub 
        nie podano kolumny, reguła dotyczy wszystkich komponentów w danym arkuszu.
        """
        df = df.copy()
        if self._class_col in df.columns:
            df = df.rename(columns={self._class_col: "Component_Type"})

        rules = self._rules_db.copy()
        if "Component_Class" in rules.columns:
            rules = rules.rename(columns={"Component_Class": "Component_Type"})
        if "Component_Type" not in rules.columns:
            rules["Component_Type"] = "ALL"

        # Normalizacja kluczy (strip)
        rules[self._sheet_col] = rules[self._sheet_col].astype(str).str.strip()
        rules["Component_Type"] = rules["Component_Type"].astype(str).str.strip()

        # Usuwamy ewentualne istniejące kolumny bezpieczeństwa z BOM dla uniknięcia suffixów _x, _y
        drop_cols = ["Safety_Related", "Is_SPF", "DC_Coverage", "Local_Temp"]
        for col in drop_cols:
            if col in df.columns:
                df = df.drop(columns=[col])

        # Rozdziel i usuń duplikaty w obrębie reguł z ALL, by zapobiec Cartesian Explosion
        rules_all = rules[rules["Component_Type"] == "ALL"].drop(columns=["Component_Type"])
        rules_all = rules_all.drop_duplicates(subset=[self._sheet_col], keep="last")
        rules_spec = rules[rules["Component_Type"] != "ALL"]

        # Krok A: Dopasowanie precyzyjne (Sheet + Component)
        if not rules_spec.empty:
            merged = df.merge(rules_spec, on=[self._sheet_col, "Component_Type"], how="left")
        else:
            merged = df.copy()
            for col in drop_cols:
                if col in rules.columns:
                    merged[col] = pd.NA

        # Krok B: Wypełnienie ogólnymi regułami arkusza ("ALL") dla niedopasowanych wierszy
        if not rules_all.empty:
            merged_all = df.merge(rules_all, on=self._sheet_col, how="left")
            for col in drop_cols:
                if col in rules_all.columns:
                    if col in merged.columns:
                        merged[col] = merged[col].fillna(merged_all[col])
                    else:
                        merged[col] = merged_all[col]

        # Wyciszenie FutureWarning: Downcasting object dtype
        with pd.option_context("future.no_silent_downcasting", True):
            # Wartości domyślne dla bazowych kolumn ISO26262 jeśli nigdzie nie było dopasowania
            if "Safety_Related" in merged.columns:
                merged["Safety_Related"] = merged["Safety_Related"].fillna(False).astype(bool)
            else:
                merged["Safety_Related"] = False

            if "Is_SPF" in merged.columns:
                merged["Is_SPF"] = merged["Is_SPF"].fillna(False).astype(bool)
            else:
                merged["Is_SPF"] = False

            if "DC_Coverage" in merged.columns:
                merged["DC_Coverage"] = pd.to_numeric(merged["DC_Coverage"], errors="coerce").fillna(0.0)
            else:
                merged["DC_Coverage"] = 0.0

            merged["DC_Latent"] = 0.0  # latentne DC domyślnie 0 — predykcja rozszerzenia

            if "Local_Temp" in merged.columns:
                merged["Local_Temp"] = pd.to_numeric(merged["Local_Temp"], errors="coerce").fillna(65.0)
            else:
                merged["Local_Temp"] = 65.0

        return merged.reset_index(drop=True)

    def _step7_block_metrics(
        self, df: pd.DataFrame
    ) -> dict[str, dict[str, Any]]:
        """
        Krok 7: Block-Level FMEDA — metryki per arkusz schematu.

        Grupuje po SheetNumber i dla każdej grupy:
          1. Klasyfikuje koszyki (SF/DD/RF/MPF_D/MPF_L)
          2. Oblicza SPFM i LFM

        Zwraca słownik: {sheet_name: dict z metrykami i koszykami FIT}
        """
        results: dict[str, dict[str, Any]] = {}

        for sheet, group in df.groupby(self._sheet_col):
            try:
                df_classified, buckets = classify_fault_buckets(
                    group,
                    fit_col="FIT_Mode",
                    safety_col="Safety_Related",
                    spf_col="Is_SPF",
                    dc_col="DC_Coverage",
                    dc_latent_col="DC_Latent",
                )
                metrics = compute_metrics(buckets)

                results[str(sheet)] = {
                    **metrics.to_dict(),
                    "SPFM_pct": metrics.spfm_pct(),
                    "LFM_pct": metrics.lfm_pct(),
                    "ASIL_B": metrics.check_asil("ASIL B"),
                    "ASIL_C": metrics.check_asil("ASIL C"),
                    "ASIL_D": metrics.check_asil("ASIL D"),
                    "n_modes": len(group),
                }
            except Exception as exc:  # noqa: BLE001
                warnings.warn(
                    f"Błąd dla arkusza '{sheet}': {exc}",
                    UserWarning,
                    stacklevel=2,
                )
                results[str(sheet)] = {"error": str(exc)}

        return results

    # ------------------------------------------------------------------
    # Główna metoda
    # ------------------------------------------------------------------

    def run_pipeline(self) -> dict[str, dict[str, Any]]:
        """
        Uruchamia pełny pipeline FMEDA.

        Zwraca
        -------
        dict[str, dict]
            Klucz: nazwa arkusza (SheetNumber).
            Wartość: słownik z metrykami:
              - SF_FIT, DD_FIT, RF_FIT, MPF_D_FIT, MPF_L_FIT, Total_FIT
              - SPFM (float lub None), SPFM_pct (str)
              - LFM  (float lub None), LFM_pct  (str)
              - ASIL_B, ASIL_C, ASIL_D (dict z SPFM_pass / LFM_pass)
              - n_modes (int: liczba trybów awarii w arkuszu)

        Raises
        ------
        KeyError
            Gdy brakuje wymaganej kolumny w danych wejściowych.
        ValueError
            Gdy po filtrowaniu nie pozostają żadne komponenty.
        """
        # Krok 1 — explode designatorów
        df = self._step1_explode_designators()
        self._df_exploded = df

        # Krok 2 — merge FIT
        df = self._step2_merge_fit(df)

        # Krok 3 — explode arkuszy
        df = self._step5_explode_sheets(df)

        # Krok 4 — reguły bezpieczeństwa (dodaje Local_Temp z rules_db)
        df = self._step6_rules_engine(df)
        self._df_classified = df

        # Krok 5 — Arrhenius (wymaga Local_Temp z kroku 4)
        df = self._step3_arrhenius(df)
        self._df_with_fit = df

        # Krok 6 — tryby awarii (wymaga Real_FIT z Arrheniusa)
        df = self._step4_failure_modes(df)
        self._df_failure_modes = df

        # Krok 7 — metryki per arkusz
        return self._step7_block_metrics(df)
