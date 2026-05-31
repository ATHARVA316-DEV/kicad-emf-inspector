"""
Unit Tests for EMF Inspector Core Modules
Run with: python -m pytest tests/ -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import math

from emf_inspector.core.pcb_parser import (
    KiCadPCBParser, PCBBoard, create_demo_board,
    Point, Trace, Via, Zone
)
from emf_inspector.core.field_estimator import (
    EMFieldEstimator, FieldEstimationConfig
)
from emf_inspector.core.emi_detector import (
    EMIDetector, Severity
)
from emf_inspector.core.ai_engine import AIAnalysisEngine
from emf_inspector.core.report_generator import ReportGenerator


# ─────────────────────────────────────────────────────────────
# PCB Parser tests
# ─────────────────────────────────────────────────────────────

class TestPCBParser:

    def test_demo_board_loads(self):
        board = create_demo_board()
        assert board.width > 0
        assert board.height > 0
        assert len(board.traces) > 0
        assert len(board.vias) > 0
        assert len(board.nets) > 0

    def test_demo_board_layers(self):
        board = create_demo_board()
        assert "F.Cu" in board.layers
        assert "B.Cu" in board.layers

    def test_demo_board_ground_nets(self):
        board = create_demo_board()
        gnd = board.ground_nets
        assert len(gnd) > 0
        # GND net should be net 1
        assert 1 in gnd

    def test_demo_board_zones(self):
        board = create_demo_board()
        gnd_zones = [z for z in board.zones if z.net in board.ground_nets]
        assert len(gnd_zones) > 0

    def test_point_distance(self):
        p1 = Point(0, 0)
        p2 = Point(3, 4)
        assert abs(p1.distance_to(p2) - 5.0) < 1e-9

    def test_trace_length(self):
        t = Trace(Point(0, 0), Point(10, 0), width=0.2, layer="F.Cu", net=1)
        assert abs(t.length - 10.0) < 1e-9

    def test_trace_center(self):
        t = Trace(Point(0, 0), Point(10, 10), width=0.2, layer="F.Cu", net=1)
        assert abs(t.center.x - 5.0) < 1e-9
        assert abs(t.center.y - 5.0) < 1e-9

    def test_parse_simple_sexp(self):
        """Test parsing a minimal KiCad file structure."""
        minimal = """(kicad_pcb (version 20221018)
          (general)
          (layers
            (0 "F.Cu" signal)
            (31 "B.Cu" signal)
          )
          (net 0 "")
          (net 1 "GND")
          (net 2 "VCC")
          (segment (start 10 10) (end 50 10) (width 0.25)
                   (layer "F.Cu") (net 1))
          (via (at 30 10) (size 0.8) (drill 0.4)
               (layers "F.Cu" "B.Cu") (net 1))
        )"""
        parser = KiCadPCBParser()
        board = parser.parse_text(minimal)
        assert len(board.traces) == 1
        assert len(board.vias) == 1
        assert board.nets[1] == "GND"
        assert board.nets[2] == "VCC"
        assert board.traces[0].width == 0.25

    def test_board_copper_layers(self):
        board = create_demo_board()
        copper = board.copper_layers
        assert "F.Cu" in copper
        assert "B.Cu" in copper


# ─────────────────────────────────────────────────────────────
# Field Estimator tests
# ─────────────────────────────────────────────────────────────

class TestFieldEstimator:

    def setup_method(self):
        self.board = create_demo_board()
        self.estimator = EMFieldEstimator()

    def test_field_map_shape(self):
        cfg = FieldEstimationConfig(grid_resolution=20)
        fm = self.estimator.compute(self.board, cfg)
        assert fm.E_field.shape == (20, 20)
        assert fm.B_field.shape == (20, 20)
        assert fm.heatmap.shape == (20, 20)

    def test_heatmap_normalized(self):
        cfg = FieldEstimationConfig(grid_resolution=20)
        fm = self.estimator.compute(self.board, cfg)
        assert fm.heatmap.min() >= 0.0
        assert fm.heatmap.max() <= 1.0

    def test_field_nonzero(self):
        cfg = FieldEstimationConfig(grid_resolution=20)
        fm = self.estimator.compute(self.board, cfg)
        assert np.any(fm.E_field > 0)
        assert np.any(fm.B_field > 0)

    def test_frequency_effect(self):
        """Higher frequency should increase heatmap values."""
        cfg_low  = FieldEstimationConfig(frequency_hz=1e6,  grid_resolution=20)
        cfg_high = FieldEstimationConfig(frequency_hz=5.8e9, grid_resolution=20)
        fm_low  = self.estimator.compute(self.board, cfg_low)
        fm_high = self.estimator.compute(self.board, cfg_high)
        assert fm_high.heatmap.mean() >= fm_low.heatmap.mean()

    def test_grid_coverage(self):
        cfg = FieldEstimationConfig(grid_resolution=20)
        fm = self.estimator.compute(self.board, cfg)
        assert fm.x_grid[0]  >= self.board.origin.x - 1
        assert fm.x_grid[-1] <= self.board.origin.x + self.board.width + 1
        assert len(fm.x_grid) == 20


# ─────────────────────────────────────────────────────────────
# EMI Detector tests
# ─────────────────────────────────────────────────────────────

class TestEMIDetector:

    def setup_method(self):
        self.board = create_demo_board()
        self.detector = EMIDetector()

    def test_analysis_returns_report(self):
        report = self.detector.analyze(self.board, 2.4e9)
        assert report is not None
        assert isinstance(report.issues, list)

    def test_scores_in_range(self):
        report = self.detector.analyze(self.board, 2.4e9)
        assert 0 <= report.emi_score <= 100
        assert 0 <= report.rf_score <= 100

    def test_demo_board_has_issues(self):
        """Demo board is designed to have multiple issues."""
        report = self.detector.analyze(self.board, 2.4e9)
        assert len(report.issues) > 0

    def test_demo_board_has_critical_issues(self):
        """Demo board should trigger at least one critical issue."""
        report = self.detector.analyze(self.board, 2.4e9)
        crits = [i for i in report.issues if i.severity == Severity.CRITICAL]
        assert len(crits) > 0

    def test_long_rf_trace_detection(self):
        """A 37mm trace at 2.4 GHz should be flagged (λ/4 ≈ 31mm)."""
        board = PCBBoard(file_path="test")
        board.width = 100; board.height = 80
        board.layers = ["F.Cu"]; board.nets = {0: "", 1: "RF"}
        board.traces = [
            Trace(Point(0, 0), Point(37, 0), width=0.2,
                  layer="F.Cu", net=1, net_name="RF")
        ]
        report = self.detector.analyze(board, 2.4e9)
        titles = [i.title for i in report.issues]
        assert any("RF Trace" in t or "Antenna" in t for t in titles)

    def test_no_issues_clean_board(self):
        """A minimal board with only short traces should have low score."""
        board = PCBBoard(file_path="test")
        board.width = 20; board.height = 20
        board.origin = Point(0, 0)
        board.layers = ["F.Cu"]; board.nets = {0: "", 1: "GND", 2: "SIG"}
        board.traces = [
            Trace(Point(0, 0), Point(2, 0), width=0.2,
                  layer="F.Cu", net=2, net_name="SIG")
        ]
        board.zones = [
            Zone("B.Cu", 1, "GND",
                 [Point(0,0), Point(20,0), Point(20,20), Point(0,20)])
        ]
        report = self.detector.analyze(board, 100e6)
        assert report.emi_score < 50  # should be low risk

    def test_severity_ordering(self):
        report = self.detector.analyze(self.board, 2.4e9)
        for issue in report.issues:
            assert isinstance(issue.severity, Severity)

    def test_ground_plane_check(self):
        """Board without ground plane should trigger critical issue."""
        board = PCBBoard(file_path="test")
        board.width = 50; board.height = 40
        board.origin = Point(0, 0)
        board.layers = ["F.Cu"]
        board.nets = {0: "", 1: "VCC"}
        board.traces = [
            Trace(Point(0, 0), Point(10, 0), width=0.2,
                  layer="F.Cu", net=1, net_name="VCC")
        ]
        report = self.detector.analyze(board, 1e6)
        titles = [i.title for i in report.issues]
        assert "No Ground Plane Detected" in titles

    def test_by_severity_grouping(self):
        report = self.detector.analyze(self.board, 2.4e9)
        grouped = report.by_severity
        for sev_name, issues in grouped.items():
            for issue in issues:
                assert issue.severity.name == sev_name


# ─────────────────────────────────────────────────────────────
# AI Engine tests
# ─────────────────────────────────────────────────────────────

class TestAIEngine:

    def setup_method(self):
        self.board = create_demo_board()
        self.detector = EMIDetector()
        self.ai = AIAnalysisEngine()

    def test_explain_returns_explanation(self):
        report = self.detector.analyze(self.board, 2.4e9)
        for issue in report.issues[:5]:
            exp = self.ai.explain(issue)
            assert exp.why_it_happened
            assert exp.physics_background
            assert len(exp.fix_steps) > 0

    def test_summary_generation(self):
        report = self.detector.analyze(self.board, 2.4e9)
        summary = self.ai.generate_summary(
            report.issues, report.emi_score, report.rf_score)
        assert "EMI" in summary
        assert len(summary) > 50

    def test_all_templates_covered(self):
        """Check that known issue titles have templates."""
        from emf_inspector.core.ai_engine import _TEMPLATES
        known_titles = [
            "Long RF Trace", "Large Current Loop",
            "Quarter-Wave Antenna Effect", "No Ground Plane Detected",
        ]
        for title in known_titles:
            assert title in _TEMPLATES, f"Missing template for: {title}"


# ─────────────────────────────────────────────────────────────
# Report Generator tests
# ─────────────────────────────────────────────────────────────

class TestReportGenerator:

    def setup_method(self):
        self.board = create_demo_board()
        detector = EMIDetector()
        self.report = detector.analyze(self.board, 2.4e9)
        self.rg = ReportGenerator()
        self.tmp = Path(__file__).parent / "tmp_test_output"
        self.tmp.mkdir(exist_ok=True)

    def test_json_export(self):
        path = str(self.tmp / "test_report.json")
        out = self.rg.export_json(self.board, self.report, 2.4e9, path)
        import json
        data = json.loads(Path(out).read_text())
        assert data["scores"]["emi_score"] >= 0
        assert "issues" in data
        assert len(data["issues"]) == len(self.report.issues)

    def test_html_export(self):
        path = str(self.tmp / "test_report.html")
        out = self.rg.export_html(self.board, self.report, 2.4e9, path)
        html = Path(out).read_text(encoding="utf-8")
        assert "EMF Inspector" in html
        assert "EMI" in html
        assert len(html) > 1000

    def test_json_structure(self):
        path = str(self.tmp / "test_structure.json")
        out = self.rg.export_json(self.board, self.report, 2.4e9, path)
        import json
        data = json.loads(Path(out).read_text())
        assert "metadata" in data
        assert "board" in data
        assert "scores" in data
        assert data["board"]["width_mm"] == round(self.board.width, 2)

    def teardown_method(self):
        import shutil
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────────────
# Physics constant sanity checks
# ─────────────────────────────────────────────────────────────

class TestPhysicsConstants:

    def test_biot_savart_at_1m(self):
        """B = μ₀I/(2πr) at r=1m, I=1A should be 2×10⁻⁷ T."""
        mu0 = 4 * math.pi * 1e-7
        B = mu0 * 1.0 / (2 * math.pi * 1.0)
        assert abs(B - 2e-7) < 1e-9

    def test_wavelength_2_4ghz(self):
        """λ at 2.4 GHz ≈ 125 mm."""
        c = 3e8
        f = 2.4e9
        lam_mm = c / f * 1000
        assert abs(lam_mm - 125) < 1

    def test_quarter_wave_2_4ghz(self):
        """λ/4 at 2.4 GHz ≈ 31.25 mm."""
        c = 3e8; f = 2.4e9
        qw = c / f * 1000 / 4
        assert abs(qw - 31.25) < 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
