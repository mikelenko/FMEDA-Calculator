import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import math
import pandas as pd
from fmeda.pipeline import FMEDAPipeline

class MissionProfileWindow(ctk.CTkToplevel):
    def __init__(self, parent: "FMEDA_App", row_data: dict):
        super().__init__(parent)
        self.parent_app = parent
        self.row_data = row_data
        self.title("Kalkulator Profilu Misji (Model Arrheniusa)")
        self.geometry("600x400")
        self.attributes("-topmost", True)
        
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        self.lbl_title = ctk.CTkLabel(self, text="Zdefiniuj Fazy Pracy Systemu", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_title.grid(row=0, column=0, padx=10, pady=10)
        
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.scroll_frame.grid_columnconfigure(0, weight=2)
        self.scroll_frame.grid_columnconfigure(1, weight=1)
        self.scroll_frame.grid_columnconfigure(2, weight=1)
        
        headers = ["Nazwa fazy (np. Jazda)", "% Czasu", "Temperatura [°C]"]
        for i, text in enumerate(headers):
            lbl = ctk.CTkLabel(self.scroll_frame, text=text, font=ctk.CTkFont(weight="bold"))
            lbl.grid(row=0, column=i, padx=5, pady=5)
            
        self.phase_rows = []
        # Dodajemy pierwszy wiersz domyślnie
        self.add_phase_row("Normalna Praca", "100", "85")
        
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=2, column=0, pady=10)
        
        self.btn_add = ctk.CTkButton(self.btn_frame, text="+ Dodaj Fazę", command=lambda: self.add_phase_row("", "", ""))
        self.btn_add.grid(row=0, column=0, padx=10)
        
        self.btn_calc = ctk.CTkButton(self.btn_frame, text="Zastosuj i Oblicz T_eq", fg_color="#1b5e20", hover_color="#2e7d32", font=ctk.CTkFont(weight="bold"), command=self.calculate_t_eq)
        self.btn_calc.grid(row=0, column=1, padx=10)
        
    def add_phase_row(self, default_name, default_pct, default_temp):
        row_idx = len(self.phase_rows) + 1
        
        entry_name = ctk.CTkEntry(self.scroll_frame, placeholder_text="Nazwa fazy...")
        if default_name: entry_name.insert(0, default_name)
        entry_name.grid(row=row_idx, column=0, padx=5, pady=5, sticky="ew")
        
        entry_pct = ctk.CTkEntry(self.scroll_frame, placeholder_text="%", width=60)
        if default_pct: entry_pct.insert(0, default_pct)
        entry_pct.grid(row=row_idx, column=1, padx=5, pady=5)
        
        entry_temp = ctk.CTkEntry(self.scroll_frame, placeholder_text="°C", width=60)
        if default_temp: entry_temp.insert(0, default_temp)
        entry_temp.grid(row=row_idx, column=2, padx=5, pady=5)
        
        self.phase_rows.append({
            "name": entry_name,
            "pct": entry_pct,
            "temp": entry_temp
        })
        
    def calculate_t_eq(self):
        try:
            total_pct = 0.0
            sum_degradation = 0.0
            Ea = 0.4
            k = 8.617e-5
            
            for row in self.phase_rows:
                pct_str = row["pct"].get().strip()
                temp_str = row["temp"].get().strip()
                
                if not pct_str or not temp_str:
                    continue
                    
                pct = float(pct_str)
                temp_C = float(temp_str)
                
                total_pct += pct
                
                # Degradation contribution
                temp_K = temp_C + 273.15
                degradation = (pct / 100.0) * math.exp(-Ea / (k * temp_K))
                sum_degradation += degradation
                
            if sum_degradation == 0:
                messagebox.showerror("Błąd", "Suma degradacji wynosi zero. Wprowadź prawidłowe wartości (Time % > 0).")
                return
                
            if abs(total_pct - 100.0) > 1.0:
                messagebox.showwarning("Uwaga", f"Suma procentów czasu wynosi {total_pct}% (różna od 100%).\nWynik T_eq będzie oszacowany dla podanego udziału.")
                
            # Obliczenie T_eq z odwróconego wzoru Arrheniusa
            T_eq_K = -Ea / (k * math.log(sum_degradation))
            T_eq_C = T_eq_K - 273.15
            
            # Zaokrąglenie do jednego miejsca po przecinku
            T_eq_C = round(T_eq_C, 1)
            
            # Zastosuj do konkretnego wiersza
            self.row_data['t_eq'] = float(T_eq_C)
            self.row_data['lbl_temp'].configure(text=f"T_eq: {T_eq_C} °C")
            
            self.destroy()
            
        except ValueError:
            messagebox.showerror("Błąd wartości", "Upewnij się, że wpisane %. wartości oraz temperatury są poprawne (liczby).")

