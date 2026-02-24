"""
main.py – Demo Kalkulatora FMEDA wg SN 29500 / IEC 61709
==========================================================
Uruchom: python main.py
"""

import pandas as pd

from fmeda import (
    calculate_lambda_real,
    calculate_pi_t,
    distribute_failure_modes,
    analyse,
    SPFM_TARGETS,
    LFM_TARGETS,
    FMEDAPipeline,
)

# ---------------------------------------------------------------------------
# Przykładowe komponenty z BOM (symulacja)
# ---------------------------------------------------------------------------

COMPONENTS = [
    {"name": "Mikrokontroler MCU",    "type": "IC_Digital",            "lambda_ref": 5.0,  "e_a": 0.4},
    {"name": "Czujnik Temperatury",   "type": "IC_Analog",             "lambda_ref": 0.8,  "e_a": 0.4},
    {"name": "Tranzystor MOSFET",     "type": "Transistor_MOSFET",     "lambda_ref": 2.0,  "e_a": 0.35},
    {"name": "Kondensator C1",        "type": "Capacitor_Electrolytic","lambda_ref": 1.5,  "e_a": 0.4},
    {"name": "Rezystor R1",           "type": "Resistor",              "lambda_ref": 1.2,  "e_a": 0.4},
]

TEMPERATURES = [40.0, 55.0, 70.0, 85.0, 105.0, 125.0]


def print_separator(char: str = "─", width: int = 80) -> None:
    print(char * width)


