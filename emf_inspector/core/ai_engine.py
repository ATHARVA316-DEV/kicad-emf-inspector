"""
AI Analysis Engine
Generates intelligent, physics-based explanations and design recommendations
using template-driven responses (offline, no LLM API required).

Each explanation covers:
  1. Why the warning occurred
  2. The underlying physics
  3. EMI consequences
  4. Step-by-step recommendations
"""

from __future__ import annotations
from dataclasses import dataclass
from .emi_detector import EMIIssue, Severity

C_LIGHT = 3e8


@dataclass
class AIExplanation:
    issue_title: str
    why_it_happened: str
    physics_background: str
    emi_consequence: str
    fix_steps: list[str]
    priority: str
    estimated_improvement: str


# Rich physics explanation templates
_TEMPLATES: dict[str, dict] = {

    "Long RF Trace": {
        "why": (
            "Your trace length is electrically significant at the selected "
            "frequency. When a conductor's length approaches a significant "
            "fraction of the signal wavelength (λ/20 or more), it can no "
            "longer be treated as a simple wire — it becomes a radiating element."
        ),
        "physics": (
            "At frequency f, the wavelength λ = c/f. A conductor of length L "
            "radiates efficiently when L ≈ λ/4 (quarter-wave monopole). The "
            "radiation efficiency η scales as (L/λ)². Radiation resistance "
            "Rrad ≈ 80π²(L/λ)² Ω. For L = λ/4, Rrad ≈ 40 Ω — comparable to "
            "the 50 Ω system impedance, making it an extremely efficient radiator."
        ),
        "consequence": (
            "Unintended radiation causes EMC test failures (radiated emissions). "
            "The trace becomes an antenna that transmits noise at the clock "
            "frequency and its harmonics, potentially causing interference "
            "with nearby wireless systems (Bluetooth, Wi-Fi, cellular)."
        ),
        "steps": [
            "Calculate λ for your frequency: λ(mm) = 300,000 / f(MHz)",
            "Keep all signal traces below λ/20",
            "If the trace must be long, control its impedance (50 Ω microstrip)",
            "Add a ground guard trace (GND) on both sides",
            "Consider using a coplanar waveguide (CPW) structure",
            "Add RF shielding can over the RF section if needed"
        ],
        "priority": "HIGH",
        "improvement": "Shortening below λ/20 can reduce radiated emissions by 20–40 dB"
    },

    "Large Current Loop": {
        "why": (
            "Signal currents always need a return path to their source. When "
            "the return path (usually GND) is far from the signal trace, the "
            "signal and its return current form a large loop. This loop acts "
            "as a magnetic dipole antenna."
        ),
        "physics": (
            "The magnetic dipole radiation formula: P_rad ∝ (I × A × f²)² "
            "where I is current, A is loop area, f is frequency. Doubling the "
            "loop area quadruples the radiated power. Doubling frequency "
            "increases radiation by 16×. Even small currents (10 mA) in a "
            "large loop (1000 mm²) can cause FCC Part 15 failures."
        ),
        "consequence": (
            "Large current loops are the #1 cause of magnetic field EMI. "
            "They generate H-field that couples into nearby circuits, "
            "power supplies, and cables. CISPR 25/FCC radiated emissions "
            "tests will detect this."
        ),
        "steps": [
            "Route GND return trace directly alongside signal trace",
            "Use a solid ground plane — return current follows path of least inductance",
            "Minimize the physical area enclosed by signal + return path",
            "For power circuits, use twisted pairs or differential signaling",
            "Add GND stitching vias to tie surface GND to plane GND"
        ],
        "priority": "CRITICAL",
        "improvement": "Reducing loop area by 10× reduces radiated EMI by 20 dB"
    },

    "Missing Return Path": {
        "why": (
            "High-speed signals switching at fast edge rates generate broadband "
            "noise. Without a low-impedance GND return path adjacent to the "
            "signal trace, return currents are forced to find alternate paths "
            "through the board, creating unintended radiation."
        ),
        "physics": (
            "Current follows the path of least impedance (not least resistance). "
            "At high frequencies, inductance dominates: Z = jωL. A GND trace "
            "directly below a signal trace provides the lowest inductance return "
            "path (coupled microstrip). Without this, return current spreads "
            "out, increasing effective loop area and L."
        ),
        "consequence": (
            "Signal integrity degradation: reflections, ringing, jitter. "
            "Increased common-mode noise on cables. Poor EMC performance. "
            "Potential data corruption on adjacent signals (ground bounce)."
        ),
        "steps": [
            "Place GND stitching vias every 5–10 mm along high-speed traces",
            "Ensure solid ground plane exists on adjacent copper layer",
            "Add bypass capacitors from VCC to GND at source and load",
            "Use differential pairs (LVDS, CML) to eliminate return path issues",
            "Check that all ICs have GND thermal pad properly connected"
        ],
        "priority": "HIGH",
        "improvement": "Proper return path reduces common-mode emissions by 15–25 dB"
    },

    "Ground Plane Discontinuity": {
        "why": (
            "The ground plane provides the return current path for all signals. "
            "A split or gap in the ground plane forces return currents to detour "
            "around the gap, dramatically increasing the effective loop area at "
            "the crossing point."
        ),
        "physics": (
            "Return current in a ground plane follows the magnetic field "
            "distribution directly below the signal trace (image current theory). "
            "A gap in the plane forces current to flow around it, creating a "
            "large current loop whose area equals approximately: "
            "A ≈ trace_length × gap_width. This area drives magnetic radiation."
        ),
        "consequence": (
            "The gap acts as a slot antenna, radiating strongly at frequencies "
            "where gap length ≈ λ/2. This is a classic cause of radiated EMI "
            "failures. The slot also creates ground bounce between the two "
            "ground regions."
        ),
        "steps": [
            "Never route signal traces across ground plane splits",
            "Bridge the gap with GND stitching vias on each side",
            "Re-route signal traces to stay within one ground region",
            "If a split is intentional, add bridge capacitors across it",
            "Use pour/fill to create continuous ground coverage"
        ],
        "priority": "HIGH",
        "improvement": "Eliminating ground plane splits can reduce emissions by 20–30 dB"
    },

    "Crosstalk Risk": {
        "why": (
            "When two traces run parallel and close together, electromagnetic "
            "coupling occurs through both electric fields (capacitive coupling) "
            "and magnetic fields (inductive coupling). The victim trace picks "
            "up noise from the aggressor trace."
        ),
        "physics": (
            "Capacitive coupling: I_victim = C_mutual × dV/dt × ΔV. "
            "Inductive coupling: V_victim = M × dI/dt. "
            "Mutual capacitance and inductance both scale inversely with trace "
            "separation. The 3W rule (separation = 3× trace width) reduces "
            "coupling by approximately 70%."
        ),
        "consequence": (
            "False switching of digital signals. Degraded SNR on analog signals. "
            "Bit errors in high-speed data. Increased EMI through common-mode "
            "conversion. LVDS or single-ended signals may see eye closure."
        ),
        "steps": [
            "Apply 3W rule: trace-edge to trace-edge ≥ 3× trace width",
            "Insert GND guard trace between sensitive signals",
            "Minimize the parallel run length between aggressor and victim",
            "Use differential signaling for noise immunity",
            "Route sensitive analog traces on a separate layer from digital"
        ],
        "priority": "MEDIUM",
        "improvement": "3W spacing reduces crosstalk by ~70% compared to 1W spacing"
    },

    "Quarter-Wave Antenna Effect": {
        "why": (
            "The trace length exactly matches the quarter-wavelength resonance "
            "at your operating frequency. At this length, the trace presents "
            "a resistive (real) impedance and achieves maximum radiation "
            "efficiency — it becomes a tuned antenna."
        ),
        "physics": (
            "A quarter-wave monopole above a ground plane has: "
            "Radiation resistance Rrad = 36.5 Ω, gain G = 5.15 dBi. "
            "At resonance, reactive components cancel and all delivered "
            "power goes to radiation. This is by far the most efficient "
            "accidental radiator geometry."
        ),
        "consequence": (
            "Maximum radiated EMI at the operating frequency. This will "
            "almost certainly fail radiated emissions tests (FCC, CE, CISPR). "
            "The trace will also receive RF energy, potentially disrupting "
            "on-board circuits through RE susceptibility."
        ),
        "steps": [
            "Immediately shorten or lengthen the trace to detune from λ/4",
            "Target trace length < λ/20 for low radiation",
            "If an antenna is intentional, add proper matching network",
            "Shield the area with a metal can or EMC coating",
            "Add series ferrite bead to detune the resonance"
        ],
        "priority": "CRITICAL",
        "improvement": "Detuning from λ/4 can reduce radiated power by 20–40 dB"
    },

    "Excessive Via Transitions": {
        "why": (
            "Each via introduces a parasitic inductance (typically 0.5–1 nH) "
            "and a capacitance stub. Multiple vias in series on the same net "
            "create significant parasitic inductance that degrades signal "
            "integrity and increases EMI at high frequencies."
        ),
        "physics": (
            "Via inductance: L_via ≈ (μ₀ × h)/(2π) × ln(4h/d) + h/d "
            "where h = board thickness, d = via diameter. "
            "Via stub resonates at f_res = c/(4 × stub_length × √ε_r). "
            "Multiple vias multiply the inductance, raising impedance: "
            "Z = jωL_total."
        ),
        "consequence": (
            "Signal reflections and ringing at each via transition. "
            "Resonant peaks in insertion loss. Ground bounce when "
            "high-current vias are involved. The via inductance also "
            "reduces the effectiveness of decoupling capacitors."
        ),
        "steps": [
            "Minimize layer transitions on RF/high-speed signals",
            "Use smaller drill vias (microvias) to reduce inductance",
            "Back-drill blind vias to eliminate stubs",
            "Place GND return vias adjacent to each signal via",
            "For power supply vias, use multiple parallel vias"
        ],
        "priority": "MEDIUM",
        "improvement": "Reducing via count and stub length can improve SI by 3–10 dB"
    },

    "Unshielded RF Trace": {
        "why": (
            "RF signals on PCB traces radiate electromagnetic energy. Without "
            "adjacent ground conductors to define a controlled field region "
            "(as in microstrip or CPW topologies), the field distribution "
            "is uncontrolled and radiation is maximized."
        ),
        "physics": (
            "Coplanar waveguide (CPW): the electric field is mostly "
            "concentrated between the signal trace and adjacent ground conductors. "
            "A bare microstrip without ground guard has a wider field spread. "
            "The characteristic impedance Z₀ and field confinement both depend "
            "on the ratio W/h and gap geometry."
        ),
        "consequence": (
            "Uncontrolled RF radiation. Susceptibility to external RF. "
            "Impedance discontinuities. Coupling to adjacent digital signals. "
            "Potential regulatory compliance failure."
        ),
        "steps": [
            "Add GND guard traces on both sides of RF trace (CPW structure)",
            "Add via fencing: GND vias spaced λ/10 apart along the trace",
            "Ensure ground plane exists below the RF trace (grounded CPW)",
            "Use coax-to-PCB connector with proper ground transition",
            "Calculate and maintain 50 Ω impedance throughout RF path"
        ],
        "priority": "HIGH",
        "improvement": "Proper RF routing can reduce radiation by 10–20 dB"
    },

    "Poor Decoupling Capacitor Placement": {
        "why": (
            "Decoupling capacitors only work effectively when their parasitic "
            "inductance (ESL) is minimized. ESL is dominated by the PCB trace "
            "inductance between the capacitor and the IC power pin. A physically "
            "distant capacitor has high trace inductance and is ineffective at "
            "high frequencies."
        ),
        "physics": (
            "Effective frequency range of a decoupling capacitor: "
            "f_max = 1/(2π√(L_trace × C)). For a 100 nF cap with 10 nH "
            "trace inductance (≈ 5 mm trace), f_max ≈ 159 MHz. "
            "Placing the cap at 2 mm (L ≈ 2 nH) gives f_max ≈ 355 MHz. "
            "Power supply noise is the primary source of common-mode EMI."
        ),
        "consequence": (
            "Supply voltage fluctuations under load cause current spikes "
            "that radiate from supply traces. IC ground bounce degrades "
            "signal quality. Power rail noise couples into RF sections."
        ),
        "steps": [
            "Place 100 nF decap within 2–3 mm of each power pin",
            "Place bulk cap (10 µF) within 10–15 mm for low-frequency stability",
            "Use multiple capacitor values for broadband filtering (100 nF + 1 µF + 10 µF)",
            "Route capacitor directly between VCC pin and GND via",
            "Minimize trace length from IC pin through capacitor to GND"
        ],
        "priority": "HIGH",
        "improvement": "Proper decoupling reduces power supply EMI by 20–40 dB"
    },

    "Transmission Line Behavior": {
        "why": (
            "When a trace becomes electrically long (> λ/10), wave propagation "
            "effects dominate over lumped circuit behavior. The trace acts as "
            "a transmission line with characteristic impedance determined by "
            "trace geometry and substrate properties."
        ),
        "physics": (
            "Transmission line characteristic impedance: "
            "Z₀ = √(L_per_meter / C_per_meter). For microstrip: "
            "Z₀ ≈ (87/√(εr+1.41)) × ln(5.98h / (0.8w + t)) Ω. "
            "Reflections occur when load impedance ≠ Z₀: "
            "Γ = (ZL - Z₀) / (ZL + Z₀). Reflected energy causes ringing, "
            "overshoot, and increased EMI."
        ),
        "consequence": (
            "Signal reflections causing overshoot and undershoot. "
            "Ringing on signal edges. Increased EMI from standing waves. "
            "Potential false triggering of logic. Reduced setup/hold margin."
        ),
        "steps": [
            "Calculate required trace width for 50 Ω impedance",
            "Add source series termination resistor (33–68 Ω)",
            "Add far-end parallel termination to Z₀ (if needed)",
            "Maintain consistent trace width and reference plane",
            "Use PCB stackup calculator for exact impedance control"
        ],
        "priority": "MEDIUM",
        "improvement": "Proper termination can reduce reflections by 15–30 dB"
    },

    "Impedance Discontinuity": {
        "why": (
            "Abrupt changes in trace width cause sudden changes in "
            "characteristic impedance. At each width transition, a portion "
            "of the signal energy is reflected back toward the source, "
            "creating signal integrity and EMI issues."
        ),
        "physics": (
            "Wider traces have lower impedance (more capacitance per unit length). "
            "At a width transition, the reflection coefficient: "
            "Γ = (Z2 - Z1)/(Z2 + Z1). For 50→100 Ω transition, Γ = 0.33 "
            "(33% voltage reflection). Each reflection creates a secondary "
            "source of radiation."
        ),
        "consequence": (
            "Ringing and overshoot at transitions. Increased timing jitter. "
            "Radiated emissions from reflected energy. "
            "Potential data errors in high-speed designs."
        ),
        "steps": [
            "Design traces for consistent Z₀ throughout signal path",
            "Use gradual tapered transitions when width must change",
            "Calculate impedance for each section using stackup",
            "Match trace impedance to driver and receiver impedances",
            "Avoid mixing different copper weights on the same signal path"
        ],
        "priority": "MEDIUM",
        "improvement": "Consistent impedance can reduce reflections by 10–20 dB"
    },

    "Trace Crossing Potential Split Plane": {
        "why": (
            "When a trace crosses a boundary between different power domains "
            "or different sections of the ground plane, the return current "
            "must detour around the boundary instead of flowing directly "
            "below the trace."
        ),
        "physics": (
            "Return current wants to follow the path of least inductance, "
            "which is the mirror image directly below the signal trace. "
            "A plane gap forces the return current to flow around the gap, "
            "forming a large loop proportional to gap size × trace length."
        ),
        "consequence": (
            "Increased loop inductance → more EMI. Ground noise coupling "
            "between power domains. Potential for latch-up in mixed-signal "
            "designs. Increased susceptibility to ESD."
        ),
        "steps": [
            "Re-route traces to avoid crossing plane boundaries",
            "If crossing is unavoidable, add bridge capacitors across the boundary",
            "Add GND stitching vias at each side of the crossing",
            "Separate analog and digital routing into distinct board regions",
            "Use a single unified ground plane and separate power planes"
        ],
        "priority": "MEDIUM",
        "improvement": "Proper routing can reduce EMI by 10–20 dB at affected traces"
    },

    "No Ground Plane Detected": {
        "why": (
            "No copper fill zone assigned to GND was found on any layer. "
            "The ground plane is one of the most critical EMC design elements — "
            "it provides low-impedance return paths and acts as an EMI shield."
        ),
        "physics": (
            "A solid copper plane presents very low impedance at high frequencies "
            "due to skin effect distributing current across a wide area. "
            "The plane creates a reference voltage that minimizes common-mode noise. "
            "Without a plane, each trace has only its own trace as return path."
        ),
        "consequence": (
            "Extremely high EMI. Poor signal integrity. All traces have long "
            "return paths. Multiple ground bounce issues. Almost certain "
            "regulatory compliance failure."
        ),
        "steps": [
            "Add a solid copper pour on at least one inner or outer layer assigned to GND",
            "Use 4-layer stackup: signal / GND / power / signal for best performance",
            "Set pour clearance to 0.2 mm and priority correctly",
            "Stitch all GND connections to the plane with vias",
            "Ensure plane covers the full PCB footprint"
        ],
        "priority": "CRITICAL",
        "improvement": "Adding a ground plane is the single highest-impact EMI improvement"
    },

    "Unconnected Trace (Antenna Structure)": {
        "why": (
            "A floating (unconnected) copper trace has no defined potential. "
            "It will charge up to whatever voltage is induced by nearby fields. "
            "This makes it an excellent receiver and re-radiator of "
            "electromagnetic energy."
        ),
        "physics": (
            "Floating conductors respond to incident electromagnetic fields "
            "by developing induced voltages: V_induced = E × L (for electric field) "
            "or V_induced = -dΦ/dt (for magnetic field). These induced voltages "
            "then re-radiate, acting as secondary antennas."
        ),
        "consequence": (
            "Unpredictable radiation. Susceptibility to ESD. Potential "
            "latch-up or logic errors if the floating conductor is near "
            "active circuitry. Undefined behavior with temperature and humidity."
        ),
        "steps": [
            "Remove all floating (unconnected) copper traces",
            "If copper is needed for thermal reasons, connect to GND",
            "Run DRC (Design Rule Check) and fix all unconnected net errors",
            "Use copper pour rules to avoid isolated copper islands",
            "Set minimum copper island size to force removal of small floaters"
        ],
        "priority": "HIGH",
        "improvement": "Eliminating floating conductors removes unpredictable radiation sources"
    },
}


