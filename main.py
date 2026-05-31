"""
EMF Inspector — Main GUI Application
A rich, dark-themed desktop UI for PCB electromagnetic analysis.

Built with tkinter (standard library) + matplotlib for cross-platform
compatibility without needing PySide6 installed.
"""

from __future__ import annotations
import sys
import os
import threading
import warnings
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import queue

# Suppress harmless matplotlib glyph-missing warnings (emoji not in mpl fonts)
warnings.filterwarnings(
    "ignore",
    message="Glyph .* missing from font",
    category=UserWarning,
    module="matplotlib"
)

# Matplotlib setup (must be before pyplot import)
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import numpy as np

# Local modules
sys.path.insert(0, str(Path(__file__).parent))
from emf_inspector.core.pcb_parser import KiCadPCBParser, PCBBoard, create_demo_board
from emf_inspector.core.field_estimator import EMFieldEstimator, FieldEstimationConfig, EMFieldMap
from emf_inspector.core.emi_detector import EMIDetector, EMIReport, Severity
from emf_inspector.core.ai_engine import AIAnalysisEngine
from emf_inspector.core.report_generator import ReportGenerator

# ─────────────────────────────────────────────────────────────────────────────
# Color palette
# ─────────────────────────────────────────────────────────────────────────────
BG_DARK     = "#0f172a"
BG_CARD     = "#1e293b"
BG_PANEL    = "#152034"
ACCENT_BLUE = "#38bdf8"
ACCENT_CYAN = "#67e8f9"
TEXT_PRIM   = "#e2e8f0"
TEXT_SEC    = "#94a3b8"
TEXT_MUT    = "#475569"
BORDER      = "#334155"
COL_CRIT    = "#ef4444"
COL_HIGH    = "#f97316"
COL_MED     = "#eab308"
COL_LOW     = "#22c55e"
COL_INFO    = "#3b82f6"

SEV_COLORS  = {
    "CRITICAL": COL_CRIT,
    "HIGH":     COL_HIGH,
    "MEDIUM":   COL_MED,
    "LOW":      COL_LOW,
    "INFO":     COL_INFO,
}

FREQUENCIES = {
    "1 MHz":    1e6,
    "10 MHz":   10e6,
    "100 MHz":  100e6,
    "433 MHz":  433e6,
    "868 MHz":  868e6,
    "915 MHz":  915e6,
    "2.4 GHz":  2.4e9,
    "5.8 GHz":  5.8e9,
}

LAYERS = ["ALL", "F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]

EMI_COLORMAP = mcolors.LinearSegmentedColormap.from_list(
    "emi", ["#1a472a", "#22c55e", "#eab308", "#f97316", "#ef4444"])


# ─────────────────────────────────────────────────────────────────────────────
# Styled widget helpers
# ─────────────────────────────────────────────────────────────────────────────

def styled_button(parent, text: str, command=None,
                  fg=BG_DARK, bg=ACCENT_BLUE,
                  font_size=10, **kwargs) -> tk.Button:
    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, font=("Segoe UI", font_size, "bold"),
        relief="flat", cursor="hand2",
        padx=12, pady=6,
        activebackground=ACCENT_CYAN, activeforeground=BG_DARK,
        **kwargs
    )
    btn.bind("<Enter>", lambda e: btn.config(bg=ACCENT_CYAN))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg))
    return btn


def styled_label(parent, text: str, size=10,
                 color=TEXT_PRIM, bold=False, **kwargs) -> tk.Label:
    weight = "bold" if bold else "normal"
    return tk.Label(
        parent, text=text, bg=BG_DARK,
        fg=color, font=("Segoe UI", size, weight), **kwargs
    )


def styled_frame(parent, **kwargs) -> tk.Frame:
    return tk.Frame(parent, bg=BG_DARK, **kwargs)


