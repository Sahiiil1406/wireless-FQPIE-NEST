#!/usr/bin/env python3
"""Plot a loss-based retransmission-overhead proxy from the FQ-PIE sweep.

The archived sweep does not contain a TCP retransmission counter.  The closest
available signal is the bottleneck qdisc's cumulative ``drops`` and ``packets``
counters:

    overhead_proxy(t) = 100 * drops(t) / (packets(t) - drops(t))

That is "dropped packets per delivered packet", i.e. the extra traffic a
perfect retransmission repair would add.  It is deliberately labelled a proxy
in every output.

Outputs (under presentation/assets/):
  retransmission_overhead_vs_time.png
  retransmission_overhead_vs_target.png
  retransmission_overhead_summary.csv
"""

from __future__ import annotations

import csv
import glob
import os
import sys
from typing import Dict, Iterable, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "wirelesss_final")
OUT = os.path.join(ROOT, "presentation", "assets")

SCENARIOS = [
    ("synchronous", "Synchronous"),
    ("staggered", "Staggered"),
    ("rtt_fairness", "RTT fairness"),
    ("pulse_wave", "Pulse wave"),
    ("udp_background", "UDP background"),
]

CASES = [
    ("bandwidth", "bw100mbit", "bw100"),
    ("bandwidth", "bw10mbit", "bw10"),
    ("delay", "rtt60ms", "rtt60"),
    ("delay", "rtt120ms", "rtt120"),
    ("queue", "queue100pkt", "q100"),
    ("queue", "queue1000pkt", "q1000"),
    ("load", "load10flows", "load10"),
    ("load", "load100flows", "load100"),
]

TARGETS = [5, 10, 15, 30]
TARGET_COLORS = {
    5: "#0B6E69",
    10: "#D98E04",
    15: "#7B4FA0",
    30: "#B23A48",
}

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "axes.edgecolor": "#D8D3CA",
        "axes.linewidth": 0.8,
        "axes.facecolor": "#FFFFFF",
        "figure.facecolor": "#F7F5F1",
        "grid.color": "#E7E2D8",
        "grid.linewidth": 0.6,
        "legend.frameon": False,
        "xtick.color": "#55524C",
        "ytick.color": "#55524C",
        "text.color": "#1D1D1F",
    }
)


def _read_xy(path: str) -> np.ndarray:
    return np.loadtxt(path, ndmin=2)


def _run_dirs(scenario: str, category: str, case: str, target: int) -> List[str]:
    return sorted(
        glob.glob(
            os.path.join(DATA, scenario, category, case, f"target_{target}ms", "run_*")
        )
    )


def _cumulative_proxy(run_dir: str) -> Tuple[np.ndarray, np.ndarray]:
    drops = _read_xy(os.path.join(run_dir, "raw", "fq_pie_tc_drops.dat"))
    packets = _read_xy(os.path.join(run_dir, "raw", "fq_pie_tc_packets.dat"))
    n = min(len(drops), len(packets))
    t = drops[:n, 0]
    d = drops[:n, 1]
    p = packets[:n, 1]
    delivered = np.maximum(p - d, 1.0)
    return t, 100.0 * d / delivered


def _steady_proxy(run_dir: str) -> Tuple[float, float]:
    """Mean cumulative overhead over the last 50% of the 60 s analysis window.

    This mirrors the sweep pipeline: the reported packet-loss curve is the
    cumulative ratio ``drops / packets`` from the start of the trace, and the
    steady state is the mean of the last 50% of that curve.  Using increments
    over the same window would report a different (lower) number because the
    loss ratio keeps falling as the flows settle.
    """
    drops = _read_xy(os.path.join(run_dir, "raw", "fq_pie_tc_drops.dat"))
    packets = _read_xy(os.path.join(run_dir, "raw", "fq_pie_tc_packets.dat"))
    n = min(len(drops), len(packets))
    t = drops[:n, 0]
    d = drops[:n, 1]
    p = packets[:n, 1]
    mask = (t >= 30.0) & (t <= 60.0)
    if not np.any(mask):
        mask = t >= 0.5 * min(t[-1], 60.0)
    d = d[mask]
    p = p[mask]
    delivered = np.maximum(p - d, 1.0)
    return float(np.mean(100.0 * d / delivered)), float(np.mean(100.0 * d / np.maximum(p, 1.0)))


def _mean_time_series(run_dirs: Iterable[str]) -> Tuple[np.ndarray, np.ndarray]:
    series = [_cumulative_proxy(d) for d in run_dirs]
    if not series:
        return np.array([]), np.array([])
    t_max = min(60.0, min(float(t[-1]) for t, _ in series))
    grid = np.arange(1.0, t_max, 0.5)
    curves = []
    for t, y in series:
        mask = t <= 60.0
        curves.append(np.interp(grid, t[mask], y[mask]))
    return grid, np.mean(np.vstack(curves), axis=0)


