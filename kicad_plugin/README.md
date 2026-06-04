# EMF Inspector — KiCad Plugin

⚡ **Physics-based EMI analysis directly inside KiCad's PCB editor.**

![EMF Inspector](plugins/emf_inspector_plugin/resources/icon.png)

## Features

- **12+ EMI Detection Rules** — Long RF traces, current loops, crosstalk, impedance discontinuities, missing return paths, decoupling placement, antenna structures, and more
- **FR4-Corrected Physics** — Wavelength calculations use substrate-corrected values (εr = 4.4), not free-space approximations
- **AI-Powered Explanations** — Each issue includes physics background, EMI consequences, and step-by-step fix recommendations
- **Severity Scoring** — EMI Score (0–100) and RF Score with CRITICAL/HIGH/MEDIUM/LOW classifications
- **Export Reports** — HTML and JSON report export directly from the plugin
- **Works Offline** — All analysis runs locally, no internet required

## Installation

### Method 1: Manual Install (Recommended)

1. **Find your KiCad plugins directory:**
   - **Windows:** `%APPDATA%\KiCad\8.0\scripting\plugins\`
   - **macOS:** `~/Library/Preferences/KiCad/8.0/scripting/plugins/`
   - **Linux:** `~/.local/share/KiCad/8.0/scripting/plugins/`

   > For KiCad 7, replace `8.0` with `7.0`.

2. **Copy the plugin folder:**
   - Extract the ZIP file
   - Copy the entire `emf_inspector_plugin` folder into your plugins directory

3. **Restart KiCad** and open a PCB in the PCB Editor

4. **Find EMF Inspector** in the toolbar (⚡ icon) or under **Tools → External Plugins → EMF Inspector**

### Method 2: KiCad Plugin Manager (PCM)

> Coming soon — the plugin will be submitted to the KiCad PCM repository.

## Requirements

- **KiCad 7.0+** (tested on 7.0, 8.0, 9.0)
- **Python 3.10+** (bundled with KiCad)
- **NumPy** (usually bundled with KiCad's Python)
- **Matplotlib** (usually bundled with KiCad's Python)

## Usage

1. Open a PCB file in KiCad's PCB Editor
2. Click the **⚡ EMF Inspector** button in the toolbar
3. Enter your operating frequency (in MHz)
4. View the analysis results with severity-coded issues
5. Click **Export HTML Report** or **Export JSON** to save

## File Structure

```
emf_inspector_plugin/
├── __init__.py              # Main plugin (ActionPlugin class)
├── resources/
│   ├── icon.png             # 128×128 plugin icon
│   ├── icon_24x24.png       # Toolbar icon
│   └── icon_64x64.png       # Dialog icon
└── emf_core/                # Bundled analysis engine
    ├── __init__.py
    ├── constants.py          # Physical constants & shared config
    ├── pcb_parser.py         # KiCad S-expression parser
    ├── field_estimator.py    # Biot-Savart / near-field estimator
    ├── emi_detector.py       # 12+ rule-based EMI detectors
    ├── ai_engine.py          # Physics explanation templates
    └── report_generator.py   # HTML/JSON/PDF export
```

## License

MIT License — see [LICENSE](../LICENSE)
