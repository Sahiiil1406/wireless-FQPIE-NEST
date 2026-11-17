#!/usr/bin/env python3
"""
plot_compare.py - Easy-to-compare plots across FQ-PIE target values.

Why the old plots were unreadable:
  * raw 0.2s samples from 100 flows = thousands of spike segments
    (the pink "fill" is not data, it's spike density)
  * a startup transient (slow-start burst) crushed the steady-state y-scale
  * a dead zero-tail after t=100s wasted half the x-axis
  * packet_loss was plotted as a cumulative-counter ratio (decay curve),
    hiding the steady-state loss rate

What this does instead (reads sahil_final/fq_pie_*_target_*ms.dat):
  * bins every series to 1-second means -> smooth lines, one per target
  * restricts time plots to the steady window [t0, t1] = [10, 100]s
  * packet loss is recomputed as an INSTANTANEOUS rate:
    loss = d(drops)/d(packets) per 1s bin (counters are cumulative)
  * adds one BAR CHART per metric (steady-state mean per target, labeled):
    the fastest way to compare 7 targets
  * writes a summary CSV with the same numbers

Output: <finals>/compare/*.png + summary.csv

Usage:
  nest/.venv/bin/python scripts/plot_compare.py
  nest/.venv/bin/python scripts/plot_compare.py --finals-dir sahil_final --capacity 100
  nest/.venv/bin/python scripts/plot_compare.py --targets "1 5 15" --t0 20 --t1 100 --bin 2.0
"""
import argparse
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

SUFFIX_RE = re.compile(r"^(?P<base>fq_pie_.+?)_target_(?P<t>\d+)ms\.dat$")
TITLES = {
    "throughput": "Per-flow Throughput (Mbps)",
    "queue_delay": "Queue Delay (ms)",
    "packet_loss": "Packet Loss Rate (%)",
    "fairness": "Fairness (Jain Index)",
    "link_utilization": "Aggregate Link Utilization (%)",
}
KEYS = ["throughput", "queue_delay", "packet_loss", "fairness", "link_utilization"]


def find_finals(arg):
    if arg:
        p = Path(arg)
        if p.exists():
            return p
    proj = Path(__file__).resolve().parent.parent
    for c in [proj / "sahil_final", proj / "finals", Path("sahil_final")]:
        if c.exists():
            return c
    return proj / "sahil_final"


def read_series(path):
    xs, ys = [], []
    try:
        with open(path) as fin:
            for line in fin:
                p = line.split()
                if len(p) < 2:
                    continue
                try:
                    xs.append(float(p[0]))
                    ys.append(float(p[1]))
                except ValueError:
                    continue
    except OSError as e:
        print(f"WARN read {path}: {e}", file=sys.stderr)
    return xs, ys


def collect(finals):
    per_target = defaultdict(dict)
    for f in finals.glob("fq_pie_*_target_*ms.dat"):
        m = SUFFIX_RE.match(f.name)
        if not m:
            continue
        per_target[int(m.group("t"))][m.group("base")[len("fq_pie_"):]] = f
    for sub in finals.glob("target_*ms"):
        mt = re.search(r"(\d+)ms", sub.name)
        if not mt or not sub.is_dir():
            continue
        t = int(mt.group(1))
        for f in sub.glob("fq_pie_*.dat"):
            m = SUFFIX_RE.match(f.name)
            metric = m.group("base")[len("fq_pie_"):] if m else f.name[len("fq_pie_"):-4]
            per_target[t].setdefault(metric, f)
    return dict(sorted(per_target.items()))


def bin_last(xs, ys, t0, t1, width):
    """Last value of y in each bin (for cumulative counters)."""
    if not xs or width <= 0:
        return [], []
    nb = max(1, int(math.ceil((t1 - t0) / width)))
    last = [None] * nb
    for x, y in zip(xs, ys):
        if x < t0 or x > t1:
            continue
        k = min(nb - 1, int((x - t0) / width))
        last[k] = y
    bx = [t0 + (i + 0.5) * width for i in range(nb) if last[i] is not None]
    by = [last[i] for i in range(nb) if last[i] is not None]
    return bx, by