def make_time_plot() -> None:
    fig, axes = plt.subplots(
        len(SCENARIOS), 1, figsize=(11, 10.5), sharex=True
    )
    fig.subplots_adjust(left=0.075, right=0.985, top=0.93, bottom=0.095, hspace=0.42)
    for ax, (scenario, label) in zip(axes, SCENARIOS):
        for target in TARGETS:
            dirs = _run_dirs(scenario, "bandwidth", "bw100mbit", target)
            t, y = _mean_time_series(dirs)
            if len(t):
                ax.plot(
                    t,
                    y,
                    color=TARGET_COLORS[target],
                    lw=1.8,
                    label=f"{target} ms",
                )
        ax.set_title(f"{label}  ·  bw100mbit", loc="left", fontweight="bold")
        ax.set_ylabel("Overhead proxy (%)")
        ax.grid(True, axis="y")
        ax.set_ylim(bottom=0)
        ax.set_xlim(0, 60)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[-1].set_xlabel("Time (s)")
    axes[0].legend(ncol=4, loc="upper right")
    fig.suptitle(
        "Loss-based retransmission overhead proxy over time",
        x=0.01,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.075,
        0.012,
        "Proxy = cumulative drops / (packets − drops), averaged across the 4 runs per target. "
        "This is not a TCP retransmission count.",
        fontsize=8,
        color="#6E6E73",
    )
    path = os.path.join(OUT, "retransmission_overhead_vs_time.png")
    fig.savefig(path, dpi=190, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"wrote {path}")


def make_target_plot(summary: Dict[Tuple[str, str, int], Tuple[float, float]]) -> None:
    fig, axes = plt.subplots(
        len(SCENARIOS), 1, figsize=(11, 11.5), sharex=True
    )
    fig.subplots_adjust(left=0.075, right=0.985, top=0.93, bottom=0.085, hspace=0.42)
    x = np.arange(len(CASES))
    width = 0.2
    for ax, (scenario, label) in zip(axes, SCENARIOS):
        for i, target in enumerate(TARGETS):
            means = []
            errs = []
            for _, case, _ in CASES:
                vals = [
                    summary.get((scenario, case, target), (np.nan, np.nan))
                    for _ in [0]
                ]
                mean, std = vals[0]
                means.append(mean)
                errs.append(std)
            ax.bar(
                x + (i - 1.5) * width,
                means,
                width,
                yerr=errs,
                capsize=2,
                color=TARGET_COLORS[target],
                edgecolor="white",
                linewidth=0.5,
                label=f"{target} ms",
                error_kw={"elinewidth": 0.7, "ecolor": "#777777"},
            )
        ax.set_title(f"{label}", loc="left", fontweight="bold")
        ax.set_ylabel("Steady-state proxy (%)")
        ax.grid(True, axis="y")
        ax.set_ylim(bottom=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels([label for _, _, label in CASES], rotation=0)
    axes[-1].set_xlabel("Parameter case")
    axes[0].legend(ncol=4, loc="upper right")
    fig.suptitle(
        "Steady-state retransmission overhead proxy vs target",
        x=0.01,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.075,
        0.012,
        "Bars are the mean of the 4 runs; whiskers are one standard deviation. "
        "Overhead proxy = mean drops / (packets − drops) over the last 50% of the 60 s trace.",
        fontsize=8,
        color="#6E6E73",
    )
    path = os.path.join(OUT, "retransmission_overhead_vs_target.png")
    fig.savefig(path, dpi=190, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"wrote {path}")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    rows = []
    summary: Dict[Tuple[str, str, int], Tuple[float, float]] = {}
    for scenario, _ in SCENARIOS:
        for category, case, _ in CASES:
            for target in TARGETS:
                dirs = _run_dirs(scenario, category, case, target)
                vals = [_steady_proxy(d) for d in dirs]
                if not vals:
                    continue
                arr = np.array(vals)
                mean = float(np.mean(arr[:, 0]))
                std = float(np.std(arr[:, 0], ddof=1)) if len(arr) > 1 else 0.0
                loss_mean = float(np.mean(arr[:, 1]))
                summary[(scenario, case, target)] = (mean, std)
                rows.append(
                    {
                        "scenario": scenario,
                        "category": category,
                        "case": case,
                        "target_ms": target,
                        "n_runs": len(vals),
                        "overhead_proxy_pct_mean": f"{mean:.4f}",
                        "overhead_proxy_pct_std": f"{std:.4f}",
                        "packet_loss_pct_mean": f"{loss_mean:.4f}",
                    }
                )

    csv_path = os.path.join(OUT, "retransmission_overhead_summary.csv")
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {csv_path}")

    make_time_plot()
    make_target_plot(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
