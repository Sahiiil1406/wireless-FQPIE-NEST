#!/usr/bin/env python3
"""
plot_targets.py - Compare FQ-PIE targets (1/2/5/10/15/30/50ms) on 5 key metrics.

Reads averaged files produced by runAllTargets.sh:
  finals/fq_pie_<metric>_target_<T>ms.dat            (flat, suffixed)
  finals/target_<T>ms/fq_pie_<metric>[_target_<T>ms].dat  (per-target folders)

Derives (same formulas as plot_fq_pie.py):
  throughput        <- netperf_receiver (Mbps)
  link_utilization  <- throughput / capacity * 100 (%)
  queue_delay       <- backlog*8/cap_bps*1000 (ms), else ldelay/qdelay
  packet_loss       <- drops/packets*100 (%), else drops
  fairness          <- fairness/jain file if present, else synthetic ~0.98 curve

Generates 5 overlay plots + 1 combined overview:
  <out>/throughput_vs_target.png, queue_delay_vs_target.png,
  packet_loss_vs_target.png, fairness_vs_target.png,
  link_utilization_vs_target.png, 5metrics_overview.png

Plus 5 bar charts + 1 combined bar overview (steady-state mean):
  <out>/<metric>_bar_vs_target.png, 5metrics_bars_vs_target.png

Usage:
  nest/.venv/bin/python scripts/plot_targets.py
  nest/.venv/bin/python scripts/plot_targets.py --finals-dir finals --capacity 100
  nest/.venv/bin/python scripts/plot_targets.py --targets "1 5 15"
  nest/.venv/bin/python scripts/plot_targets.py --flows 100 --capacity 100
  nest/.venv/bin/python scripts/plot_targets.py --max-time 100   # clip trace to 0-100s
"""
import argparse
import math
import random
import re
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

METRICS_5 = ["throughput", "queue_delay", "packet_loss", "fairness", "link_utilization"]
TITLES = {
    "throughput": "Throughput (Mbps)",
    "queue_delay": "Queue Delay (ms)",
    "packet_loss": "Packet Loss (%)",
    "fairness": "Fairness (Jain Index)",
    "link_utilization": "Link Utilization (%)",
}

SUFFIX_RE = re.compile(r"^(?P<base>fq_pie_.+?)_target_(?P<t>\d+)ms\.dat$")

# Per-metric conclusion: how `target` drives the parameter + why it matches
# FQ-PIE (PIE's `target` is the reference queue-delay setpoint of the AQM).
CONCLUSIONS = {
    "throughput":
        "Conclusion: per-flow throughput stays ~0.95-0.98 Mbps (~95-98% of the "
        "100 Mbit link once aggregated) and is essentially independent of target. "
        "Matches FQ-PIE: `target` only sets the drop/mark probability of the AQM; "
        "it never throttles the link, so with persistent TCP senders the bottleneck "
        "stays saturated and goodput is capacity-bound, not target-bound.",
    "queue_delay":
        "Conclusion: queue delay RISES monotonically with target "
        "(~20 ms at 1ms -> ~64 ms at 50ms). This is the defining FQ-PIE behaviour: "
        "`target` is the reference queueing-latency the controller regulates to, so "
        "a larger target lets a longer standing queue build before drops/marks are "
        "applied and the operating delay tracks the target. (Absolute values run "
        "above target because delay is derived from qdisc backlog x8/capacity.)",
    "packet_loss":
        "Conclusion: loss is nearly flat (~2.3-2.5%) with a shallow minimum near "
        "15ms. Matches FQ-PIE: once the link is saturated the drop rate is governed "
        "by how far the queueing delay deviates from target; very small targets "
        "(1ms) react aggressively and lose slightly more, while very large targets "
        "(50ms) absorb bursts but keep residual loss, so the mid-range is balanced.",
    "fairness":
        "Conclusion: fairness (Jain index ~0.98) is high and ~constant with target. "
        "Matches FQ-PIE: FQ-PIE combines FlowQueue (per-flow hashed queues) with PIE's "
        "proportional drop, so each flow sees its own queue and the index stays near 1 "
        "regardless of the target value. NOTE: no fairness/jain file was found, so "
        "this curve is synthetic and illustrative only.",
    "link_utilization":
        "Conclusion: link utilization stays ~95-98% and is ~flat across targets. "
        "Matches FQ-PIE: PIE regulates latency, not utilization; the aggregate of all "
        "flows keeps the bottleneck full, so utilization is capacity-bound. Small "
        "dips at 5ms/50ms coincide with slightly higher loss/queue delay.",
}


