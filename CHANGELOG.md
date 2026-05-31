# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-31

### Added
- **PCB Parser**: Pure Python parser for KiCad `.kicad_pcb` layout files supporting traces, vias, pads, ground zones, and components.
- **Field Estimator**: Physics-based 2D electromagnetic field estimation (Biot-Savart magnetic fields and near-field electric fields).
- **FR4 Dielectric Physics**: Implemented velocity factor correction and Hammerstad-Jensen microstrip impedance models for real PCB substrate conditions.
- **EMI Detection Engine**: 12 automated rule checks (long RF traces, quarter-wave antennas, large loops, ground gaps, crosstalk, decoupling, via counts, etc.).
- **AI Inspector Engine**: Provides detailed physics explanations, root cause analysis, and actionable fix steps for every detected EMI issue.
- **Report Generator**: HTML, JSON, and PDF export capabilities.
- **GUI Application**: Dark-themed interactive desktop application using standard `tkinter` and `matplotlib` (zero heavy Qt dependencies).