def bin_sum(xs, ys, t0, t1, width):
    """Sum of y in each [t0+k*width, t0+(k+1)*width) bin inside [t0, t1]."""
    if not xs or width <= 0:
        return [], []
    nb = max(1, int(math.ceil((t1 - t0) / width)))
    sums = [0.0] * nb
    cnts = [0] * nb
    for x, y in zip(xs, ys):
        if x < t0 or x > t1:
            continue
        k = min(nb - 1, int((x - t0) / width))
        sums[k] += y
        cnts[k] += 1
    bx = [t0 + (i + 0.5) * width for i in range(nb) if cnts[i]]
    by = [sums[i] for i in range(nb) if cnts[i]]
    return bx, by


def window_sorted(xs, ys, t0, t1):
    """Every raw sample inside [t0, t1], sorted by time.

    Raw .dat files interleave samples flow-by-flow (each with its own
    clock), so file order is NOT time order -- sorting is required,
    otherwise the line zigzags back and forth in time.
    """
    pts = sorted(
        ((x, y) for x, y in zip(xs, ys) if t0 <= x <= t1),
        key=lambda p: p[0],
    )
    if not pts:
        return [], []
    return [p[0] for p in pts], [p[1] for p in pts]


def window_counter_ratio(dxs, dys, pxs, pys, t0, t1):
    """Overall loss over the window from cumulative counters:
    (drops_last - drops_first) / (packets_last - packets_first)."""
    dp = sorted(((x, y) for x, y in zip(dxs, dys) if t0 <= x <= t1), key=lambda p: p[0])
    pp = sorted(((x, y) for x, y in zip(pxs, pys) if t0 <= x <= t1), key=lambda p: p[0])
    if len(dp) < 2 or len(pp) < 2:
        return float("nan")
    dd = dp[-1][1] - dp[0][1]
    pk = pp[-1][1] - pp[0][1]
    if pk <= 0 or dd < 0:
        return float("nan")
    return max(0.0, min(100.0, dd / pk * 100.0))


