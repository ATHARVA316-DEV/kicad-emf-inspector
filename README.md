# ⚡ EMF Inspector — AI-Powered PCB EMI Analyzer

A **production-quality** standalone Python tool that analyzes KiCad PCB files
for electromagnetic interference (EMI), RF design issues, and signal integrity risks.
No Ansys HFSS or CST Studio required.

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Application

```bash
python main.py
```

### 3. Load a PCB or Use Demo Board

- Click **📂 Open PCB File** to load a `.kicad_pcb` file
- Click **🧪 Demo Board** to load a synthetic ESP32 RF board
- Select **RF Frequency** and **Layer**
- Click **⚡ Analyze Board**

---

## 📁 Project Structure

```
kicad_builds/
├── main.py                          # Main GUI application (entry point)
├── requirements.txt                 # Python dependencies
├── README.md                        # This file
│
├── emf_inspector/                   # Core package
│   ├── __init__.py
│   └── core/
│       ├── __init__.py
│       ├── pcb_parser.py            # .kicad_pcb S-expression parser
│       ├── field_estimator.py       # E/B field estimation engine
│       ├── emi_detector.py          # 12 EMI rule-based detectors
│       ├── ai_engine.py             # Physics-based AI explanations
│       └── report_generator.py     # PDF / HTML / JSON export
│
└── tests/
    └── test_core.py                 # Unit tests (pytest)
```

---

## 🔬 Analysis Capabilities

### EM Field Estimation
| Field | Model | Output |
|-------|-------|--------|
| Electric (E) | E = V/d near-field | V/m heatmap |
| Magnetic (B) | Biot-Savart B = μ₀I/2πr | T field map |
| Power density | S = E×H (Poynting) | W/m² composite |

### EMI Detectors (12 rules)
| # | Check | Physics |
|---|-------|---------|
| 1 | Long RF traces (>λ/20) | Radiation efficiency ∝ (L/λ)² |
| 2 | Large current loops | P_rad ∝ (I·A·f²)² |
| 3 | Missing return paths | Return current inductance |
| 4 | Ground plane discontinuities | Image current theory |
| 5 | Traces crossing split planes | Return current detour |
| 6 | Excessive via transitions | Stub inductance L=μ₀h/2π·ln(4h/d) |
| 7 | Crosstalk (3W rule) | Capacitive/inductive coupling |
| 8 | Quarter-wave antennas (λ/4) | Monopole resonance Rrad=36.5Ω |
| 9 | Unshielded RF traces | Field confinement (CPW theory) |
| 10 | Poor decoupling placement | ESL = L_trace dominates |
| 11 | Transmission line behavior | TL theory when L>λ/10 |
| 12 | Impedance discontinuities | Γ=(Z2-Z1)/(Z2+Z1) |

### RF Frequency Support
- 1 MHz, 10 MHz, 100 MHz
- 433 MHz, 868 MHz, 915 MHz (IoT/LoRa)
- 2.4 GHz (Wi-Fi, Bluetooth, Zigbee)
- 5.8 GHz (Wi-Fi 5/6)

---

## 🖥️ UI Features

| Feature | Description |
|---------|-------------|
| **2D Heatmap** | Color overlay: green→yellow→orange→red |
| **Layer selector** | Analyze F.Cu, B.Cu, inner layers |
| **EMI/RF Score gauges** | 0–100 circular gauges |
| **Issue list** | Filterable by severity (CRITICAL/HIGH/MEDIUM/LOW) |
| **AI Inspector** | Click any issue for physics explanation + fix steps |
| **Zoom/pan** | Matplotlib navigation toolbar |
| **Map types** | Composite / E-field / B-field |

---

## 📤 Export Formats

```bash
# All from the GUI:
# File → Export → HTML / JSON / PDF
```

| Format | Contents |
|--------|----------|
| **HTML** | Interactive dark-themed report with AI explanations |
| **JSON** | Machine-readable data (CI/CD integration ready) |
| **PDF** | Multi-page printable report with heatmap |

---

## 🧪 Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

Expected: **~25 tests**, all passing.

---

## 🏗️ Architecture

```
.kicad_pcb file
      │
      ▼
 KiCadPCBParser          (pure Python S-expr parser)
      │
      ▼
   PCBBoard              (traces, vias, pads, zones, nets)
      │
      ├──► EMFieldEstimator   ──► EMFieldMap (E, B, heatmap grids)
      │                                │
      ├──► EMIDetector        ──► EMIReport (12 rule checks + scores)
      │                                │
      ├──► AIAnalysisEngine   ──► AIExplanation (physics + fixes)
      │
      ├──► VisualizationPanel  (matplotlib heatmap + PCB overlay)
      ├──► IssueListPanel      (tkinter listbox with severity filter)
      ├──► AIInspectorPanel    (rich text AI explanations)
      └──► ReportGenerator    (HTML / JSON / PDF)
```

---

## 🔮 Future: KiCad Plugin Integration

This code is structured to be directly wrapped into a KiCad plugin:

1. Replace `pcb_parser.py` with KiCad `pcbnew` API calls
2. Replace `main.py` GUI with KiCad dockable panel (PySide6)
3. Register as KiCad plugin action

---

## ⚠️ Disclaimer

This tool provides **engineering estimations** based on analytical models,
not full-wave electromagnetic simulation. Results should be validated
with proper EM simulation (OpenEMS, FastHenry, Elmer FEM) for
production designs. EMI scores are relative indicators, not absolute
field strength measurements.

---

*Built with Python · NumPy · Matplotlib · tkinter*
