"""
Report Generator Module
Exports EMI analysis results to PDF, HTML, and JSON formats.
"""

from __future__ import annotations
import json
import datetime
from pathlib import Path
from typing import Optional

from .emi_detector import EMIReport, EMIIssue, Severity
from .pcb_parser import PCBBoard
from .ai_engine import AIAnalysisEngine


class ReportGenerator:
    """Generates PDF, HTML, and JSON reports from EMI analysis results."""

    def __init__(self):
        self.ai = AIAnalysisEngine()

    # ─────────────────────────────────────────────────────────
    # JSON
    # ─────────────────────────────────────────────────────────

    def export_json(self, board: PCBBoard, report: EMIReport,
                    freq_hz: float, output_path: str) -> str:
        data = {
            "metadata": {
                "tool": "EMF Inspector",
                "version": "1.0.0",
                "timestamp": datetime.datetime.now().isoformat(),
                "source_file": board.file_path,
                "frequency_hz": freq_hz,
            },
            "board": {
                "title": board.title,
                "width_mm": round(board.width, 2),
                "height_mm": round(board.height, 2),
                "layer_count": len(board.layers),
                "trace_count": len(board.traces),
                "via_count": len(board.vias),
                "component_count": len(board.components),
                "net_count": len(board.nets),
            },
            "scores": {
                "emi_score": round(report.emi_score, 1),
                "rf_score": round(report.rf_score, 1),
                "overall_risk": self._risk_label(report.emi_score),
            },
            "issues": [
                {
                    "category": i.category,
                    "title": i.title,
                    "severity": i.severity.name,
                    "description": i.description,
                    "recommendation": i.recommendation,
                    "affected_net": i.affected_net,
                    "affected_ref": i.affected_ref,
                    "detail": i.detail_value,
                    "location": (
                        {"x": round(i.location.x, 2), "y": round(i.location.y, 2)}
                        if i.location else None
                    ),
                }
                for i in report.issues
            ],
        }
        path = Path(output_path)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return str(path)

    # ─────────────────────────────────────────────────────────
    # HTML
    # ─────────────────────────────────────────────────────────

    def export_html(self, board: PCBBoard, report: EMIReport,
                    freq_hz: float, output_path: str,
                    heatmap_image: Optional[str] = None) -> str:
        summary = self.ai.generate_summary(
            report.issues, report.emi_score, report.rf_score)

        sev_colors = {
            "CRITICAL": "#ef4444",
            "HIGH":     "#f97316",
            "MEDIUM":   "#eab308",
            "LOW":      "#22c55e",
            "INFO":     "#3b82f6",
        }

        issues_html = ""
        for issue in sorted(report.issues,
                             key=lambda x: x.severity.score_weight,
                             reverse=True):
            col = sev_colors.get(issue.severity.name, "#6b7280")
            loc_text = ""
            if issue.location:
                loc_text = (f"<span class='loc'>📍 "
                            f"({issue.location.x:.1f}, {issue.location.y:.1f}) mm</span>")
            ai_exp = self.ai.explain(issue)
            steps_html = "".join(
                f"<li>{s}</li>" for s in ai_exp.fix_steps)

            issues_html += f"""
            <div class="issue-card" style="border-left: 4px solid {col};">
              <div class="issue-header">
                <span class="badge" style="background:{col}">{issue.severity.name}</span>
                <span class="issue-title">{issue.title}</span>
                <span class="issue-cat">[{issue.category.upper()}]</span>
                {loc_text}
              </div>
              <p class="issue-desc">{issue.description}</p>
              <details>
                <summary>🧠 AI Explanation &amp; Fix</summary>
                <div class="ai-section">
                  <h4>⚡ Physics Background</h4>
                  <p>{ai_exp.physics_background}</p>
                  <h4>⚠️ EMI Consequence</h4>
                  <p>{ai_exp.emi_consequence}</p>
                  <h4>🔧 Recommended Fix Steps</h4>
                  <ol>{steps_html}</ol>
                  <p class="improvement">
                    <strong>Expected Improvement:</strong> {ai_exp.estimated_improvement}
                  </p>
                </div>
              </details>
            </div>"""

        img_html = ""
        if heatmap_image:
            img_html = f'<img src="{heatmap_image}" alt="EMI Heatmap" class="heatmap-img"/>'

        gauge_color = (
            "#ef4444" if report.emi_score > 70 else
            "#f97316" if report.emi_score > 40 else
            "#eab308" if report.emi_score > 20 else "#22c55e"
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EMF Inspector Report — {board.title or board.file_path}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: #0f172a; color: #e2e8f0;
      line-height: 1.6; padding: 2rem;
    }}
    h1 {{ color: #38bdf8; font-size: 2rem; margin-bottom: 0.5rem; }}
    h2 {{ color: #7dd3fc; font-size: 1.3rem; margin: 1.5rem 0 1rem; }}
    h4 {{ color: #93c5fd; margin: 0.8rem 0 0.3rem; }}
    .header {{ border-bottom: 2px solid #1e40af; padding-bottom: 1rem; margin-bottom: 2rem; }}
    .subtitle {{ color: #94a3b8; font-size: 0.9rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
             gap: 1rem; margin-bottom: 2rem; }}
    .stat-card {{
      background: #1e293b; border-radius: 12px; padding: 1.2rem;
      border: 1px solid #334155;
    }}
    .stat-val {{ font-size: 2rem; font-weight: 700; color: #38bdf8; }}
    .stat-label {{ color: #94a3b8; font-size: 0.85rem; margin-top: 0.3rem; }}
    .score-circle {{
      display: inline-block; width: 80px; height: 80px;
      border-radius: 50%; border: 6px solid {gauge_color};
      line-height: 68px; text-align: center;
      font-size: 1.5rem; font-weight: 700; color: {gauge_color};
    }}
    .summary-box {{
      background: #1e293b; border-radius: 12px; padding: 1.5rem;
      border: 1px solid #334155; margin-bottom: 2rem;
      white-space: pre-wrap; font-family: monospace; font-size: 0.9rem;
      color: #94a3b8;
    }}
    .issue-card {{
      background: #1e293b; border-radius: 8px; padding: 1.2rem;
      margin-bottom: 1rem; border: 1px solid #334155;
    }}
    .issue-header {{
      display: flex; gap: 0.8rem; align-items: center;
      flex-wrap: wrap; margin-bottom: 0.5rem;
    }}
    .badge {{
      padding: 0.2rem 0.6rem; border-radius: 4px;
      font-size: 0.75rem; font-weight: 700; color: white;
    }}
    .issue-title {{ font-weight: 600; font-size: 1rem; }}
    .issue-cat {{ color: #94a3b8; font-size: 0.8rem; }}
    .loc {{ color: #60a5fa; font-size: 0.8rem; }}
    .issue-desc {{ color: #94a3b8; font-size: 0.9rem; margin: 0.5rem 0; }}
    details {{ margin-top: 0.8rem; }}
    summary {{
      cursor: pointer; color: #7dd3fc; font-size: 0.9rem;
      padding: 0.4rem 0;
    }}
    .ai-section {{
      background: #0f172a; border-radius: 8px; padding: 1rem;
      margin-top: 0.5rem; border: 1px solid #1e3a5f;
    }}
    .ai-section p {{ color: #94a3b8; font-size: 0.88rem; margin-bottom: 0.5rem; }}
    .ai-section ol {{ padding-left: 1.5rem; color: #94a3b8; font-size: 0.88rem; }}
    .ai-section li {{ margin-bottom: 0.3rem; }}
    .improvement {{
      color: #4ade80 !important; margin-top: 0.8rem !important;
      font-size: 0.88rem !important;
    }}
    .heatmap-img {{
      max-width: 100%; border-radius: 12px;
      border: 1px solid #334155; margin-bottom: 2rem;
    }}
    footer {{ color: #475569; font-size: 0.8rem; margin-top: 3rem;
              border-top: 1px solid #1e293b; padding-top: 1rem; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>⚡ EMF Inspector Report</h1>
    <p class="subtitle">
      {board.title or board.file_path} &nbsp;|&nbsp;
      {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp;
      Frequency: {freq_hz/1e6:.0f} MHz
    </p>
  </div>

  <div class="grid">
    <div class="stat-card">
      <div class="score-circle">{report.emi_score:.0f}</div>
      <div class="stat-label">EMI Risk Score (0=best)</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">{report.rf_score:.0f}</div>
      <div class="stat-label">RF Design Score</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">{len(report.issues)}</div>
      <div class="stat-label">Total Issues Found</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" style="color:#ef4444">{report.critical_count}</div>
      <div class="stat-label">Critical Issues</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">{len(board.traces)}</div>
      <div class="stat-label">Traces Analyzed</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">{len(board.components)}</div>
      <div class="stat-label">Components</div>
    </div>
  </div>

  {img_html}

  <h2>🤖 AI Board Assessment</h2>
  <div class="summary-box">{summary}</div>

  <h2>📋 Detailed Issues ({len(report.issues)})</h2>
  {issues_html}

  <footer>
    Generated by EMF Inspector v1.0 &nbsp;|&nbsp;
    Physics-based EMI estimation engine &nbsp;|&nbsp;
    Not a substitute for full-wave simulation
  </footer>
</body>
</html>"""

        path = Path(output_path)
        path.write_text(html, encoding="utf-8")
        return str(path)

    # ─────────────────────────────────────────────────────────
    # PDF (via matplotlib)
    # ─────────────────────────────────────────────────────────

    def export_pdf(self, board: PCBBoard, report: EMIReport,
                   freq_hz: float, output_path: str,
                   heatmap_path: Optional[str] = None) -> str:
        """Export a PDF report using matplotlib as PDF backend."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
            from matplotlib.backends.backend_pdf import PdfPages
        except ImportError:
            raise RuntimeError("matplotlib required for PDF export")

        path = Path(output_path)

        with PdfPages(str(path)) as pdf:
            # ── Page 1: Summary ──────────────────────────────
            fig, ax = plt.subplots(figsize=(11, 8.5))
            fig.patch.set_facecolor("#0f172a")
            ax.set_facecolor("#0f172a")
            ax.axis("off")

            y = 0.95
            ax.text(0.5, y, "EMF Inspector — EMI Analysis Report",
                    ha="center", va="top", fontsize=20, fontweight="bold",
                    color="#38bdf8", transform=ax.transAxes)
            y -= 0.06
            ax.text(0.5, y, f"{board.title or board.file_path}  |  "
                    f"{freq_hz/1e6:.0f} MHz  |  "
                    f"{datetime.datetime.now().strftime('%Y-%m-%d')}",
                    ha="center", va="top", fontsize=11, color="#94a3b8",
                    transform=ax.transAxes)
            y -= 0.08

            # Score boxes
            score_col = ("#ef4444" if report.emi_score > 70 else
                         "#f97316" if report.emi_score > 40 else
                         "#eab308" if report.emi_score > 20 else "#22c55e")
            for label, val, col, x_pos in [
                (f"EMI Score\n{report.emi_score:.0f}/100", report.emi_score, score_col, 0.2),
                (f"RF Score\n{report.rf_score:.0f}/100",  report.rf_score,  "#7dd3fc", 0.5),
                (f"Issues\n{len(report.issues)} total",    len(report.issues)*5, "#a78bfa", 0.8),
            ]:
                fancy = mpatches.FancyBboxPatch(
                    (x_pos - 0.12, y - 0.12), 0.24, 0.14,
                    boxstyle="round,pad=0.01",
                    facecolor="#1e293b", edgecolor=col, linewidth=2,
                    transform=ax.transAxes)
                ax.add_patch(fancy)
                ax.text(x_pos, y - 0.05, label,
                        ha="center", va="center", fontsize=12,
                        fontweight="bold", color=col,
                        transform=ax.transAxes)
            y -= 0.18

            # AI Summary text
            summary = self.ai.generate_summary(
                report.issues, report.emi_score, report.rf_score)
            ax.text(0.05, y, summary, va="top", fontsize=8.5,
                    color="#94a3b8", transform=ax.transAxes,
                    fontfamily="monospace", wrap=True)

            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            # ── Page 2: Heatmap (if available) ───────────────
            if heatmap_path and Path(heatmap_path).exists():
                fig2, ax2 = plt.subplots(figsize=(11, 8.5))
                fig2.patch.set_facecolor("#0f172a")
                img = plt.imread(heatmap_path)
                ax2.imshow(img)
                ax2.axis("off")
                ax2.set_title("EMI Heatmap", color="#38bdf8",
                              fontsize=16, pad=15)
                pdf.savefig(fig2, bbox_inches="tight")
                plt.close(fig2)

            # ── Pages 3+: Issues ─────────────────────────────
            issues_sorted = sorted(report.issues,
                                   key=lambda x: x.severity.score_weight,
                                   reverse=True)
            sev_colors = {
                Severity.CRITICAL: "#ef4444",
                Severity.HIGH:     "#f97316",
                Severity.MEDIUM:   "#eab308",
                Severity.LOW:      "#22c55e",
                Severity.INFO:     "#3b82f6",
            }

            per_page = 4
            for page_start in range(0, len(issues_sorted), per_page):
                page_issues = issues_sorted[page_start:page_start + per_page]
                fig3, axes = plt.subplots(
                    len(page_issues), 1,
                    figsize=(11, 8.5))
                if len(page_issues) == 1:
                    axes = [axes]
                fig3.patch.set_facecolor("#0f172a")

                for ax3, issue in zip(axes, page_issues):
                    ax3.set_facecolor("#1e293b")
                    col = sev_colors.get(issue.severity, "#94a3b8")
                    ax3.axvline(0, color=col, linewidth=5)
                    ax3.axis("off")
                    ai_exp = self.ai.explain(issue)
                    text = (
                        f"[{issue.severity.name}] {issue.title}\n"
                        f"{issue.description[:200]}\n"
                        f"Fix: {ai_exp.fix_steps[0] if ai_exp.fix_steps else issue.recommendation}"
                    )
                    ax3.text(0.02, 0.5, text, va="center", fontsize=8,
                             color="#e2e8f0", transform=ax3.transAxes,
                             wrap=True)

                plt.tight_layout(pad=0.5)
                pdf.savefig(fig3, bbox_inches="tight")
                plt.close(fig3)

        return str(path)

    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _risk_label(score: float) -> str:
        if score > 70:
            return "CRITICAL"
        if score > 40:
            return "HIGH"
        if score > 20:
            return "MODERATE"
        return "LOW"