def derive(per_target, cap_mbit, n_flows, t0, t1, loss_bin):
    """Return ({target: {metric: (xs, ys)}}, {target: {metric: bar_value}}).

    Trend series use EVERY raw sample in the window, time-sorted (no
    coarse binning, nothing thrown away). Only packet loss needs binning:
    counters are cumulative, so per-sample diffs are meaningless; the
    trend is the instantaneous rate d(drops)/d(packets) per `loss_bin`
    seconds, and the bar is the exact overall ratio over the window.
    """
    series, bars = {}, {}
    for t, files in per_target.items():
        get = files.get
        d, b = {}, {}
        thr = None
        for k in ("throughput", "netperf_receiver"):
            if get(k) and get(k).exists():
                thr = window_sorted(*read_series(get(k)), t0, t1)
                break
        if thr and thr[0]:
            d["throughput"] = thr
            b["throughput"] = sum(thr[1]) / len(thr[1])
            # AGGREGATE link utilization: at any second, ~1 sample per flow
            # sits in each 1s bin, so the bin SUM over flows ~= link total.
            # (Scaling a single flow's sample x100 would be bogus.)
            fsrc = next(f for f in (get("throughput"), get("netperf_receiver")) if f and f.exists())
            fxs, fys = read_series(fsrc)
            bxs, bys = bin_sum(fxs, fys, t0, t1, 1.0)
            lus = [s / cap_mbit * 100.0 if cap_mbit > 0 else 0.0 for s in bys]
            if bxs:
                d["link_utilization"] = (bxs, lus)
                b["link_utilization"] = sum(lus) / len(lus)
        qd = None
        if get("queue_delay") and get("queue_delay").exists():
            qd = window_sorted(*read_series(get("queue_delay")), t0, t1)
        elif get("qdelay") and get("qdelay").exists():
            qd = window_sorted(*read_series(get("qdelay")), t0, t1)
        elif get("backlog") and get("backlog").exists():
            xs, ys = read_series(get("backlog"))
            cap_bps = cap_mbit * 1e6
            qd = window_sorted(
                xs, [bval * 8 / cap_bps * 1000.0 if cap_bps > 0 else 0.0 for bval in ys], t0, t1
            )
        elif get("ldelay") and get("ldelay").exists():
            qd = window_sorted(*read_series(get("ldelay")), t0, t1)
        if qd and qd[0]:
            d["queue_delay"] = qd
            b["queue_delay"] = sum(qd[1]) / len(qd[1])
        if get("drops") and get("packets") and get("drops").exists() and get("packets").exists():
            dxs, dys = read_series(get("drops"))
            pxs, pys = read_series(get("packets"))
            bxd, byd = bin_last(dxs, dys, t0, t1, loss_bin)
            bxp, byp = bin_last(pxs, pys, t0, t1, loss_bin)
            n = min(len(byd), len(byp))
            lx, ly = [], []
            for i in range(1, n):
                dd, dp = byd[i] - byd[i - 1], byp[i] - byp[i - 1]
                if dp > 0 and dd >= 0:
                    lx.append(bxd[i])
                    ly.append(max(0.0, min(100.0, dd / dp * 100.0)))
            if lx:
                d["packet_loss"] = (lx, ly)
            r = window_counter_ratio(dxs, dys, pxs, pys, t0, t1)
            if r == r:
                b["packet_loss"] = r
        if "packet_loss" not in d and get("packet_loss") and get("packet_loss").exists():
            pl = window_sorted(*read_series(get("packet_loss")), t0, t1)
            if pl[0]:
                d["packet_loss"] = pl
                b["packet_loss"] = sum(pl[1]) / len(pl[1])
        fr = None
        if get("fairness") and get("fairness").exists():
            fr = window_sorted(*read_series(get("fairness")), t0, t1)
        elif get("jain") and get("jain").exists():
            fr = window_sorted(*read_series(get("jain")), t0, t1)
        if fr and fr[0]:
            d["fairness"] = fr
            b["fairness"] = sum(fr[1]) / len(fr[1])
        series[t] = d
        bars[t] = b
    return series, bars