def card_frame(parent, **kwargs) -> tk.Frame:
    return tk.Frame(parent, bg=BG_CARD,
                    highlightbackground=BORDER,
                    highlightthickness=1, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Visualization panel (matplotlib canvas)
# ─────────────────────────────────────────────────────────────────────────────

class VisualizationPanel:
    """Left panel: PCB viewer + EM field heatmap overlay."""

    def __init__(self, parent):
        self.frame = card_frame(parent)
        self.frame.pack(fill="both", expand=True, padx=6, pady=6)

        # Matplotlib figure — constrained_layout keeps axis size stable when
        # the colorbar is added/removed; tight_layout() caused progressive
        # shrinking every time the user switched heatmap type.
        self.fig = Figure(figsize=(8, 6), facecolor=BG_CARD,
                          constrained_layout=True)
        self.ax = self.fig.add_subplot(111)
        self._style_ax(self.ax)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        toolbar_frame = tk.Frame(self.frame, bg=BG_CARD)
        toolbar_frame.pack(fill="x")
        toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        toolbar.config(background=BG_CARD)
        for child in toolbar.winfo_children():
            try:
                child.config(background=BG_CARD)
            except Exception:
                pass
        toolbar.update()

        # State
        self.board: PCBBoard | None = None
        self.field_map: EMFieldMap | None = None
        self.emi_report: EMIReport | None = None
        self.show_heatmap = tk.BooleanVar(value=True)
        self.show_traces  = tk.BooleanVar(value=True)
        self.show_markers = tk.BooleanVar(value=True)
        self.heatmap_type = tk.StringVar(value="composite")
        self._colorbar = None   # track so we can remove before redraw

        self._draw_welcome()

    def _style_ax(self, ax):
        ax.set_facecolor(BG_PANEL)
        ax.tick_params(colors=TEXT_SEC, labelsize=8)
        ax.spines["bottom"].set_color(BORDER)
        ax.spines["left"].set_color(BORDER)
        ax.spines["top"].set_color(BORDER)
        ax.spines["right"].set_color(BORDER)
        ax.title.set_color(ACCENT_BLUE)
        ax.xaxis.label.set_color(TEXT_SEC)
        ax.yaxis.label.set_color(TEXT_SEC)

    def _draw_welcome(self):
        self.ax.clear()
        self._style_ax(self.ax)
        self.ax.text(0.5, 0.56,
                     "EMF Inspector",
                     ha="center", va="center", fontsize=18,
                     fontweight="bold",
                     color=ACCENT_BLUE, transform=self.ax.transAxes,
                     fontfamily="DejaVu Sans")
        self.ax.text(0.5, 0.44,
                     "AI-Powered PCB EMI Analyzer",
                     ha="center", va="center", fontsize=11,
                     color=ACCENT_CYAN, transform=self.ax.transAxes,
                     fontfamily="DejaVu Sans")
        self.ax.text(0.5, 0.32,
                     "Load a .kicad_pcb file  or  click Demo Board"
                     "\nthen press  Analyze Board  to begin",
                     ha="center", va="center", fontsize=9,
                     color=TEXT_SEC, transform=self.ax.transAxes,
                     fontfamily="DejaVu Sans")
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.canvas.draw()

    def draw_board(self, board: PCBBoard,
                   field_map: EMFieldMap | None = None,
                   emi_report: EMIReport | None = None):
        self.board = board
        self.field_map = field_map
        self.emi_report = emi_report
        self.refresh()

    def refresh(self):
        if not self.board:
            return
        board = self.board
        ax = self.ax
        ax.clear()
        self._style_ax(ax)

        ox, oy = board.origin.x, board.origin.y
        W, H = board.width, board.height

        # ── Heatmap ─────────────────────────────────────────
        # Remove any previous colorbar before redrawing.
        # Colorbars live on the Figure (not the Axes), so ax.clear() never
        # removes them — without this guard they stack up every refresh.
        if self._colorbar is not None:
            try:
                self._colorbar.remove()
            except Exception:
                pass
            self._colorbar = None

        if (self.show_heatmap.get() and
                self.field_map is not None):
            fm = self.field_map
            htype = self.heatmap_type.get()
            if htype == "E_field":
                data = fm.E_field
                vmin, vmax = data.min(), data.max()
            elif htype == "B_field":
                data = fm.B_field
                vmin, vmax = data.min(), data.max()
            else:
                data = fm.heatmap
                vmin, vmax = 0, 1

            extent = [fm.x_grid[0], fm.x_grid[-1],
                      fm.y_grid[0], fm.y_grid[-1]]
            im = ax.imshow(
                data, origin="lower", extent=extent,
                cmap=EMI_COLORMAP, alpha=0.75,
                vmin=vmin, vmax=vmax, aspect="auto",
                interpolation="bicubic"
            )
            self._colorbar = self.fig.colorbar(
                im, ax=ax, fraction=0.025, pad=0.01)
            self._colorbar.ax.yaxis.set_tick_params(color=TEXT_SEC, labelsize=7)
            self._colorbar.set_label(
                {"composite": "EMI Intensity", "E_field": "E-field (V/m)",
                 "B_field": "B-field (T)"}.get(htype, "EMI"),
                color=TEXT_SEC, fontsize=8)
            plt.setp(self._colorbar.ax.yaxis.get_ticklabels(), color=TEXT_SEC)

        # ── Board outline ───────────────────────────────────
        rect = mpatches.FancyBboxPatch(
            (ox, oy), W, H,
            boxstyle="square,pad=0",
            facecolor="none",
            edgecolor=ACCENT_BLUE, linewidth=1.5, linestyle="--"
        )
        ax.add_patch(rect)

        # ── Traces ──────────────────────────────────────────
        if self.show_traces.get():
            layer_colors = {
                "F.Cu":   "#60a5fa",
                "B.Cu":   "#f472b6",
                "In1.Cu": "#34d399",
                "In2.Cu": "#fbbf24",
            }
            for trace in board.traces:
                col = layer_colors.get(trace.layer, "#94a3b8")
                lw = max(0.3, min(3.0, trace.width * 2))
                ax.plot(
                    [trace.start.x, trace.end.x],
                    [trace.start.y, trace.end.y],
                    color=col, linewidth=lw, alpha=0.7, solid_capstyle="round"
                )

        # ── Vias ────────────────────────────────────────────
        for via in board.vias:
            circle = plt.Circle(
                (via.position.x, via.position.y),
                radius=via.size / 2,
                color="#a78bfa", fill=False, linewidth=0.8, alpha=0.8
            )
            ax.add_patch(circle)

        # ── Ground plane zones ──────────────────────────────
        for zone in board.zones:
            if zone.net in board.ground_nets:
                xs = [p.x for p in zone.polygon] + [zone.polygon[0].x]
                ys = [p.y for p in zone.polygon] + [zone.polygon[0].y]
                ax.fill(xs, ys, color="#16a34a", alpha=0.08)
                ax.plot(xs, ys, color="#16a34a", linewidth=0.5,
                        linestyle=":", alpha=0.4)

        # ── Components ──────────────────────────────────────
        for comp in board.components:
            ax.plot(comp.position.x, comp.position.y,
                    "s", color="#e2e8f0", markersize=4, alpha=0.6)
            ax.text(comp.position.x, comp.position.y + 1.5,
                    comp.reference, fontsize=5, color=TEXT_MUT,
                    ha="center", va="bottom")

        # ── EMI Issue markers ───────────────────────────────
        if self.show_markers.get() and self.emi_report:
            sev_marker_colors = {
                Severity.CRITICAL: COL_CRIT,
                Severity.HIGH:     COL_HIGH,
                Severity.MEDIUM:   COL_MED,
                Severity.LOW:      COL_LOW,
                Severity.INFO:     COL_INFO,
            }
            sev_sizes = {
                Severity.CRITICAL: 160,
                Severity.HIGH:     120,
                Severity.MEDIUM:   80,
                Severity.LOW:      50,
                Severity.INFO:     30,
            }
            for issue in self.emi_report.issues:
                if not issue.location:
                    continue
                col = sev_marker_colors.get(issue.severity, "#94a3b8")
                sz  = sev_sizes.get(issue.severity, 60)
                ax.scatter(
                    issue.location.x, issue.location.y,
                    s=sz, c=col, marker="^", alpha=0.85,
                    zorder=5, linewidths=0.5, edgecolors="white"
                )

        # ── Legend ──────────────────────────────────────────
        legend_elems = [
            mpatches.Patch(color="#60a5fa", label="F.Cu traces"),
            mpatches.Patch(color="#f472b6", label="B.Cu traces"),
            mpatches.Patch(color="#a78bfa", label="Vias"),
            mpatches.Patch(color="#16a34a", label="GND zones"),
            mpatches.Patch(color=COL_CRIT,  label="CRITICAL"),
            mpatches.Patch(color=COL_HIGH,  label="HIGH"),
            mpatches.Patch(color=COL_MED,   label="MEDIUM"),
        ]
        ax.legend(handles=legend_elems, loc="lower right",
                  fontsize=6.5, framealpha=0.7,
                  facecolor=BG_CARD, edgecolor=BORDER,
                  labelcolor=TEXT_PRIM)

        # ── Axis limits, labels, title ───────────────────────
        pad_x = max(2.0, W * 0.05)
        pad_y = max(2.0, H * 0.05)
        ax.set_xlim(ox - pad_x, ox + W + pad_x)
        ax.set_ylim(oy - pad_y, oy + H + pad_y)
        ax.set_xlabel("X (mm)", color=TEXT_SEC, fontsize=8)
        ax.set_ylabel("Y (mm)", color=TEXT_SEC, fontsize=8)
        n_copper = len(board.copper_layers) or len(
            [l for l in board.layers if "Cu" in l])
        layer_str = (f"{n_copper} copper layer"
                     + ("s" if n_copper != 1 else ""))
        ax.set_title(
            f"PCB: {board.title or 'Board'}   "
            f"{W:.0f} x {H:.0f} mm   "
            f"{layer_str}   "
            f"{len(board.traces)} traces",
            fontsize=9, pad=6)
        ax.set_aspect("auto")
        ax.grid(True, color=BORDER, linewidth=0.3, alpha=0.4)
        # Do NOT call tight_layout() here — constrained_layout on the Figure
        # handles spacing automatically without shrinking the axes each call.
        self.canvas.draw()

    def save_heatmap(self, path: str):
        """Save the current figure as a PNG for report embedding."""
        self.fig.savefig(path, facecolor=BG_CARD, dpi=150, bbox_inches="tight")


# ─────────────────────────────────────────────────────────────────────────────
# Issue list panel
# ─────────────────────────────────────────────────────────────────────────────

class IssueListPanel:
    """Right panel: scrollable list of EMI issues with click-to-inspect."""

    def __init__(self, parent, on_select_callback=None):
        self.frame = card_frame(parent)
        self.on_select = on_select_callback
        self.issues = []

        # Header
        hdr = styled_frame(self.frame)
        hdr.pack(fill="x", padx=8, pady=(8, 4))
        styled_label(hdr, "⚠  EMI Issues", size=11, bold=True,
                     color=ACCENT_BLUE).pack(side="left")

        self.count_label = styled_label(hdr, "", size=9, color=TEXT_SEC)
        self.count_label.pack(side="right")

        # Filter bar
        flt = styled_frame(self.frame)
        flt.pack(fill="x", padx=8, pady=2)
        styled_label(flt, "Filter:", size=8, color=TEXT_SEC).pack(side="left")
        self.filter_var = tk.StringVar(value="ALL")
        for sev in ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            col = SEV_COLORS.get(sev, ACCENT_BLUE)
            rb = tk.Radiobutton(
                flt, text=sev, variable=self.filter_var, value=sev,
                command=self._apply_filter,
                bg=BG_DARK, fg=col, selectcolor=BG_CARD,
                font=("Segoe UI", 7, "bold"),
                activebackground=BG_DARK, activeforeground=col,
                indicatoron=False, relief="flat",
                padx=4, pady=2, cursor="hand2"
            )
            rb.pack(side="left", padx=1)

        # Scrollable list
        list_frame = tk.Frame(self.frame, bg=BG_CARD)
        list_frame.pack(fill="both", expand=True, padx=4, pady=4)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            list_frame, bg=BG_CARD, fg=TEXT_PRIM,
            font=("Segoe UI", 8), selectbackground="#1e3a5f",
            selectforeground=ACCENT_CYAN,
            yscrollcommand=scrollbar.set,
            relief="flat", bd=0,
            activestyle="none", cursor="hand2"
        )
        self.listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

    def load_issues(self, issues):
        self.issues = issues
        self._apply_filter()

    def _apply_filter(self):
        flt = self.filter_var.get()
        self.listbox.delete(0, "end")
        self._displayed_issues = []
        for issue in self.issues:
            if flt != "ALL" and issue.severity.name != flt:
                continue
            self._displayed_issues.append(issue)
            col = SEV_COLORS.get(issue.severity.name, TEXT_SEC)
            prefix = {
                "CRITICAL": "🔴",
                "HIGH":     "🟠",
                "MEDIUM":   "🟡",
                "LOW":      "🟢",
                "INFO":     "🔵",
            }.get(issue.severity.name, "•")
            label = (f"{prefix} [{issue.severity.name}] {issue.title}"
                     + (f" — {issue.detail_value}" if issue.detail_value else ""))
            self.listbox.insert("end", label)
            self.listbox.itemconfig("end", fg=col)

        n = len(self._displayed_issues)
        total = len(self.issues)
        self.count_label.config(
            text=f"{n}/{total}" if flt != "ALL" else f"{total} issues")

    def _on_select(self, event):
        sel = self.listbox.curselection()
        if sel and self.on_select:
            idx = sel[0]
            if idx < len(self._displayed_issues):
                self.on_select(self._displayed_issues[idx])


