"""
EM Field Estimator Module
Estimates electric and magnetic field distributions over a PCB using
simplified analytical models (fast engineering estimation, not full-wave).

Physics models used:
  - Electric field: E = V / d  (parallel-plate / near-field approximation)
  - Magnetic field: B = μ₀ I / (2π r)  (Biot-Savart for infinite wire)
  - FR4 substrate correction: λ_eff = λ₀ / √εr  (εr = 4.4 for FR4)
  - Radiation estimate: combines both with frequency + loop-area correction

References:
  - Ott, H.W. (2009). Electromagnetic Compatibility Engineering. Wiley.
  - Paul, C.R. (2006). Introduction to Electromagnetic Compatibility. Wiley.
  - Balanis, C.A. (2016). Antenna Theory: Analysis and Design, 4th ed.
"""

from __future__ import annotations
import math
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from .pcb_parser import PCBBoard, Trace, Via, Point

# ─────────────────────────────────────────────────────────────
# Physical constants
# ─────────────────────────────────────────────────────────────
MU_0      = 4 * math.pi * 1e-7   # H/m  permeability of free space
EPSILON_0 = 8.854e-12            # F/m  permittivity of free space
C_LIGHT   = 2.998e8              # m/s  speed of light (exact)
RHO_CU    = 1.68e-8              # Ω·m  copper resistivity at 20°C
T_CU_1OZ  = 35e-6               # m    1 oz/ft² copper thickness

# FR4 substrate defaults
ER_FR4_DEFAULT    = 4.4          # dimensionless, relative permittivity
TAND_FR4_DEFAULT  = 0.02         # loss tangent (used for future attenuation)


