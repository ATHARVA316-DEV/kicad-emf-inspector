"""
Shared physical constants and project metadata for EMF Inspector.

All physics constants are defined here as the single source of truth.
Other modules must import from here rather than redefining locally.
"""

from __future__ import annotations
import math

# ─────────────────────────────────────────────────────────────
# Project metadata
# ─────────────────────────────────────────────────────────────
__version__ = "1.1.0"

# ─────────────────────────────────────────────────────────────
# Electromagnetic constants (SI)
# ─────────────────────────────────────────────────────────────
MU_0      = 4 * math.pi * 1e-7   # H/m   — permeability of free space
EPSILON_0 = 8.854187817e-12       # F/m   — permittivity of free space
C_LIGHT   = 299_792_458.0         # m/s   — speed of light (exact, SI definition)

# ─────────────────────────────────────────────────────────────
# Copper properties
# ─────────────────────────────────────────────────────────────
RHO_CU    = 1.68e-8              # Ω·m   — copper resistivity at 20 °C
T_CU_1OZ  = 35e-6                # m     — 1 oz/ft² copper thickness

# ─────────────────────────────────────────────────────────────
# FR4 substrate defaults
# ─────────────────────────────────────────────────────────────
ER_FR4_DEFAULT   = 4.4           # dimensionless — relative permittivity
TAND_FR4_DEFAULT = 0.02          # dimensionless — loss tangent

# ─────────────────────────────────────────────────────────────
# Risk score thresholds (used by AI engine & report generator)
# ─────────────────────────────────────────────────────────────
RISK_CRITICAL_THRESHOLD = 70     # score >= 70 → Critical Risk
RISK_HIGH_THRESHOLD     = 40     # score >= 40 → High Risk
RISK_MEDIUM_THRESHOLD   = 20     # score >= 20 → Medium Risk
# Below 20 → Low Risk


def pcb_velocity_factor(er: float = ER_FR4_DEFAULT) -> float:
    """Signal propagation velocity factor on PCB dielectric.

    On a substrate with relative permittivity εr the effective phase
    velocity is reduced by 1/√εr compared to free space.

    Args:
        er: Relative dielectric permittivity of the substrate.

    Returns:
        Velocity factor in range (0, 1].
    """
    return 1.0 / math.sqrt(er)


def pcb_wavelength_mm(frequency_hz: float, er: float = ER_FR4_DEFAULT) -> float:
    """Effective guided wavelength on PCB substrate in millimetres.

    λ_eff = (c / f) × vf   where vf = 1/√εr

    For εr = 4.4 (FR4) the guided wavelength is approximately half the
    free-space value, which means antenna-like resonances occur at shorter
    physical trace lengths than free-space formulas predict.

    Args:
        frequency_hz: Signal frequency in Hz.
        er: Substrate relative permittivity (default 4.4 for FR4).

    Returns:
        Effective wavelength in millimetres.
    """
    vf = pcb_velocity_factor(er)
    return (C_LIGHT * vf / frequency_hz) * 1000.0


def risk_label(score: float) -> str:
    """Convert a 0-100 risk score to a human-readable label."""
    if score >= RISK_CRITICAL_THRESHOLD:
        return "CRITICAL"
    elif score >= RISK_HIGH_THRESHOLD:
        return "HIGH"
    elif score >= RISK_MEDIUM_THRESHOLD:
        return "MEDIUM"
    else:
        return "LOW"