class AIAnalysisEngine:
    """
    Generates rich, physics-based AI explanations for each EMI issue.
    Works offline — no external API required.
    """

    def explain(self, issue: EMIIssue) -> AIExplanation:
        """Return an AI explanation for the given EMI issue."""
        template = _TEMPLATES.get(issue.title, self._generic_template(issue))

        return AIExplanation(
            issue_title=issue.title,
            why_it_happened=self._format_why(template, issue),
            physics_background=template["physics"],
            emi_consequence=template["consequence"],
            fix_steps=template["steps"],
            priority=template["priority"],
            estimated_improvement=template["improvement"]
        )

    def generate_summary(self, issues: list[EMIIssue],
                          emi_score: float, rf_score: float) -> str:
        """Generate a board-level AI summary."""
        n = len(issues)
        n_crit = sum(1 for i in issues if i.severity == Severity.CRITICAL)
        n_high = sum(1 for i in issues if i.severity == Severity.HIGH)

        if emi_score > 70:
            overall = "CRITICAL — Immediate redesign required"
            color_tag = "🔴"
        elif emi_score > 40:
            overall = "HIGH RISK — Significant EMI improvements needed"
            color_tag = "🟠"
        elif emi_score > 20:
            overall = "MODERATE — Several EMI improvements recommended"
            color_tag = "🟡"
        else:
            overall = "GOOD — Minor improvements possible"
            color_tag = "🟢"

        top_issues = sorted(issues,
                            key=lambda i: i.severity.score_weight,
                            reverse=True)[:3]
        top_text = "\n".join(
            f"  • {i.title} ({i.severity.name}): {i.detail_value or i.description[:60]}..."
            for i in top_issues
        )

        return (
            f"{color_tag} Board EMI Assessment: {overall}\n\n"
            f"EMI Score: {emi_score:.0f}/100  |  RF Score: {rf_score:.0f}/100\n"
            f"Issues: {n} total  |  {n_crit} critical  |  {n_high} high severity\n\n"
            f"Top Concerns:\n{top_text}\n\n"
            f"Key Recommendations:\n"
            f"  1. Ensure a solid ground plane exists on every design\n"
            f"  2. Keep signal trace lengths below λ/20 at your target frequency\n"
            f"  3. Apply the 3W rule for all parallel traces\n"
            f"  4. Place decoupling capacitors within 2 mm of IC power pins\n"
            f"  5. Add GND stitching vias adjacent to every high-speed trace"
        )

    def _format_why(self, template: dict, issue: EMIIssue) -> str:
        base = template["why"]
        extras = []
        if issue.detail_value:
            extras.append(f"Detected value: {issue.detail_value}")
        if issue.affected_net:
            extras.append(f"Affected net: {issue.affected_net}")
        if issue.affected_ref:
            extras.append(f"Affected component: {issue.affected_ref}")
        if extras:
            return base + "\n\n" + " | ".join(extras)
        return base

    def _generic_template(self, issue: EMIIssue) -> dict:
        return {
            "why": issue.description,
            "physics": (
                "This issue involves electromagnetic coupling between PCB "
                "structures. The underlying physics relates to Maxwell's equations "
                "governing how electric and magnetic fields propagate and radiate "
                "from current-carrying conductors."
            ),
            "consequence": (
                "This issue may cause EMC compliance failures, signal integrity "
                "degradation, or interference with nearby systems."
            ),
            "steps": [issue.recommendation],
            "priority": issue.severity.name,
            "improvement": "Resolution will improve overall EMI performance"
        }
