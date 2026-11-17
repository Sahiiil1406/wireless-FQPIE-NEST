#!/usr/bin/env python3
"""Build a concise, visual FQ-PIE scenario/case report as a local .docx.

Data: ``wirelesss_final`` (5 scenarios x 8 cases x 4 targets, 4 archived runs).
Output: ``presentation/FQPIE_Detailed_Report.docx``
"""

from __future__ import annotations

import glob
import json
import os
import statistics
from typing import Dict, List, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch
import numpy as np

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "wirelesss_final")
OUT_DIR = os.path.join(ROOT, "presentation")
ASSETS = os.path.join(OUT_DIR, "assets")
OUT_PATH = os.path.join(OUT_DIR, "FQPIE_Detailed_Report.docx")

INK = RGBColor(0x11, 0x11, 0x11)
INK2 = RGBColor(0x2B, 0x2B, 0x2B)
BODY = RGBColor(0x20, 0x21, 0x24)
MUTED = RGBColor(0x55, 0x55, 0x55)
HEADER_FILL = "1A1A1A"
ZEBRA = "F5F5F5"
RULE = "C9C9C9"
LIGHT = "D9D9D9"

SCENARIOS = [
    ("synchronous", "Synchronous"),
    ("staggered", "Staggered"),
    ("rtt_fairness", "RTT fairness"),
    ("pulse_wave", "Pulse wave"),
    ("udp_background", "UDP background"),
]

CASES = [
    ("bw100mbit", "bandwidth"),
    ("bw10mbit", "bandwidth"),
    ("rtt60ms", "delay"),
    ("rtt120ms", "delay"),
    ("queue100pkt", "queue"),
    ("queue1000pkt", "queue"),
    ("load10flows", "load"),
    ("load100flows", "load"),
]

CASE_SHORT = {
    "bw100mbit": "bw100",
    "bw10mbit": "bw10",
    "rtt60ms": "rtt60",
    "rtt120ms": "rtt120",
    "queue100pkt": "q100",
    "queue1000pkt": "q1000",
    "load10flows": "load10",
    "load100flows": "load100",
}

TARGETS = [5, 10, 15, 30]

SCENARIO_INFO = {
    "synchronous": (
        "All flows start together with equal RTT.",
        "Equal start, equal RTT",
    ),
    "staggered": (
        "Flows start 250 ms apart; the full start span is capped at 10 s.",
        "Staggered arrivals",
    ),
    "rtt_fairness": (
        "Flows start together with 0.5x, 1x and 2x the case RTT.",
        "Mixed RTTs",
    ),
    "pulse_wave": (
        "Bottleneck capacity toggles between 100% and 50% every 10 s.",
        "Changing capacity",
    ),
    "udp_background": (
        "Bulk UDP flows take 20% of the bottleneck alongside TCP.",
        "TCP/UDP competition",
    ),
}

CASE_INFO = {
    "bw100mbit": ("100 Mbit", "100", "100", "default", "Canonical reference"),
    "bw10mbit": ("10 Mbit", "10", "100", "default", "Capacity, fixed 1 Mbit/flow"),
    "rtt60ms": ("100 Mbit", "100", "60", "default", "Shorter control loop"),
    "rtt120ms": ("100 Mbit", "100", "120", "default", "Longer control loop"),
    "queue100pkt": ("100 Mbit", "100", "100", "100 pkt", "Shallow queue"),
    "queue1000pkt": ("100 Mbit", "100", "100", "1000 pkt", "Deep queue"),
    "load10flows": ("100 Mbit", "10", "100", "default", "Low flow count"),
    "load100flows": ("100 Mbit", "100", "100", "default", "High flow count"),
}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_cells() -> Dict[Tuple[str, str, int], Dict[str, object]]:
    cells: Dict[Tuple[str, str, int], Dict[str, object]] = {}
    for scenario, _ in SCENARIOS:
        for case, category in CASES:
            for target in TARGETS:
                paths = glob.glob(
                    os.path.join(
                        DATA, scenario, category, case,
                        f"target_{target}ms", "run_*", "metrics.json",
                    )
                )
                runs = [json.load(open(p)) for p in sorted(paths)]
                if not runs:
                    continue
                clean = [
                    r for r in runs
                    if float(r["link_utilization_pct"]) <= 100.5
                    and float(r["fairness_jain"]) >= 0.5
                ]
                flagged = len(clean) < 2
                use = clean if not flagged else runs
                med = {
                    key: statistics.median(float(r[key]) for r in use)
                    for key in (
                        "throughput_mbps",
                        "link_utilization_pct",
                        "packet_loss_pct",
                        "fairness_jain",
                        "queue_delay_ms",
                        "queue_delay_p95_ms",
                    )
                }
                cells[(scenario, case, target)] = {
                    **med,
                    "n_runs": len(runs),
                    "n_clean": len(clean),
                    "flagged": flagged,
                    "max_util": max(float(r["link_utilization_pct"]) for r in runs),
                }
    return cells