def run_demo() -> None:
    T_OPERATING = 85.0

    print()
    print("=" * 80)
    print("  KALKULATOR FMEDA – SN 29500 / IEC 61709 / ISO 26262")
    print(f"  Arrhenius @ T_ref=40°C  |  T_operating={T_OPERATING}°C")
    print("=" * 80)

    # ------------------------------------------------------------------
    # 1. Tabela π_T
    # ------------------------------------------------------------------
    print("\n📊 WSPÓŁCZYNNIK TEMPERATUROWY π_T (E_a = 0.40 eV)\n")
    header = f"{'Temperatura [°C]':>18} | {'π_T':>10} | {'Interpretacja'}"
    print(header)
    print_separator()
    for t in TEMPERATURES:
        pi_t = calculate_pi_t(t_real_celsius=t)
        if pi_t < 1.0:
            label = "↓ poniżej ref."
        elif pi_t == 1.0:
            label = "= punkt ref."
        elif pi_t < 3.0:
            label = "⚠ umiarkowany wzrost"
        elif pi_t < 10.0:
            label = "⚠⚠ znaczny wzrost"
        else:
            label = "🔴 krytyczny wzrost!"
        print(f"{t:>18.1f} | {pi_t:>10.4f} | {label}")

    # ------------------------------------------------------------------
    # 2. Tabela λ_real dla komponentów przy T = 85°C
    # ------------------------------------------------------------------
    print(f"\n\n📋 λ_real DLA KOMPONENTÓW BOM @ T = {T_OPERATING}°C\n")
    header = f"{'Komponent':<30} | {'λ_ref [FIT]':>12} | {'E_a [eV]':>9} | {'λ_real [FIT]':>13}"
    print(header)
    print_separator()

    bom_rows = []
    total_lambda_ref = 0.0
    total_lambda_real = 0.0

    for comp in COMPONENTS:
        lam_real = calculate_lambda_real(
            lambda_ref=comp["lambda_ref"],
            t_real_celsius=T_OPERATING,
            e_a=comp["e_a"],
        )
        total_lambda_ref += comp["lambda_ref"]
        total_lambda_real += lam_real
        print(
            f"{comp['name']:<30} | {comp['lambda_ref']:>12.2f} | "
            f"{comp['e_a']:>9.2f} | {lam_real:>13.2f}"
        )
        bom_rows.append(
            {
                "Designator": comp["name"],
                "Component_Type": comp["type"],
                "Total_FIT": lam_real,
            }
        )

    print_separator()
    print(
        f"{'SUMA (λ_total)':<30} | {total_lambda_ref:>12.2f} | "
        f"{'':>9} | {round(total_lambda_real, 2):>13.2f}"
    )

    # ------------------------------------------------------------------
    # 3. MTTF
    # ------------------------------------------------------------------
    print(f"\n\n🔢 PODSTAWOWE WSKAŹNIKI NIEZAWODNOŚCI\n")
    lambda_total_per_hour = total_lambda_real * 1e-9
    if lambda_total_per_hour > 0:
        mttf_hours = 1.0 / lambda_total_per_hour
        mttf_years = mttf_hours / 8760
    else:
        mttf_hours = float("inf")
        mttf_years = float("inf")

    print(f"  λ_total (@ {T_OPERATING}°C) = {total_lambda_real:.2f} FIT")
    print(f"  λ_total                    = {lambda_total_per_hour:.4e} awarii/h")
    print(f"  MTTF                       = {mttf_hours:,.0f} h  ≈  {mttf_years:.0f} lat")

    # ------------------------------------------------------------------
    # 4. MODUŁ 2 — Rozkład trybów awarii (IEC 61709)
    # ------------------------------------------------------------------
    print()
    print("=" * 80)
    print("  ROZKŁAD TRYBÓW AWARII – IEC 61709 (Failure Mode Distribution)")
    print("=" * 80)

    df_bom = pd.DataFrame(bom_rows)
    df_fmeda = distribute_failure_modes(df_bom)

    # Ładne wypisanie
    print(f"\n📋 FMEDA – tryby awarii per komponent @ T = {T_OPERATING}°C\n")
    header = (
        f"{'Komponent':<25} | {'Typ':<25} | "
        f"{'Tryb awarii':<20} | {'Udział':>7} | {'FIT_Mode':>9}"
    )
    print(header)
    print_separator(width=95)

    prev_designator = None
    for _, row in df_fmeda.iterrows():
        designator = row["Designator"]
        if designator != prev_designator and prev_designator is not None:
            print_separator(char="·", width=95)
        prev_designator = designator

        print(
            f"{designator:<25} | {row['Component_Type']:<25} | "
            f"{row['Failure_Mode']:<20} | {row['Mode_Ratio']:>6.0%} | "
            f"{row['FIT_Mode']:>9.2f}"
        )

    print_separator(width=95)
    print(f"{'SUMA FIT_Mode':<75} | {df_fmeda['FIT_Mode'].sum():>9.2f}")

    # Podsumowanie per tryb awarii
    print(f"\n\n📊 PODSUMOWANIE — FIT per tryb awarii (wszystkie komponenty)\n")
    mode_summary = (
        df_fmeda.groupby("Failure_Mode")["FIT_Mode"]
        .sum()
        .sort_values(ascending=False)
    )
    for mode, fit in mode_summary.items():
        pct = fit / mode_summary.sum() * 100
        print(f"  {mode:<25} {fit:>8.2f} FIT  ({pct:>5.1f}%)")

    print()
    print("=" * 80)
    print("  Obliczenia: SN 29500 (Arrhenius) + IEC 61709 (tryby awarii)")
    print("=" * 80)

    # ------------------------------------------------------------------
    # 5. MODUŁ 3 — Metryki architektoniczne (SPFM / LFM, ISO 26262)
    # ------------------------------------------------------------------
    print()
    print("=" * 80)
    print("  METRYKI ARCHITEKTONICZNE ISO 26262 – SPFM / LFM")
    print("=" * 80)

    # Adnotacje bezpieczeństwa (normalnie wypełniane przez inżyniera)
    #  Safety_Related: czy tryb awarii może naruszyć Safety Goal?
    #  Is_SPF: True = usterka jednopunktowa (brak redundancji)
    #  DC_Coverage: pokrycie diagnostyczne mechanizmu detekcji
    #  DC_Latent:   pokrycie latentnych usterek (np. Built-In Self-Test)
    FMEDA_ANNOTATIONS = {
        # (Designator, Failure_Mode) -> (Safety_Related, Is_SPF, DC_Cov, DC_Latent)
        ("Mikrokontroler MCU", "Loss of Function"):   (True,  True,  0.95, 0.0),
        ("Mikrokontroler MCU", "Incorrect Output"):   (True,  True,  0.90, 0.0),
        ("Mikrokontroler MCU", "Short Circuit"):       (True,  False, 0.0,  0.80),
        ("Czujnik Temperatury", "Drift"):              (True,  True,  0.85, 0.0),
        ("Czujnik Temperatury", "Loss of Function"):  (True,  True,  0.90, 0.0),
        ("Czujnik Temperatury", "Short Circuit"):      (False, False, 0.0,  0.0),
        ("Tranzystor MOSFET",  "Short Circuit"):       (True,  True,  0.80, 0.0),
        ("Tranzystor MOSFET",  "Open Circuit"):        (True,  False, 0.0,  0.75),
        ("Tranzystor MOSFET",  "Drift"):               (False, False, 0.0,  0.0),
        ("Kondensator C1",     "Short Circuit"):       (True,  True,  0.70, 0.0),
        ("Kondensator C1",     "Open Circuit"):        (False, False, 0.0,  0.0),
        ("Kondensator C1",     "Drift"):               (False, False, 0.0,  0.0),
        ("Rezystor R1",        "Open Circuit"):        (False, False, 0.0,  0.0),
        ("Rezystor R1",        "Short Circuit"):       (False, False, 0.0,  0.0),
        ("Rezystor R1",        "Drift"):               (False, False, 0.0,  0.0),
    }

    def annotate_row(row):
        key = (row["Designator"], row["Failure_Mode"])
        if key in FMEDA_ANNOTATIONS:
            sr, spf, dc, dcl = FMEDA_ANNOTATIONS[key]
        else:
            sr, spf, dc, dcl = False, False, 0.0, 0.0
        return pd.Series(
            [sr, spf, dc, dcl],
            index=["Safety_Related", "Is_SPF", "DC_Coverage", "DC_Latent"],
        )

    annotations = df_fmeda.apply(annotate_row, axis=1)
    df_annotated = pd.concat([df_fmeda, annotations], axis=1)

    df_classified, metrics = analyse(df_annotated)
    b = metrics.buckets

    print(f"\n📊 KOSZYKI AWARII (fault buckets) @ T = {T_OPERATING}°C\n")
    print(f"  SF   (Safe Faults)                 {b.SF:>8.3f} FIT")
    print(f"  DD   (Dangerous Detected)          {b.DD:>8.3f} FIT")
    print(f"  RF   (Residual Faults – SPF)       {b.RF:>8.3f} FIT")
    print(f"  MPF_D (Multi-Point Fault Detected) {b.MPF_D:>8.3f} FIT")
    print(f"  MPF_L (Multi-Point Fault Latent)   {b.MPF_L:>8.3f} FIT")
    print_separator()
    print(f"  Total FIT                          {b.Total:>8.3f} FIT")

    print(f"\n🔢 METRYKI ISO 26262\n")
    print(f"  SPFM = {metrics.spfm_pct():>10}  (Single-Point Fault Metric)")
    print(f"  LFM  = {metrics.lfm_pct():>10}  (Latent Fault Metric)")

    print(f"\n✅ WERYFIKACJA WYMAGAŃ ASIL\n")
    header = f"  {'ASIL':<10} | {'SPFM wymagane':>15} | {'SPFM OK?':>10} | "\
             f"{'LFM wymagane':>14} | {'LFM OK?':>9}"
    print(header)
    print("  " + "─" * 70)
    for asil in ("ASIL B", "ASIL C", "ASIL D"):
        result = metrics.check_asil(asil)
        spfm_req = f">= {SPFM_TARGETS[asil]*100:.0f}%"
        lfm_req = f">= {LFM_TARGETS[asil]*100:.0f}%"
        spfm_ok = "✅ TAK" if result["SPFM_pass"] else "❌ NIE"
        lfm_ok  = "✅ TAK" if result["LFM_pass"]  else "❌ NIE"
        if result["SPFM_pass"] is None:
            spfm_ok = "N/A"
        if result["LFM_pass"] is None:
            lfm_ok = "N/A"
        print(f"  {asil:<10} | {spfm_req:>15} | {spfm_ok:>10} | "
              f"{lfm_req:>14} | {lfm_ok:>9}")

    print()
    print("=" * 80)
    print("  Koniec analizy FMEDA.")
    print("=" * 80)
    print()

    # ------------------------------------------------------------------
    # 6. MODUŁ 4: PIPELINE (DATA PIPELINE — BOM EXCEL END-TO-END)
    # ------------------------------------------------------------------
    print("=" * 80)
    print("  FMEDA PIPELINE (ZAUTOMATYZOWANY PRZEPŁYW DANYCH — EXCEL)")
    print("=" * 80)

    # 6a. Przygotowanie przykładowych baz danych do demo
    # W projekcie te dane pochodziłyby z zunifikowanych arkuszy komponentów.
    fit_db = pd.DataFrame({
        "Footprint": [
            "TST_POINT_FLAT", "CAPC0603L", "CAPC0402L", "RESC0402L", 
            "RESC0603L", "RESC0805L", "RESC1206L", "CAPC1206L",
            "LQFP50P1200X1200X160", "LQFP50P1200X1200X160-64TH — with MC33771BSP1AE body"
        ],
        "Base_FIT": [0.1, 1.5, 0.8, 1.2, 1.3, 1.4, 1.6, 2.0, 15.0, 25.0],
        "Component_Class": [
            "Connector", "Capacitor", "Capacitor", "Resistor", 
            "Resistor", "Resistor", "Resistor", "Capacitor",
            "IC_Digital", "IC_Digital"
        ],
    })

    # Reguły bezpieczeństwa per arkusz i klasa komponentu
    rules_db = pd.DataFrame({
        "SheetNumber": ["4.1.1", "4.1.1", "4.1.1", "6.1.1", "3.3.1", "3.1.1"],
        "Component_Class": ["Resistor", "Capacitor", "IC_Digital", "Capacitor", "Resistor", "IC_Digital"],
        "Safety_Related": [True, True, True, False, True, True],
        "Is_SPF": [True, False, True, False, True, True],
        "DC_Coverage": [0.90, 0.0, 0.99, 0.0, 0.90, 0.98],
    })

    try:
        # 6b. Uruchomienie Pipeline
        print(f"\nWczytywanie BOM z '284-CMU-01.xlsx'...")
        bom_df = pd.read_excel("284-CMU-01.xlsx")
        
        pipeline = FMEDAPipeline(bom_df, fit_db, rules_db, mission_temp=75.0)
        results = pipeline.run_pipeline()

        print(f"Sukces! Przetworzono {len(results)} arkuszy schematu.")
        print("-" * 65)
        print(f"{'Arkusz':<25} | {'SPFM':<10} | {'LFM':<10} | {'Status'}")
        print("-" * 65)
        
        for sheet, m in sorted(results.items())[:8]: # Pokaż próbkę wyników
            spfm = m.get("SPFM_pct", "N/A")
            lfm = m.get("LFM_pct", "N/A")
            asil_ok = m.get("ASIL_D", {}).get("SPFM_pass", False)
            status = "✅ ASIL D OK" if asil_ok else "⚠ Low Coverage"
            if m.get("SPFM") is None: status = "—"
            
            print(f"{sheet:<25} | {spfm:<10} | {lfm:<10} | {status}")
        
        print("-" * 65)
        print("\nPipeline zakończony pomyślnie. Dane są gotowe do raportowania.")

    except Exception as e:
        print(f"\n[!] Pipeline Demo Error: {e}")


if __name__ == "__main__":
    run_demo()