def pcb_velocity_factor(er: float) -> float:
    """Signal propagation velocity factor on PCB dielectric.

    On a substrate with relative permittivity εr the effective phase
    velocity is reduced by 1/√εr compared to free space.  For microstrip
    an effective permittivity εr_eff ≈ (εr + 1)/2 is more accurate, but
    the simple √εr model gives good first-order correction.

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


def microstrip_impedance(width_mm: float, height_mm: float,
                          er: float = ER_FR4_DEFAULT,
                          t_mm: float = 0.035) -> float:
    """Hammerstad–Jensen closed-form microstrip characteristic impedance.

    Valid for w/h from 0.1 to 10 (covers most PCB trace geometries).

    Reference:
        Hammerstad, E. & Jensen, O. (1980). Accurate Models for Microstrip
        Computer-Aided Design. IEEE MTT-S Int. Microwave Symp. Digest.

    Args:
        width_mm:  Trace width in mm.
        height_mm: Dielectric thickness (core height) in mm.
        er:        Substrate relative permittivity.
        t_mm:      Copper thickness in mm (default 0.035 = 1 oz).

    Returns:
        Characteristic impedance Z₀ in Ohms, or None if geometry invalid.
    """
    if width_mm <= 0 or height_mm <= 0:
        return 50.0  # default assumption

    # Effective width correction for copper thickness
    if t_mm > 0 and t_mm < width_mm:
        w_eff = width_mm + (t_mm / math.pi) * (
            1.0 + math.log(2.0 * height_mm / t_mm))
    else:
        w_eff = width_mm

    u = w_eff / height_mm  # normalised width

    # Effective permittivity (Schneider approximation)
    er_eff = (er + 1) / 2 + (er - 1) / 2 * (
        1 / math.sqrt(1 + 12 / u))

    # Impedance (narrow trace u ≤ 1 vs wide trace u > 1)
    if u <= 1:
        Z0 = (60 / math.sqrt(er_eff)) * math.log(
            8 / u + u / 4)
    else:
        Z0 = (120 * math.pi) / (
            math.sqrt(er_eff) * (u + 1.393 + 0.667 * math.log(u + 1.444)))

    return round(Z0, 1)


# ─────────────────────────────────────────────────────────────
# Configuration dataclass
# ─────────────────────────────────────────────────────────────

@dataclass
class FieldEstimationConfig:
    """Configuration for EM field estimation."""
    frequency_hz: float = 2.4e9       # Operating frequency (Hz)
    supply_voltage: float = 3.3       # Supply voltage (V)
    typical_current_ma: float = 100.0 # Typical trace current (mA)
    grid_resolution: int = 100        # NxN computation grid
    layer: str = "F.Cu"               # Layer to analyse
    substrate_er: float = ER_FR4_DEFAULT   # Substrate εr (4.4 = FR4)
    board_height_mm: float = 1.6      # Dielectric thickness (mm)
    copper_oz: float = 1.0            # Copper weight (oz/ft²)

    @property
    def copper_thickness_mm(self) -> float:
        """Copper thickness derived from copper weight."""
        return self.copper_oz * 0.035   # 1 oz ≈ 35 µm


@dataclass
class EMFieldMap:
    """2D field maps over the PCB area."""
    x_grid: np.ndarray          # shape (N,)  — mm coordinates
    y_grid: np.ndarray          # shape (N,)  — mm coordinates
    E_field: np.ndarray         # shape (N, N) — V/m (near-field estimate)
    B_field: np.ndarray         # shape (N, N) — T (Biot-Savart estimate)
    power_density: np.ndarray   # shape (N, N) — W/m² (Poynting estimate)
    heatmap: np.ndarray         # shape (N, N) — 0..1 composite EMI index
    wavelength_mm: float = 0.0  # effective guided wavelength used
    velocity_factor: float = 1.0


# ─────────────────────────────────────────────────────────────
# Main estimator
# ─────────────────────────────────────────────────────────────

class EMFieldEstimator:
    """
    Computes approximate 2-D EM field maps for a PCB.

    The estimator superimposes the Biot-Savart magnetic field and the
    near-field electric field contribution from every trace segment on
    the selected copper layer.  A FR4-corrected guided wavelength is used
    throughout so that antenna-length thresholds are physically meaningful
    on real PCB substrates.

    This is an *estimation* engine: absolute field values carry an
    uncertainty of one to two orders of magnitude compared with full-wave
    simulation.  Relative comparisons (hotspot location, trend with
    frequency) are reliable.
    """

    def __init__(self, config: Optional[FieldEstimationConfig] = None):
        self.config = config or FieldEstimationConfig()

    # ── Public API ────────────────────────────────────────────

    def compute(self, board: PCBBoard,
                config: Optional[FieldEstimationConfig] = None) -> EMFieldMap:
        """Run field estimation and return field maps.

        Args:
            board:  Parsed PCB data.
            config: Estimation configuration (uses instance config if None).

        Returns:
            EMFieldMap with E, B, power density, and composite heatmap.
        """
        cfg = config or self.config
        N = cfg.grid_resolution
        ox, oy = board.origin.x, board.origin.y
        w,  h  = board.width,   board.height

        # Create computation grid (mm coordinates)
        xs = np.linspace(ox, ox + w, N)
        ys = np.linspace(oy, oy + h, N)
        XX, YY = np.meshgrid(xs, ys)

        E = np.zeros((N, N), dtype=np.float64)
        B = np.zeros((N, N), dtype=np.float64)

        # FR4-corrected guided wavelength
        lam_mm = pcb_wavelength_mm(cfg.frequency_hz, cfg.substrate_er)
        vf     = pcb_velocity_factor(cfg.substrate_er)

        # Layer filter
        traces = [t for t in board.traces
                  if t.layer == cfg.layer or cfg.layer == "ALL"]
        if not traces:
            traces = board.traces   # fallback: use all layers

        for trace in traces:
            I_A, V_drop = self._trace_electrics(trace, cfg)
            self._add_trace_contribution(
                XX, YY, trace, I_A, V_drop, lam_mm, E, B, cfg)

        for via in board.vias:
            if cfg.layer in via.layers or cfg.layer == "ALL":
                self._add_via_contribution(XX, YY, via, cfg, E, B)

        E_norm = self._normalize(E)
        B_norm = self._normalize(B)
        S      = (E * B) / MU_0 if np.any(B > 0) else np.zeros_like(E)

        # Composite heatmap — weighted sum of normalised fields
        heatmap = 0.4 * E_norm + 0.4 * B_norm + 0.2 * self._normalize(S)

        # Frequency correction: higher f → more efficient radiation
        freq_factor = min(1.0, cfg.frequency_hz / 3e9)
        heatmap = np.clip(
            heatmap * (0.5 + 0.5 * freq_factor) + freq_factor * 0.05, 0, 1)

        return EMFieldMap(
            x_grid=xs, y_grid=ys,
            E_field=E, B_field=B,
            power_density=S, heatmap=heatmap,
            wavelength_mm=lam_mm, velocity_factor=vf,
        )

    # ── Private helpers ───────────────────────────────────────

    @staticmethod
    def _trace_electrics(trace: Trace,
                          cfg: FieldEstimationConfig) -> tuple[float, float]:
        """Estimate current and voltage drop for a trace segment.

        Current scales with trace width (wider copper → more current
        capacity).  Resistance is computed from the copper resistivity,
        trace geometry, and copper thickness.

        Returns:
            (I_A, V_drop) — current in Amperes, voltage drop in Volts.
        """
        # Current: 100 mA baseline + 50 mA per mm width
        I_A = (cfg.typical_current_ma + trace.width * 50.0) * 1e-3

        # DC resistance: R = ρ L / (W × T)
        length_m = trace.length * 1e-3
        width_m  = trace.width  * 1e-3
        t_m      = cfg.copper_thickness_mm * 1e-3
        if width_m > 0 and t_m > 0:
            R = RHO_CU * length_m / (width_m * t_m)
        else:
            R = 0.1
        V_drop = I_A * R
        return I_A, V_drop

    def _add_trace_contribution(self, XX: np.ndarray, YY: np.ndarray,
                                 trace: Trace, I_A: float, V_drop: float,
                                 wavelength_mm: float,
                                 E: np.ndarray, B: np.ndarray,
                                 cfg: FieldEstimationConfig) -> None:
        """Add Biot-Savart and near-field E contributions of one trace.

        The trace is sampled at 1 mm intervals along its length.
        A loop-area radiation factor scales both fields based on
        the ratio L/λ (dipole radiation efficiency).
        """
        n_samples = max(3, int(trace.length))   # ≈ 1 sample per mm
        t_vals = np.linspace(0.0, 1.0, n_samples)

        # Radiation efficiency: scales as (L/λ)² capped at 1
        loop_factor = min((trace.length / wavelength_mm) ** 2 * 10.0, 1.0)

        for t in t_vals:
            px = trace.start.x + t * (trace.end.x - trace.start.x)
            py = trace.start.y + t * (trace.end.y - trace.start.y)

            r_mm = np.sqrt((XX - px)**2 + (YY - py)**2) + 0.1  # avoid /0
            r_m  = r_mm * 1e-3

            # Biot-Savart: B = μ₀ I / (2π r)
            B += (MU_0 * I_A) / (2.0 * math.pi * r_m) * (1.0 + loop_factor)

            # Near-field E = V / d
            if trace.length > 0:
                E += (V_drop / (r_m + 1e-6)) * (1.0 + loop_factor * 0.5)

    def _add_via_contribution(self, XX: np.ndarray, YY: np.ndarray,
                               via: Via,
                               cfg: FieldEstimationConfig,
                               E: np.ndarray, B: np.ndarray) -> None:
        """Add localised field spike from a via transition.

        Vias create inductive discontinuities (stub inductance ≈ 1 nH),
        which appear as field hotspots especially at high frequencies.
        """
        r_mm = np.sqrt((XX - via.position.x)**2 +
                       (YY - via.position.y)**2) + 0.1
        r_m  = r_mm * 1e-3
        I_A  = cfg.typical_current_ma * 1e-3
        B   += (MU_0 * I_A) / (2.0 * math.pi * r_m) * 2.0
        E   += (cfg.supply_voltage / (r_m + 1e-6)) * 0.1

    @staticmethod
    def _normalize(arr: np.ndarray) -> np.ndarray:
        """Min-max normalise array to [0, 1]."""
        mn, mx = arr.min(), arr.max()
        if mx - mn < 1e-30:
            return np.zeros_like(arr)
        return (arr - mn) / (mx - mn)