def latency_utility(q: float) -> float:
    if q <= 10.0:
        return 1.0
    return max(0.0, 1.0 - (q - 10.0) / 20.0)


def score(cell: Dict[str, object]) -> float:
    return (
        0.40 * min(float(cell["link_utilization_pct"]), 100.0) / 100.0
        + 0.30 * float(cell["fairness_jain"])
        + 0.20 * (1.0 - min(float(cell["packet_loss_pct"]), 20.0) / 20.0)
        + 0.10 * latency_utility(float(cell["queue_delay_ms"]))
    )


def choose_target(cells, scenario: str, case: str) -> Tuple[int, float]:
    scores = {t: score(cells[(scenario, case, t)]) for t in TARGETS}
    best = max(scores, key=lambda t: scores[t])
    gain = scores[best] - scores[15]
    return (best if gain >= 0.015 else 15), gain


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8.5,
    "axes.edgecolor": "#444444",
    "axes.linewidth": 0.7,
    "xtick.color": "#333333",
    "ytick.color": "#333333",
    "text.color": "#111111",
})


def _save(fig, path: str) -> None:
    fig.savefig(path, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def make_topology(path: str) -> None:
    fig, ax = plt.subplots(figsize=(9.6, 3.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.2)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    def box(x, y, w, h, title, sub, fill="#F2F2F2"):
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.08",
            linewidth=1.1, edgecolor="#111111", facecolor=fill,
        ))
        ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center",
                fontsize=9.5, fontweight="bold", color="#111111")
        ax.text(x + w / 2, y + h * 0.29, sub, ha="center", va="center",
                fontsize=7.8, color="#333333")

    box(0.15, 1.05, 1.75, 2.1, "Senders", "100 or 10 TCP\nUDP in one scenario")
    box(2.65, 1.25, 1.55, 1.7, "Edge", "1000 Mbit/s\nper-flow RTT")
    box(4.70, 0.95, 1.75, 2.3, "Bottleneck", "FQ-PIE\n100 or 10 Mbit/s\n20 ms one-way")
    box(6.95, 1.25, 1.55, 1.7, "Edge", "1000 Mbit/s\nqueue sampled")
    box(8.85, 1.05, 1.0, 2.1, "Receivers", "iperf3\nbytes")

    for x0, x1 in ((1.90, 2.65), (4.20, 4.70), (6.45, 6.95), (8.50, 8.85)):
        ax.add_patch(FancyArrowPatch((x0, 2.1), (x1, 2.1), arrowstyle="-|>",
                                     mutation_scale=10, linewidth=0.9, color="#111111"))

    ax.text(5.575, 3.55, "Dumbbell topology", ha="center", va="center",
            fontsize=10.5, fontweight="bold")
    ax.text(5.575, 0.52, "Targets 5 / 10 / 15 / 30 ms   ·   CUBIC TCP   ·   60 s per run",
            ha="center", va="center", fontsize=8.2, color="#444444")
    fig.tight_layout(pad=0.2)
    _save(fig, path)