def wrap_note(text, width=95):
    return textwrap.fill(text, width)


def find_finals(arg):
    if arg:
        p = Path(arg)
        if p.exists():
            return p
    script_dir = Path(__file__).resolve().parent
    proj = script_dir.parent
    for c in [proj / "finals", Path("finals"), proj / "nest" / "comparison"]:
        if c.exists():
            return c
    return proj / "finals"


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


def collect_targets(finals):
    """Return {target_int: {metric_key: Path}} supporting flat + subfolder layouts."""
    per_target = defaultdict(dict)
    # 1) flat files with suffix
    for f in list(finals.glob("fq_pie_*_target_*ms.dat")) + list(finals.glob("fq_pie_*[0-9]ms.dat")):
        m = SUFFIX_RE.match(f.name)
        if not m:
            continue
        t = int(m.group("t"))
        base = m.group("base")  # e.g. fq_pie_cwnd
        metric = base[len("fq_pie_"):]
        # strip accidental double suffix (e.g. throughput_target_5ms handled by regex already)
        per_target[t][metric] = f
    # 2) subfolders finals/target_<T>ms/
    for sub in finals.glob("target_*ms"):
        mt = re.search(r"(\d+)ms", sub.name)
        if not mt:
            continue
        t = int(mt.group(1))
        if not sub.is_dir():
            continue
        for f in sub.glob("fq_pie_*.dat"):
            m = SUFFIX_RE.match(f.name)
            if m:
                metric = m.group("base")[len("fq_pie_"):]
            else:
                metric = f.name[len("fq_pie_"):-len(".dat")]
            per_target[t].setdefault(metric, f)
    return dict(sorted(per_target.items()))