# ─────────────────────────────────────────────────────────────────────────────
# AI Inspector panel (bottom detail panel)
# ─────────────────────────────────────────────────────────────────────────────

class AIInspectorPanel:
    """Bottom panel: shows AI explanation when an issue is selected."""

    def __init__(self, parent):
        self.frame = card_frame(parent)
        self.ai = AIAnalysisEngine()

        hdr = styled_frame(self.frame)
        hdr.pack(fill="x", padx=8, pady=(8, 4))
        styled_label(hdr, "🤖  AI Inspector", size=11, bold=True,
                     color=ACCENT_BLUE).pack(side="left")

        # Text widget with scrollbar
        txt_frame = tk.Frame(self.frame, bg=BG_CARD)
        txt_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        sb = ttk.Scrollbar(txt_frame)
        sb.pack(side="right", fill="y")

        self.text = tk.Text(
            txt_frame, bg=BG_CARD, fg=TEXT_SEC,
            font=("Segoe UI", 9), relief="flat",
            wrap="word", padx=8, pady=6,
            yscrollcommand=sb.set,
            state="disabled", cursor="arrow"
        )
        self.text.pack(fill="both", expand=True)
        sb.config(command=self.text.yview)

        # Tags for colored text
        self.text.tag_config("heading",  foreground=ACCENT_BLUE,
                             font=("Segoe UI", 10, "bold"))
        self.text.tag_config("subhead",  foreground=ACCENT_CYAN,
                             font=("Segoe UI", 9, "bold"))
        self.text.tag_config("body",     foreground=TEXT_SEC)
        self.text.tag_config("green",    foreground=COL_LOW)
        self.text.tag_config("orange",   foreground=COL_HIGH)
        self.text.tag_config("red",      foreground=COL_CRIT)
        self.text.tag_config("mono",     font=("Consolas", 8),
                             foreground="#fbbf24")
        self.text.tag_config("step",     foreground=TEXT_PRIM)

        self._show_placeholder()

    def _show_placeholder(self):
        self._write([
            ("heading", "AI Inspector\n\n"),
            ("body", "Click on an EMI issue in the list above to see:\n"
             "  • Physics explanation\n"
             "  • Root cause analysis\n"
             "  • Step-by-step recommended fixes\n"
             "  • Expected improvement estimate"),
        ])

    def show_issue(self, issue):
        exp = self.ai.explain(issue)
        sev_tag = {
            "CRITICAL": "red",
            "HIGH":     "orange",
            "MEDIUM":   "orange",
            "LOW":      "green",
            "INFO":     "body",
        }.get(issue.severity.name, "body")

        rows = [
            ("heading", f"{'─'*50}\n"),
            (sev_tag,   f"[{issue.severity.name}] "),
            ("heading",  f"{issue.title}\n\n"),
            ("subhead",  "📍 Why This Occurred\n"),
            ("body",     exp.why_it_happened + "\n\n"),
            ("subhead",  "⚡ Physics Background\n"),
            ("mono",     exp.physics_background + "\n\n"),
            ("subhead",  "⚠️  EMI Consequences\n"),
            ("body",     exp.emi_consequence + "\n\n"),
            ("subhead",  "🔧 Recommended Fix Steps\n"),
        ]
        for i, step in enumerate(exp.fix_steps, 1):
            rows.append(("step", f"  {i}. {step}\n"))

        rows += [
            ("body",  "\n"),
            ("subhead", "📈 Expected Improvement\n"),
            ("green", exp.estimated_improvement + "\n"),
        ]

        if issue.location:
            rows.append(
                ("body", f"\n📍 Location: ({issue.location.x:.1f}, "
                 f"{issue.location.y:.1f}) mm"))
        if issue.affected_net:
            rows.append(("body", f"\n🔗 Net: {issue.affected_net}"))
        if issue.affected_ref:
            rows.append(("body", f"\n🔧 Component: {issue.affected_ref}"))

        self._write(rows)

    def show_summary(self, issues, emi_score: float, rf_score: float):
        ai = AIAnalysisEngine()
        summary = ai.generate_summary(issues, emi_score, rf_score)
        self._write([
            ("heading", "Board Summary\n\n"),
            ("mono",    summary),
        ])

    def _write(self, rows: list[tuple[str, str]]):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        for tag, text in rows:
            self.text.insert("end", text, tag)
        self.text.config(state="disabled")
        self.text.see("1.0")


