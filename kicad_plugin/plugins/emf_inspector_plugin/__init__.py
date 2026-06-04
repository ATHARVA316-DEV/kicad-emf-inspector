"""
EMF Inspector — KiCad Action Plugin
Integrates physics-based EMI analysis directly into KiCad's PCB editor.
"""

import os
import sys
import pcbnew

# Ensure the plugin's own directory is on the path so we can import our modules
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)


class EMFInspectorPlugin(pcbnew.ActionPlugin):
    """KiCad Action Plugin for EMF Inspector EMI analysis."""

    def defaults(self):
        self.name = "EMF Inspector"
        self.category = "EMC / Signal Integrity"
        self.description = (
            "Analyze PCB layout for electromagnetic interference (EMI) issues. "
            "Detects long RF traces, current loops, crosstalk, impedance "
            "mismatches, and 12+ physics-based EMI rules."
        )
        self.show_toolbar_button = True
        icon_path = os.path.join(PLUGIN_DIR, "resources", "icon_24x24.png")
        if os.path.exists(icon_path):
            self.icon_file_name = icon_path
        self.dark_icon_file_name = self.icon_file_name

    def Run(self):
        """Entry point when the plugin is activated from KiCad."""
        try:
            self._run_analysis()
        except Exception as e:
            import traceback
            self._show_error(
                "EMF Inspector Error",
                f"An error occurred during analysis:\n\n{e}\n\n"
                f"{traceback.format_exc()}"
            )

    def _run_analysis(self):
        """Core analysis logic."""
        board = pcbnew.GetBoard()
        if board is None:
            self._show_error("No Board", "Please open a PCB file first.")
            return

        # Get board file path
        board_path = board.GetFileName()
        if not board_path or not os.path.exists(board_path):
            self._show_error(
                "No File",
                "Please save the PCB file before running analysis."
            )
            return

        # Import our analysis modules
        from emf_core.pcb_parser import KiCadPCBParser
        from emf_core.field_estimator import EMFieldEstimator, FieldEstimationConfig
        from emf_core.emi_detector import EMIDetector
        from emf_core.ai_engine import AIAnalysisEngine
        from emf_core.report_generator import ReportGenerator

        # Parse the board
        parser = KiCadPCBParser()
        parsed_board = parser.parse_file(board_path)

        # Show frequency dialog
        freq_hz = self._ask_frequency()
        if freq_hz is None:
            return  # User cancelled

        # Run EMI detection
        detector = EMIDetector()
        report = detector.analyze(parsed_board, freq_hz)

        # Run field estimation
        estimator = EMFieldEstimator()
        config = FieldEstimationConfig(
            frequency_hz=freq_hz,
            grid_resolution=80,
        )
        field_map = estimator.compute(parsed_board, config)

        # Generate AI summary
        ai = AIAnalysisEngine()
        summary = ai.generate_summary(
            report.issues, report.emi_score, report.rf_score
        )

        # Show results dialog
        self._show_results_dialog(
            parsed_board, report, field_map, summary, freq_hz
        )

    def _ask_frequency(self):
        """Show a dialog to ask the user for the operating frequency."""
        import wx

        dlg = wx.TextEntryDialog(
            None,
            "Enter the operating frequency for EMI analysis:\n\n"
            "Examples:\n"
            "  2400   (2.4 GHz)\n"
            "  100    (100 MHz)\n"
            "  868    (868 MHz LoRa)\n"
            "  5800   (5.8 GHz Wi-Fi)",
            "EMF Inspector — Frequency",
            "2400"
        )
        dlg.SetIcon(self._get_icon())

        if dlg.ShowModal() == wx.ID_OK:
            try:
                freq_mhz = float(dlg.GetValue().strip())
                dlg.Destroy()
                return freq_mhz * 1e6  # Convert MHz to Hz
            except ValueError:
                wx.MessageBox(
                    "Invalid frequency. Please enter a number in MHz.",
                    "Input Error", wx.OK | wx.ICON_ERROR
                )
                dlg.Destroy()
                return None
        else:
            dlg.Destroy()
            return None

    def _show_results_dialog(self, board, report, field_map, summary, freq_hz):
        """Show the analysis results in a wx dialog."""
        import wx
        import wx.html2

        # Build HTML content
        html = self._build_results_html(board, report, summary, freq_hz)

        # Create dialog
        dlg = wx.Dialog(
            None, title="EMF Inspector — Analysis Results",
            size=(900, 700),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX
        )
        dlg.SetIcon(self._get_icon())
        dlg.SetBackgroundColour(wx.Colour(15, 23, 42))

        sizer = wx.BoxSizer(wx.VERTICAL)

        # HTML viewer for results
        try:
            html_win = wx.html2.WebView.New(dlg)
            html_win.SetPage(html, "")
        except Exception:
            # Fallback to basic HTML window
            html_win = wx.html.HtmlWindow(dlg)
            html_win.SetPage(html)

        sizer.Add(html_win, 1, wx.EXPAND | wx.ALL, 5)

        # Button bar
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        btn_export_html = wx.Button(dlg, label="Export HTML Report")
        btn_export_json = wx.Button(dlg, label="Export JSON")
        btn_close = wx.Button(dlg, wx.ID_CLOSE, "Close")

        btn_export_html.Bind(wx.EVT_BUTTON,
            lambda evt: self._export_report(board, report, freq_hz, "html"))
        btn_export_json.Bind(wx.EVT_BUTTON,
            lambda evt: self._export_report(board, report, freq_hz, "json"))
        btn_close.Bind(wx.EVT_BUTTON, lambda evt: dlg.Close())

        btn_sizer.Add(btn_export_html, 0, wx.ALL, 5)
        btn_sizer.Add(btn_export_json, 0, wx.ALL, 5)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_close, 0, wx.ALL, 5)

        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)

        dlg.SetSizer(sizer)
        dlg.CenterOnScreen()
        dlg.ShowModal()
        dlg.Destroy()

    def _build_results_html(self, board, report, summary, freq_hz):
        """Build HTML content for the results dialog."""
        import html as html_mod

        sev_colors = {
            "CRITICAL": "#ef4444",
            "HIGH":     "#f97316",
            "MEDIUM":   "#eab308",
            "LOW":      "#22c55e",
            "INFO":     "#3b82f6",
        }

        score_color = (
            "#ef4444" if report.emi_score > 70 else
            "#f97316" if report.emi_score > 40 else
            "#eab308" if report.emi_score > 20 else "#22c55e"
        )

        issues_html = ""
        for issue in sorted(report.issues,
                            key=lambda x: x.severity.score_weight,
                            reverse=True):
            col = sev_colors.get(issue.severity.name, "#6b7280")
            loc = ""
            if issue.location:
                loc = f" — 📍 ({issue.location.x:.1f}, {issue.location.y:.1f}) mm"

            issues_html += f"""
            <div style="background:#1e293b; border-left:4px solid {col};
                        border-radius:8px; padding:12px; margin:8px 0;">
                <span style="background:{col}; color:white; padding:2px 8px;
                             border-radius:4px; font-size:12px; font-weight:700;">
                    {issue.severity.name}
                </span>
                <strong style="color:#e2e8f0; margin-left:8px;">
                    {html_mod.escape(issue.title)}
                </strong>
                <span style="color:#64748b; font-size:12px;">{loc}</span>
                <p style="color:#94a3b8; font-size:13px; margin:6px 0 0 0;">
                    {html_mod.escape(issue.description)}
                </p>
                <p style="color:#7dd3fc; font-size:12px; margin:4px 0 0 0;">
                    💡 {html_mod.escape(issue.recommendation)}
                </p>
            </div>"""

        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
    body {{ font-family: 'Segoe UI', system-ui, sans-serif;
           background: #0f172a; color: #e2e8f0; padding: 20px; margin: 0; }}
    h1 {{ color: #38bdf8; font-size: 24px; margin-bottom: 4px; }}
    h2 {{ color: #7dd3fc; font-size: 16px; margin: 20px 0 10px; }}
    .stats {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; }}
    .stat {{ background: #1e293b; border-radius: 10px; padding: 14px 20px;
             border: 1px solid #334155; min-width: 100px; text-align: center; }}
    .stat-val {{ font-size: 28px; font-weight: 700; }}
    .stat-lbl {{ color: #94a3b8; font-size: 11px; margin-top: 4px; }}
    .summary {{ background: #1e293b; border-radius: 10px; padding: 16px;
                border: 1px solid #334155; white-space: pre-wrap;
                font-family: monospace; font-size: 13px; color: #94a3b8; }}
</style></head><body>
    <h1>⚡ EMF Inspector Results</h1>
    <p style="color:#94a3b8; font-size:13px;">
        {html_mod.escape(board.title or board.file_path)} &nbsp;|&nbsp;
        {freq_hz/1e6:.0f} MHz
    </p>

    <div class="stats">
        <div class="stat">
            <div class="stat-val" style="color:{score_color}">
                {report.emi_score:.0f}
            </div>
            <div class="stat-lbl">EMI Score (0=best)</div>
        </div>
        <div class="stat">
            <div class="stat-val" style="color:#7dd3fc">{report.rf_score:.0f}</div>
            <div class="stat-lbl">RF Score</div>
        </div>
        <div class="stat">
            <div class="stat-val" style="color:#a78bfa">{len(report.issues)}</div>
            <div class="stat-lbl">Issues</div>
        </div>
        <div class="stat">
            <div class="stat-val" style="color:#ef4444">{report.critical_count}</div>
            <div class="stat-lbl">Critical</div>
        </div>
    </div>

    <h2>🤖 AI Assessment</h2>
    <div class="summary">{html_mod.escape(summary)}</div>

    <h2>📋 Issues ({len(report.issues)})</h2>
    {issues_html}
</body></html>"""

    def _export_report(self, board, report, freq_hz, fmt):
        """Export report to file."""
        import wx
        from emf_core.report_generator import ReportGenerator

        ext = "html" if fmt == "html" else "json"
        dlg = wx.FileDialog(
            None, f"Save {fmt.upper()} Report",
            wildcard=f"{ext.upper()} files (*.{ext})|*.{ext}",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
            defaultFile=f"emf_report.{ext}"
        )

        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            gen = ReportGenerator()
            if fmt == "html":
                gen.export_html(board, report, freq_hz, path)
            else:
                gen.export_json(board, report, freq_hz, path)
            wx.MessageBox(
                f"Report saved to:\n{path}",
                "Export Complete", wx.OK | wx.ICON_INFORMATION
            )
        dlg.Destroy()

    def _get_icon(self):
        """Load the plugin icon for dialog windows."""
        import wx
        icon_path = os.path.join(PLUGIN_DIR, "resources", "icon_64x64.png")
        icon = wx.Icon()
        if os.path.exists(icon_path):
            icon.CopyFromBitmap(wx.Bitmap(icon_path))
        return icon

    def _show_error(self, title, message):
        """Show an error dialog."""
        import wx
        wx.MessageBox(message, title, wx.OK | wx.ICON_ERROR)