def make_matrix_heatmap(cells, path: str) -> None:
    data = np.array([[choose_target(cells, s, c)[0] for c, _ in CASES] for s, _ in SCENARIOS])
    fig, ax = plt.subplots(figsize=(9.4, 3.8))
    cmap = matplotlib.colors.ListedColormap(["#1A1A1A", "#8C8C8C", "#F2F2F2"])
    ax.imshow(data, cmap=cmap, vmin=4, vmax=16, aspect="auto")
    ax.set_xticks(range(len(CASES)))
    ax.set_xticklabels([CASE_SHORT[c] for c, _ in CASES], fontsize=8.5)
    ax.set_yticks(range(len(SCENARIOS)))
    ax.set_yticklabels([label for _, label in SCENARIOS], fontsize=8.5)
    ax.set_xticks(np.arange(-0.5, len(CASES), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(SCENARIOS), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.6)
    ax.tick_params(which="minor", length=0)
    for i in range(len(SCENARIOS)):
        for j in range(len(CASES)):
            value = int(data[i, j])
            color = "white" if value == 10 else "#111111"
            ax.text(j, i, str(value), ha="center", va="center",
                    fontsize=9, fontweight="bold", color=color)
    ax.set_title("Recommended target (ms)", fontsize=10.5, fontweight="bold", pad=10)
    legend = [
        Patch(facecolor="#F2F2F2", edgecolor="#C9C9C9", label="15 ms"),
        Patch(facecolor="#8C8C8C", edgecolor="#8C8C8C", label="10 ms"),
    ]
    ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.10),
              ncol=2, frameon=False, fontsize=8.5)
    fig.tight_layout()
    _save(fig, path)


