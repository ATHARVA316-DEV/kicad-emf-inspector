"""
EMI Detection Engine
Performs rule-based EMI analysis on parsed PCB data.
Each detector returns a list of EMIIssue objects with severity, location,
explanation, and recommended fix.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from .pcb_parser import PCBBoard, Trace, Via, Point, Zone

from .constants import C_LIGHT, pcb_wavelength_mm


class Severity(Enum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def color(self) -> str:
        return {
            Severity.INFO:     "#60A5FA",   # blue
            Severity.LOW:      "#86EFAC",   # green
            Severity.MEDIUM:   "#FDE68A",   # yellow
            Severity.HIGH:     "#FB923C",   # orange
            Severity.CRITICAL: "#F87171",   # red
        }[self]

    @property
    def score_weight(self) -> float:
        return {
            Severity.INFO:     0,
            Severity.LOW:      5,
            Severity.MEDIUM:   15,
            Severity.HIGH:     30,
            Severity.CRITICAL: 50,
        }[self]


@dataclass
class EMIIssue:
    category: str
    title: str
    description: str
    severity: Severity
    location: Optional[Point]
    recommendation: str
    affected_net: str = ""
    affected_ref: str = ""
    detail_value: str = ""          # e.g. "37.2 mm trace"

    @property
    def severity_label(self) -> str:
        return self.severity.name


@dataclass
class EMIReport:
    issues: list[EMIIssue] = field(default_factory=list)
    emi_score: float = 0.0     # 0–100, higher = worse
    rf_score: float = 0.0

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.HIGH)

    @property
    def by_severity(self) -> dict[str, list[EMIIssue]]:
        result: dict[str, list[EMIIssue]] = {}
        for issue in self.issues:
            result.setdefault(issue.severity.name, []).append(issue)
        return result


class EMIDetector:
    """
    Master EMI analysis engine.

    Call .analyze(board, frequency_hz) to get a full EMIReport.
    """

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    def analyze(self, board: PCBBoard,
                frequency_hz: float = 2.4e9) -> EMIReport:
        report = EMIReport()
        issues = report.issues

        self._check_long_rf_traces(board, frequency_hz, issues)
        self._check_large_current_loops(board, issues)
        self._check_missing_return_paths(board, issues)
        self._check_gnd_plane_discontinuity(board, issues)
        self._check_crossing_split_planes(board, issues)
        self._check_excessive_via_transitions(board, frequency_hz, issues)
        self._check_crosstalk(board, issues)
        self._check_antenna_structures(board, frequency_hz, issues)
        self._check_unshielded_rf(board, frequency_hz, issues)
        self._check_decoupling_placement(board, issues)
        self._check_transmission_line(board, frequency_hz, issues)
        self._check_impedance_mismatch(board, frequency_hz, issues)

        # Deduplicate: if the same trace/net is flagged by multiple
        # rules, keep only the highest-severity instance per (title_group, net).
        report.issues = self._deduplicate(issues)
        issues = report.issues

        report.emi_score = self._compute_score(issues, "emi")
        report.rf_score  = self._compute_score(issues, "rf")
        return report

    # ─────────────────────────────────────────────────────────
    # Individual detectors
    # ─────────────────────────────────────────────────────────

    def _check_long_rf_traces(self, board: PCBBoard,
                               freq_hz: float,
                               issues: list[EMIIssue]):
        """Traces longer than λ/20 at operating frequency are potential antennas."""
        wavelength_mm = pcb_wavelength_mm(freq_hz)
        threshold_lambda_20 = wavelength_mm / 20
        threshold_lambda_4  = wavelength_mm / 4

        for trace in board.traces:
            if "Edge.Cuts" in trace.layer:
                continue
            L = trace.length
            if L > threshold_lambda_4:
                sev = Severity.CRITICAL
                desc = (f"Trace length {L:.1f} mm exceeds λ/4 = "
                        f"{threshold_lambda_4:.1f} mm at {freq_hz/1e6:.0f} MHz. "
                        f"This trace will radiate as an antenna.")
                rec = (f"Shorten trace below {threshold_lambda_20:.1f} mm "
                       f"(λ/20), or add RF shielding / ground guard traces.")
            elif L > threshold_lambda_20:
                sev = Severity.HIGH
                desc = (f"Trace length {L:.1f} mm exceeds λ/20 = "
                        f"{threshold_lambda_20:.1f} mm at {freq_hz/1e6:.0f} MHz. "
                        f"Significant radiation possible.")
                rec = (f"Keep traces below λ/20 ({threshold_lambda_20:.1f} mm). "
                       f"Add ground return alongside signal trace.")
            else:
                continue

            issues.append(EMIIssue(
                category="rf",
                title="Long RF Trace",
                description=desc,
                severity=sev,
                location=trace.center,
                recommendation=rec,
                affected_net=trace.net_name,
                detail_value=f"{L:.1f} mm"
            ))

    def _check_large_current_loops(self, board: PCBBoard,
                                    issues: list[EMIIssue]):
        """Detect signal-GND pairs that form large loop areas."""
        gnd_nets = set(board.ground_nets)
        signal_traces = [t for t in board.traces
                         if t.net not in gnd_nets and t.net != 0]
        gnd_traces = [t for t in board.traces if t.net in gnd_nets]

        for sig in signal_traces:
            # Find nearest GND trace
            nearest_gnd = None
            nearest_dist = float("inf")
            for gnd in gnd_traces:
                d = sig.center.distance_to(gnd.center)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_gnd = gnd

            if nearest_gnd is None or nearest_dist < 5:
                continue

            # Estimate loop area (signal length × separation)
            loop_area = sig.length * nearest_dist  # mm²
            if loop_area > 500:
                sev = Severity.CRITICAL if loop_area > 2000 else Severity.HIGH
                issues.append(EMIIssue(
                    category="emi",
                    title="Large Current Loop",
                    description=(
                        f"Net '{sig.net_name}' forms a large current loop "
                        f"(~{loop_area:.0f} mm²) with its nearest GND return. "
                        f"Large loops are efficient EMI radiators proportional "
                        f"to A·f²."),
                    severity=sev,
                    location=sig.center,
                    recommendation=(
                        "Route GND return trace parallel and close to signal. "
                        "Use a continuous ground plane to minimize loop area."),
                    affected_net=sig.net_name,
                    detail_value=f"{loop_area:.0f} mm²"
                ))

    def _check_missing_return_paths(self, board: PCBBoard,
                                     issues: list[EMIIssue]):
        """Check if high-speed nets have nearby ground returns."""
        hs_keywords = {"MOSI", "MISO", "SCK", "CLK", "TX", "RX",
                       "DATA", "SDA", "SCL", "DP", "DM", "DIFF"}
        gnd_nets = set(board.ground_nets)

        for trace in board.traces:
            name_up = trace.net_name.upper()
            if not any(k in name_up for k in hs_keywords):
                continue

            # Look for nearby GND pad or via
            has_nearby_gnd = any(
                v.position.distance_to(trace.center) < 10
                for v in board.vias if v.net in gnd_nets
            )
            if not has_nearby_gnd:
                has_nearby_gnd = any(
                    p.position.distance_to(trace.center) < 8
                    for p in board.pads if p.net in gnd_nets
                )

            if not has_nearby_gnd:
                issues.append(EMIIssue(
                    category="emi",
                    title="Missing Return Path",
                    description=(
                        f"High-speed net '{trace.net_name}' has no ground "
                        f"via or pad within 10 mm. Return currents must travel "
                        f"a long path, increasing loop area and EMI."),
                    severity=Severity.HIGH,
                    location=trace.center,
                    recommendation=(
                        "Place GND stitching vias every 5–10 mm adjacent to "
                        "high-speed traces. Ensure solid ground plane below "
                        "the signal layer."),
                    affected_net=trace.net_name
                ))

    def _check_gnd_plane_discontinuity(self, board: PCBBoard,
                                        issues: list[EMIIssue]):
        """Detect split/missing ground planes or gaps."""
        gnd_zones = [z for z in board.zones
                     if z.net in board.ground_nets]

        if not gnd_zones:
            issues.append(EMIIssue(
                category="emi",
                title="No Ground Plane Detected",
                description=(
                    "No copper fill zones assigned to GND were found. "
                    "Without a ground plane, return currents are poorly "
                    "defined causing high EMI."),
                severity=Severity.CRITICAL,
                location=Point(board.origin.x + board.width / 2,
                               board.origin.y + board.height / 2),
                recommendation=(
                    "Add a solid ground plane on an inner copper layer "
                    "or back copper layer. Fill all unused areas with GND."),
            ))
            return

        # Check for multiple GND zones on same layer (split plane)
        layer_zones: dict[str, list[Zone]] = {}
        for z in gnd_zones:
            layer_zones.setdefault(z.layer, []).append(z)

        for layer, zones in layer_zones.items():
            if len(zones) > 1:
                # Check if any high-speed trace crosses the gap
                for trace in board.traces:
                    if trace.layer == layer:
                        issues.append(EMIIssue(
                            category="emi",
                            title="Ground Plane Discontinuity",
                            description=(
                                f"Split GND plane detected on layer {layer} "
                                f"({len(zones)} separate GND zones). "
                                f"Traces crossing the gap see a broken return "
                                f"path — a major EMI source."),
                            severity=Severity.HIGH,
                            location=trace.center,
                            recommendation=(
                                "Merge GND zones or bridge the gap with a GND "
                                "trace. Avoid routing signal traces across "
                                "plane splits. Use stitching vias."),
                            affected_net=trace.net_name
                        ))


    def _check_crossing_split_planes(self, board: PCBBoard,
                                      issues: list[EMIIssue]):
        """Detect long traces that likely cross the board center (proxy for split)."""
        threshold_frac = 0.6   # trace spanning >60% of board width
        W = board.width

        for trace in board.traces:
            span_x = abs(trace.end.x - trace.start.x)
            if span_x > W * threshold_frac:
                issues.append(EMIIssue(
                    category="emi",
                    title="Trace Crossing Potential Split Plane",
                    description=(
                        f"Trace on net '{trace.net_name}' spans "
                        f"{span_x:.1f} mm ({span_x/W*100:.0f}% of board "
                        f"width) and likely crosses voltage domain boundaries. "
                        f"Return current must detour, increasing loop area."),
                    severity=Severity.MEDIUM,
                    location=trace.center,
                    recommendation=(
                        "Re-route to avoid crossing power domain boundaries. "
                        "Add a local GND bridge at crossing points."),
                    affected_net=trace.net_name,
                    detail_value=f"{span_x:.1f} mm span"
                ))

    def _check_excessive_via_transitions(self, board: PCBBoard,
                                          freq_hz: float,
                                          issues: list[EMIIssue]):
        """Check nets with many layer transitions (stub inductance)."""
        net_via_count: dict[int, list[Via]] = {}
        for via in board.vias:
            net_via_count.setdefault(via.net, []).append(via)

        for net_id, vias in net_via_count.items():
            if len(vias) >= 4:
                net_name = board.nets.get(net_id, f"net_{net_id}")
                # Each via stub adds inductance ≈ 1 nH
                stub_L_nH = len(vias) * 1.0
                Xl_ohm = 2 * math.pi * freq_hz * stub_L_nH * 1e-9
                issues.append(EMIIssue(
                    category="rf",
                    title="Excessive Via Transitions",
                    description=(
                        f"Net '{net_name}' uses {len(vias)} vias. "
                        f"Each via stub adds ~1 nH. Total stub inductance "
                        f"≈ {stub_L_nH:.0f} nH → X_L ≈ {Xl_ohm:.1f} Ω "
                        f"at {freq_hz/1e6:.0f} MHz. This degrades SI "
                        f"and causes resonances."),
                    severity=Severity.MEDIUM,
                    location=vias[0].position,
                    recommendation=(
                        "Minimize via count on RF/high-speed nets. "
                        "Use back-drilled vias or HDI microvias to "
                        "reduce stub length. Add anti-pad around vias."),
                    affected_net=net_name,
                    detail_value=f"{len(vias)} vias"
                ))

    def _check_crosstalk(self, board: PCBBoard,
                          issues: list[EMIIssue]):
        """Detect parallel traces running very close together."""
        traces = board.traces
        PARALLEL_DIST_MM = 0.3   # < 0.3 mm = crosstalk risk
        MIN_PARALLEL_LEN = 5     # must be parallel for >5 mm

        checked = set()
        for i, t1 in enumerate(traces):
            for j, t2 in enumerate(traces):
                if j <= i or (i, j) in checked:
                    continue
                checked.add((i, j))
                if t1.net == t2.net or t1.layer != t2.layer:
                    continue

                # Simple parallel check: similar angle
                dx1 = t1.end.x - t1.start.x
                dy1 = t1.end.y - t1.start.y
                dx2 = t2.end.x - t2.start.x
                dy2 = t2.end.y - t2.start.y

                len1 = math.hypot(dx1, dy1)
                len2 = math.hypot(dx2, dy2)
                if len1 < 2 or len2 < 2:
                    continue

                # Dot product to check parallel
                dot = abs((dx1 * dx2 + dy1 * dy2) / (len1 * len2))
                if dot < 0.98:   # not parallel enough
                    continue

                # Check distance between traces
                d = t1.center.distance_to(t2.center)
                parallel_len = min(len1, len2)

                if d < PARALLEL_DIST_MM * 10 and parallel_len > MIN_PARALLEL_LEN:
                    sep = d - (t1.width + t2.width) / 2
                    if sep < PARALLEL_DIST_MM:
                        issues.append(EMIIssue(
                            category="emi",
                            title="Crosstalk Risk",
                            description=(
                                f"Nets '{t1.net_name}' and '{t2.net_name}' "
                                f"run parallel for {parallel_len:.1f} mm with "
                                f"edge separation ~{sep:.2f} mm. "
                                f"Capacitive/inductive crosstalk may cause "
                                f"signal integrity failures."),
                            severity=Severity.HIGH if sep < 0.15 else Severity.MEDIUM,
                            location=t1.center,
                            recommendation=(
                                "Apply 3W rule: trace separation ≥ 3× trace width. "
                                "Add GND guard traces between sensitive signals. "
                                "Minimize parallel run length."),
                            affected_net=f"{t1.net_name} ↔ {t2.net_name}",
                            detail_value=f"{sep:.2f} mm sep"
                        ))

    def _check_antenna_structures(self, board: PCBBoard,
                                   freq_hz: float,
                                   issues: list[EMIIssue]):
        """Detect floating or stub traces that act as antennas."""
        wavelength_mm = pcb_wavelength_mm(freq_hz)

        for trace in board.traces:
            if trace.net == 0:   # unconnected net
                issues.append(EMIIssue(
                    category="rf",
                    title="Unconnected Trace (Antenna Structure)",
                    description=(
                        f"Trace on layer {trace.layer} has no net assigned "
                        f"(floating conductor). Floating conductors act as "
                        f"unintended antennas and reradiate RF energy."),
                    severity=Severity.HIGH,
                    location=trace.center,
                    recommendation=(
                        "Remove floating traces or connect them to GND. "
                        "Ensure all copper is either functionally connected "
                        "or removed from the design."),
                    detail_value=f"{trace.length:.1f} mm floating"
                ))
                continue

            # Quarter-wave resonance check
            qwave = wavelength_mm / 4
            if abs(trace.length - qwave) / qwave < 0.15:
                issues.append(EMIIssue(
                    category="rf",
                    title="Quarter-Wave Antenna Effect",
                    description=(
                        f"Trace length {trace.length:.1f} mm ≈ λ/4 "
                        f"({qwave:.1f} mm) at {freq_hz/1e6:.0f} MHz. "
                        f"The trace resonates as an efficient quarter-wave "
                        f"monopole — maximum radiation efficiency."),
                    severity=Severity.CRITICAL,
                    location=trace.center,
                    recommendation=(
                        "Avoid λ/4 trace lengths at your operating frequency. "
                        "Shorten trace, add series termination, or shield "
                        "with ground guard traces on both sides."),
                    affected_net=trace.net_name,
                    detail_value=f"λ/4 = {qwave:.1f} mm"
                ))

    def _check_unshielded_rf(self, board: PCBBoard,
                              freq_hz: float,
                              issues: list[EMIIssue]):
        """Check for RF nets without nearby GND shielding."""
        rf_keywords = {"RF", "ANT", "LNA", "PA", "VCO", "PLL",
                       "RFIN", "RFOUT", "ANTENNA"}
        gnd_nets = set(board.ground_nets)

        for trace in board.traces:
            name_up = trace.net_name.upper()
            if not any(k in name_up for k in rf_keywords):
                continue

            # Check for nearby GND traces (guard traces)
            nearby_gnd = [
                t for t in board.traces
                if t.net in gnd_nets and
                t.layer == trace.layer and
                trace.center.distance_to(t.center) < 3.0
            ]

            if not nearby_gnd:
                issues.append(EMIIssue(
                    category="rf",
                    title="Unshielded RF Trace",
                    description=(
                        f"RF net '{trace.net_name}' has no ground guard "
                        f"trace within 3 mm. Unshielded RF lines radiate "
                        f"and are susceptible to interference."),
                    severity=Severity.HIGH,
                    location=trace.center,
                    recommendation=(
                        "Add ground guard traces (GND) on both sides of "
                        "the RF trace. Consider microstrip or coplanar "
                        "waveguide (CPW) topology. Add via fencing."),
                    affected_net=trace.net_name
                ))

    def _check_decoupling_placement(self, board: PCBBoard,
                                     issues: list[EMIIssue]):
        """Check if decoupling capacitors are placed close to IC power pins."""
        cap_refs = {"C", "CAP"}
        decap_comps = [c for c in board.components
                       if any(c.reference.startswith(r) for r in cap_refs)]

        ic_prefixes = ("U", "IC", "DD")
        ic_comps = [c for c in board.components
                    if c.reference.startswith(ic_prefixes)]

        for ic in ic_comps:
            # Find nearest decap
            nearest_d = float("inf")
            for cap in decap_comps:
                d = ic.position.distance_to(cap.position)
                if d < nearest_d:
                    nearest_d = d

            if nearest_d > 15:   # no decap within 15 mm
                issues.append(EMIIssue(
                    category="emi",
                    title="Poor Decoupling Capacitor Placement",
                    description=(
                        f"IC '{ic.reference}' ({ic.value}) has no decoupling "
                        f"capacitor within 15 mm (nearest: {nearest_d:.1f} mm). "
                        f"Decaps must be as close as possible to VCC/GND "
                        f"pins to be effective."),
                    severity=Severity.HIGH,
                    location=ic.position,
                    recommendation=(
                        "Place 100 nF decoupling capacitor within 2–3 mm of "
                        "each IC power pin. Add bulk capacitor (10 µF) within "
                        "10 mm. Use multiple values for broadband filtering."),
                    affected_ref=ic.reference
                ))

    def _check_transmission_line(self, board: PCBBoard,
                                  freq_hz: float,
                                  issues: list[EMIIssue]):
        """Warn when traces are electrically long (transmission line behavior)."""
        wavelength_mm = pcb_wavelength_mm(freq_hz)
        threshold = wavelength_mm / 10   # λ/10 = electrical length threshold

        for trace in board.traces:
            if "Edge.Cuts" in trace.layer:
                continue
            if trace.length > threshold:
                elec_len_deg = (trace.length / wavelength_mm) * 360
                issues.append(EMIIssue(
                    category="rf",
                    title="Transmission Line Behavior",
                    description=(
                        f"Trace length {trace.length:.1f} mm > λ/10 "
                        f"({threshold:.1f} mm). Electrical length = "
                        f"{elec_len_deg:.0f}°. Trace must be treated "
                        f"as a transmission line — lumped circuit models "
                        f"no longer apply."),
                    severity=Severity.MEDIUM,
                    location=trace.center,
                    recommendation=(
                        f"Use controlled impedance routing (50 Ω typical). "
                        f"Add source termination resistor. Calculate trace "
                        f"width for target impedance using board stack-up."),
                    affected_net=trace.net_name,
                    detail_value=f"{elec_len_deg:.0f}° electrical length"
                ))

    def _check_impedance_mismatch(self, board: PCBBoard,
                                   freq_hz: float,
                                   issues: list[EMIIssue]):
        """Detect abrupt trace width changes on same net (impedance discontinuity)."""
        net_traces: dict[int, list[Trace]] = {}
        for t in board.traces:
            net_traces.setdefault(t.net, []).append(t)

        for net_id, traces in net_traces.items():
            if len(traces) < 2:
                continue
            widths = [t.width for t in traces]
            min_w, max_w = min(widths), max(widths)
            if max_w / (min_w + 1e-9) > 2.5:
                net_name = board.nets.get(net_id, f"net_{net_id}")
                issues.append(EMIIssue(
                    category="rf",
                    title="Impedance Discontinuity",
                    description=(
                        f"Net '{net_name}' has trace widths ranging from "
                        f"{min_w:.2f} mm to {max_w:.2f} mm "
                        f"(ratio {max_w/min_w:.1f}×). Abrupt width changes "
                        f"cause impedance discontinuities, reflections, and "
                        f"increased radiation at transitions."),
                    severity=Severity.MEDIUM,
                    location=traces[0].center,
                    recommendation=(
                        "Keep consistent trace width on signal nets. "
                        "Use tapered transitions if width must change. "
                        "Calculate target impedance and maintain it."),
                    affected_net=net_name,
                    detail_value=f"{min_w:.2f}–{max_w:.2f} mm"
                ))

    @staticmethod
    def _deduplicate(issues: list[EMIIssue]) -> list[EMIIssue]:
        """Remove duplicate issues for the same net keeping highest severity."""
        # Group related titles so e.g. 'Long RF Trace' and
        # 'Transmission Line Behavior' on the same net don't both appear.
        _RELATED = {
            "Long RF Trace": "trace_length",
            "Transmission Line Behavior": "trace_length",
            "Quarter-Wave Antenna Effect": "trace_length",
        }
        seen: dict[tuple[str, str], EMIIssue] = {}
        unique: list[EMIIssue] = []
        for issue in issues:
            group = _RELATED.get(issue.title, issue.title)
            key = (group, issue.affected_net or id(issue))
            if key in seen:
                if issue.severity.value > seen[key].severity.value:
                    unique.remove(seen[key])
                    seen[key] = issue
                    unique.append(issue)
            else:
                seen[key] = issue
                unique.append(issue)
        return unique

    # ─────────────────────────────────────────────────────────
    # Scoring
    # ─────────────────────────────────────────────────────────

    def _compute_score(self, issues: list[EMIIssue],
                        category: str) -> float:
        relevant = [i for i in issues if i.category == category]
        total = sum(i.severity.score_weight for i in relevant)
        return min(100.0, total)