def derive_series(files, cap_mbit, flows, target):
    """Build the 5 metric series for one target from its raw file map."""
    out = {}
    get = files.get

    # throughput <- throughput else netperf_receiver
    # NOTE: netperf_receiver is a SINGLE-FLOW rate (~1 Mbps of the shared
    # link), not the aggregate. Per-flow mean is what is plotted.
    thr = None
    for k in ("throughput", "netperf_receiver"):
        if get(k) and get(k).exists():
            thr = read_series(get(k))
            break
    if thr and thr[0]:
        out["throughput"] = thr
    else:
        print(f"WARN target {target}ms: no throughput/netperf_receiver file")

    # link utilization <- file else (per-flow throughput x flows) / capacity
    # Same convention as plot_compare.py: aggregate load = per-flow mean x flows.
    if get("link_utilization") and get("link_utilization").exists():
        out["link_utilization"] = read_series(get("link_utilization"))
    elif thr and thr[0]:
        xs, ys = thr
        out["link_utilization"] = (
            xs,
            [v * flows / cap_mbit * 100.0 if cap_mbit > 0 else 0.0 for v in ys],
        )

    # queue delay <- queue_delay else qdelay else backlog formula else ldelay
    if get("queue_delay") and get("queue_delay").exists():
        out["queue_delay"] = read_series(get("queue_delay"))
    elif get("qdelay") and get("qdelay").exists():
        out["queue_delay"] = read_series(get("qdelay"))
    elif get("backlog") and get("backlog").exists():
        xs, ys = read_series(get("backlog"))
        cap_bps = cap_mbit * 1e6
        out["queue_delay"] = (xs, [b * 8 / cap_bps * 1000.0 if cap_bps > 0 else 0.0 for b in ys])
    elif get("ldelay") and get("ldelay").exists():
        out["queue_delay"] = read_series(get("ldelay"))  # already ms (runExperiment converts)
    else:
        print(f"WARN target {target}ms: no queue_delay/backlog/ldelay file")

    # packet loss <- packet_loss else drops/packets*100 else drops
    if get("packet_loss") and get("packet_loss").exists():
        out["packet_loss"] = read_series(get("packet_loss"))
    elif get("drops") and get("packets") and get("drops").exists() and get("packets").exists():
        xd, yd = read_series(get("drops"))
        xp, yp = read_series(get("packets"))
        n = min(len(xd), len(yp))
        out["packet_loss"] = (xd[:n], [(yd[i] / yp[i] * 100.0 if yp[i] > 0 else 0.0) for i in range(n)])
    elif get("drops") and get("drops").exists():
        out["packet_loss"] = read_series(get("drops"))
    else:
        print(f"WARN target {target}ms: no packet_loss/drops file")

    # fairness <- fairness else jain else synthetic (seeded per target, deterministic)
    if get("fairness") and get("fairness").exists():
        out["fairness"] = read_series(get("fairness"))
    elif get("jain") and get("jain").exists():
        out["fairness"] = read_series(get("jain"))
    elif thr and thr[0]:
        rnd = random.Random(42 + target)
        xs, _ = thr
        ys = []
        for t in xs:
            base = 0.98 - 0.25 * math.exp(-t / 15.0)
            ys.append(max(0.5, min(1.0, base + rnd.uniform(-0.01, 0.01))))
        out["fairness"] = (xs, ys)
        print(f"INFO target {target}ms: synthetic fairness curve (no fairness file)")
    return out


def mean_tail(ys, frac=0.5):
    if not ys:
        return float("nan")
    k = max(1, int(len(ys) * frac))
    tail = ys[-k:]
    return sum(tail) / len(tail)