def make_target_effect(cells, path: str) -> None:
    metrics = [
        ("link_utilization_pct", "Utilization (%)", "Utilization"),
        ("packet_loss_pct", "Packet loss (%)", "Packet loss"),
        ("fairness_jain", "Jain fairness", "Fairness"),
        ("queue_delay_ms", "Queue delay (ms)", "Queue delay"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(9.4, 5.6))
    for ax, (key, ylabel, title) in zip(axes.flat, metrics):
        meds, lows, highs = [], [], []
        for t in TARGETS:
            vals = [float(cells[(s, c, t)][key]) for s, _ in SCENARIOS for c, _ in CASES]
            meds.append(statistics.median(vals))
            lows.append(np.percentile(vals, 25))
            highs.append(np.percentile(vals, 75))
        ax.fill_between(TARGETS, lows, highs, color="#D9D9D9", alpha=0.7, linewidth=0)
        ax.plot(TARGETS, meds, color="#111111", marker="o", markersize=4, linewidth=1.4)
        ax.axvline(15, color="#888888", linestyle="--", linewidth=0.8)
        ax.set_xticks(TARGETS)
        ax.set_xlabel("Target (ms)")
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=9.5, fontweight="bold", loc="left")
        ax.text(15.6, ax.get_ylim()[0] + 0.04 * (ax.get_ylim()[1] - ax.get_ylim()[0]),
                "default", fontsize=7, color="#666666")
        ax.grid(axis="y", color="#E6E6E6", linewidth=0.6)
    fig.suptitle("Median across all 40 cells (band: interquartile range)",
                 fontsize=10, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    _save(fig, path)


def make_queue_heatmap(cells, path: str) -> None:
    data = np.array([
        [float(cells[(s, c, 15)]["queue_delay_ms"]) for c, _ in CASES]
        for s, _ in SCENARIOS
    ])
    fig, ax = plt.subplots(figsize=(9.4, 3.6))
    im = ax.imshow(data, cmap="Greys", vmin=0, vmax=14, aspect="auto")
    ax.set_xticks(range(len(CASES)))
    ax.set_xticklabels([CASE_SHORT[c] for c, _ in CASES], fontsize=8.5)
    ax.set_yticks(range(len(SCENARIOS)))
    ax.set_yticklabels([label for _, label in SCENARIOS], fontsize=8.5)
    ax.set_xticks(np.arange(-0.5, len(CASES), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(SCENARIOS), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.6)
    ax.tick_params(which="minor", length=0)
    for i in range(len(SCENARIOS)):
        for j in range(len(CASES)):
            value = float(data[i, j])
            ax.text(j, i, f"{value:.1f}", ha="center", va="center", fontsize=8,
                    fontweight="bold", color="white" if value >= 8 else "#111111")
    ax.set_title("Queue delay at the 15 ms reference (ms)", fontsize=10.5,
                 fontweight="bold", pad=10)
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cbar.ax.tick_params(labelsize=7)
    cbar.set_label("ms", fontsize=7)
    fig.tight_layout()
    _save(fig, path)


def make_scenario_dotplot(cells, scenario: str, path: str) -> None:
    fig, ax = plt.subplots(figsize=(9.4, 4.6))
    ypos = np.arange(len(CASES))
    styles = {
        5: dict(marker="o", facecolors="white", edgecolors="#777777", s=32),
        10: dict(marker="s", facecolors="#9A9A9A", edgecolors="#666666", s=30),
        15: dict(marker="D", facecolors="#111111", edgecolors="#111111", s=32),
        30: dict(marker="^", facecolors="white", edgecolors="#BBBBBB", s=38),
    }
    for y, (case, _) in zip(ypos, CASES):
        xs = [float(cells[(scenario, case, t)]["queue_delay_ms"]) for t in TARGETS]
        ax.plot([min(xs), max(xs)], [y, y], color="#E0E0E0", linewidth=3.2,
                solid_capstyle="round", zorder=1)
        for t in TARGETS:
            ax.scatter(float(cells[(scenario, case, t)]["queue_delay_ms"]), y,
                       zorder=3, **styles[t])
        chosen, _ = choose_target(cells, scenario, case)
        if chosen != 15:
            ax.text(max(xs) * 1.10, y, f"-> {chosen} ms", va="center", fontsize=7.5,
                    color="#111111", fontweight="bold")

    labels = []
    for case, _ in CASES:
        chosen, _ = choose_target(cells, scenario, case)
        labels.append(CASE_SHORT[case])
    ax.set_yticks(ypos)
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.invert_yaxis()
    ax.axvline(10, color="#999999", linestyle="--", linewidth=0.8)
    ax.set_xscale("log")
    ax.set_xticks([1, 1.5, 2, 3, 5, 7, 10, 15, 20, 30])
    ax.set_xticklabels(["1", "1.5", "2", "3", "5", "7", "10", "15", "20", "30"])
    ax.minorticks_off()
    ax.set_xlabel("Queue delay (ms, log scale)")
    ax.set_title(f"{dict(SCENARIOS)[scenario]}: queue delay by target",
                 fontsize=10.5, fontweight="bold", loc="left")
    ax.grid(axis="x", color="#E8E8E8", linewidth=0.6)
    ax.set_xlim(1.0, max(
        float(cells[(scenario, c, t)]["queue_delay_ms"])
        for c, _ in CASES for t in TARGETS
    ) * 1.45)
    handles = [
        Line2D([0], [0], marker=styles[t]["marker"], linestyle="None",
               markerfacecolor=styles[t]["facecolors"],
               markeredgecolor=styles[t]["edgecolors"], markersize=6, label=f"{t} ms")
        for t in TARGETS
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.13),
              ncol=4, frameon=False, fontsize=7.8)
    fig.tight_layout()
    _save(fig, path)


def make_gain_bars(cells, path: str) -> None:
    rows = []
    for s, slabel in SCENARIOS:
        for c, _ in CASES:
            chosen, gain = choose_target(cells, s, c)
            rows.append((max(gain, 0.0), s, c, chosen))
    rows.sort(key=lambda r: r[0])
    fig, ax = plt.subplots(figsize=(9.4, 4.0))
    ys = np.arange(len(rows))
    colors = ["#111111" if r[0] >= 0.015 else "#D9D9D9" for r in rows]
    ax.barh(ys, [r[0] for r in rows], color=colors, edgecolor="none", height=0.78)
    ax.axvline(0.015, color="#555555", linestyle="--", linewidth=1.0)
    ax.text(0.0152, 1.5, "0.015 margin", fontsize=7.2, color="#333333")
    ax.set_yticks([])
    ax.set_xlabel("Score gain over 15 ms")
    ax.set_title("Only three cells clear the materiality margin", fontsize=10.5,
                 fontweight="bold", loc="left")
    for k, (gain, s, c, chosen) in enumerate(rows[::-1][:3]):
        y = len(rows) - 1 - k * 2.4
        ax.text(0.0203, y, f"{dict(SCENARIOS)[s].split()[0]} / {CASE_SHORT[c]} -> {chosen} ms",
                va="center", fontsize=7.6)
    ax.grid(axis="x", color="#E8E8E8", linewidth=0.6)
    ax.set_xlim(0, 0.030)
    fig.tight_layout()
    _save(fig, path)


# ---------------------------------------------------------------------------
# Word helpers
# ---------------------------------------------------------------------------
def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def set_cell_margins(cell, top=40, bottom=40, left=70, right=70) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for tag, value in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        node = OxmlElement(f"w:{tag}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tc_pr.append(mar)


def set_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = OxmlElement(f"w:{edge}")
        if edge == "insideV":
            node.set(qn("w:val"), "nil")
        else:
            node.set(qn("w:val"), "single")
            node.set(qn("w:sz"), "4")
            node.set(qn("w:space"), "0")
            node.set(qn("w:color"), RULE)
        borders.append(node)
    tbl_pr.append(borders)


def set_repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def set_col_widths(table, widths: Sequence[float]) -> None:
    table.autofit = False
    table.allow_autofit = False
    tbl_pr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)
    for row in table.rows:
        for cell, width in zip(row.cells, widths):
            cell.width = Inches(width)


def add_page_number(paragraph) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)
    run.font.size = Pt(8)
    run.font.color.rgb = MUTED
    run.font.name = "Calibri"


