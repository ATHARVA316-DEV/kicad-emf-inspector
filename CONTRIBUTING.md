# Contributing to EMF Inspector

Thank you for your interest in contributing to **EMF Inspector**! This document provides everything you need to get started, whether you're fixing a bug, adding a new EMI detection rule, or improving the documentation.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Setting Up the Development Environment](#setting-up-the-development-environment)
3. [Running the Test Suite](#running-the-test-suite)
4. [Project Architecture Overview](#project-architecture-overview)
5. [Adding New EMI Detectors](#adding-new-emi-detectors)
6. [Code Style Guidelines](#code-style-guidelines)
7. [Submitting a Pull Request](#submitting-a-pull-request)
8. [Reporting Bugs](#reporting-bugs)
9. [Feature Requests](#feature-requests)

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before contributing.

---

## Setting Up the Development Environment

### Prerequisites

- **Python 3.10 or 3.11** (recommended; other versions may work but are untested)
- **Git**
- A virtual environment tool (`venv` or `conda`)

### Step-by-Step Setup

1. **Fork the repository** on GitHub, then clone your fork locally:

   ```bash
   git clone https://github.com/<your-username>/emf-inspector.git
   cd emf-inspector
   ```

2. **Create and activate a virtual environment:**

   ```bash
   # On Linux/macOS
   python3 -m venv .venv
   source .venv/bin/activate

   # On Windows (PowerShell)
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. **Install the package in editable mode with all development dependencies:**

   ```bash
   pip install -e ".[dev]"
   ```

   This installs:
   - The `emf_inspector` package itself (editable / "development" install)
   - All runtime dependencies (`numpy`, `scipy`, `matplotlib`, `shapely`, `networkx`)
   - All development-only extras: `pytest`, `pytest-cov`, `black`, `flake8`, `mypy`, `sphinx`, `sphinx-rtd-theme`

4. **Verify the installation:**

   ```bash
   python -c "import emf_inspector; print(emf_inspector.__version__)"
   emf-inspector --version
   ```

### Optional: Set Up Pre-commit Hooks

We strongly recommend installing the pre-commit hooks to automatically enforce code style before each commit:

```bash
pip install pre-commit
pre-commit install
```

---

## Running the Test Suite

All tests live in the `tests/` directory and are written with **pytest**.

### Run the full test suite

```bash
python -m pytest tests/ -v --tb=short
```

### Run tests with coverage

```bash
python -m pytest tests/ -v --tb=short --cov=emf_inspector --cov-report=term-missing
```

### Run a specific test file

```bash
python -m pytest tests/test_emi_detector.py -v
```

### Run a specific test by name

```bash
python -m pytest tests/test_emi_detector.py::test_via_stitching_rule -v
```

### Checking syntax correctness of core modules

```bash
python -m py_compile emf_inspector/core/pcb_parser.py \
                     emf_inspector/core/field_estimator.py \
                     emf_inspector/core/emi_detector.py \
                     emf_inspector/core/ai_engine.py \
                     emf_inspector/core/report_generator.py
```

All tests **must pass** before a pull request can be merged. If you add new functionality, please include corresponding tests.

---

## Project Architecture Overview

```
emf_inspector/
├── core/
│   ├── pcb_parser.py        # KiCad .kicad_pcb file parser (S-expression)
│   ├── field_estimator.py   # Physics engine: Biot-Savart, near-field, radiation
│   ├── emi_detector.py      # EMIDetector base class + all 12 rule implementations
│   ├── ai_engine.py         # Heuristic/ML-based recommendation engine
│   └── report_generator.py  # HTML/PDF report synthesis
├── gui/
│   ├── main_window.py       # Qt/Tkinter main window
│   ├── canvas.py            # PCB rendering canvas
│   └── widgets.py           # Reusable UI widgets
├── utils/
│   ├── constants.py         # Physical constants (mu0, epsilon0, c, etc.)
│   ├── geometry.py          # Shapely-based geometry helpers
│   └── units.py             # Unit conversion utilities
tests/
├── conftest.py
├── fixtures/                # Sample .kicad_pcb files for testing
├── test_pcb_parser.py
├── test_field_estimator.py
├── test_emi_detector.py
├── test_ai_engine.py
└── test_report_generator.py
```

---

## Adding New EMI Detectors

All EMI detection rules are implemented as subclasses of the `EMIDetector` abstract base class defined in `emf_inspector/core/emi_detector.py`.

### The `EMIDetector` Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

@dataclass
class EMIFinding:
    """Represents a single EMI issue found on the PCB."""
    rule_id: str          # Unique identifier, e.g. "EMI-007"
    severity: str         # "critical", "warning", or "info"
    description: str      # Human-readable description of the issue
    location: tuple       # (x, y) coordinates in mm on the PCB
    net_name: str         # The net where the issue was found
    recommendation: str   # Actionable fix suggestion
    reference_standard: str = ""  # e.g. "IPC-2141A Section 4.2"
    extra: dict = field(default_factory=dict)  # Rule-specific extra data


class EMIDetector(ABC):
    """Abstract base class for all EMI detection rules."""

    # --- Required class-level attributes ---
    rule_id: str        # Must be unique across all detectors, e.g. "EMI-013"
    name: str           # Short human-readable rule name
    description: str    # One-sentence description of what this rule checks
    category: str       # One of: "routing", "power", "ground", "signal", "thermal"
    severity: str       # Default severity: "critical", "warning", or "info"

    def __init__(self, config: dict = None):
        """
        Args:
            config: Optional dict of rule-specific configuration parameters.
                    Keys and their defaults should be documented in the subclass.
        """
        self.config = config or {}

    @abstractmethod
    def analyze(self, pcb_data: dict) -> List[EMIFinding]:
        """
        Run this rule against the parsed PCB data.

        Args:
            pcb_data: The dictionary produced by `PCBParser.parse()`.
                      See pcb_parser.py for the full schema.

        Returns:
            A list of `EMIFinding` objects. Return an empty list if no issues
            are found — never return None.
        """
        ...

    def is_enabled(self) -> bool:
        """Return False to disable this rule by default (can be overridden by config)."""
        return self.config.get("enabled", True)
```

### Step-by-Step: Adding a New Detector

1. **Choose a unique `rule_id`** following the format `EMI-NNN` (check `emi_detector.py` for the next available number).

2. **Create your class** in `emf_inspector/core/emi_detector.py` (or a separate file that you import in `emi_detector.py`):

   ```python
   class DifferentialPairSkewDetector(EMIDetector):
       """EMI-013: Detects excessive length mismatch in differential pairs."""

       rule_id = "EMI-013"
       name = "Differential Pair Skew"
       description = (
           "Checks that positive and negative traces of differential pairs "
           "have length mismatch below the threshold (default 100 mil)."
       )
       category = "signal"
       severity = "warning"

       # Default configuration — document all keys here
       DEFAULT_MAX_SKEW_MM = 2.54  # 100 mil

       def analyze(self, pcb_data: dict) -> List[EMIFinding]:
           findings = []
           max_skew = self.config.get("max_skew_mm", self.DEFAULT_MAX_SKEW_MM)

           for pair_name, traces in pcb_data.get("diff_pairs", {}).items():
               pos_len = traces["positive"]["length_mm"]
               neg_len = traces["negative"]["length_mm"]
               skew = abs(pos_len - neg_len)

               if skew > max_skew:
                   findings.append(EMIFinding(
                       rule_id=self.rule_id,
                       severity=self.severity,
                       description=(
                           f"Differential pair '{pair_name}' has {skew:.2f} mm "
                           f"length mismatch (limit: {max_skew:.2f} mm)."
                       ),
                       location=traces["positive"]["midpoint"],
                       net_name=pair_name,
                       recommendation=(
                           "Add serpentine length-matching tuning on the shorter trace. "
                           "Keep the tuning section close to the source end."
                       ),
                       reference_standard="IPC-2141A, IEEE 802.3",
                       extra={"skew_mm": skew, "pos_len_mm": pos_len, "neg_len_mm": neg_len},
                   ))

           return findings
   ```

3. **Register your detector** by adding it to the `ALL_DETECTORS` list at the bottom of `emi_detector.py`:

   ```python
   ALL_DETECTORS = [
       # ... existing detectors ...
       DifferentialPairSkewDetector,
   ]
   ```

4. **Write tests** in `tests/test_emi_detector.py`:

   ```python
   def test_diff_pair_skew_exceeds_limit(sample_pcb_with_skewed_pairs):
       detector = DifferentialPairSkewDetector(config={"max_skew_mm": 1.0})
       findings = detector.analyze(sample_pcb_with_skewed_pairs)
       assert len(findings) == 1
       assert findings[0].rule_id == "EMI-013"
       assert findings[0].severity == "warning"

   def test_diff_pair_skew_within_limit(sample_pcb_with_matched_pairs):
       detector = DifferentialPairSkewDetector()
       findings = detector.analyze(sample_pcb_with_matched_pairs)
       assert findings == []
   ```

5. **Update the documentation** in `docs/detectors.rst` with a description of your new rule.

6. **Bump the detector count** in `README.md` if applicable.

### Configuration Pattern

Detectors can be configured by passing a `config` dict. Always document all configuration keys and their defaults as class-level constants or in the class docstring. This allows users to tune rules without modifying source code.

---

## Code Style Guidelines

EMF Inspector follows **PEP 8** with the following additional conventions:

### Formatting

- We use **Black** for automatic code formatting (line length: 88).
- Run before committing:
  ```bash
  black emf_inspector/ tests/
  ```

### Linting

- We use **Flake8** for style and error checking:
  ```bash
  flake8 emf_inspector/ tests/ --max-line-length=88 --extend-ignore=E203,W503
  ```

### Type Annotations

- All public functions and methods **must** have type annotations.
- We use **mypy** for static type checking:
  ```bash
  mypy emf_inspector/ --ignore-missing-imports
  ```

### Docstrings

- Use **Google-style docstrings** for all public classes and functions.
- Every public function must have at least a one-line summary docstring.

### Naming Conventions

| Item | Convention | Example |
|------|-----------|---------|
| Modules | `snake_case` | `field_estimator.py` |
| Classes | `PascalCase` | `EMIDetector` |
| Functions/methods | `snake_case` | `analyze_trace_length()` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_MAX_SKEW_MM` |
| Private attributes | `_leading_underscore` | `self._cache` |

### Imports

- Organize imports in three groups separated by blank lines: stdlib → third-party → local.
- Use `isort` to sort imports automatically:
  ```bash
  isort emf_inspector/ tests/
  ```

---

## Submitting a Pull Request

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/emi-013-diff-pair-skew
   ```

2. **Make your changes**, following the guidelines above.

3. **Ensure all tests pass:**
   ```bash
   python -m pytest tests/ -v --tb=short
   ```

4. **Run the linters:**
   ```bash
   black --check emf_inspector/ tests/
   flake8 emf_inspector/ tests/ --max-line-length=88
   mypy emf_inspector/ --ignore-missing-imports
   ```

5. **Update documentation** if you changed or added public APIs.

6. **Update `CHANGELOG.md`** under the `[Unreleased]` section, following the [Keep a Changelog](https://keepachangelog.com/) format.

7. **Push your branch and open a Pull Request** against `main`:
   - Fill in the PR template completely.
   - Reference any related issues (e.g., `Closes #42`).
   - Describe *what* you changed and *why*.
   - Include screenshots or test output if relevant.

8. **Respond to review feedback.** A maintainer will review your PR within 5 business days. Maintain a respectful, collaborative tone.

### PR Checklist

- [ ] Tests pass locally (`pytest tests/ -v`)
- [ ] New functionality has test coverage
- [ ] Code formatted with Black
- [ ] No new Flake8 warnings
- [ ] Docstrings added/updated
- [ ] `CHANGELOG.md` updated
- [ ] Documentation updated (if applicable)

---

## Reporting Bugs

Please report bugs using **GitHub Issues** with the following template:

```
**Bug Report**

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Load PCB file '...'
2. Run analysis with options '...'
3. See error

**Expected behavior**
A clear description of what you expected to happen.

**Actual behavior**
What actually happened. Include the full error message and stack trace.

**Environment**
- OS: [e.g. Ubuntu 22.04, Windows 11, macOS 14]
- Python version: [e.g. 3.11.2]
- EMF Inspector version: [e.g. 1.0.0]
- KiCad version (if relevant): [e.g. 7.0.10]

**Sample PCB file**
If possible, attach or link to a minimal `.kicad_pcb` file that reproduces the issue.

**Additional context**
Any other context about the problem here.
```

**Please search existing issues** before opening a new one to avoid duplicates.

For security vulnerabilities, do **not** use public issues — email the maintainers directly.

---

## Feature Requests

Feature requests are welcome! Open a GitHub Issue with the label `enhancement` and describe:

- **The problem** you're trying to solve.
- **Your proposed solution** or the feature you'd like to see.
- **Alternatives** you've considered.
- **Additional context**, such as references to EMC standards or academic papers supporting the request.

---

*Thank you for helping make EMF Inspector better for the PCB design community!*