def main():
    ap = argparse.ArgumentParser(description="Clear comparison plots across FQ-PIE targets")
    ap.add_argument("--finals-dir", default=None)
    ap.add_argument("--capacity", type=float, default=100.0)
    ap.add_argument("--targets", default=None, help='e.g. "1 5 15"')
    ap.add_argument("--t0", type=float, default=10.0, help="steady window start (s)")
    ap.add_argument("--t1", type=float, default=100.0, help="steady window end (s)")
    ap.add_argument("--bin", type=float, default=1.0,
                    help="bin width (s) for the packet-loss-rate trend only; "
                         "all other trends plot every raw sample")
    ap.add_argument("--flows", type=float, default=100.0,
                    help="number of TCP flows (link utilization = per-flow mean x flows / capacity)")
    ap.add_argument("--out-subdir", default="compare")
    args = ap.parse_args()

    finals = find_finals(args.finals_dir)
    if not finals.exists():
        print(f"ERROR: {finals} not found", file=sys.stderr)
        sys.exit(1)
    per_target = collect(finals)
    if args.targets:
        want = {int(x) for x in args.targets.split()}
        per_target = {t: v for t, v in per_target.items() if t in want}
    if not per_target:
        print(f"ERROR: no fq_pie_*_target_*ms.dat in {finals}", file=sys.stderr)
        sys.exit(1)

    all_series, all_bars = derive(per_target, args.capacity, args.flows, args.t0, args.t1, args.bin)
    targets = sorted(all_series)
    npts = {k: sum(len(all_series[t].get(k, ([], []))[0]) for t in targets) for k in KEYS}
    print(f"Targets: {targets}  window=[{args.t0},{args.t1}]s")
    print("Trend points per metric: " + ", ".join(f"{k}={npts[k]}" for k in KEYS))

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"matplotlib missing: {e} (use nest/.venv/bin/python)", file=sys.stderr)
        sys.exit(1)

    out_dir = finals / args.out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    colors = plt.get_cmap("tab10").colors

    summary = {}
    # Throughput/fairness samples jump sample-to-sample, so connecting
    # them paints fake vertical bands: markers only (every point, zero
    # interpolation). Link utilization is already true 1s aggregates and
    # queue delay / loss rate are smooth, so thin lines stay faithful.
    SCATTER_KEYS = {"throughput", "fairness"}
    for key in KEYS:
        # ---- 1. trend overlay: EVERY raw sample, time-sorted ----
        plt.figure(figsize=(12, 5))
        ax = plt.gca()
        any_curve = False
        for i, t in enumerate(targets):
            s = all_series[t].get(key)
            if not s or not s[0]:
                continue
            if key in SCATTER_KEYS:
                ax.plot(s[0], s[1], linestyle="none", marker=".", markersize=2,
                        alpha=0.45, color=colors[i % 10], label=f"target {t} ms ({len(s[0])} pts)")
            else:
                # loss trend is per-second rates, queue delay is smooth:
                # thin connecting lines are faithful here
                ax.plot(s[0], s[1], linewidth=1.2, alpha=0.9,
                        color=colors[i % 10], label=f"target {t} ms ({len(s[0])} pts)")
            any_curve = True
        if not any_curve:
            print(f"Skip {key}: no data")
            plt.close()
            continue
        ax.set_xlabel("Time (s)")
        ax.set_ylabel(TITLES[key])
        ax.set_title(
            f"FQ-PIE {TITLES[key]} by target — all samples, steady state {args.t0:.0f}-{args.t1:.0f}s, "
            f"{args.flows:.0f} flows"
        )
        ax.set_xlim(args.t0, args.t1)
        if key == "fairness":
            ax.set_ylim(0.9, 1.0)
        if key == "link_utilization":
            ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=10, title="target")
        plt.tight_layout()
        plt.savefig(out_dir / f"{key}_trend.png", dpi=150)
        plt.close()

        # ---- 2. bar chart of steady-state means ----
        # (loss bar = exact overall counter ratio over the window)
        vals = [all_bars[t].get(key, float("nan")) for t in targets]
        summary[key] = vals
        plt.figure(figsize=(10, 4.5))
        ax = plt.gca()
        bars = ax.bar(
            [str(t) for t in targets],
            vals,
            color=[colors[i % 10] for i in range(len(targets))],
            edgecolor="black",
            width=0.6,
        )
        ax.set_xlabel("FQ-PIE target (ms)")
        ax.set_ylabel(f"Steady-state mean {TITLES[key]}")
        ax.set_title(f"FQ-PIE {TITLES[key]} vs target — mean over {args.t0:.0f}-{args.t1:.0f}s, "
                     f"{args.flows:.0f} flows")
        if key == "fairness":
            lo = min(v for v in vals if v == v)
            ax.set_ylim(max(0.0, lo - 0.02), 1.0)
        ax.grid(True, axis="y", alpha=0.3)
        for b, v in zip(bars, vals):
            if v == v:
                ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:.3g}",
                        ha="center", va="bottom", fontsize=10)
        plt.tight_layout()
        plt.savefig(out_dir / f"{key}_bars.png", dpi=150)
        plt.close()
        print(f"Saved {key}_trend.png + {key}_bars.png")

    # ---- 3. summary CSV ----
    csv_path = out_dir / "summary.csv"
    with open(csv_path, "w") as f:
        f.write("target_ms," + ",".join(KEYS) + "\n")
        for i, t in enumerate(targets):
            f.write(str(t) + "," + ",".join(
                f"{summary[k][i]:.6g}" if summary[k][i] == summary[k][i] else "n/a" for k in KEYS
            ) + "\n")
    print(f"\nWrote {csv_path}")
    print("target_ms " + " ".join(f"{k:>16}" for k in KEYS))
    for i, t in enumerate(targets):
        print(f"{t:>9} " + " ".join(
            f"{summary[k][i]:16.4f}" if summary[k][i] == summary[k][i] else f"{'n/a':>16}"
            for k in KEYS
        ))
    print(f"\nPlots in {out_dir}/")


if __name__ == "__main__":
    main()