def style_document(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)
    normal.font.color.rgb = BODY
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.12

    for name, size, color, before, after in (
        ("Heading 1", 17, INK, 14, 5),
        ("Heading 2", 12.5, INK2, 11, 3),
    ):
        style = doc.styles[name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    h1 = doc.styles["Heading 1"]
    p_pr = h1.element.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), RULE)
    p_bdr.append(bottom)
    p_pr.append(p_bdr)

    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(1.9)
        section.bottom_margin = Cm(1.9)
        section.left_margin = Cm(2.1)
        section.right_margin = Cm(2.1)


def add_header_footer(doc: Document) -> None:
    section = doc.sections[0]
    section.different_first_page_header_footer = True
    header = section.header
    p = header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run("FQ-PIE target sweep · visual report")
    run.font.name = "Calibri"
    run.font.size = Pt(8)
    run.font.color.rgb = MUTED
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_page_number(p)


def add_para(doc: Document, text: str, *, bold_lead: str | None = None,
             size: float | None = None, color: RGBColor | None = None,
             space_after: float | None = None, align=None):
    p = doc.add_paragraph()
    if bold_lead:
        r = p.add_run(bold_lead)
        r.bold = True
        if size:
            r.font.size = Pt(size)
        if color:
            r.font.color.rgb = color
    r = p.add_run(text)
    if size:
        r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    if align is not None:
        p.alignment = align
    return p


def add_bullet(doc: Document, lead: str, text: str) -> None:
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(lead)
    r.bold = True
    p.add_run(text)


def add_caption(doc: Document, text: str, *, before: float = 2, after: float = 8) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    r = p.add_run(text)
    r.italic = True
    r.font.size = Pt(8)
    r.font.color.rgb = MUTED


def add_table_caption(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.font.size = Pt(8)
    r.font.color.rgb = MUTED


def add_figure(doc: Document, path: str, caption: str, width: float = 6.45) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(path, width=Inches(width))
    add_caption(doc, caption)


def add_table(doc: Document, header: Sequence[str], rows: Sequence[Sequence[str]],
              widths: Sequence[float], *, align_right_from: int = 1,
              cell_size: float = 8.0, bold_rows: Sequence[int] = (),
              grey_cells: Dict[Tuple[int, int], str] | None = None):
    table = doc.add_table(rows=1, cols=len(header))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table)
    header_row = table.rows[0]
    set_repeat_header(header_row)
    for i, text in enumerate(header):
        cell = header_row.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if i >= align_right_from else WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(text)
        r.bold = True
        r.font.size = Pt(cell_size)
        r.font.name = "Calibri"
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        set_cell_shading(cell, HEADER_FILL)
        set_cell_margins(cell)
    for ridx, row in enumerate(rows):
        tr = table.add_row()
        for cidx, text in enumerate(row):
            cell = tr.cells[cidx]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if cidx >= align_right_from else WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(str(text))
            r.font.size = Pt(cell_size)
            r.font.name = "Calibri"
            r.font.color.rgb = BODY
            if ridx in bold_rows:
                r.bold = True
            set_cell_margins(cell)
            if ridx % 2 == 1:
                set_cell_shading(cell, ZEBRA)
            if grey_cells and (ridx, cidx) in grey_cells:
                set_cell_shading(cell, grey_cells[(ridx, cidx)])
    set_col_widths(table, widths)
    return table