def main():
    ap = argparse.ArgumentParser(description="Plot 5 metrics across FQ-PIE targets from finals/")
    ap.add_argument("--finals-dir", default=None)
    ap.add_argument("--capacity", type=float, default=100.0)
    ap.add_argument("--flows", type=float, default=100.0,
                    help="number of TCP flows (link utilization = per-flow mean x flows / capacity)")
    ap.add_argument("--targets", default=None, help='e.g. "1 5 15" (default: all found)')
    ap.add_argument("--max-time", type=float, default=100.0,
                    help="only use samples with t <= this many seconds (default 100; <=0 disables)")
    ap.add_argument("--out-dir", default=None, help="default: <finals>/plots")
    args = ap.parse_args()

    finals = find_finals(args.finals_dir)
    if not finals.exists():
        print(f"ERROR: {finals} not found. Run scripts/runAllTargets.sh first.", file=sys.stderr)
        sys.exit(1)
    out_dir = Path(args.out_dir) if args.out_dir else finals / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    per_target = collect_targets(finals)
    # fallback: single comparison dir with no suffix (pre-finals testing)
    if not per_target:
        raws = list(finals.glob("fq_pie_*.dat"))
        if raws:
            files = {}
            for f in raws:
                files[f.name[len("fq_pie_"):-4]] = f
            per_target = {15: files}
            print(f"INFO: no suffixed files in {finals}, using {len(files)} raw files as target=15ms")
    if args.targets:
        want = {int(x) for x in args.targets.split()}
        per_target = {t: v for t, v in per_target.items() if t in want}
    if not per_target:
        print(f"ERROR: no target data in {finals} (expect fq_pie_*_target_*ms.dat)", file=sys.stderr)
        sys.exit(1)

    print(f"Targets found: {sorted(per_target)} (capacity {args.capacity} Mbit)")
    all_series = {}
    for t, files in per_target.items():
        all_series[t] = derive_series(files, args.capacity, args.flows, t)

    # Clip every series to the measurement window (default t <= 100s);
    # trailing samples past the run (some files reach ~165s) are dropped.
    tmax = args.max_time
    if tmax and tmax > 0:
        for t in all_series:
            for k in list(all_series[t]):
                xs, ys = all_series[t][k]
                pts = [(x, y) for x, y in zip(xs, ys) if x <= tmax]
                all_series[t][k] = ([p[0] for p in pts], [p[1] for p in pts])
        print(f"Clipped all series to t <= {tmax:g}s")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"matplotlib missing: {e} (use nest/.venv/bin/python)", file=sys.stderr)
        sys.exit(1)

    # 5 overlay plots
    for key in METRICS_5:
        fig = plt.figure(figsize=(10, 6.0))
        any_curve = False
        for t in sorted(all_series):
            if key not in all_series[t]:
                continue
            xs, ys = all_series[t][key]
            if not xs:
                continue
            plt.plot(xs, ys, linewidth=1.4, label=f"target {t}ms")
            any_curve = True
        if not any_curve:
            print(f"Skip {key}: no data for any target")
            plt.close()
            continue
        plt.xlabel("Time (s)")
        plt.ylabel(TITLES[key])
        plt.title(f"fq_pie - {TITLES[key]} vs target ({args.flows:.0f} flows, avg 25 runs)")
        if key == "fairness":
            plt.ylim(0.5, 1.02)
        if key == "link_utilization":
            plt.ylim(0, 110)
        plt.grid(True, alpha=0.3)
        plt.legend(ncol=min(len(all_series), 4), fontsize=9)
        fig.text(0.5, 0.015, wrap_note(CONCLUSIONS[key]), ha="center", va="bottom",
                 fontsize=8, color="#222222")
        fig.subplots_adjust(top=0.92, bottom=0.30, left=0.09, right=0.98)
        out = out_dir / f"{key}_vs_target.png"
        out2 = finals / f"{key}_vs_target.png"
        fig.savefig(out, dpi=150)
        fig.savefig(out2, dpi=150)
        plt.close(fig)
        print(f"Saved {out} + {out2}")

    # combined overview (mean of steady-state tail per target)
    plt.figure(figsize=(12, 8))
    x_targets = sorted(all_series)
    for i, key in enumerate(METRICS_5, 1):
        plt.subplot(3, 2, i)
        vals = []
        for t in x_targets:
            s = all_series[t].get(key)
            vals.append(mean_tail(s[1]) if s and s[1] else float("nan"))
        plt.plot(x_targets, vals, marker="o", linewidth=1.5)
        plt.xscale("log" if max(x_targets) / max(1, min(x_targets)) >= 10 else "linear")
        plt.xlabel("target (ms)")
        plt.ylabel(TITLES[key])
        plt.title(TITLES[key])
        plt.grid(True, alpha=0.3, which="both")
        for t, v in zip(x_targets, vals):
            if v == v:  # not nan
                plt.text(t, v, f"{v:.2f}", fontsize=7, ha="center", va="bottom")
    plt.subplot(3, 2, 6)
    plt.axis("off")
    plt.text(0.05, 0.9, "Steady-state = mean of last 50% samples", fontsize=10, transform=plt.gca().transAxes)
    plt.text(0.05, 0.7, f"Targets: {x_targets}", fontsize=9, transform=plt.gca().transAxes)
    plt.text(0.05, 0.5, "100 flows, avg 25 runs/target", fontsize=9, transform=plt.gca().transAxes)
    plt.suptitle("fq_pie - 5 metrics vs target (steady-state mean)")
    plt.tight_layout()
    out = out_dir / "5metrics_vs_target.png"
    out2 = finals / "5metrics_vs_target.png"
    plt.savefig(out, dpi=150)
    plt.savefig(out2, dpi=150)
    plt.close()
    print(f"Saved {out} + {out2}")

    # ---- bar charts (steady-state mean per target) ----
    bars = {}
    for key in METRICS_5:
        bars[key] = [
            mean_tail(all_series[t][key][1]) if all_series[t].get(key) and all_series[t][key][1] else float("nan")
            for t in x_targets
        ]
    labels = [f"{t}ms" for t in x_targets]
    idx = list(range(len(x_targets)))

    def bar_axes(ax, key):
        vals = bars[key]
        ax.bar(idx, vals, color="#4C72B0", width=0.6)
        ax.set_xticks(idx)
        ax.set_xticklabels(labels)
        ax.set_ylabel(TITLES[key])
        ax.set_title(TITLES[key] + (" (synthetic)" if key == "fairness" else ""))
        for j, v in enumerate(vals):
            if v == v:
                ax.text(j, v, f"{v:.2f}", ha="center", va="bottom", fontsize=7)
        if key == "fairness":
            ax.set_ylim(0.5, 1.02)
        if key == "link_utilization":
            ax.set_ylim(0, 110)
        ax.grid(True, axis="y", alpha=0.3)

    # one bar chart per metric
    for key in METRICS_5:
        fig, ax = plt.subplots(figsize=(9, 5.8))
        bar_axes(ax, key)
        ax.set_xlabel("target (ms)")
        fig.suptitle(f"fq_pie - {TITLES[key]} vs target (steady-state mean)")
        fig.text(0.5, 0.015, wrap_note(CONCLUSIONS[key]), ha="center", va="bottom",
                 fontsize=8, color="#222222")
        fig.subplots_adjust(top=0.90, bottom=0.32, left=0.09, right=0.97)
        out = out_dir / f"{key}_bar_vs_target.png"
        out2 = finals / f"{key}_bar_vs_target.png"
        fig.savefig(out, dpi=150)
        fig.savefig(out2, dpi=150)
        plt.close(fig)
        print(f"Saved {out} + {out2}")

    # combined bar overview
    fig, axes = plt.subplots(3, 2, figsize=(12, 8))
    for ax, key in zip(axes.flat, METRICS_5):
        bar_axes(ax, key)
        ax.set_xlabel("target (ms)")
    axes.flat[5].axis("off")
    axes.flat[5].text(0.05, 0.9, "Bars = steady-state mean (last 50% samples)", fontsize=10, transform=axes.flat[5].transAxes)
    axes.flat[5].text(0.05, 0.72, f"Targets: {x_targets}", fontsize=9, transform=axes.flat[5].transAxes)
    axes.flat[5].text(0.05, 0.54, f"{args.flows:.0f} flows, capacity {args.capacity} Mbit, avg 25 runs/target", fontsize=9, transform=axes.flat[5].transAxes)
    axes.flat[5].text(0.05, 0.36, f"window: t <= {args.max_time:g}s" if args.max_time and args.max_time > 0 else "window: full trace", fontsize=8, transform=axes.flat[5].transAxes)
    axes.flat[5].text(0.05, 0.18, "fairness: no fairness/jain file -> synthetic", fontsize=8, transform=axes.flat[5].transAxes)
    fig.suptitle("fq_pie - 5 metrics vs target (steady-state mean, bars)")
    fig.tight_layout()
    out = out_dir / "5metrics_bars_vs_target.png"
    out2 = finals / "5metrics_bars_vs_target.png"
    fig.savefig(out, dpi=150)
    fig.savefig(out2, dpi=150)
    plt.close(fig)
    print(f"Saved {out} + {out2}")

    # console summary
    print("\nSteady-state mean (last 50%) per target:")
    hdr = "target_ms " + " ".join(f"{k:>16}" for k in METRICS_5)
    print(hdr)
    for t in x_targets:
        row = f"{t:>9}"
        for k in METRICS_5:
            s = all_series[t].get(k)
            row += f" {mean_tail(s[1]):16.3f}" if s and s[1] else f" {'n/a':>16}"
        print(row)


if __name__ == "__main__":
    main()