# Konfiguracja nowoczesnego wyglądu
ctk.set_appearance_mode("Dark")  # Tryb ciemny
ctk.set_default_color_theme("blue")  # Niebieskie akcenty

class FMEDA_App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Ustawienia głównego okna
        self.title("Kalkulator FMEDA - ISO 26262 (CMU Tool)")
        self.geometry("1400x700")
        self.minsize(1100, 600)

        # Siatka głównego okna: 2 kolumny
        # col 0: Sidebar (stała szerokość)
        # col 1: Obszar roboczy z zakładkami (rozciągliwy)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Zmienne do przechowywania ścieżek do plików
        self.filepath_bom = ""
        self.filepath_fit = ""
        self.filepath_rules = ""

        # Referencje do dynamicznych wierszy konfiguracji
        self.config_rows = []

        self.setup_sidebar()
        self.setup_sidebar()
        self.setup_tabview()

    def setup_sidebar(self):
        # --- LEWY PANEL (Sidebar) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(8, weight=1) # Wypycha przycisk uruchamiania na sam dół

        # Tytuł w panelu
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Ustawienia FMEDA", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 20))

        # Sekcja wczytywania plików
        self.btn_bom = ctk.CTkButton(self.sidebar_frame, text="KROK 1: Wczytaj BOM (.csv, .xlsx)", command=self.load_bom)
        self.btn_bom.grid(row=1, column=0, padx=20, pady=5)
        self.lbl_bom = ctk.CTkLabel(self.sidebar_frame, text="Brak pliku", text_color="gray")
        self.lbl_bom.grid(row=2, column=0, padx=20, pady=(0, 15))

        self.btn_fit = ctk.CTkButton(self.sidebar_frame, text="KROK 2: Wczytaj Bazę FIT", command=self.load_fit)
        self.btn_fit.grid(row=3, column=0, padx=20, pady=5)
        self.lbl_fit = ctk.CTkLabel(self.sidebar_frame, text="Brak pliku", text_color="gray")
        self.lbl_fit.grid(row=4, column=0, padx=20, pady=(0, 15))

        self.btn_apply_all = ctk.CTkButton(self.sidebar_frame, text="KROK 3: Zastosuj Profil z góry na dół", fg_color="#c27a00", hover_color="#8f5a00", command=self.apply_profile_to_all)
        self.btn_apply_all.grid(row=5, column=0, padx=20, pady=(0, 15))

        self.btn_rules = ctk.CTkButton(self.sidebar_frame, text="KROK 4: Reguły DC (Zapisany CSV)", command=self.load_rules)
        self.btn_rules.grid(row=6, column=0, padx=20, pady=5)
        self.lbl_rules = ctk.CTkLabel(self.sidebar_frame, text="Brak pliku", text_color="gray")
        self.lbl_rules.grid(row=7, column=0, padx=20, pady=(0, 20))

        self.btn_knowledge = ctk.CTkButton(self.sidebar_frame, text="📚 Baza Wiedzy ISO 26262", command=self.open_knowledge_base, fg_color="#3b5998", hover_color="#2b406e")
        self.btn_knowledge.grid(row=8, column=0, padx=20, pady=(10, 0), sticky="s")

        # Główny przycisk akcji
        self.btn_run = ctk.CTkButton(self.sidebar_frame, text="URUCHOM ANALIZĘ z GUI", fg_color="#1b5e20", hover_color="#2e7d32", height=40, font=ctk.CTkFont(weight="bold"), command=self.run_analysis)
        self.btn_run.grid(row=9, column=0, padx=20, pady=20, sticky="s")

    def setup_tabview(self):
        # Główny kontener na całą prawą stronę
        self.workspace_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.workspace_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.workspace_frame.grid_rowconfigure(1, weight=1)
        self.workspace_frame.grid_columnconfigure(0, weight=1)
        
        # Pasek zakładek (SegmentedButton rozciągnięty do odpowiednich proporcji lub ściśnięty)
        self.top_tabs_frame = ctk.CTkFrame(self.workspace_frame, fg_color="transparent")
        self.top_tabs_frame.grid(row=0, column=0, sticky="ew")
        
        self.tab_selector = ctk.CTkSegmentedButton(self.top_tabs_frame, values=["Konfiguracja Bloków", "Konsola Raportu"], command=self.switch_tab)
        # Centrowanie na "środek" z góry jeśli trzeba, ew w lewo - zgodnie ze stanem docelowym dajemy go np w centrum, lub z zachowaniem odpowiedniego układu w CSS (padding).
        # Upewniamy się, że przyciski kontrolujące rozkładają się wyżej a nie na dole ramki (anchor n)
        self.tab_selector.pack(pady=5)
        self.tab_selector.set("Konfiguracja Bloków") # domyślnie ukaż pierwszy
        
        # --- ZAKŁADKA 1: KONFIGURACJA BLOKÓW ---
        self.tab_config = ctk.CTkFrame(self.workspace_frame, fg_color="transparent")
        self.tab_config.grid_rowconfigure(1, weight=1)
        self.tab_config.grid_columnconfigure(0, weight=1)
        
        self.top_frame_config = ctk.CTkFrame(self.tab_config, fg_color="transparent")
        self.top_frame_config.grid(row=0, column=0, sticky="ew", pady=(5, 10))
        
        self.lbl_config = ctk.CTkLabel(self.top_frame_config, text="Block-Level Configuration", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_config.pack(side="left")
        
        # Kontener przewijany na wiersze arkuszy
        self.scroll_frame = ctk.CTkScrollableFrame(self.tab_config)
        self.scroll_frame.grid(row=1, column=0, sticky="nsew")
        
        for i in range(6): # Mamy 6 kolumn
            self.scroll_frame.grid_columnconfigure(i, weight=1)

        # Nagłówki kolumn w panelu konfiguracyjnym
        headers = [
            ("Arkusz", None), 
            ("Nazwa Bloku (Notatka)", None), 
            ("Safety Related", "Określa, czy usterka w tym bloku sprzętowym może bezpośrednio lub pośrednio naruszyć cel bezpieczeństwa (Safety Goal), np. doprowadzając do pożaru lub utraty hamulców. Jeśli odznaczysz (False), wszystkie usterki bloku zostaną uznane za bezpieczne (Safe Faults)."), 
            ("Target ASIL", "Wymagany poziom nienaruszalności bezpieczeństwa zdefiniowany dla tego bloku (od A do D). Determinuje rygorystyczność metryk. Np. dla ASIL C system będzie wymagał SPFM na poziomie \u2265 97%. Wybór 'QM' oznacza brak rygorów bezpieczeństwa."), 
            ("DC Coverage", "Współczynnik w przedziale 0.00 - 1.00. Określa, jaki procent niebezpiecznych usterek sprzęt potrafi samodzielnie wykryć i zneutralizować (np. dzięki BIST, sumom CRC czy redundancji), zanim wyrządzą one krzywdę."),
            ("Mission Profile", "T_eq (Temperatura Ekwiwalentna): Stała wartość temperatury, która powoduje dokładnie taką samą degradację termiczną komponentu (zgodnie z wykładniczym modelem Arrheniusa), co rzeczywisty, zmienny w czasie Profil Misji (jazda, postój, ładowanie).")
        ]
        
        for i, (text, tooltip) in enumerate(headers):
            frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            frame.grid(row=0, column=i, padx=10, pady=5, sticky="w")
            
            lbl = ctk.CTkLabel(frame, text=text, font=ctk.CTkFont(weight="bold"))
            lbl.pack(side="left")
            
            if tooltip:
                btn_help = ctk.CTkButton(frame, text="?", width=22, height=22, 
                                         corner_radius=11, 
                                         font=ctk.CTkFont(size=11, weight="bold"), 
                                         command=lambda t=text, m=tooltip: self.show_tooltip(f"Pojęcie: {t}", m))
                btn_help.pack(side="left", padx=(5, 0))

        # Przycisk zapisu konfiguracji na dole panelu konfiguracji
        self.btn_save_config = ctk.CTkButton(self.tab_config, text="Zapisz Konfigurację do CSV", command=self.export_config)
        self.btn_save_config.grid(row=2, column=0, pady=(15, 0), sticky="e")
        
        # --- ZAKŁADKA 2: KONSOLA RAPORTU ---
        self.tab_console = ctk.CTkFrame(self.workspace_frame, fg_color="transparent")
        self.tab_console.grid_rowconfigure(1, weight=1)
        self.tab_console.grid_columnconfigure(0, weight=1)
        
        self.lbl_wyniki = ctk.CTkLabel(self.tab_console, text="Konsola Logów ISO 26262", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_wyniki.grid(row=0, column=0, pady=(0, 10), sticky="w")
        
        # Konsola tekstowa do wyświetlania wyników z potoku Pandas
        self.console = ctk.CTkTextbox(self.tab_console, font=ctk.CTkFont(family="Consolas", size=13), wrap="none")
        self.console.grid(row=1, column=0, sticky="nsew")
        self.console.insert("0.0", "Witaj w Kalkulatorze FMEDA (Block-Level Interface).\n1. Wczytaj plik BOM (zakładka KROK 1), aby wykryć arkusze.\n2. Skonfiguruj każdy blok w zakładce 'Konfiguracja Bloków'.\n3. Możesz zapisać reguły do pliku CSV.\n4. Zbudujemy Pipeline automatycznie po kliknięciu Uruchom.\n\n")
        
        # Przycisk eksportu na dole
        self.btn_export = ctk.CTkButton(self.tab_console, text="Eksportuj Raport PDF/CSV", state="disabled", command=self.export_report)
        self.btn_export.grid(row=2, column=0, pady=(15, 0), sticky="e")

        # Inicjalne renderowanie pierwszej zakładki (przypinamy ją do wiersza nr 1)
        self.tab_config.grid(row=1, column=0, sticky="nsew")

    def switch_tab(self, tab_name):
        if tab_name == "Konfiguracja Bloków":
            self.tab_console.grid_forget()
            self.tab_config.grid(row=1, column=0, sticky="nsew")
        elif tab_name == "Konsola Raportu":
            self.tab_config.grid_forget()
            self.tab_console.grid(row=1, column=0, sticky="nsew")

    # --- Metody obsługi zdarzeń ---
    def load_bom(self):
        self.filepath_bom = filedialog.askopenfilename(filetypes=[("Excel Files", "*.xlsx"), ("CSV Files", "*.csv")])
        if self.filepath_bom:
            self.lbl_bom.configure(text=os.path.basename(self.filepath_bom))
            self.populate_config_panel()

    def load_fit(self):
        self.filepath_fit = filedialog.askopenfilename(filetypes=[("Excel Files", "*.xlsx"), ("CSV Files", "*.csv")])
        if self.filepath_fit:
            self.lbl_fit.configure(text=os.path.basename(self.filepath_fit))

    def load_rules(self):
        self.filepath_rules = filedialog.askopenfilename(filetypes=[("Excel Files", "*.xlsx"), ("CSV Files", "*.csv")])
        if self.filepath_rules:
            self.lbl_rules.configure(text=os.path.basename(self.filepath_rules))

    def open_mission_profile(self, row_data):
        MissionProfileWindow(self, row_data)

    def apply_profile_to_all(self):
        if not self.config_rows:
            return
        first_row = self.config_rows[0]
        if first_row['t_eq'] is None:
            messagebox.showwarning("Brak profilu", "Najpierw skonfiguruj Profil Misji dla pierwszego wiersza (arkusza).")
            return
            
        t_eq = first_row['t_eq']
        for row in self.config_rows[1:]:
            row['t_eq'] = t_eq
            row['lbl_temp'].configure(text=f"T_eq: {t_eq} °C")

    def show_tooltip(self, title, text):
        top = ctk.CTkToplevel(self)
        top.title(title)
        top.geometry("400x200")
        top.attributes("-topmost", True)
        
        lbl_title = ctk.CTkLabel(top, text=title, font=ctk.CTkFont(size=14, weight="bold"))
        lbl_title.pack(pady=(15, 5))
        
        txt = ctk.CTkTextbox(top, wrap="word", font=ctk.CTkFont(size=12))
        txt.pack(fill="both", expand=True, padx=15, pady=10)
        txt.insert("0.0", text)
        txt.configure(state="disabled")
        
        btn_ok = ctk.CTkButton(top, text="Zrozumiałem", command=top.destroy, width=120)
        btn_ok.pack(pady=(0, 15))

    def open_knowledge_base(self):
        top = ctk.CTkToplevel(self)
        top.title("Baza Wiedzy ISO 26262")
        top.geometry("650x500")
        top.attributes("-topmost", True)
        
        lbl_title = ctk.CTkLabel(top, text="Słowniczek Pojęć ISO 26262", font=ctk.CTkFont(size=20, weight="bold"))
        lbl_title.pack(pady=15)
        
        textbox = ctk.CTkTextbox(top, wrap="word", font=ctk.CTkFont(size=14))
        textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        glossary_text = """BAZA WIEDZY FMEDA - ISO 26262 (Part 5)

1. FIT (Failures In Time)
Podstawowa miara awaryjności elektroniki. 1 FIT oznacza 1 awarię sprzętu na miliard (10^9) godzin pracy. Jeśli komponent ma 10 FIT, oznacza to, że w grupie miliarda takich komponentów, statystycznie 10 zepsuje się w ciągu godziny.

2. KLASYFIKACJA USTEREK (FAULTS)
Skrypt kategoryzuje każdą usterkę sprzętową do jednego z "koszyków":
SF (Safe Fault): Usterka bezpieczna. Nie ma wpływu na bezpieczeństwo pojazdu (np. spalona dioda LED od statusu).
SPF (Single-Point Fault): Usterka jednopunktowa. Awaria elementu, która natychmiast prowadzi do katastrofy, ponieważ nie przewidziano dla niej żadnego mechanizmu obronnego.
RF (Residual Fault): Usterka szczątkowa. Ta część usterek niebezpiecznych, której nasz mechanizm obronny nie zdołał wykryć. (Np. jeśli DC=90%, to pozostałe 10% to usterki szczątkowe RF).
MPF (Multiple-Point Fault): Usterka wielopunktowa. Wymaga awarii dwóch lub więcej niezależnych elementów naraz, aby stać się niebezpieczną (np. awaria głównego ADC oraz jednoczesna awaria redundantnego ADC).

3. GŁÓWNE METRYKI SPRZĘTOWE
SPFM (Single-Point Fault Metric): Procent bezpieczeństwa architektury. Mówi o tym, przed jaką częścią usterek bezpośrednich (SPF+RF) system jest sprzętowo zabezpieczony.
SPFM = 1 - (SUM(SPF + RF) / (SUM(Total_FIT) - SUM(SF)))

LFM (Latent Fault Metric): Metryka usterek ukrytych. Określa zdolność systemu do wykrywania awarii mechanizmów obronnych, zanim nastąpi druga, krytyczna awaria.
PMHF (Probabilistic Metric for Random Hardware Failures): Absolutny limit awaryjności systemu wyrażony w FIT. Dla najwyższego poziomu bezpieczeństwa (ASIL D), PMHF całego systemu musi być mniejsze niż 10 FIT.

4. BIST (Built-In Self-Test)
Sprzętowy mechanizm autodiagnostyki wbudowany bezpośrednio w krzem nowoczesnych układów scalonych (np. NXP, TI). Pozwala procesorowi testować własną pamięć (MBIST), logikę (LBIST) i przetworniki (ABIST) w czasie rzeczywistym, co drastycznie podnosi wartość pokrycia diagnostycznego (DC)."""
        textbox.insert("0.0", glossary_text.strip())
        textbox.configure(state="disabled")

    def _read_data_file(self, filepath: str) -> pd.DataFrame:
        if filepath.endswith(".csv"):
            return pd.read_csv(filepath)
        elif filepath.endswith(".xlsx"):
            return pd.read_excel(filepath)
        else:
            raise ValueError(f"Nieobsługiwany format pliku: {filepath}")

    def populate_config_panel(self):
        # Czyszczenie poprzednich wierszy
        for widget_dict in self.config_rows:
            for widget in widget_dict.values():
                if isinstance(widget, ctk.CTkBaseClass):
                    widget.destroy()
        self.config_rows.clear()

        try:
            # Wczytywanie BOM i znajdowanie unikalnych arkuszy
            df_bom = self._read_data_file(self.filepath_bom)
            
            # Obsługa BOM gdzie SheetNumber może być CSV string w jednym wierszu (zgodnie z pipeline.py)
            if 'SheetNumber' in df_bom.columns:
                sheets_str = df_bom['SheetNumber'].astype(str).str.split(r"\s*,\s*").explode().str.strip()
                unique_sheets = sorted([s for s in sheets_str.unique() if s and s != 'nan'])
            else:
                self.console.insert("end", "⚠️ Plik BOM nie zawiera kolumny 'SheetNumber'. Generowanie mock listy.\n")
                unique_sheets = ['3.1.1', '4.1.1', '5.1.1'] # Fallback dla błędnego BOM
                
        except Exception as e:
            self.console.insert("end", f"Błąd podczas parsowania arkuszy: {e}\n")
            unique_sheets = ['3.1.1', '4.1.1', '5.1.1'] # Fallback w razie błędu odczytu

        # Tworzenie wierszy dla każdego arkusza
        for idx, sheet in enumerate(unique_sheets):
            row_idx = idx + 1 # +1 bo wiersz 0 to nagłówki
            
            # 1. Sheet Label
            lbl_sheet = ctk.CTkLabel(self.scroll_frame, text=sheet, font=ctk.CTkFont(weight="bold"))
            lbl_sheet.grid(row=row_idx, column=0, padx=5, pady=10)
            
            # 2. Block Name Entry
            entry_name = ctk.CTkEntry(self.scroll_frame, placeholder_text="Nazwa bloku...")
            entry_name.grid(row=row_idx, column=1, padx=5, pady=10, sticky="ew")
            
            # 3. Safety Related Checkbox
            var_safety = ctk.BooleanVar(value=True)
            chk_safety = ctk.CTkCheckBox(self.scroll_frame, text="", variable=var_safety)
            chk_safety.grid(row=row_idx, column=2, padx=5, pady=10)
            
            # 4. ASIL Target Dropdown
            asil_options = ["QM", "ASIL A", "ASIL B", "ASIL C", "ASIL D"]
            opt_asil = ctk.CTkOptionMenu(self.scroll_frame, values=asil_options)
            opt_asil.set("ASIL C") # Domyślnie
            opt_asil.grid(row=row_idx, column=3, padx=5, pady=10)
            
            # --- DC Coverage Label ---
            lbl_dc = ctk.CTkLabel(self.scroll_frame, text="97%", text_color="lightgreen")
            lbl_dc.grid(row=row_idx, column=4, padx=5, pady=10)
            
            def update_dc(choice, lbl=lbl_dc):
                if choice == "ASIL A": lbl.configure(text="60%", text_color="yellow")
                elif choice == "ASIL B": lbl.configure(text="90%", text_color="orange")
                elif choice == "ASIL C": lbl.configure(text="97%", text_color="lightgreen")
                elif choice == "ASIL D": lbl.configure(text="99%", text_color="green")
                else: lbl.configure(text="0%", text_color="gray")
                
            opt_asil.configure(command=update_dc)
            update_dc("ASIL C")
            
            # 5. Mission Profile (Label + Button)
            frame_profile = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            frame_profile.grid(row=row_idx, column=5, padx=5, pady=10)
            
            lbl_temp = ctk.CTkLabel(frame_profile, text="T_eq: -- °C", width=80)
            lbl_temp.pack(side="left", padx=(0, 5))
            
            row_dict = {
                'sheet_val': sheet,
                'lbl_sheet': lbl_sheet,
                'entry_name': entry_name,
                'var_safety': var_safety,
                'chk_safety': chk_safety,
                'opt_asil': opt_asil,
                'lbl_temp': lbl_temp,
                't_eq': None
            }
            
            btn_profile = ctk.CTkButton(frame_profile, text="🖩 Profil", width=60, command=lambda rd=row_dict: self.open_mission_profile(rd))
            btn_profile.pack(side="left")
            
            self.config_rows.append(row_dict)
            
        self.console.insert("end", f"✓ Wczytano {len(unique_sheets)} arkuszy do konfiguracji.\n")
        self.console.see("end")

    def export_config(self):
        if not self.config_rows:
            messagebox.showwarning("Brak Konfiguracji", "Musisz najpierw wczytać bazę BOM, aby wygenerować listę arkuszy.")
            return

        records = []
        for row in self.config_rows:
            sheet_num = row['sheet_val']
            # Odtwarzamy format kolumn oczekiwany przez Pipeline (rules_db)
            # Uwaga: Dla uproszczenia w tym demie zakładamy jedną regułę per cały arkusz
            # W pełnej implementacji można by rozszerzyć reguły na (Sheet, Component_Class)
            
            # Ustalamy domyślne Coverage na podstawie ASIL
            asil = row['opt_asil'].get()
            dc_cov = 0.0
            if asil == "ASIL A": dc_cov = 0.60
            elif asil == "ASIL B": dc_cov = 0.90
            elif asil == "ASIL C": dc_cov = 0.97
            elif asil == "ASIL D": dc_cov = 0.99
            
            # Domyślny Local_Temp jeśli T_eq The nie ustawiono
            local_temp = row['t_eq'] if row['t_eq'] is not None else 85.0
            
            records.append({
                "SheetNumber": sheet_num,
                "Block_Name": row['entry_name'].get(),
                "Component_Class": "ALL", # Fake placeholder dla całego bloku (jeśli nie rozróżniamy klas w GUI)
                "Safety_Related": row['var_safety'].get(),
                "ASIL_Target": asil,
                "Is_SPF": row['var_safety'].get(), # Założenie upraszczające
                "DC_Coverage": dc_cov,
                "Local_Temp": local_temp
            })
            
        df_rules = pd.DataFrame(records)
        save_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Plik", "*.csv")],
            title="Zapisz reguły arkuszy"
        )
        
        if save_path:
            try:
                df_rules.to_csv(save_path, index=False)
                self.console.insert("end", f"\nPomyślnie zapisano plik z regułami bloków do:\n{save_path}\n")
                # Od razu podpinamy to pod symulowany zbiór reguł aplikacji
                self.filepath_rules = save_path
                self.lbl_rules.configure(text=os.path.basename(save_path))
                self.console.see("end")
            except Exception as e:
                self.console.insert("end", f"Błąd zapisu: {e}\n")

    def run_analysis(self):
        # Automatycznie przełącz na zakładkę z konsolą logów
        self.tab_selector.set("Konsola Raportu")
        self.switch_tab("Konsola Raportu")
        
        self.console.insert("end", "="*80 + "\n")
        self.console.insert("end", f"⚙️ URUCHAMIANIE POTOKU FMEDA (Block-Level Profiling)...\n")
        self.console.insert("end", "="*80 + "\n")
        
        # Sprawdzanie plików
        if not self.filepath_bom:
            self.console.insert("end", "BŁĄD: Nie wczytano pliku BOM!\n")
            self.console.see("end")
            return
        if not self.filepath_fit:
            self.console.insert("end", "BŁĄD: Nie wczytano bazy FIT!\n")
            self.console.see("end")
            return
            
        self.console.insert("end", f"Wczytywanie BOM: {os.path.basename(self.filepath_bom)}\n")
        self.console.insert("end", f"Wczytywanie bazy FIT: {os.path.basename(self.filepath_fit)}\n")
        
        # Jeśli nie ma bazy reguł, to może zrób z konfiguracji GUI, ale na teraz trzymamy się potoku
        if not self.filepath_rules:
            self.console.insert("end", "⚠️ Ostrzeżenie: Brak wczytanych reguł DC. Potok użyje wartości domyślnych (Safety=False).\nMasz tu wygenerowane na bieżąco w GUI zasady? Kliknij 'Zapisz konfigurację' najpierw by je tu wpiąć.\n")
        else:
            self.console.insert("end", f"Wczytywanie reguł z tabeli: {os.path.basename(self.filepath_rules)}\n")
        
        try:
            bom_df = self._read_data_file(self.filepath_bom)
            fit_db = self._read_data_file(self.filepath_fit)
            
            # W przypadku pliku reguł: użyj wczytanego lub w locie zbuduj z GUI
            if self.filepath_rules:
                rules_db = self._read_data_file(self.filepath_rules)
            else:
                self.console.insert("end", "⚠️ Generowanie reguł na podstawie bieżącego stanu GUI (Brak podanego CSV).\n")
                records = []
                for row in self.config_rows:
                    sheet_num = row['sheet_val']
                    asil = row['opt_asil'].get()
                    dc_cov = 0.0
                    if asil == "ASIL A": dc_cov = 0.60
                    elif asil == "ASIL B": dc_cov = 0.90
                    elif asil == "ASIL C": dc_cov = 0.97
                    elif asil == "ASIL D": dc_cov = 0.99
                    
                    local_temp = row['t_eq'] if row['t_eq'] is not None else 85.0
                    
                    records.append({
                        "SheetNumber": sheet_num,
                        "Component_Class": "ALL",
                        "Safety_Related": row['var_safety'].get(),
                        "ASIL_Target": asil,
                        "Is_SPF": row['var_safety'].get(), 
                        "DC_Coverage": dc_cov,
                        "Local_Temp": local_temp
                    })
                rules_db = pd.DataFrame(records) if records else pd.DataFrame(columns=["SheetNumber", "Component_Class", "Safety_Related", "Is_SPF", "DC_Coverage", "Local_Temp"])

            # Konfiguracja pipeline i wstrzyknięcie zignorowania ostrzeżeń
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pipeline = FMEDAPipeline(bom_df, fit_db, rules_db)
                self.results = pipeline.run_pipeline()
            
            # Wypisywanie wyników
            self.console.insert("end", f"\nSukces! Przetworzono {len(self.results)} arkuszy schematu.\n")
            self.console.insert("end", "-" * 65 + "\n")
            self.console.insert("end", f"{'Arkusz':<25} | {'SPFM':<10} | {'LFM':<10} | {'Status'}\n")
            self.console.insert("end", "-" * 65 + "\n")
            
            for sheet, m in sorted(self.results.items()):
                if "error" in m:
                    self.console.insert("end", f"{sheet:<25} | BŁĄD OBLICZEŃ: {m['error']}\n")
                    continue
                    
                spfm = m.get("SPFM_pct", "N/A")
                lfm = m.get("LFM_pct", "N/A")
                
                # Zależnie od wybranego targetu w wierszu szukamy, czy status jest OK
                # (Dla uproszczenia wyświetlam statyczny status na podstawie SPFM > 97)
                spfm_val = m.get("SPFM")
                if spfm_val is None:
                    status = "— (SF Only)"
                else:
                    status = "✅ ASIL C" if spfm_val >= 0.97 else "⚠ Low Coverage"
                    if spfm_val >= 0.99:
                        status = "✅ ASIL D"

                self.console.insert("end", f"{sheet:<25} | {spfm:<10} | {lfm:<10} | {status}\n")
            
            self.console.insert("end", "-" * 65 + "\n")
            self.console.insert("end", "Pipeline zakończony pomyślnie. Dane są gotowe do raportowania.\n\n")
            
            self.btn_export.configure(state="normal") # Odblokowanie eksportu
            
        except Exception as e:
            self.console.insert("end", f"\nBŁĄD podczas wykonywania analizy:\n{str(e)}\n")
        
        self.console.see("end") # Automatyczne przewijanie na dół

    def export_report(self):
        if not hasattr(self, 'results') or not self.results:
            return
            
        save_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Plik", "*.csv")],
            title="Zapisz raport z analizy jako CSV"
        )
        
        if save_path:
            try:
                df_export = pd.DataFrame.from_dict(self.results, orient='index')
                df_export.index.name = "SheetNumber"
                df_export.to_csv(save_path, sep=';', decimal=',')
                self.console.insert("end", f"\nPomyślnie zapisano raport do:\n{save_path}\n")
                self.console.see("end")
            except Exception as e:
                self.console.insert("end", f"\nBŁĄD podczas zapisu pliku:\n{str(e)}\n")
                self.console.see("end")

if __name__ == "__main__":
    app = FMEDA_App()
    app.mainloop()