# ─────────────────────────────────────────────────────────────────────────────
# Score gauge widget
# ─────────────────────────────────────────────────────────────────────────────

class ScoreGauge(tk.Canvas):
    def __init__(self, parent, label="Score", **kwargs):
        super().__init__(parent, width=90, height=90,
                         bg=BG_CARD, highlightthickness=0, **kwargs)
        self.label_text = label
        self._score = 0
        self._draw(0)

    def set_score(self, score: float):
        self._score = score
        self._draw(score)

    def _draw(self, score: float):
        self.delete("all")
        col = (COL_CRIT if score > 70 else
               COL_HIGH if score > 40 else
               COL_MED  if score > 20 else COL_LOW)
        # Arc background
        self.create_arc(8, 8, 82, 82, start=0, extent=360,
                        outline=BORDER, width=6, style="arc")
        # Score arc
        extent = score / 100 * 360
        self.create_arc(8, 8, 82, 82, start=90, extent=-extent,
                        outline=col, width=6, style="arc")
        # Score text
        self.create_text(45, 38, text=f"{score:.0f}",
                         fill=col, font=("Segoe UI", 18, "bold"))
        self.create_text(45, 58, text=self.label_text,
                         fill=TEXT_SEC, font=("Segoe UI", 7))
        self.create_text(45, 72, text="/100",
                         fill=TEXT_MUT, font=("Segoe UI", 6))