def add_kpi_row(doc: Document, items: Sequence[Tuple[str, str]]) -> None:
    table = doc.add_table(rows=1, cols=len(items))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table)
    for i, (big, label) in enumerate(items):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        r = p.add_run(big)
        r.bold = True
        r.font.size = Pt(20)
        r.font.color.rgb = INK
        p2 = cell.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2.paragraph_format.space_after = Pt(6)
        r2 = p2.add_run(label)
        r2.font.size = Pt(8)
        r2.font.color.rgb = MUTED
        set_cell_shading(cell, "F2F2F2")
        set_cell_margins(cell, 80, 60, 70, 70)
    set_col_widths(table, [6.4 / len(items)] * len(items))


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------
def build() -> None:
    os.makedirs(ASSETS, exist_ok=True)
    cells = load_cells()

    topo = os.path.join(ASSETS, "report_topology.png")
    matrix_img = os.path.join(ASSETS, "report_matrix_heatmap.png")
    effect_img = os.path.join(ASSETS, "report_target_effect.png")
    qheat_img = os.path.join(ASSETS, "report_queue_heatmap.png")
    gain_img = os.path.join(ASSETS, "report_gain_bars.png")
    make_topology(topo)
    make_matrix_heatmap(cells, matrix_img)
    make_target_effect(cells, effect_img)
    make_queue_heatmap(cells, qheat_img)
    make_gain_bars(cells, gain_img)
    scenario_imgs = {}
    for scenario, _ in SCENARIOS:
        path = os.path.join(ASSETS, f"report_queue_{scenario}.png")
        make_scenario_dotplot(cells, scenario, path)
        scenario_imgs[scenario] = path

    doc = Document()
    style_document(doc)
    add_header_footer(doc)

    # Cover
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(110)
    r = p.add_run("FQ-PIE · NeST DUMBBELL EVALUATION")
    r.font.size = Pt(9)
    r.bold = True
    r.font.color.rgb = MUTED

    title = doc.add_paragraph()
    title.paragraph_format.space_before = Pt(8)
    title.paragraph_format.space_after = Pt(8)
    r = title.add_run("FQ-PIE Target Sweep\nScenario and Case Report")
    r.font.size = Pt(26)
    r.bold = True
    r.font.color.rgb = INK

    sub = doc.add_paragraph()
    r = sub.add_run("Five traffic scenarios · eight parameter cases · four targets")
    r.font.size = Pt(12)
    r.font.color.rgb = MUTED

    doc.add_paragraph()
    add_table(
        doc,
        ["Item", "Value"],
        [
            ["Dataset", "wirelesss_final — 640 archived runs, 160 aggregated rows"],
            ["Qdisc / TCP", "FQ-PIE / CUBIC"],
            ["Targets", "5, 10, 15, 30 ms"],
            ["Repetitions", "10-run protocol; 4 complete archived repeats per cell"],
            ["Window", "Last 50% of each 60 s trace"],
            ["Recommendation", "15 ms default; 10 ms for three UDP cells"],
        ],
        [1.5, 4.9],
        align_right_from=99,
        cell_size=9,
    )

    doc.add_page_break()

    # 1 At a glance
    doc.add_heading("1. At a glance", level=1)
    add_kpi_row(doc, [
        ("37 / 40", "cells stay at 15 ms"),
        ("3 / 40", "cells move to 10 ms"),
        ("10%", "weight on latency"),
    ])
    add_para(doc, "")
    add_figure(doc, matrix_img,
               "Figure 1. Recommended FQ-PIE target for every scenario × case cell.", width=6.4)
    add_bullet(doc, "15 ms is the default. ",
               "It is the Linux FQ-PIE default and keeps the queue near the 10 ms knee in most cells.")
    add_bullet(doc, "Only three cells move. ",
               "All are UDP-background cases where 10 ms lowers queue delay without a throughput penalty.")
    add_bullet(doc, "Latency moves; throughput does not. ",
               "Utilization, loss and Jain fairness stay close to flat from 5 to 30 ms.")

    doc.add_page_break()

    # 2 Setup
    doc.add_heading("2. Setup", level=1)
    add_para(doc, "A dumbbell topology with FQ-PIE on the bottleneck. Each case is crossed "
                  "with every traffic scenario and every target.")
    add_figure(doc, topo,
               "Figure 2. Dumbbell topology. Queueing and drops are measured only on the bottleneck.",
               width=6.3)

    doc.add_heading("2.1 Traffic scenarios", level=2)
    add_table(
        doc,
        ["Scenario", "Traffic pattern", "What it tests"],
        [[label, SCENARIO_INFO[key][0], SCENARIO_INFO[key][1]] for key, label in SCENARIOS],
        [1.15, 3.35, 1.85],
        align_right_from=99,
        cell_size=8.4,
    )

    doc.add_heading("2.2 Parameter cases", level=2)
    case_rows = []
    for case, _ in CASES:
        cap, flows, rtt, limit, tests = CASE_INFO[case]
        case_rows.append([case, cap, flows, rtt, limit, tests])
    add_table(
        doc,
        ["Case", "Capacity", "TCP flows", "RTT", "Queue limit", "Isolates"],
        case_rows,
        [0.95, 0.78, 0.66, 0.50, 0.78, 1.85],
        align_right_from=1,
        cell_size=8.2,
    )

    doc.add_heading("2.3 Protocol", level=2)
    add_bullet(doc, "Grid. ", "5 scenarios × 8 cases × 4 targets = 160 cells.")
    add_bullet(doc, "Repeats. ", "10-run protocol; the archive has 4 complete runs per cell.")
    add_bullet(doc, "Analysis. ", "60 s per run; steady state is the last 50% of the trace.")
    add_bullet(doc, "Cleaning. ", "Drop runs with utilization > 100.5% or Jain < 0.5; use the median of clean runs. Flag cells with fewer than two clean runs.")
    add_bullet(doc, "Score. ", "40% utilization, 30% Jain, 20% loss, 10% latency. Keep 15 ms unless another target gains at least 0.015.")
    add_para(doc, "L(q) = 1 if q ≤ 10 ms, otherwise max(0, 1 − (q − 10)/20).",
             size=8.5, color=MUTED)

    doc.add_page_break()

    # 3 Results
    doc.add_heading("3. Results by scenario", level=1)
    add_para(doc, "Each panel shows queue delay at all four targets. The table reports the "
                  "15 ms reference and the recommended target.")

    for idx, (scenario, label) in enumerate(SCENARIOS, start=1):
        if idx > 1:
            doc.add_page_break()
        doc.add_heading(f"3.{idx} {label}", level=2)
        add_para(doc, SCENARIO_INFO[scenario][0], size=9, color=MUTED)
        add_figure(doc, scenario_imgs[scenario],
                   f"Figure {idx + 2}. {label}: queue delay by target.", width=6.4)

        rows = []
        grey = {}
        for ridx, (case, _) in enumerate(CASES):
            chosen, _ = choose_target(cells, scenario, case)
            c = cells[(scenario, case, 15)]
            rows.append([
                case,
                f"{chosen}",
                f"{float(c['link_utilization_pct']):.1f}",
                f"{float(c['packet_loss_pct']):.2f}",
                f"{float(c['fairness_jain']):.4f}",
                f"{float(c['queue_delay_ms']):.2f}",
            ])
            if chosen != 15:
                grey[(ridx, 1)] = LIGHT
        add_table_caption(doc, f"Table {idx}. {label}: metrics at the 15 ms reference.")
        add_table(
            doc,
            ["Case", "Target", "Util. %", "Loss %", "Jain", "Queue ms"],
            rows,
            [1.55, 0.65, 0.82, 0.72, 0.85, 0.85],
            align_right_from=1,
            cell_size=8.2,
            grey_cells=grey,
        )

        moved = [f"{case} → {choose_target(cells, scenario, case)[0]} ms"
                 for case, _ in CASES if choose_target(cells, scenario, case)[0] != 15]
        flagged = [case for case, _ in CASES if cells[(scenario, case, 15)]["flagged"]]
        add_bullet(doc, "Verdict. ",
                   ("All eight cases stay at 15 ms." if not moved
                    else "Move " + ", ".join(moved) + "."))
        if flagged:
            add_bullet(doc, "Flag. ",
                       ", ".join(flagged) + " has fewer than two clean runs at 15 ms; "
                       "the 15 ms row uses all four runs.")

    # 4 Synthesis
    doc.add_page_break()
    doc.add_heading("4. What changes with the target", level=1)
    add_figure(doc, effect_img,
               "Figure 8. Median across all 40 cells; the band is the interquartile range. "
               "Only queue delay responds to the target.", width=6.4)
    add_para(doc, "Throughput, loss and fairness are effectively flat. Queue delay rises with "
                  "the target in every scenario.", space_after=4)

    add_figure(doc, qheat_img,
               "Figure 9. Queue delay at 15 ms. Darker cells hold a larger standing queue.",
               width=6.2)

    doc.add_heading("4.1 Why only three cells move", level=2)
    add_figure(doc, gain_img,
               "Figure 10. Score gain over 15 ms. Only the three UDP-background cells clear the 0.015 margin.",
               width=6.2)
    add_para(doc, "With latency at 10% of the score, a cell moves only when lower delay is "
                  "large enough to outweigh the small weight. That happens in three UDP cases.",
             space_after=4)

    doc.add_heading("4.2 Data-quality flags", level=2)
    flag_rows = []
    for scenario, label in SCENARIOS:
        for case, _ in CASES:
            for target in TARGETS:
                c = cells[(scenario, case, target)]
                if c["max_util"] > 100.5:
                    flag_rows.append([
                        label, case, str(target),
                        f"{float(c['max_util']):.1f}",
                        f"{c['n_clean']}/{c['n_runs']}",
                        "All runs used" if c["flagged"] else "Clean median",
                    ])
    add_table_caption(doc, "Table 6. Cells with a run above 100.5% utilization.")
    add_table(
        doc,
        ["Scenario", "Case", "Target", "Max util. %", "Clean", "Treatment"],
        flag_rows,
        [1.25, 1.25, 0.62, 0.92, 0.68, 1.55],
        align_right_from=2,
        cell_size=7.8,
    )
    add_para(doc, "These are measurement artifacts, not extra capacity. Two cells have fewer "
                  "than two clean runs and are flagged.", size=8.5, color=MUTED)

    # 5 Conclusions
    doc.add_page_break()
    doc.add_heading("5. Conclusions", level=1)
    add_bullet(doc, "15 ms is the right default. ",
               "37 of 40 cells stay there; it is also the Linux FQ-PIE default.")
    add_bullet(doc, "Three UDP cells prefer 10 ms. ",
               "bw100mbit, bw10mbit and rtt120ms gain 0.0155–0.0176, just above the margin.")
    add_bullet(doc, "30 ms buys no throughput. ",
               "It roughly doubles queue delay with no consistent gain in utilization, loss or fairness.")
    add_bullet(doc, "5 ms is a fairness option, not a win. ",
               "It helps two shallow-queue cells on Jain, but no cell selects it under this weighting.")
    add_bullet(doc, "The target is a latency control. ",
               "Choose it for queue delay, not for capacity.")

    # Appendix
    doc.add_page_break()
    doc.add_heading("Appendix. Definitions and sources", level=1)
    add_table_caption(doc, "Table 7. Metric definitions.")
    add_table(
        doc,
        ["Metric", "Definition"],
        [
            ["Utilization", "Aggregate throughput / case capacity × 100."],
            ["Loss", "Qdisc drops / packets × 100."],
            ["Jain fairness", "(Σxᵢ)² / (n Σxᵢ²), across per-flow rates."],
            ["Queue delay", "(backlog − fair-queue batch) × 8 / capacity, in ms."],
            ["P95 queue", "95th percentile of the queue-delay series."],
        ],
        [1.2, 5.2],
        align_right_from=99,
        cell_size=8.4,
    )
    add_table_caption(doc, "Table 8. Source files.")
    add_table(
        doc,
        ["File", "Role"],
        [
            ["wirelesss_final/summary/results.csv", "160 aggregated rows"],
            ["wirelesss_final/<scenario>/<case>/target_<T>ms/run_*/metrics.json", "Per-run values"],
            ["scripts/fqpie_eval.py", "Sweep and metric definitions"],
            ["scripts/build_detailed_report.py", "Builder for this report"],
        ],
        [3.2, 3.2],
        align_right_from=99,
        cell_size=8.2,
    )
    add_para(doc, "Rebuild: nest/.venv/bin/python scripts/build_detailed_report.py",
             size=8.5, color=MUTED)

    doc.save(OUT_PATH)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    build()