# ─────────────────────────────────────────────────────────────────────────────
# Main Application Window
# ─────────────────────────────────────────────────────────────────────────────

class EMFInspectorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("⚡ EMF Inspector — AI-Powered PCB EMI Analyzer")
        self.root.geometry("1400x860")
        self.root.minsize(1100, 700)
        self.root.configure(bg=BG_DARK)

        # Configure ttk styles
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TScrollbar", background=BG_CARD,
                        troughcolor=BG_DARK, arrowcolor=TEXT_SEC)
        # Full dark-theme combobox: text must be visible in the field
        style.configure(
            "TCombobox",
            fieldbackground=BG_CARD,
            background=BG_CARD,
            foreground=TEXT_PRIM,
            selectbackground="#1e3a5f",
            selectforeground=ACCENT_CYAN,
            arrowcolor=ACCENT_BLUE,
            bordercolor=BORDER,
            lightcolor=BG_CARD,
            darkcolor=BG_CARD,
            insertcolor=TEXT_PRIM,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", BG_CARD)],
            foreground=[("readonly", TEXT_PRIM)],
            selectbackground=[("readonly", "#1e3a5f")],
            selectforeground=[("readonly", ACCENT_CYAN)],
        )
        style.configure("TProgressbar", background=ACCENT_BLUE,
                        troughcolor=BG_DARK)

        # State
        self.board: PCBBoard | None = None
        self.field_map: EMFieldMap | None = None
        self.emi_report: EMIReport | None = None
        self._analysis_queue: queue.Queue = queue.Queue()
        self._pcb_file_path: str | None = None

        # Build UI
        self._build_toolbar()
        self._build_main_area()
        self._build_status_bar()

        # Poll queue
        self.root.after(100, self._poll_queue)

    # ─────────────────────────────────────────────────────────
    # UI Construction
    # ─────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = tk.Frame(self.root, bg=BG_CARD, height=56,
                      highlightbackground=BORDER, highlightthickness=1)
        tb.pack(fill="x", padx=0, pady=0)
        tb.pack_propagate(False)

        # Logo
        logo_frame = tk.Frame(tb, bg=BG_CARD)
        logo_frame.pack(side="left", padx=16, pady=6)
        tk.Label(logo_frame, text="⚡", bg=BG_CARD, fg=ACCENT_BLUE,
                 font=("Segoe UI", 20)).pack(side="left")
        tk.Label(logo_frame, text="EMF Inspector", bg=BG_CARD, fg=ACCENT_BLUE,
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=4)
        tk.Label(logo_frame, text="v1.0", bg=BG_CARD, fg=TEXT_MUT,
                 font=("Segoe UI", 8)).pack(side="left")

        # File buttons
        btn_frame = tk.Frame(tb, bg=BG_CARD)
        btn_frame.pack(side="left", padx=20)
        styled_button(btn_frame, "📂 Open PCB File",
                      command=self._open_file).pack(side="left", padx=4)
        styled_button(btn_frame, "🧪 Demo Board",
                      command=self._load_demo,
                      bg="#6d28d9", fg="white").pack(side="left", padx=4)

        # Divider
        tk.Frame(tb, bg=BORDER, width=1).pack(side="left",
                                              fill="y", pady=8, padx=8)

        # Frequency selector
        freq_frame = tk.Frame(tb, bg=BG_CARD)
        freq_frame.pack(side="left", padx=8)
        tk.Label(freq_frame, text="RF Freq:", bg=BG_CARD, fg=TEXT_SEC,
                 font=("Segoe UI", 8)).pack(side="left")
        self.freq_var = tk.StringVar(value="2.4 GHz")
        freq_cb = ttk.Combobox(
            freq_frame, textvariable=self.freq_var,
            values=list(FREQUENCIES.keys()), width=9,
            state="readonly", font=("Segoe UI", 9)
        )
        freq_cb.pack(side="left", padx=4)

        # Layer selector
        layer_frame = tk.Frame(tb, bg=BG_CARD)
        layer_frame.pack(side="left", padx=8)
        tk.Label(layer_frame, text="Layer:", bg=BG_CARD, fg=TEXT_SEC,
                 font=("Segoe UI", 8)).pack(side="left")
        self.layer_var = tk.StringVar(value="F.Cu")
        layer_cb = ttk.Combobox(
            layer_frame, textvariable=self.layer_var,
            values=LAYERS, width=8,
            state="readonly", font=("Segoe UI", 9)
        )
        layer_cb.pack(side="left", padx=4)

        # Grid resolution
        res_frame = tk.Frame(tb, bg=BG_CARD)
        res_frame.pack(side="left", padx=8)
        tk.Label(res_frame, text="Grid:", bg=BG_CARD, fg=TEXT_SEC,
                 font=("Segoe UI", 8)).pack(side="left")
        self.grid_var = tk.StringVar(value="60")
        res_cb = ttk.Combobox(
            res_frame, textvariable=self.grid_var,
            values=["30", "60", "100", "150"],
            width=5, state="readonly", font=("Segoe UI", 9)
        )
        res_cb.pack(side="left", padx=2)

        # Analyze button
        self.analyze_btn = styled_button(
            tb, "⚡ Analyze Board",
            command=self._start_analysis,
            bg="#dc2626", fg="white", font_size=11)
        self.analyze_btn.pack(side="left", padx=16)

        # Scores (right side of toolbar)
        score_frame = tk.Frame(tb, bg=BG_CARD)
        score_frame.pack(side="right", padx=16)
        self.emi_gauge = ScoreGauge(score_frame, label="EMI")
        self.emi_gauge.pack(side="left", padx=4)
        self.rf_gauge = ScoreGauge(score_frame, label="RF")
        self.rf_gauge.pack(side="left", padx=4)

        # Export buttons
        export_frame = tk.Frame(tb, bg=BG_CARD)
        export_frame.pack(side="right", padx=8)
        styled_button(export_frame, "📄 HTML",
                      command=lambda: self._export("html"),
                      bg="#065f46", fg="white",
                      font_size=8).pack(side="left", padx=2)
        styled_button(export_frame, "📋 JSON",
                      command=lambda: self._export("json"),
                      bg="#1e3a5f", fg="white",
                      font_size=8).pack(side="left", padx=2)
        styled_button(export_frame, "🖨 PDF",
                      command=lambda: self._export("pdf"),
                      bg="#4c1d95", fg="white",
                      font_size=8).pack(side="left", padx=2)

    def _build_main_area(self):
        main = styled_frame(self.root)
        main.pack(fill="both", expand=True, padx=4, pady=4)

        # Left pane: visualization
        left = styled_frame(main)
        left.pack(side="left", fill="both", expand=True)

        # Toggle controls above viz
        ctrl = styled_frame(left)
        ctrl.pack(fill="x", padx=6, pady=2)

        self.heatmap_var = tk.BooleanVar(value=True)
        self.traces_var  = tk.BooleanVar(value=True)
        self.markers_var = tk.BooleanVar(value=True)

        for label, var, cmd in [
            ("🔥 Heatmap", self.heatmap_var, None),
            ("📏 Traces",  self.traces_var,  None),
            ("⚠ Markers", self.markers_var, None),
        ]:
            cb = tk.Checkbutton(
                ctrl, text=label, variable=var,
                command=self._refresh_view,
                bg=BG_DARK, fg=TEXT_PRIM,
                selectcolor=BG_CARD,
                font=("Segoe UI", 8),
                activebackground=BG_DARK,
                activeforeground=ACCENT_CYAN,
                cursor="hand2"
            )
            cb.pack(side="left", padx=6)

        # Heatmap type selector
        tk.Label(ctrl, text="  Map:", bg=BG_DARK, fg=TEXT_SEC,
                 font=("Segoe UI", 8)).pack(side="left")
        self.maptype_var = tk.StringVar(value="composite")
        for val, label in [("composite", "Composite"),
                           ("E_field", "E-field"),
                           ("B_field", "B-field")]:
            rb = tk.Radiobutton(
                ctrl, text=label, variable=self.maptype_var, value=val,
                command=self._refresh_view,
                bg=BG_DARK, fg=ACCENT_CYAN,
                selectcolor=BG_CARD,
                font=("Segoe UI", 8),
                activebackground=BG_DARK,
                indicatoron=False, relief="flat",
                padx=4, pady=2, cursor="hand2"
            )
            rb.pack(side="left", padx=1)

        self.viz = VisualizationPanel(left)

        # Right pane: issues + AI panel
        right = styled_frame(main)
        right.pack(side="right", fill="both", padx=(0, 4))
        right.config(width=420)
        right.pack_propagate(False)

        # Issue list (top 60%)
        self.issue_panel = IssueListPanel(right, on_select_callback=self._on_issue_select)
        self.issue_panel.frame.pack(fill="both", expand=True, pady=(0, 4))

        # AI Inspector (bottom 40%)
        self.ai_panel = AIInspectorPanel(right)
        self.ai_panel.frame.pack(fill="both", expand=True)

    def _build_status_bar(self):
        sb = tk.Frame(self.root, bg=BG_CARD, height=24,
                      highlightbackground=BORDER, highlightthickness=1)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)

        self.status_var = tk.StringVar(value="Ready — load a .kicad_pcb file or use Demo Board")
        tk.Label(sb, textvariable=self.status_var,
                 bg=BG_CARD, fg=TEXT_SEC,
                 font=("Segoe UI", 8), anchor="w").pack(
            side="left", padx=10, fill="x", expand=True)

        self.progress = ttk.Progressbar(sb, mode="indeterminate",
                                        length=150, style="TProgressbar")
        self.progress.pack(side="right", padx=10, pady=3)

    # ─────────────────────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────────────────────

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Open KiCad PCB File",
            filetypes=[("KiCad PCB", "*.kicad_pcb"), ("All Files", "*.*")]
        )
        if path:
            self._pcb_file_path = path
            self._load_board_file(path)

    def _load_board_file(self, path: str):
        self._set_status(f"Parsing {Path(path).name}…")
        try:
            parser = KiCadPCBParser()
            self.board = parser.parse_file(path)
            self._set_status(
                f"Loaded: {Path(path).name}  |  "
                f"{len(self.board.traces)} traces  "
                f"{len(self.board.vias)} vias  "
                f"{len(self.board.components)} components  "
                f"[{self.board.width:.0f}×{self.board.height:.0f} mm]"
            )
            self.viz.draw_board(self.board)
        except Exception as e:
            messagebox.showerror("Parse Error",
                                 f"Could not parse PCB file:\n{e}")
            self._set_status("Error loading file")

    def _load_demo(self):
        self._set_status("Loading demo ESP32 RF board…")
        self.board = create_demo_board()
        self._pcb_file_path = None
        self._set_status(
            f"Demo Board: {self.board.title}  |  "
            f"{len(self.board.traces)} traces  "
            f"{len(self.board.vias)} vias  "
            f"{len(self.board.components)} components  "
            f"[{self.board.width:.0f}×{self.board.height:.0f} mm]"
        )
        self.viz.draw_board(self.board)

    def _start_analysis(self):
        if not self.board:
            messagebox.showwarning("No Board", "Please load a PCB file first.")
            return

        self.analyze_btn.config(state="disabled", text="⏳ Analyzing…")
        self.progress.start(10)
        self._set_status("Running EM field estimation and EMI analysis…")

        freq = FREQUENCIES[self.freq_var.get()]
        layer = self.layer_var.get()
        grid = int(self.grid_var.get())
        board = self.board

        def _worker():
            try:
                # Field estimation
                cfg = FieldEstimationConfig(
                    frequency_hz=freq,
                    grid_resolution=grid,
                    layer=layer
                )
                estimator = EMFieldEstimator(cfg)
                field_map = estimator.compute(board, cfg)

                # EMI detection
                detector = EMIDetector()
                emi_report = detector.analyze(board, freq)

                self._analysis_queue.put(("done", field_map, emi_report))
            except Exception as e:
                self._analysis_queue.put(("error", str(e)))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _poll_queue(self):
        try:
            msg = self._analysis_queue.get_nowait()
            if msg[0] == "done":
                _, field_map, emi_report = msg
                self._on_analysis_done(field_map, emi_report)
            elif msg[0] == "error":
                self.progress.stop()
                self.analyze_btn.config(state="normal",
                                        text="⚡ Analyze Board")
                messagebox.showerror("Analysis Error", msg[1])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _on_analysis_done(self, field_map: EMFieldMap,
                           emi_report: EMIReport):
        self.field_map = field_map
        self.emi_report = emi_report
        self.progress.stop()
        self.analyze_btn.config(state="normal", text="⚡ Analyze Board")

        # Update viz
        self.viz.field_map = field_map
        self.viz.show_heatmap = self.heatmap_var
        self.viz.show_traces  = self.traces_var
        self.viz.show_markers = self.markers_var
        self.viz.heatmap_type = self.maptype_var
        self.viz.draw_board(self.board, field_map, emi_report)

        # Update scores
        self.emi_gauge.set_score(emi_report.emi_score)
        self.rf_gauge.set_score(emi_report.rf_score)

        # Update issue list
        self.issue_panel.load_issues(emi_report.issues)

        # Show summary in AI panel
        self.ai_panel.show_summary(
            emi_report.issues, emi_report.emi_score, emi_report.rf_score)

        n_crit = emi_report.critical_count
        n_high = emi_report.high_count
        self._set_status(
            f"Analysis complete  |  "
            f"EMI Score: {emi_report.emi_score:.0f}  "
            f"RF Score: {emi_report.rf_score:.0f}  |  "
            f"{len(emi_report.issues)} issues  "
            f"({n_crit} critical, {n_high} high)"
        )

    def _on_issue_select(self, issue):
        self.ai_panel.show_issue(issue)
        if issue.location:
            ax = self.viz.ax
            ax.set_xlim(issue.location.x - 20, issue.location.x + 20)
            ax.set_ylim(issue.location.y - 20, issue.location.y + 20)
            self.viz.canvas.draw()

    def _refresh_view(self):
        if not self.board:
            return
        self.viz.show_heatmap = self.heatmap_var
        self.viz.show_traces  = self.traces_var
        self.viz.show_markers = self.markers_var
        self.viz.heatmap_type = self.maptype_var
        self.viz.refresh()

    def _export(self, fmt: str):
        if not self.board or not self.emi_report:
            messagebox.showwarning("No Analysis",
                                   "Run analysis first before exporting.")
            return

        ext = {"html": ".html", "json": ".json", "pdf": ".pdf"}[fmt]
        default = (Path(self.board.file_path).stem
                   if self.board.file_path != "<demo>"
                   else "emf_report") + "_emf_report"
        path = filedialog.asksaveasfilename(
            defaultextension=ext,
            initialfile=default,
            filetypes=[(fmt.upper(), f"*{ext}"), ("All", "*.*")]
        )
        if not path:
            return

        self._set_status(f"Exporting {fmt.upper()} report…")
        try:
            rg = ReportGenerator()
            freq = FREQUENCIES[self.freq_var.get()]

            # Save heatmap image for embedding
            heatmap_img = None
            if fmt in ("html", "pdf") and self.field_map is not None:
                heatmap_img = path + "_heatmap.png"
                self.viz.save_heatmap(heatmap_img)

            if fmt == "html":
                out = rg.export_html(self.board, self.emi_report,
                                     freq, path, heatmap_img)
            elif fmt == "json":
                out = rg.export_json(self.board, self.emi_report,
                                     freq, path)
            elif fmt == "pdf":
                out = rg.export_pdf(self.board, self.emi_report,
                                    freq, path, heatmap_img)
            else:
                return

            self._set_status(f"Report saved: {out}")
            if messagebox.askyesno("Export Complete",
                                   f"Report saved:\n{out}\n\nOpen file?"):
                import subprocess
                os.startfile(out) if sys.platform == "win32" else \
                    subprocess.run(["xdg-open", out])
        except Exception as e:
            messagebox.showerror("Export Error", str(e))
            self._set_status("Export failed")

    def _set_status(self, msg: str):
        self.status_var.set(msg)
        self.root.update_idletasks()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    app = EMFInspectorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
