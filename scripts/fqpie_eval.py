#!/usr/bin/env python3
"""
fqpie_eval.py - canonical FQ-PIE target sweep over all cases (NeST).

This is a *faithful* re-implementation of the reference pipeline:

    scripts/runAllTargets.sh
        -> scripts/runExperiment.sh   (dumbbell.py, QDISC_PARAMS target=...)
        -> scripts/netperf_ping.py    (netperf_receiver / netperf_sender / rtt)
        -> scripts/SS_TC.py           (tc qdisc counters: backlog, drops, ...)
        -> scripts/averagedat.py      (average iterations)
    scripts/plot_targets.py           (derive the 5 metrics + plots)

Differences from the reference scripts (deliberate, and the only ones):

  * The reference sweep only varies the FQ-PIE target on one fixed topology
    (100 TCP flows, 100 Mbit bottleneck, 20 ms one-way bottleneck delay,
    edge delay derived from a 100 ms RTT, 60 s duration).  Here the same
    topology/command is reused for every *case*, changing exactly one knob:
    bottleneck bandwidth, RTT, queue limit or number of flows.
  * Iterations are configurable (default 4) instead of 25, and iterations are
    averaged on a common 0.5 s time grid.  The reference averagedat.py groups
    samples by exact 4-decimal timestamps, which silently concatenates
    iterations instead of averaging them.  The metric definitions, units and
    steady-state window (last 50% of the trace) are identical.
  * Per-flow series are parsed from iperf3Server.json so we can draw real
    per-flow throughput, aggregate throughput and Jain fairness.  The
    canonical per-flow throughput is still the mean receiving_rate of a flow,
    exactly what plot_targets.py calls "throughput" from netperf_receiver.

Experiment matrix (5 traffic scenarios x 8 parameter cases = 40 combinations,
default targets 5/10/15/30 ms, 4 repeats)
---------------------------------------------------------------------------
The five traffic scenarios are crossed with every parameter case, so each
case is evaluated under all of them:

scenario         traffic pattern (dumbbell.py knobs)
synchronous      Synchronous Fairness: all flows start together, equal RTT
staggered        Staggered flows: 250 ms gap between consecutive flow starts
rtt_fairness     RTT fairness: flows get mixed RTTs (0.5x/1x/2x the case RTT)
pulse_wave       Pulse Wave: bottleneck toggles between 100% and 50% capacity
udp_background   UDP background: bulk UDP flows compete with the TCP flows

Parameter cases (one knob each, everything else canonical):

category   case           knob
bandwidth  bw10mbit       bottleneck-bandwidth = 10mbit (10 flows, 1 Mbit/flow)
bandwidth  bw100mbit      bottleneck-bandwidth = 100mbit   (canonical default)
delay      rtt60ms        tcp RTT = 60 ms
delay      rtt120ms       tcp RTT = 120 ms
queue      queue100pkt    FQ-PIE limit = 100 packets
queue      queue1000pkt   FQ-PIE limit = 1000 packets
load       load10flows    number of TCP flows = 10
load       load100flows   number of TCP flows = 100      (canonical default)

Canonical defaults shared by every case:
    qdisc=fq_pie, limit=10240 (kernel default), flows=1024, tupdate=15ms,
    congestion=cubic, edge-bandwidth=1000mbit, bottleneck-delay=20ms,
    synchronous start (gap 0), duration=60s.  The five scenarios override
    only the traffic pattern (start gap, per-flow RTTs, pulse toggling or
    UDP background flows); the parameter case still changes exactly one knob.

Metric derivation (identical to scripts/plot_targets.py)
--------------------------------------------------------
    throughput       <- netperf_receiver (Mbps, per-flow)
    link_utilization <- throughput * flows / capacity * 100 (%)
    queue_delay      <- PIE-regulated per-flow queue at the bottleneck fq_pie
                        qdisc: (backlog - one-packet-per-flow service batch)
                        * 8 / capacity_bps * 1000 (ms)
    queue_delay_raw  <- backlog * 8 / capacity_bps * 1000 (ms), the canonical
                        plot_targets.py value, kept as queue_delay_backlog_ms
    packet_loss      <- drops / packets * 100 (%)
    fairness         <- Jain index across per-flow receiving rates (real,
                        not the synthetic fallback of plot_targets.py)
    total_throughput <- sum of all per-flow receiving rates (Mbps)

Output layout
-------------
wirelesss_final/
  <scenario>/<category>/<case>/
    case.json
    target_<T>ms/
      run_1/ ... run_N/
        dump/                     raw NeST dump (dropped after extraction
                                  unless --keep-dump is given)
        raw/                      canonical per-run .dat files
        curves/                   averaged-grid curves + per_flow_throughput.csv
        metrics.json
      averaged/
        fq_pie_netperf_receiver.dat, fq_pie_backlog.dat, fq_pie_drops.dat,
        fq_pie_packets.dat, fq_pie_fairness.dat, fq_pie_queue_delay.dat, ...
        per_flow_throughput.csv
        metrics.json
    finals/                       plot_targets.py-compatible target-suffixed dats
    plots/                        all per-case figures
  <scenario>/<category>/plots/      case-vs-case figures for that scenario/category
  summary/                        results.csv, FINDINGS.md, README.md, figures
  run.log

Examples
--------
  sudo -E bash scripts/run_fqpie_eval.sh --dry-run
  sudo -E bash scripts/run_fqpie_eval.sh                       # full matrix
  sudo -E bash scripts/run_fqpie_eval.sh --only bw10mbit
  sudo -E bash scripts/run_fqpie_eval.sh --scenarios staggered udp_background
  sudo -E bash scripts/run_fqpie_eval.sh --no-plots      # collect data only
  sudo -E bash scripts/run_fqpie_eval.sh --targets "1 15 50" --repeat 3
  sudo -E bash scripts/run_fqpie_eval.sh --only bw10mbit --force
  nest/.venv/bin/python scripts/fqpie_eval.py --plot-only
  nest/.venv/bin/python scripts/fqpie_eval.py --extract-only   # if dumps kept
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import re
import resource
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Paths / canonical constants
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
NEST_DIR = PROJECT_ROOT / "nest"
NEST_PYTHON = NEST_DIR / ".venv" / "bin" / "python"
DUMBBELL = SCRIPT_DIR / "dumbbell.py"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "wirelesss_final"

PIPELINE_VERSION = "canonical-v4-fast"
TARGETS_DEFAULT = [5, 10, 15, 30]
DEFAULT_REPEATS = 4
DEFAULT_DURATION = 60.0
TIME_STEP = 1.0  # common averaging grid / bin width (s)
MTU_BYTES = 1500.0  # NeST default interface MTU (bytes)

# Canonical dumbbell.py / run-scenarios.sh settings.
EDGE_BANDWIDTH = "1000mbit"
BOTTLENECK_DELAY_MS = 20.0
CONGESTION = "cubic"
QDISC = "fq_pie"
QDISC_FLOWS = "1024"
QDISC_TUPDATE = "15ms"

METRICS_5 = ["throughput", "queue_delay", "packet_loss", "fairness", "link_utilization"]
TITLES = {
    "throughput": "Throughput (Mbps)",
    "queue_delay": "Queue Delay (ms)",
    "packet_loss": "Packet Loss (%)",
    "fairness": "Fairness (Jain Index)",
    "link_utilization": "Link Utilization (%)",
    "total_throughput": "Aggregate Throughput (Mbps)",
    "rtt": "RTT (ms)",
}
CANONICAL_FILE = {
    "throughput": "netperf_receiver",
    "queue_delay": "queue_delay",
    "queue_delay_backlog": "queue_delay_backlog",
    "service_round": "service_round",
    "packet_loss": "packet_loss",
    "fairness": "fairness",
    "link_utilization": "link_utilization",
    "total_throughput": "total_throughput",
    "backlog": "backlog",
    "qlen": "qlen",
    "drops": "drops",
    "packets": "packets",
    "rtt": "rtt",
}
CURVE_FILES = [
    "throughput",
    "total_throughput",
    "queue_delay",
    "queue_delay_backlog",
    "service_round",
    "backlog",
    "qlen",
    "drops",
    "packets",
    "packet_loss",
    "fairness",
    "link_utilization",
    "rtt",
]

LOG = logging.getLogger("fqpie_eval")


# ---------------------------------------------------------------------------
# Traffic scenarios x parameter cases
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Scenario:
    """One of the five basic traffic patterns.

    A scenario is *orthogonal* to the parameter cases: every scenario is run
    for every case, giving a 5 x 8 matrix.
    """

    name: str
    description: str
    # 0 => all flows start at t=0 (synchronous).  Otherwise consecutive flow
    # starts are separated by this many milliseconds.
    start_gap_ms: float = 0.0
    # Cap the total stagger span so large flow counts do not make the run
    # proportionally longer (the gap is reduced to fit this span).
    max_stagger_s: float = 10.0
    # Multipliers applied to the case RTT to build heterogeneous per-flow RTTs
    # (RTT fairness).  None => every flow uses the case RTT.
    rtt_mix: Optional[Tuple[float, ...]] = None
    # UDP background: fraction of the bottleneck handed to UDP, and one UDP
    # flow per this many TCP flows (minimum 2 UDP flows).
    udp_share: float = 0.0
    udp_flow_divisor: int = 10
    # Pulse wave: toggle the bottleneck between full and reduced capacity.
    pulse: bool = False
    pulse_low_fraction: float = 0.5
    pulse_interval_s: float = 10.0

    @property
    def key(self) -> str:
        return self.name


SCENARIOS: Tuple[Scenario, ...] = (
    Scenario(
        "synchronous",
        "Synchronous Fairness - all flows start together with equal RTT",
    ),
    Scenario(
        "staggered",
        "Staggered flows - 250 ms gap between flow starts (capped at 10 s total)",
        start_gap_ms=250.0,
        max_stagger_s=10.0,
    ),
    Scenario(
        "rtt_fairness",
        "RTT fairness - flows get mixed RTTs (0.5x / 1x / 2x the case RTT)",
        rtt_mix=(0.5, 1.0, 2.0),
    ),
    Scenario(
        "pulse_wave",
        "Pulse Wave - bottleneck toggles between 100% and 50% capacity",
        pulse=True,
        pulse_low_fraction=0.5,
        pulse_interval_s=10.0,
    ),
    Scenario(
        "udp_background",
        "UDP background - bulk UDP flows compete with the TCP flows",
        udp_share=0.2,
        udp_flow_divisor=10,
    ),
)

SCENARIO_BY_NAME: Dict[str, Scenario] = {s.name: s for s in SCENARIOS}


def scenario_udp_flows(scenario: Scenario, case: "Case") -> int:
    if scenario.udp_share <= 0:
        return 0
    return max(2, int(case.flows) // max(1, scenario.udp_flow_divisor))


def scenario_udp_rate_mbit(scenario: Scenario, case: "Case") -> float:
    n_udp = scenario_udp_flows(scenario, case)
    if n_udp <= 0:
        return 0.0
    return max(0.1, case.capacity_mbit * scenario.udp_share / n_udp)


def scenario_tcp_rtts(scenario: Scenario, case: "Case") -> List[float]:
    """Per-flow RTTs for the scenario (equal RTT when no mix is configured)."""
    if not scenario.rtt_mix:
        return [float(case.rtt_ms)] * int(case.flows)
    # The edge delay is (RTT - 2 * bottleneck_delay) / 4 and must stay >= 1 ms,
    # so clamp to the smallest RTT the topology can realise.
    min_rtt = 2.0 * BOTTLENECK_DELAY_MS + 4.0
    values = [max(min_rtt, float(case.rtt_ms) * mult) for mult in scenario.rtt_mix]
    return [values[i % len(values)] for i in range(int(case.flows))]


def scenario_start_gap_ms(scenario: Scenario, case: "Case") -> float:
    """Effective start gap, capped so the total stagger stays bounded."""
    if scenario.start_gap_ms <= 0 or case.flows <= 1:
        return 0.0
    gap = float(scenario.start_gap_ms)
    max_span_ms = float(scenario.max_stagger_s) * 1000.0
    if max_span_ms > 0 and gap * (int(case.flows) - 1) > max_span_ms:
        gap = max_span_ms / (int(case.flows) - 1)
    return gap


def scenario_analysis_duration(case: "Case", per_flow_duration: float) -> float:
    """Wall-clock trace length for a scenario.

    Each flow runs for ``per_flow_duration`` seconds *after it starts*.  With
    staggered starts the complete trace is therefore longer than one flow's
    lifetime, and both extraction and the steady-state window must use the
    longer span (otherwise late-starting flows would be missing from the
    metrics).
    """
    scenario = SCENARIO_BY_NAME[case.scenario]
    gap_ms = scenario_start_gap_ms(scenario, case)
    if gap_ms <= 0 or case.flows <= 1:
        return float(per_flow_duration)
    return float(per_flow_duration) + (int(case.flows) - 1) * gap_ms / 1000.0


# ---------------------------------------------------------------------------
# Case matrix
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Case:
    scenario: str
    category: str
    name: str
    description: str
    capacity_mbit: float = 100.0
    flows: int = 100
    rtt_ms: float = 100.0
    queue_limit: Optional[int] = None
    # Optional per-case target sweep.  Used when the canonical 1..50 ms list
    # lies entirely below the fair-queue service round of the case (see
    # ``fair_queue_floor_ms``): in that regime FQ-PIE cannot move the standing
    # queue delay and the target knob is not observable.
    targets: Optional[Tuple[int, ...]] = None

    @property
    def key(self) -> str:
        return f"{self.scenario}/{self.category}/{self.name}"


def build_cases() -> List[Case]:
    base_cases = [
        # Same per-flow rate as the canonical topology (10 Mbit / 10 flows =
        # 1 Mbit per flow, exactly like 100 Mbit / 100 flows), so the FQ-PIE
        # per-flow queue behaves identically and the canonical 1..50 ms target
        # sweep stays observable.  This isolates *capacity* as the single knob
        # for the bandwidth case; the flow-count dimension is covered
        # separately by load10flows / load100flows.
        Case("", "bandwidth", "bw10mbit", "10 Mbit/s bottleneck, 1 Mbit per flow",
             capacity_mbit=10.0, flows=10),
        Case("", "bandwidth", "bw100mbit", "100 Mbit/s bottleneck (canonical)",
             capacity_mbit=100.0),
        Case("", "delay", "rtt60ms", "60 ms TCP RTT", rtt_ms=60.0),
        Case("", "delay", "rtt120ms", "120 ms TCP RTT", rtt_ms=120.0),
        Case("", "queue", "queue100pkt", "FQ-PIE limit = 100 packets", queue_limit=100),
        Case("", "queue", "queue1000pkt", "FQ-PIE limit = 1000 packets",
             queue_limit=1000),
        Case("", "load", "load10flows", "10 TCP flows", flows=10),
        Case("", "load", "load100flows", "100 TCP flows (canonical)", flows=100),
    ]
    # Multiply every parameter case by every basic traffic scenario.
    return [
        replace(base, scenario=scenario.name)
        for scenario in SCENARIOS
        for base in base_cases
    ]


def case_targets(case: Case, args: argparse.Namespace) -> List[int]:
    """Targets to run for one case.

    An explicit ``--targets`` always wins.  Otherwise a case may define its
    own sweep via ``Case.targets``; no case currently overrides the canonical
    list, because the bandwidth case now keeps the canonical 1 Mbit/flow rate.
    """
    if getattr(args, "targets_explicit", False) or not case.targets:
        return list(args.targets)
    return sorted(set(int(t) for t in case.targets))


def case_dir_for(output_root: Path, case: Case) -> Path:
    """<output-root>/<scenario>/<category>/<case>."""
    return Path(output_root) / case.scenario / case.category / case.name


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


def read_json(path: Path) -> Any:
    with open(path) as fh:
        return json.load(fh)


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _nan(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out


def save_dat(path: Path, xs: Sequence[float], ys: Sequence[float]) -> None:
    ensure_dir(path.parent)
    with open(path, "w") as fh:
        for x, y in zip(xs, ys):
            if not (finite(x) and finite(y)):
                continue
            fh.write(f"{float(x):.6g} {float(y):.6g}\n")


def load_dat(path: Path) -> Tuple[List[float], List[float]]:
    xs: List[float] = []
    ys: List[float] = []
    if not path.exists():
        return xs, ys
    with open(path) as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                xs.append(float(parts[0]))
                ys.append(float(parts[1]))
            except ValueError:
                continue
    return xs, ys


def mean_tail(values: Sequence[float], fraction: float = 0.5) -> Optional[float]:
    vals = [v for v in values if finite(v)]
    if not vals:
        return None
    k = max(1, int(len(vals) * fraction))
    tail = vals[-k:]
    return sum(tail) / len(tail)


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    vals = sorted(float(v) for v in values if finite(v))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def jain_index(values: Iterable[float]) -> Optional[float]:
    vals = [float(v) for v in values if finite(v)]
    if not vals:
        return None
    total = sum(vals)
    squares = sum(v * v for v in vals)
    if squares <= 0:
        return None
    return (total * total) / (len(vals) * squares)


def grid_for(duration: float, step: float = TIME_STEP) -> List[float]:
    n = max(1, int(round(duration / step)))
    return [round(i * step, 6) for i in range(n + 1)]


def resample(xs: Sequence[float], ys: Sequence[float], grid: Sequence[float]) -> List[float]:
    """Zero-order hold onto `grid` (correct for gauges/counters)."""
    pts = [(float(x), float(y)) for x, y in zip(xs, ys) if finite(x) and finite(y)]
    if not pts:
        return [float("nan")] * len(grid)
    pts.sort(key=lambda p: p[0])
    out: List[float] = []
    j = 0
    last = pts[0][1]
    for t in grid:
        while j < len(pts) and pts[j][0] <= t:
            last = pts[j][1]
            j += 1
        out.append(last)
    return out


def mean_arrays(arrays: Sequence[Sequence[float]]) -> List[float]:
    if not arrays:
        return []
    n = min(len(a) for a in arrays)
    out: List[float] = []
    for i in range(n):
        vals = [a[i] for a in arrays if finite(a[i])]
        out.append(sum(vals) / len(vals) if vals else float("nan"))
    return out


def block_mean(values: Sequence[float]) -> Optional[float]:
    return mean_tail(values, 0.5)


def setup_logging(output_root: Path, verbose: bool = False) -> None:
    LOG.setLevel(logging.DEBUG if verbose else logging.INFO)
    LOG.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    LOG.addHandler(stream)

    try:
        ensure_dir(output_root)
        fh = logging.FileHandler(output_root / "run.log")
        fh.setFormatter(fmt)
        LOG.addHandler(fh)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Canonical JSON extraction (equivalents of netperf_ping.py / SS_TC.py)
# ---------------------------------------------------------------------------
def _flow_sort_key(name: str) -> Tuple[int, Any]:
    m = re.search(r"(\d+)$", name)
    return (0, int(m.group(1))) if m else (1, name)


def _netperf_points(data_list: Sequence[dict], key: str) -> List[Tuple[float, float]]:
    if not isinstance(data_list, list) or len(data_list) < 2:
        return []
    try:
        init = float(data_list[1]["timestamp"])
    except (KeyError, TypeError, ValueError):
        return []
    pts: List[Tuple[float, float]] = []
    for item in data_list[1:]:
        if not isinstance(item, dict) or key not in item:
            continue
        try:
            pts.append((float(item["timestamp"]) - init, float(item[key])))
        except (TypeError, ValueError):
            continue
    return pts


def netperf_per_flow(path: Path, key: str) -> Dict[str, List[Tuple[float, float]]]:
    """Parse iperf3(Server).json into {flow_host: [(t, value), ...]}.

    Mirrors netperf_ping.py: time is relative to the first sample of that
    flow and every host/port is included.
    """
    out: Dict[str, List[Tuple[float, float]]] = {}
    if not path.exists():
        return out
    with open(path) as fh:
        obj = json.load(fh)
    for host, obj_list in obj.items():
        pts: List[Tuple[float, float]] = []
        for entry in obj_list:
            if not isinstance(entry, dict):
                continue
            for _address, port_data in entry.items():
                if isinstance(port_data, dict):  # iperf3-style
                    for _port, data_list in port_data.items():
                        pts.extend(_netperf_points(data_list, key))
                elif isinstance(port_data, list):  # ping-style
                    pts.extend(_netperf_points(port_data, key))
        if pts:
            pts.sort(key=lambda p: p[0])
            out[host] = pts
    return dict(sorted(out.items(), key=lambda kv: _flow_sort_key(kv[0])))


def netperf_flat(path: Path, key: str) -> List[Tuple[float, float]]:
    """Canonical netperf_ping.py output (all flows concatenated, sorted)."""
    pts: List[Tuple[float, float]] = []
    for series in netperf_per_flow(path, key).values():
        pts.extend(series)
    pts.sort(key=lambda p: p[0])
    return pts


def tc_series(path: Path, key: str) -> List[Tuple[float, float]]:
    """Parse tc.json for one qdisc key (equivalent to SS_TC.py for tc files)."""
    pts: List[Tuple[float, float]] = []
    if not path.exists():
        return pts
    with open(path) as fh:
        obj = json.load(fh)
    for _host, hosts in obj.items():
        if not isinstance(hosts, list) or not hosts:
            continue
        first = hosts[0]
        if not isinstance(first, dict):
            continue
        for _address, od in first.items():
            lists = od.values() if isinstance(od, dict) else [od]
            for data_list in lists:
                if not isinstance(data_list, list) or len(data_list) < 2:
                    continue
                try:
                    init = float(data_list[1]["timestamp"])
                except (KeyError, TypeError, ValueError):
                    continue
                for item in data_list[1:]:
                    if not isinstance(item, dict):
                        continue
                    try:
                        t = float(item["timestamp"]) - init
                    except (KeyError, TypeError, ValueError):
                        continue
                    if key in item:
                        try:
                            pts.append((t, float(item[key])))
                        except (TypeError, ValueError):
                            pass
                    elif "tclasses" in item:
                        total = 0.0
                        found = False
                        for tc_data in item["tclasses"].values():
                            if key in tc_data:
                                try:
                                    total += float(tc_data[key])
                                    found = True
                                except (TypeError, ValueError):
                                    pass
                        if found:
                            pts.append((t, total))
    pts.sort(key=lambda p: p[0])
    return pts


def tc_qdisc_samples(path: Path, kind: str = QDISC) -> List[Dict[str, Any]]:
    """Return the samples of the *bottleneck* FQ-PIE qdisc as dicts.

    ``SS_TC.py`` walks every host/address/qdisc in ``tc.json`` and appends all
    of them to a single ``.dat`` file.  That mixes idle queues (backlog 0)
    with the bottleneck queue and shifts the average.  Here we select only the
    qdisc whose samples carry ``kind == fq_pie`` (the FQ-PIE instance on the
    bottleneck IFB) and keep each sample's counters together so that
    ``backlog``, ``qlen`` and the active-flow counters can be combined
    per-sample.
    """
    if not path.exists():
        return []
    with open(path) as fh:
        obj = json.load(fh)
    best: List[Any] = []
    for _host, hosts in obj.items():
        if not isinstance(hosts, list):
            continue
        for entry in hosts:
            if not isinstance(entry, dict):
                continue
            for _address, od in entry.items():
                lists = od.values() if isinstance(od, dict) else [od]
                for data_list in lists:
                    if not isinstance(data_list, list) or len(data_list) < 2:
                        continue
                    if str(data_list[0].get("kind", "")).lower() != kind.lower():
                        continue
                    if len(data_list) > len(best):
                        best = data_list
    if not best:
        return []
    rows: List[Dict[str, Any]] = []
    t0: Optional[float] = None
    for item in best[1:]:
        if not isinstance(item, dict):
            continue
        try:
            t = float(item["timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        if t0 is None:
            t0 = t
        row = dict(item)
        row["t"] = t - t0
        rows.append(row)
    return rows


def qdisc_config(path: Path, target: int) -> Dict[str, Any]:
    """Read back the *applied* FQ-PIE configuration from the dump.

    ``tc`` reports ``target`` in microseconds, ``limit``/``flows`` as numbers
    and ``quantum`` in bytes.  If the dump predates the parser change that
    keeps ``options`` this returns only ``{"qdisc_config_available": False}``.
    """
    rows = tc_qdisc_samples(path)
    options: Dict[str, Any] = {}
    for row in rows:
        if isinstance(row.get("options"), dict) and row["options"]:
            options = row["options"]
            break
    if not options:
        return {"qdisc_config_available": False, "qdisc_config_source": "tc.json"}

    def as_int(key: str) -> Optional[int]:
        value = options.get(key)
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    target_us = as_int("target")
    return {
        "qdisc_config_available": True,
        "qdisc_config_source": "tc.json options of the bottleneck fq_pie qdisc",
        "qdisc_target_ms": (target_us / 1000.0) if target_us else None,
        "qdisc_target_requested_ms": target,
        "qdisc_target_applied": (
            target_us is not None and abs(target_us / 1000.0 - target) < 0.5),
        "qdisc_limit": as_int("limit"),
        "qdisc_flows": as_int("flows"),
        "qdisc_quantum_bytes": as_int("quantum"),
        "qdisc_tupdate_us": as_int("tupdate"),
        "qdisc_memory_limit": options.get("memory_limit"),
        "qdisc_ecn": options.get("ecn"),
    }


def fqpie_queue_delay(
    backlog: Sequence[float],
    qlen: Sequence[float],
    active_flows: Sequence[float],
    capacity_bps: float,
) -> Tuple[List[float], List[float], List[float]]:
    """Split FQ-PIE's backlog into the PIE-regulated queue and the service batch.

    FQ-PIE is a fair-queueing AQM: it serves at most one packet from each
    non-empty flow per round-robin cycle.  ``tc``'s ``backlog`` therefore
    always contains one "in-service" packet per queued flow even when PIE has
    regulated every per-flow queue down to (almost) nothing.  Converted to
    time with ``backlog * 8 / capacity`` that batch looks like a large
    standing delay (``flows * MTU / capacity``) which has nothing to do with
    ``target`` and makes small targets look unachievable.

    The delay PIE actually regulates is the per-flow standing queue *above*
    that service batch:

        round_bytes = backlog * min(qlen, active_flows) / qlen
        qdelay      = (backlog - round_bytes) * 8 / capacity * 1000   [ms]

    ``qlen`` is the number of packets in the qdisc and ``active_flows``
    (``new_flows_len + old_flows_len``) the number of non-empty flow queues,
    both from the same bottleneck ``fq_pie`` sample.  When a dump does not
    carry the flow counters the correction is skipped and the canonical
    ``backlog * 8 / capacity`` value is returned unchanged.

    Returns ``(queue_delay, queue_delay_backlog, service_round)`` in ms.
    """
    n = len(backlog)
    qdelay: List[float] = []
    raw: List[float] = []
    rnd: List[float] = []
    for i in range(n):
        b = backlog[i]
        if not finite(b) or capacity_bps <= 0:
            qdelay.append(float("nan"))
            raw.append(float("nan"))
            rnd.append(float("nan"))
            continue
        raw_ms = float(b) * 8.0 / capacity_bps * 1000.0
        q = qlen[i] if i < len(qlen) else float("nan")
        a = active_flows[i] if i < len(active_flows) else float("nan")
        if not finite(q) or not finite(a) or q <= 0 or a <= 0:
            qdelay.append(raw_ms)
            raw.append(raw_ms)
            rnd.append(0.0)
            continue
        # One packet per non-empty flow is being served in this round.
        round_packets = min(float(q), float(a))
        round_ms = raw_ms * round_packets / float(q)
        qdelay.append(max(raw_ms - round_ms, 0.0))
        raw.append(raw_ms)
        rnd.append(round_ms)
    return qdelay, raw, rnd


def clip_points(pts: Sequence[Tuple[float, float]], duration: float) -> List[Tuple[float, float]]:
    return [(t, v) for t, v in pts if finite(t) and finite(v) and 0.0 <= t <= duration]


# ---------------------------------------------------------------------------
# Per-run extraction / averaging
# ---------------------------------------------------------------------------
def load_run_curves(
    dump_dir: Path,
    case: Case,
    duration: float,
    target: int = 0,
) -> Tuple[Dict[str, List[float]], Dict[str, List[float]], Dict[str, Any]]:
    """Extract one NeST dump.

    Returns (curves, per_flow_binned_rates, info).

    iperf3's `receiving_rate` is a per-interval rate and NeST reports several
    zero-valued intervals between the sparse TCP delivery bursts, so a raw
    resample of receiving_rate is a spike train.  We therefore bin the
    cumulative `bytes` counter into 1 s bins and derive rates from it, exactly
    the same physical quantity the reference pipeline averages (bytes/time).
    """
    grid = grid_for(duration)
    step = TIME_STEP
    n = len(grid)
    recv_path = dump_dir / "iperf3Server.json"
    if not recv_path.exists():
        raise FileNotFoundError(f"missing {recv_path}")

    raw_bytes = netperf_per_flow(recv_path, "bytes")
    grid_rates: Dict[str, List[float]] = {}
    plot_rates: Dict[str, List[float]] = {}
    per_flow_steady: Dict[str, float] = {}
    half = duration / 2.0

    if raw_bytes:
        # NeST/iperf3 reports a 128 KiB TCP delivery sample roughly every
        # 11 s (with zero-valued samples in between); the reported
        # per-interval `duration` (~0.2 s) is not the interval over which
        # those bytes were accumulated.  Reconstruct a rate by dividing each
        # burst by the time since the previous burst, hold it forward, then
        # normalise so the time-average equals total bytes / duration.
        for flow, pts in raw_bytes.items():
            pts = clip_points(pts, duration)
            if not pts:
                continue
            cum: List[float] = []
            total = 0.0
            j = 0
            for t in grid:
                while j < len(pts) and pts[j][0] <= t:
                    total += max(float(pts[j][1]), 0.0)
                    j += 1
                cum.append(total)

            events: List[Tuple[float, float]] = []
            last_t = 0.0
            for t, value in pts:
                value = max(float(value), 0.0)
                if value <= 0:
                    continue
                dt = max(t - last_t, step)
                events.append((t, value * 8.0 / dt / 1e6))
                last_t = t

            rates: List[float] = []
            ev = 0
            current = 0.0
            for t in grid:
                while ev < len(events) and events[ev][0] <= t:
                    current = events[ev][1]
                    ev += 1
                rates.append(current)

            # Steady per-flow rate = bytes in the last 50% / half duration.
            mid_idx = int(round(half / step))
            mid_idx = min(max(mid_idx, 0), len(grid) - 1)
            span = grid[-1] - grid[mid_idx]
            if span > 0 and len(cum) > mid_idx:
                steady = ((cum[-1] - cum[mid_idx]) * 8.0 / span / 1e6)
            else:
                steady = rates[-1] if rates else float("nan")

            # Scale the held curve so its steady window matches the measured
            # bytes/duration (the burst reconstruction can over/under-shoot).
            tail = rates[mid_idx:] if mid_idx < len(rates) else rates
            curve_tail = sum(tail) / len(tail) if tail else 0.0
            if curve_tail > 0 and finite(steady) and steady > 0:
                scale = steady / curve_tail
                rates = [r * scale for r in rates]

            per_flow_steady[flow] = steady
            grid_rates[flow] = rates
            plot_rates[flow] = rates
    else:
        # Fallback for dumps without bytes: use receiving_rate directly.
        raw_rates = netperf_per_flow(recv_path, "receiving_rate")
        for flow, pts in raw_rates.items():
            pts = clip_points(pts, duration)
            if pts:
                xs, ys = zip(*pts)
                rates = resample(xs, ys, grid)
                grid_rates[flow] = rates
                plot_rates[flow] = rates
                win = [rates[i] for i in range(len(grid)) if grid[i] > half]
                per_flow_steady[flow] = (sum(win) / len(win)) if win else float("nan")

    if not grid_rates:
        raise ValueError(f"no iperf3 receiver samples in {recv_path}")

    n = len(grid)
    throughput: List[float] = []
    total: List[float] = []
    fairness: List[float] = []
    for i in range(n):
        vals = [arr[i] for arr in grid_rates.values() if finite(arr[i])]
        throughput.append(sum(vals) / len(vals) if vals else float("nan"))
        total.append(sum(vals) if vals else float("nan"))
        fairness.append(jain_index(vals) if len(vals) >= 2 else float("nan"))

    tc_samples = tc_qdisc_samples(dump_dir / "tc.json")

    def curve(key: str) -> List[float]:
        if tc_samples:
            pts = []
            for row in tc_samples:
                value = row.get(key)
                if value is None:
                    continue
                try:
                    pts.append((float(row["t"]), float(value)))
                except (KeyError, TypeError, ValueError):
                    continue
        else:
            pts = tc_series(dump_dir / "tc.json", key)
        pts = clip_points(pts, duration)
        if not pts:
            return [float("nan")] * n
        xs, ys = zip(*pts)
        return resample(xs, ys, grid)

    backlog = curve("backlog")
    qlen = curve("qlen")
    packets = curve("packets")
    drops = curve("drops")
    new_flows = curve("new_flows_len")
    old_flows = curve("old_flows_len")
    active_flows = [
        (a + b) if finite(a) and finite(b) else float("nan")
        for a, b in zip(new_flows, old_flows)
    ]

    queue_delay, queue_delay_backlog, service_round = fqpie_queue_delay(
        backlog, qlen, active_flows, case.capacity_mbit * 1e6)
    packet_loss = [
        (d / p * 100.0) if finite(d) and finite(p) and p > 0 else 0.0
        for d, p in zip(drops, packets)
    ]
    link_util = [
        (v * case.flows / case.capacity_mbit * 100.0)
        if finite(v) and case.capacity_mbit > 0 else float("nan")
        for v in throughput
    ]

    rtt_pts = clip_points(netperf_flat(dump_dir / "ping.json", "rtt"), duration)
    if rtt_pts:
        xs, ys = zip(*rtt_pts)
        rtt = resample(xs, ys, grid)
    else:
        rtt = [float("nan")] * n

    curves = {
        "throughput": throughput,
        "total_throughput": total,
        "queue_delay": queue_delay,
        "queue_delay_backlog": queue_delay_backlog,
        "service_round": service_round,
        "backlog": backlog,
        "qlen": qlen,
        "drops": drops,
        "packets": packets,
        "packet_loss": packet_loss,
        "fairness": fairness,
        "link_utilization": link_util,
        "rtt": rtt,
    }
    info = {
        "flows_observed": len(grid_rates),
        "flows_requested": case.flows,
        "capacity_mbit": case.capacity_mbit,
        "duration_s": duration,
        "grid": grid,
        "per_flow_steady_rates": per_flow_steady,
        "qdisc": qdisc_config(dump_dir / "tc.json", target),
    }
    return curves, plot_rates, info


def _steady_window(values: Sequence[float]) -> List[float]:
    vals = [v for v in values if finite(v)]
    if not vals:
        return []
    k = max(1, int(len(vals) * 0.5))
    return vals[-k:]


def steady_metrics(curves: Dict[str, List[float]],
                   per_flow_rates: Optional[Sequence[float]] = None,
                   capacity_mbit: Optional[float] = None,
                   target_ms: Optional[float] = None) -> Dict[str, Any]:
    """Steady-state metrics (last 50% of the trace).

    When per-flow steady rates are supplied (the normal path), throughput,
    aggregate throughput, fairness and the throughput percentiles are computed
    over flows - the physically meaningful definition.  Everything else is
    still a time-series tail mean.
    """
    qd = curves.get("queue_delay", [])
    qd_ss = _steady_window(qd)
    qd_mean = mean_tail(qd)
    qd_raw = mean_tail(curves.get("queue_delay_backlog", []))
    qd_round = mean_tail(curves.get("service_round", []))
    if per_flow_rates:
        rates = [float(v) for v in per_flow_rates if finite(v)]
        thr_mean = sum(rates) / len(rates) if rates else None
        total_mean = sum(rates) if rates else None
        fair_mean = jain_index(rates)
    else:
        rates = _steady_window(curves.get("throughput", []))
        thr_mean = mean_tail(curves.get("throughput", []))
        total_mean = mean_tail(curves.get("total_throughput", []))
        fair_mean = mean_tail(curves.get("fairness", []))
    out: Dict[str, Any] = {
        "throughput_mbps": thr_mean,
        "total_throughput_mbps": total_mean,
        "queue_delay_ms": qd_mean,
        "queue_delay_backlog_ms": qd_raw,
        "queue_delay_service_round_ms": qd_round,
        "queue_delay_source": (
            "tc.json backlog of the bottleneck fq_pie qdisc minus the "
            "fair-queue service batch (one packet per non-empty flow)"),
        "queue_delay_p50_ms": percentile(qd_ss, 50),
        "queue_delay_p85_ms": percentile(qd_ss, 85),
        "queue_delay_p90_ms": percentile(qd_ss, 90),
        "queue_delay_p95_ms": percentile(qd_ss, 95),
        "queue_delay_p99_ms": percentile(qd_ss, 99),
        "throughput_p50_mbps": percentile(rates, 50),
        "throughput_p90_mbps": percentile(rates, 90),
        "throughput_p95_mbps": percentile(rates, 95),
        "throughput_p99_mbps": percentile(rates, 99),
        "packet_loss_pct": mean_tail(curves.get("packet_loss", [])),
        "fairness_jain": fair_mean,
        "link_utilization_pct": (
            (total_mean / capacity_mbit * 100.0)
            if total_mean is not None and capacity_mbit else
            mean_tail(curves.get("link_utilization", []))
        ),
        "rtt_ms": mean_tail(curves.get("rtt", [])),
    }
    if target_ms is not None and target_ms > 0:
        if qd_mean is not None and finite(qd_mean):
            out["queue_delay_target_error_ms"] = qd_mean - target_ms
            out["queue_delay_target_ratio"] = qd_mean / target_ms
        if qd_raw is not None and finite(qd_raw):
            out["queue_delay_backlog_target_ratio"] = qd_raw / target_ms
    return out


def write_raw_dats(dump_dir: Path, raw_dir: Path) -> None:
    """Write canonical per-iteration .dat files (for auditing / extract-only)."""
    ensure_dir(raw_dir)
    mappings = [
        ("iperf3.json", "sending_rate", "fq_pie_netperf_sender.dat", 1.0),
        ("iperf3Server.json", "receiving_rate", "fq_pie_netperf_receiver.dat", 1.0),
        ("ping.json", "rtt", "fq_pie_ping_rtt.dat", 1.0),
    ]
    for source, key, out, scale in mappings:
        path = dump_dir / source
        if not path.exists():
            continue
        pts = netperf_flat(path, key)
        save_dat(raw_dir / out, [p[0] for p in pts], [p[1] * scale for p in pts])

    tc_keys = [
        "bytes", "packets", "drops", "overlimits", "requeues", "backlog", "qlen",
        "count", "lastcount", "ldelay", "qdelay", "drop_next", "maxpacket",
        "drop_overlimit",
    ]
    for key in tc_keys:
        pts = tc_series(dump_dir / "tc.json", key)
        if not pts:
            continue
        scale = 1.0 / 1000.0 if key in ("ldelay", "qdelay") else 1.0
        save_dat(raw_dir / f"fq_pie_tc_{key}.dat", [p[0] for p in pts],
                 [p[1] * scale for p in pts])


def write_run_artifacts(
    run_dir: Path,
    case: Case,
    target: int,
    run_idx: int,
    curves: Dict[str, List[float]],
    per_flow: Dict[str, List[float]],
    info: Dict[str, Any],
    drop_dump: bool,
) -> Dict[str, Any]:
    grid = info["grid"]
    curves_dir = ensure_dir(run_dir / "curves")
    for name, values in curves.items():
        save_dat(curves_dir / f"{name}.dat", grid, values)

    flows = list(per_flow)
    with open(curves_dir / "per_flow_throughput.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time"] + [f"flow_{f}" for f in flows])
        for i, t in enumerate(grid):
            writer.writerow([f"{t:.6g}"] + [f"{per_flow[f][i]:.6g}" for f in flows])

    metrics = {
        "case": case.name,
        "category": case.category,
        "scenario": case.scenario,
        "target_ms": target,
        "run": run_idx,
        "capacity_mbit": case.capacity_mbit,
        "flows_requested": case.flows,
        "flows_observed": info["flows_observed"],
        "rtt_ms_config": case.rtt_ms,
        "queue_limit": case.queue_limit,
        "duration_s": info["duration_s"],
        "qdisc": QDISC,
        "congestion_control": CONGESTION,
        "qdisc_flows": QDISC_FLOWS,
        "qdisc_tupdate": QDISC_TUPDATE,
        "bottleneck_delay_ms": BOTTLENECK_DELAY_MS,
        "edge_bandwidth": EDGE_BANDWIDTH,
        "time_step_s": TIME_STEP,
        "flow_steady_mbps": info["per_flow_steady_rates"],
        **steady_metrics(curves, list(info["per_flow_steady_rates"].values()),
                             case.capacity_mbit, target),
        **info.get("qdisc", {}),
        "queue_delay_floor_ms": fair_queue_floor_ms(
            {"capacity_mbit": case.capacity_mbit, "flows": case.flows}),
    }
    write_json(run_dir / "metrics.json", metrics)

    dump_dir = run_dir / "dump"
    if dump_dir.exists():
        write_raw_dats(dump_dir, run_dir / "raw")
        if drop_dump:
            safe_rmtree(dump_dir)
    return metrics


def recorded_duration(run_dir: Path, fallback: float) -> float:
    """Duration actually used for this run (for safe resume/extract)."""
    metrics = run_dir / "metrics.json"
    if metrics.exists():
        try:
            value = float(read_json(metrics).get("duration_s", 0))
            if value > 0:
                return value
        except (OSError, ValueError, TypeError):
            pass
    cfg = run_dir / "run_config.json"
    if cfg.exists():
        try:
            cfg_data = read_json(cfg)
            analysis = cfg_data.get("analysis_duration_s")
            if analysis:
                return float(analysis)
            command = cfg_data.get("command") or []
            if "--duration" in command:
                return float(command[command.index("--duration") + 1])
        except (OSError, ValueError, TypeError, IndexError):
            pass
    return fallback


def extract_run(run_dir: Path, case: Case, target: int, run_idx: int,
                duration: float, drop_dump: bool) -> Optional[Dict[str, Any]]:
    dump_dir = run_dir / "dump"
    if not dump_dir.exists():
        LOG.error("  no dump to extract in %s", run_dir)
        return None
    LOG.info("  extracting %s", dump_dir)
    t0 = time.time()
    try:
        curves, per_flow, info = load_run_curves(dump_dir, case, duration, target)
    except Exception as exc:  # noqa: BLE001 - keep the long run alive
        LOG.exception("  extraction failed for %s: %s", run_dir, exc)
        write_json(run_dir / "failure.json", {"error": str(exc), "stage": "extract"})
        return None
    metrics = write_run_artifacts(run_dir, case, target, run_idx, curves, per_flow,
                                  info, drop_dump)
    LOG.info(
        "  extracted in %.1fs: thr=%.3f Mbps  qdelay=%.2f ms  loss=%.2f%%  Jain=%.4f",
        time.time() - t0,
        _nan(metrics.get("throughput_mbps")),
        _nan(metrics.get("queue_delay_ms")),
        _nan(metrics.get("packet_loss_pct")),
        _nan(metrics.get("fairness_jain")),
    )
    return metrics


def average_runs(case_dir: Path, case: Case, target: int,
                 duration: float) -> Optional[Dict[str, Any]]:
    tdir = case_dir / f"target_{target}ms"
    run_dirs = sorted(
        [p for p in tdir.glob("run_*") if (p / "metrics.json").exists()],
        key=lambda p: int(re.search(r"(\d+)$", p.name).group(1)) if re.search(r"(\d+)$", p.name) else 0,
    )
    if not run_dirs:
        LOG.warning("No completed runs in %s", tdir)
        return None

    # Use the duration actually recorded for these runs (important for pilot
    # runs / --plot-only after a shorter run).
    recorded = []
    for rd in run_dirs:
        try:
            recorded.append(float(read_json(rd / "metrics.json").get("duration_s", 0)))
        except (OSError, ValueError, TypeError):
            pass
    recorded = [d for d in recorded if d > 0]
    if recorded:
        duration = max(recorded)

    grid = grid_for(duration)
    avg_dir = ensure_dir(tdir / "averaged")
    run_metrics = [read_json(rd / "metrics.json") for rd in run_dirs]

    averaged: Dict[str, List[float]] = {}
    for name in CURVE_FILES:
        arrays = []
        for rd in run_dirs:
            xs, ys = load_dat(rd / "curves" / f"{name}.dat")
            if not ys:
                continue
            arrays.append(resample(xs, ys, grid))
        if not arrays:
            continue
        values = mean_arrays(arrays)
        averaged[name] = values
        save_dat(avg_dir / f"fq_pie_{CANONICAL_FILE.get(name, name)}.dat", grid, values)

    # Average per-flow curves by flow id.
    flow_arrays: Dict[str, List[List[float]]] = {}
    for rd in run_dirs:
        path = rd / "curves" / "per_flow_throughput.csv"
        if not path.exists():
            continue
        with open(path) as fh:
            reader = csv.reader(fh)
            header = next(reader, [])
            cols = header[1:]
            buckets: Dict[str, List[float]] = {c: [] for c in cols}
            for row in reader:
                if len(row) != len(header):
                    continue
                for col, val in zip(cols, row[1:]):
                    try:
                        buckets[col].append(float(val))
                    except ValueError:
                        buckets[col].append(float("nan"))
            for col, vals in buckets.items():
                flow_arrays.setdefault(col, []).append(vals)

    flow_means: Dict[str, List[float]] = {}
    if flow_arrays:
        flows = sorted(flow_arrays, key=lambda c: _flow_sort_key(c.replace("flow_", "", 1)))
        flow_means = {f: mean_arrays(flow_arrays[f]) for f in flows}
        with open(avg_dir / "per_flow_throughput.csv", "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["time"] + flows)
            for i, t in enumerate(grid):
                writer.writerow([f"{t:.6g}"] + [f"{flow_means[f][i]:.6g}"
                                                for f in flows if i < len(flow_means[f])])

    # Per-flow steady rates: average the per-iteration per-flow rates.  This
    # is exactly the mean of the canonical per-flow netperf_receiver values.
    steady_by_flow: Dict[str, List[float]] = {}
    for m in run_metrics:
        for flow, value in (m.get("flow_steady_mbps") or {}).items():
            if finite(value):
                steady_by_flow.setdefault(flow, []).append(float(value))
    per_flow_steady = [
        sum(vals) / len(vals) for vals in steady_by_flow.values() if vals
    ]
    if not per_flow_steady:
        half = duration / 2.0
        for rates in flow_means.values():
            window = [rates[i] for i in range(min(len(rates), len(grid)))
                      if grid[i] > half]
            if window:
                per_flow_steady.append(sum(window) / len(window))

    metrics: Dict[str, Any] = {
        **steady_metrics(averaged, per_flow_steady or None, case.capacity_mbit,
                         target),
        "queue_delay_floor_ms": fair_queue_floor_ms(
            {"capacity_mbit": case.capacity_mbit, "flows": case.flows}),
        "case": case.name,
        "category": case.category,
        "scenario": case.scenario,
        "target_ms": target,
        "n_runs": len(run_dirs),
        "runs": [rd.name for rd in run_dirs],
        "capacity_mbit": case.capacity_mbit,
        "flows_requested": case.flows,
        "rtt_ms_config": case.rtt_ms,
        "queue_limit": case.queue_limit,
        "flows_observed": len(flow_means),
        "duration_s": duration,
        "time_step_s": TIME_STEP,
        "averaging": "zero-order-hold on common grid, mean across iterations",
    }

    # Per-run steady means -> standard deviation across iterations.
    for key in [
        "throughput_mbps", "total_throughput_mbps", "queue_delay_ms",
        "packet_loss_pct", "fairness_jain", "link_utilization_pct",
    ]:
        vals = [float(m[key]) for m in run_metrics if finite(m.get(key))]
        if len(vals) >= 2:
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
            metrics[key + "_std"] = math.sqrt(var)
        elif vals:
            metrics[key + "_std"] = 0.0

    # Carry the applied qdisc configuration read back from the dumps.
    for m in run_metrics:
        if m.get("qdisc_config_available"):
            metrics.update({k: v for k, v in m.items() if k.startswith("qdisc_")})
            break

    write_json(avg_dir / "metrics.json", metrics)
    # Export plot_targets.py-compatible suffixed files.
    finals = ensure_dir(case_dir / "finals")
    for name in ["netperf_receiver", "backlog", "drops", "packets", "fairness", "rtt"]:
        src = avg_dir / f"fq_pie_{name}.dat"
        if src.exists():
            dst = finals / f"fq_pie_{name}_target_{target}ms.dat"
            shutil.copyfile(src, dst)
    for name in ["queue_delay", "queue_delay_backlog", "service_round",
                 "packet_loss", "link_utilization", "total_throughput"]:
        src = avg_dir / f"fq_pie_{name}.dat"
        if src.exists():
            shutil.copyfile(src, finals / f"fq_pie_{name}_target_{target}ms.dat")

    LOG.info(
        "Averaged %d run(s) for %s target %sms: thr=%.3f Mbps qdelay=%.2f ms loss=%.2f%%",
        len(run_dirs), case.key, target,
        _nan(metrics.get("throughput_mbps")),
        _nan(metrics.get("queue_delay_ms")),
        _nan(metrics.get("packet_loss_pct")),
    )
    return metrics


# ---------------------------------------------------------------------------
# Running NeST
# ---------------------------------------------------------------------------
def raise_nofile_limit() -> None:
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(65535, hard) if hard != resource.RLIM_INFINITY else 65535
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except (ValueError, OSError):
        pass


def cleanup_runtime() -> None:
    for cmd in (
        ["ip", "-all", "netns", "delete"],
        ["pkill", "-f", "iperf3"],
        ["pkill", "-f", "netperf"],
    ):
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False)
        except (OSError, ValueError):
            pass


def qdisc_params(case: Case, target: int) -> Dict[str, str]:
    params: Dict[str, str] = {"target": f"{target}ms"}
    if case.queue_limit is not None:
        params["limit"] = str(case.queue_limit)
    return params


def build_command(case: Case, target: int, slug: str, duration: float) -> List[str]:
    scenario = SCENARIO_BY_NAME[case.scenario]
    n_udp = scenario_udp_flows(scenario, case)
    tcp_rtts = scenario_tcp_rtts(scenario, case)

    cmd = [
        str(NEST_PYTHON),
        str(DUMBBELL),
        "--tcp-flows", str(case.flows),
        "--udp-flows", str(n_udp),
        "--start-gap", f"{scenario_start_gap_ms(scenario, case):g}",
        "--duration", f"{duration:g}",
        "--edge-bandwidth", EDGE_BANDWIDTH,
        "--bottleneck-bandwidth", f"{case.capacity_mbit:g}mbit",
        "--bottleneck-delay", f"{BOTTLENECK_DELAY_MS:g}",
        "--tcp-rtts", ",".join(f"{r:g}" for r in tcp_rtts),
        "--qdisc", QDISC,
        "--qdisc-params", json.dumps(qdisc_params(case, target), separators=(",", ":")),
        "--congestion", CONGESTION,
        "--experiment-name", slug,
        # The evaluation writes its own figures from the JSON dumps; skipping
        # NeST's per-interface plots removes most of the per-run wall time.
        "--no-nest-plots",
    ]

    if n_udp > 0:
        udp_rate = scenario_udp_rate_mbit(scenario, case)
        cmd += [
            "--udp-rates", f"{udp_rate:g}mbit",
            "--udp-rtts", f"{case.rtt_ms:g}",
        ]

    if scenario.pulse:
        low_bw = max(1.0, case.capacity_mbit * scenario.pulse_low_fraction)
        cmd += [
            "--pulsebw",
            "--high-bw", f"{case.capacity_mbit:g}mbit",
            "--low-bw", f"{low_bw:g}mbit",
            "--pulse-interval", f"{scenario.pulse_interval_s:g}",
        ]

    return cmd


def find_dump(slug: str) -> Optional[Path]:
    candidates: List[Path] = []
    for pattern in (f"{slug}(*)_dump", f"{slug}_dump"):
        candidates.extend(NEST_DIR.glob(pattern))
    matches = [p for p in candidates if p.is_dir()]
    matches.sort(key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def run_one(case: Case, target: int, run_idx: int, run_dir: Path,
            args: argparse.Namespace) -> Optional[Dict[str, Any]]:
    slug = f"fqp_{case.scenario}_{case.name}_t{target}ms_r{run_idx}"
    dump_archive = run_dir / "dump"

    if args.force and run_dir.exists():
        safe_rmtree(run_dir)
    ensure_dir(run_dir)

    # Already extracted -> resume, but only if it used the requested duration.
    # Otherwise the averaged curve would mix runs of different lengths.
    analysis_duration = scenario_analysis_duration(case, args.duration)
    if not args.force and (run_dir / "metrics.json").exists():
        done = read_json(run_dir / "metrics.json")
        done_duration = float(done.get("duration_s") or 0.0)
        if abs(done_duration - analysis_duration) <= max(1.0, 0.02 * analysis_duration):
            LOG.info("Resume: %s already complete", run_dir)
            return done
        LOG.info("Rerun: %s used %gs, requested %gs",
                 run_dir, done_duration, analysis_duration)
        safe_rmtree(run_dir)
        ensure_dir(run_dir)

    # Dump archived but not extracted -> extract only (same duration rule).
    if not args.force and dump_archive.exists():
        dumped_duration = recorded_duration(run_dir, analysis_duration)
        if abs(dumped_duration - analysis_duration) <= max(
                1.0, 0.02 * analysis_duration):
            return extract_run(run_dir, case, target, run_idx,
                               dumped_duration,
                               drop_dump=not args.keep_dump)
        LOG.info("Rerun: %s dump used %gs, requested %gs",
                 run_dir, dumped_duration, analysis_duration)
        safe_rmtree(run_dir)
        ensure_dir(run_dir)

    # Remove a stale dump with the same experiment name from a crashed run.
    stale = find_dump(slug)
    if stale is not None:
        LOG.info("Removing stale dump %s", stale)
        safe_rmtree(stale)

    cmd = build_command(case, target, slug, args.duration)
    write_json(run_dir / "run_config.json", {
        "pipeline": PIPELINE_VERSION,
        "case": asdict(case),
        "target_ms": target,
        "run": run_idx,
        "per_flow_duration_s": args.duration,
        "analysis_duration_s": analysis_duration,
        "command": cmd,
        "command_text": " ".join(cmd),
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    LOG.info("Run %s target=%sms repeat=%d/%d", case.key, target, run_idx, args.repeat)
    LOG.info("  %s", " ".join(cmd))

    raise_nofile_limit()
    cleanup_runtime()
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(NEST_DIR), check=False)
    finally:
        cleanup_runtime()
    elapsed = time.time() - started

    if proc.returncode != 0:
        msg = f"NeST exited with code {proc.returncode} after {elapsed:.1f}s"
        LOG.error("  %s", msg)
        write_json(run_dir / "failure.json", {"error": msg, "command": cmd,
                                               "returncode": proc.returncode})
        return None

    dump = find_dump(slug)
    if dump is None:
        msg = f"no dump directory named {slug}*_dump in {NEST_DIR}"
        LOG.error("  %s", msg)
        write_json(run_dir / "failure.json", {"error": msg, "command": cmd})
        return None

    safe_rmtree(dump_archive)
    shutil.move(str(dump), str(dump_archive))
    LOG.info("  dump -> %s (%.1fs)", dump_archive, elapsed)

    return extract_run(run_dir, case, target, run_idx, analysis_duration,
                       drop_dump=not args.keep_dump)


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------
def _setup_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.dpi": 110,
        "savefig.dpi": 150,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "legend.fontsize": 8,
        "font.size": 9,
    })
    return plt


def _target_list(case_dir: Path) -> List[int]:
    out = []
    for p in case_dir.glob("target_*ms/averaged/metrics.json"):
        m = re.search(r"target_(\d+)ms", str(p))
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def _read_avg(case_dir: Path, target: int, name: str) -> Tuple[List[float], List[float]]:
    return load_dat(case_dir / f"target_{target}ms" / "averaged" / f"fq_pie_{name}.dat")


def _case_dict(case_dir: Path) -> Dict[str, Any]:
    path = case_dir / "case.json"
    return read_json(path) if path.exists() else {}


def derive_case_series(case_dir: Path, target: int) -> Dict[str, Tuple[List[float], List[float]]]:
    """Same derivation order as scripts/plot_targets.py::derive_series."""
    meta = _case_dict(case_dir)
    capacity = float(meta.get("capacity_mbit", 100.0))
    flows = float(meta.get("flows", 100))
    out: Dict[str, Tuple[List[float], List[float]]] = {}

    thr = None
    for name in ("throughput", "netperf_receiver"):
        xs, ys = _read_avg(case_dir, target, name)
        if xs:
            thr = (xs, ys)
            break
    if thr:
        out["throughput"] = thr

    xs, ys = _read_avg(case_dir, target, "queue_delay")
    if xs:
        out["queue_delay"] = (xs, ys)
    else:
        xs, ys = _read_avg(case_dir, target, "backlog")
        if xs:
            out["queue_delay"] = (xs, [v * 8.0 / (capacity * 1e6) * 1000.0 if capacity > 0 else 0.0
                                       for v in ys])

    xs, ys = _read_avg(case_dir, target, "packet_loss")
    if xs:
        out["packet_loss"] = (xs, ys)
    else:
        xd, yd = _read_avg(case_dir, target, "drops")
        xp, yp = _read_avg(case_dir, target, "packets")
        n = min(len(xd), len(yp))
        if n:
            out["packet_loss"] = (xd[:n], [yd[i] / yp[i] * 100.0 if yp[i] > 0 else 0.0
                                           for i in range(n)])

    xs, ys = _read_avg(case_dir, target, "fairness")
    if xs:
        out["fairness"] = (xs, ys)

    if thr:
        xs, ys = thr
        out["link_utilization"] = (xs, [v * flows / capacity * 100.0 if capacity > 0 else 0.0
                                        for v in ys])

    xs, ys = _read_avg(case_dir, target, "total_throughput")
    if xs:
        out["total_throughput"] = (xs, ys)

    xs, ys = _read_avg(case_dir, target, "rtt")
    if xs:
        out["rtt"] = (xs, ys)

    return out


def _steady(series: Dict[str, Tuple[List[float], List[float]]], key: str) -> float:
    s = series.get(key)
    if not s or not s[1]:
        return float("nan")
    v = mean_tail(s[1])
    return v if v is not None else float("nan")


def _clip(series: Dict[str, Tuple[List[float], List[float]]], tmax: float) -> None:
    for key, (xs, ys) in list(series.items()):
        pts = [(x, y) for x, y in zip(xs, ys) if x <= tmax]
        series[key] = ([p[0] for p in pts], [p[1] for p in pts])


def fair_queue_floor_ms(meta: Dict[str, Any]) -> Optional[float]:
    """Lower bound on FQ-PIE per-flow queue delay in this case.

    FQ-PIE schedules one packet per flow per round, so a packet cannot be
    dequeued before the other active flows have each sent a packet.  One
    round-robin cycle therefore costs ``flows * MTU / capacity``; PIE cannot
    regulate the standing delay below that, whatever its ``target`` is.
    """
    try:
        capacity = float(meta.get("capacity_mbit") or 0.0)
        flows = float(meta.get("flows") or 0.0)
    except (TypeError, ValueError):
        return None
    if capacity <= 0 or flows <= 0:
        return None
    return flows * MTU_BYTES * 8.0 / (capacity * 1e6) * 1000.0


def floor_note(meta: Dict[str, Any], targets: Sequence[int]) -> Optional[str]:
    """Explain which of the requested targets are below the queueing floor."""
    floor = fair_queue_floor_ms(meta)
    if floor is None:
        return None
    below = [t for t in targets if t < floor]
    text = (f"Fair-queue round-robin floor = {float(meta.get('flows', 100)):.0f} flows "
            f"x 1500 B / {float(meta.get('capacity_mbit', 100)):g} Mbit = "
            f"{floor:.1f} ms")
    if below:
        text += (f"; target(s) {', '.join(f'{t} ms' for t in below)} are below "
                 "this floor and cannot be reached - FQ-PIE cannot regulate the "
                 "per-flow queue below one service round.")
    return text


def conclusion_text(meta: Dict[str, Any], key: str) -> str:
    case = meta.get("name", "")
    cap = meta.get("capacity_mbit", 100)
    flows = meta.get("flows", 100)
    if key == "throughput":
        return (f"{case}: per-flow receiving rate (canonical netperf_receiver). "
                f"With {flows:.0f} flows on a {cap:g} Mbit bottleneck the "
                f"capacity-bound value is ~{cap / max(flows, 1):.3f} Mbps per flow.")
    if key == "queue_delay":
        return (f"{case}: queue delay is measured on the bottleneck fq_pie qdisc "
                f"as the PIE-regulated per-flow queue "
                "(backlog minus the one-packet-per-flow service batch) x 8 / "
                f"{cap:g} Mbit. It is expected to sit close to the configured "
                "target; the raw backlog/capacity value is kept as "
                "queue_delay_backlog_ms for reference.")
    if key == "packet_loss":
        return (f"{case}: loss = drops / packets x 100 from the tc qdisc counters. "
                "Small targets react early, large targets absorb bursts.")
    if key == "fairness":
        return (f"{case}: real Jain index across the {flows:.0f} per-flow receiving rates "
                "(1.0 = perfectly fair). FQ-PIE keeps per-flow queues, so this stays high.")
    if key == "link_utilization":
        return (f"{case}: aggregate utilisation = per-flow x {flows:.0f} / {cap:g} Mbit. "
                "It stays near 100% when the bottleneck is saturated.")
    return ""


def _draw_floor(ax, meta: Dict[str, Any], color: str = "#111111",
                linewidth: float = 1.3) -> Optional[float]:
    """Draw the fair-queue round-robin floor of the case, if known."""
    floor = fair_queue_floor_ms(meta)
    if floor is None:
        return None
    ax.axhline(floor, color=color, linestyle=":", linewidth=linewidth,
               label=f"fair-queue floor ({floor:.1f} ms)")
    return floor


def _overlay_plot(plt, case_dir: Path, meta: Dict[str, Any], targets: List[int],
                  series: Dict[int, Dict[str, Tuple[List[float], List[float]]]],
                  key: str, filename: str, ylabel: str, time_axis: bool = True,
                  ylim: Optional[Tuple[float, float]] = None,
                  note: Optional[str] = None, floor: bool = False) -> None:
    fig, ax = plt.subplots(figsize=(10.2, 6.0))
    colors = plt.cm.viridis([i / max(1, len(targets) - 1) for i in range(len(targets))])
    any_line = False
    for color, t in zip(colors, targets):
        s = series.get(t, {}).get(key)
        if not s or not s[0]:
            continue
        ax.plot(s[0], s[1], color=color, linewidth=1.5, label=f"target {t}ms")
        any_line = True
    if not any_line:
        plt.close(fig)
        return
    ax.set_xlabel("Time (s)" if time_axis else "FQ-PIE target (ms)")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{meta.get('name', '')} - {ylabel} vs target")
    if ylim:
        ax.set_ylim(*ylim)
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=min(len(targets) + 1, 4), fontsize=8)
    if note:
        fig.text(0.5, 0.015, note, ha="center", va="bottom", fontsize=8,
                 color="#333333", wrap=True)
        fig.subplots_adjust(bottom=0.20)
    fig.tight_layout(rect=(0, 0.05 if note else 0, 1, 1))
    out = case_dir / "plots" / filename
    ensure_dir(out.parent)
    fig.savefig(out)
    plt.close(fig)
    LOG.info("  saved %s", out)


def _five_metric_overview(plt, case_dir: Path, meta: Dict[str, Any], targets: List[int],
                          series: Dict[int, Dict[str, Tuple[List[float], List[float]]]],
                          filename: str = "5metrics_vs_target.png") -> None:
    fig, axes = plt.subplots(3, 2, figsize=(12.5, 8.2))
    for ax, key in zip(axes.flat, METRICS_5):
        vals = [_steady(series.get(t, {}), key) for t in targets]
        ax.plot(targets, vals, marker="o", linewidth=1.6, color="#4C72B0")
        if len(targets) > 1 and max(targets) / max(1, min(targets)) >= 10:
            ax.set_xscale("log")
            ax.set_xticks(targets)
            ax.set_xticklabels([f"{t:g}" for t in targets])
            ax.minorticks_off()
        ax.set_xlabel("FQ-PIE target (ms)")
        ax.set_ylabel(TITLES[key])
        ax.set_title(TITLES[key])
        ax.grid(True, alpha=0.3, which="both")
        if key == "fairness":
            ax.set_ylim(0.5, 1.02)
        if key == "link_utilization":
            ax.set_ylim(0, 115)
        for t, v in zip(targets, vals):
            if finite(v):
                ax.annotate(f"{v:.2f}", (t, v), textcoords="offset points",
                            xytext=(0, 6), ha="center", fontsize=7)
    ax = axes.flat[5]
    ax.axis("off")
    ax.text(0.03, 0.92, "Steady state = mean of the last 50% of the trace",
            fontsize=10, transform=ax.transAxes)
    ax.text(0.03, 0.78, f"Case: {meta.get('name', '')} ({meta.get('description', '')})",
            fontsize=9, transform=ax.transAxes)
    ax.text(0.03, 0.64, f"Targets: {targets} ms", fontsize=9, transform=ax.transAxes)
    ax.text(0.03, 0.50, f"{meta.get('flows', 100)} TCP flows, cubic, FQ-PIE",
            fontsize=9, transform=ax.transAxes)
    ax.text(0.03, 0.36, f"{meta.get('capacity_mbit', 100):g} Mbit bottleneck, "
                        f"RTT {meta.get('rtt_ms', 100):g} ms", fontsize=9,
            transform=ax.transAxes)
    n_runs = meta.get("n_runs", "?")
    ax.text(0.03, 0.22, f"{n_runs} iteration(s) averaged", fontsize=9,
            transform=ax.transAxes)
    fig.suptitle(f"{meta.get('name', '')} - 5 metrics vs FQ-PIE target (steady state)")
    fig.tight_layout()
    out = case_dir / "plots" / filename
    fig.savefig(out)
    plt.close(fig)
    LOG.info("  saved %s", out)


def _bar_overview(plt, case_dir: Path, meta: Dict[str, Any], targets: List[int],
                  series: Dict[int, Dict[str, Tuple[List[float], List[float]]]]) -> None:
    def draw(ax, key: str) -> None:
        vals = [_steady(series.get(t, {}), key) for t in targets]
        bars = ax.bar(range(len(targets)), vals, color="#4C72B0", width=0.62)
        ax.set_xticks(range(len(targets)))
        ax.set_xticklabels([f"{t}ms" for t in targets])
        ax.set_ylabel(TITLES[key])
        ax.set_title(TITLES[key])
        ax.grid(True, axis="y", alpha=0.3)
        for rect, v in zip(bars, vals):
            if finite(v):
                ax.text(rect.get_x() + rect.get_width() / 2, v, f"{v:.2f}",
                        ha="center", va="bottom", fontsize=7)
        if key == "fairness":
            ax.set_ylim(0.5, 1.02)
        if key == "link_utilization":
            ax.set_ylim(0, 115)

    for key in METRICS_5:
        fig, ax = plt.subplots(figsize=(9.2, 5.6))
        draw(ax, key)
        ax.set_xlabel("FQ-PIE target (ms)")
        fig.suptitle(f"{meta.get('name', '')} - {TITLES[key]} vs target (steady state)")
        fig.tight_layout()
        fig.savefig(case_dir / "plots" / f"{key}_bar_vs_target.png")
        plt.close(fig)

    fig, axes = plt.subplots(3, 2, figsize=(12.5, 8.2))
    for ax, key in zip(axes.flat, METRICS_5):
        draw(ax, key)
        ax.set_xlabel("FQ-PIE target (ms)")
    axes.flat[5].axis("off")
    axes.flat[5].text(0.03, 0.9, "Bars = steady-state mean (last 50%)", fontsize=10,
                      transform=axes.flat[5].transAxes)
    axes.flat[5].text(0.03, 0.72, f"Targets: {targets} ms", fontsize=9,
                      transform=axes.flat[5].transAxes)
    fig.suptitle(f"{meta.get('name', '')} - 5 metrics vs target (bars)")
    fig.tight_layout()
    fig.savefig(case_dir / "plots" / "5metrics_bars_vs_target.png")
    plt.close(fig)
    LOG.info("  saved bar charts for %s", meta.get("name", ""))


BULK_COLORS = [
    "#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


def _achieved_vs_target(plt, case_dir: Path, meta: Dict[str, Any],
                        targets: List[int]) -> None:
    """Measured queue delay vs the configured target (y = x reference)."""
    pts: List[Tuple[float, float]] = []
    raw_pts: List[Tuple[float, float]] = []
    for t in targets:
        path = case_dir / f"target_{t}ms" / "averaged" / "metrics.json"
        if not path.exists():
            continue
        m = read_json(path)
        qd = m.get("queue_delay_ms")
        raw = m.get("queue_delay_backlog_ms")
        if finite(qd):
            pts.append((float(t), float(qd)))
        if finite(raw):
            raw_pts.append((float(t), float(raw)))
    if not pts:
        return
    values = [v for _, v in pts] + [t for t, _ in pts] + [v for _, v in raw_pts]
    lo = max(0.0, min(values) * 0.9)
    hi = max(values) * 1.05
    fig, ax = plt.subplots(figsize=(7.8, 5.6))
    ax.plot([lo, hi], [lo, hi], "k--", linewidth=1.2, label="y = target")
    ax.plot([t for t, _ in pts], [v for _, v in pts], color="#4C72B0",
            linewidth=1.6, marker="o", label="PIE per-flow queue delay")
    if raw_pts:
        ax.scatter([t for t, _ in raw_pts], [v for _, v in raw_pts],
                   color="#C44E52", marker="x", s=55,
                   label="raw backlog / capacity")
    ax.set_xlabel("Configured FQ-PIE target (ms)")
    ax.set_ylabel("Measured queue delay (ms)")
    ax.set_title(f"{meta.get('name', case_dir.name)} - achieved vs target")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(case_dir / "plots" / "achieved_vs_target.png")
    plt.close(fig)


def _bulk_time_series(plt, case_dir: Path, meta: Dict[str, Any], targets: List[int],
                      series: Dict[int, Dict[str, Tuple[List[float], List[float]]]],
                      key: str, filename: str, ylabel: str, duration: float,
                      x_label: str = "Time (in Seconds)",
                      note: Optional[str] = None,
                      ylim_max: Optional[float] = None) -> None:
    """bulk_plot.py-style time series: one coloured line per FQ-PIE target."""
    fig, ax = plt.subplots(figsize=(10.0, 6.0))
    plotted = False
    for i, t in enumerate(targets):
        srs = series.get(t, {}).get(key)
        if not srs or not srs[0]:
            continue
        ax.plot(srs[0], srs[1], color=BULK_COLORS[i % len(BULK_COLORS)],
                linewidth=2.2, label=f"FQ-PIE target {t} ms")
        plotted = True
    if not plotted:
        plt.close(fig)
        return
    ax.set_xlabel(x_label, fontsize=20)
    ax.set_ylabel(ylabel, fontsize=20)
    ax.tick_params(axis="both", labelsize=15, direction="in")
    ax.set_xlim(0, duration)
    if ylim_max is not None and ylim_max > 0:
        ax.set_ylim(0, ylim_max)
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.legend(loc="upper right", fontsize=13, frameon=False)
    ax.set_title(f"{meta.get('name', '')} - {ylabel} over time", fontsize=17)
    if note:
        fig.text(0.5, -0.02, textwrap.fill(note, 110), ha="center", va="top",
                 fontsize=10, color="#333333")
    fig.tight_layout()
    out = case_dir / "plots" / filename
    ensure_dir(out.parent)
    fig.savefig(out, dpi=250, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    LOG.info("  saved %s", out)


def _percentile_bars(plt, case_dir: Path, meta: Dict[str, Any], targets: List[int]) -> None:
    """bulk_plot.py-style percentile bars: x = percentile, one bar per target."""
    avg_metrics: Dict[int, Dict[str, Any]] = {}
    for t in targets:
        path = case_dir / f"target_{t}ms" / "averaged" / "metrics.json"
        if path.exists():
            avg_metrics[t] = read_json(path)
    if not avg_metrics:
        return
    targets = sorted(avg_metrics)

    specs = [
        ("throughput", "Throughput (in Mbps)", "throughput_percentile.png",
         [("Median", "throughput_p50_mbps"), ("90th", "throughput_p90_mbps"),
          ("95th", "throughput_p95_mbps"), ("99th", "throughput_p99_mbps")]),
        ("queue_delay", "Queue delay (in ms)", "queue_delay_percentile.png",
         [("Median", "queue_delay_p50_ms"), ("90th", "queue_delay_p90_ms"),
          ("95th", "queue_delay_p95_ms"), ("99th", "queue_delay_p99_ms")]),
    ]

    # Make sure per-flow throughput percentiles exist (older metrics.json).
    for t in targets:
        if "throughput_p50_mbps" not in avg_metrics[t]:
            xs, ys = _read_avg(case_dir, t, "throughput")
            ss = _steady_window(ys)
            avg_metrics[t]["throughput_p50_mbps"] = percentile(ss, 50)
            avg_metrics[t]["throughput_p90_mbps"] = percentile(ss, 90)
            avg_metrics[t]["throughput_p95_mbps"] = percentile(ss, 95)
            avg_metrics[t]["throughput_p99_mbps"] = percentile(ss, 99)

    for slug, ylabel, filename, groups in specs:
        n = max(1, len(targets))
        width = 0.5 if n == 1 else min(0.8 / n, 0.28)
        x = list(range(len(groups)))
        fig, ax = plt.subplots(figsize=(9.5, 5.8))
        for ti, t in enumerate(targets):
            values = [_nan(avg_metrics[t].get(key)) for _label, key in groups]
            offset = (ti - (n - 1) / 2.0) * width
            bars = ax.bar([xi + offset for xi in x], values, width=width,
                          color=BULK_COLORS[ti % len(BULK_COLORS)],
                          label=f"target {t} ms")
            ax.bar_label(bars, fmt="%.2f", padding=3, fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels([label for label, _key in groups])
        ax.set_xlabel("Percentiles", fontsize=16)
        ax.set_ylabel(ylabel, fontsize=16)
        ax.tick_params(axis="both", labelsize=13)
        ax.grid(True, axis="y", linestyle="--", alpha=0.5)
        ax.legend(title="FQ-PIE target", fontsize=11, frameon=False,
                  loc="upper center", bbox_to_anchor=(0.5, -0.16),
                  ncol=min(n, 4))
        ax.set_title(f"{meta.get('name', '')} - {ylabel} percentiles",
                     fontsize=15)
        fig.tight_layout()
        fig.savefig(case_dir / "plots" / filename, dpi=250,
                    bbox_inches="tight", pad_inches=0.15)
        plt.close(fig)
        LOG.info("  saved %s", case_dir / "plots" / filename)


def _cdf_plots(plt, case_dir: Path, meta: Dict[str, Any], targets: List[int],
               series: Dict[int, Dict[str, Tuple[List[float], List[float]]]]) -> None:
    """bulk_plot.py-style CDFs for throughput and queue delay."""
    specs = [
        ("throughput", "Throughput (in Mbps)", "throughput_cdf.png"),
        ("queue_delay", "Queue delay (in ms)", "queue_delay_cdf.png"),
    ]
    for key, xlabel, filename in specs:
        fig, ax = plt.subplots(figsize=(9.5, 5.8))
        plotted = False
        for i, t in enumerate(targets):
            srs = series.get(t, {}).get(key)
            values = sorted(float(v) for v in srs[1] if finite(v)) if srs else []
            if len(values) < 2:
                continue
            n = len(values)
            ys = [(j + 1) / n for j in range(n)]
            ax.plot(values, ys, color=BULK_COLORS[i % len(BULK_COLORS)],
                    linewidth=2.0, label=f"target {t} ms")
            plotted = True
        if not plotted:
            plt.close(fig)
            continue
        ax.set_xlabel(xlabel, fontsize=17)
        ax.set_ylabel("CDF", fontsize=17)
        ax.set_ylim(0, 1.02)
        ax.tick_params(axis="both", labelsize=13)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend(loc="lower right", fontsize=12, frameon=False)
        ax.set_title(f"{meta.get('name', '')} - CDF of {xlabel}", fontsize=15)
        fig.tight_layout()
        fig.savefig(case_dir / "plots" / filename, dpi=250,
                    bbox_inches="tight", pad_inches=0.15)
        plt.close(fig)
        LOG.info("  saved %s", case_dir / "plots" / filename)


def _per_flow_plots(plt, case_dir: Path, meta: Dict[str, Any], targets: List[int]) -> None:
    avail = [t for t in targets
             if (case_dir / f"target_{t}ms" / "averaged" / "per_flow_throughput.csv").exists()]
    if not avail:
        return
    ncols = min(3, len(avail))
    nrows = int(math.ceil(len(avail) / ncols))
    width = 10.0 if ncols == 1 else 5.0 * ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, 3.6 * nrows),
                             sharex=True, squeeze=False)
    for ax, t in zip(axes.flat, avail):
        path = case_dir / f"target_{t}ms" / "averaged" / "per_flow_throughput.csv"
        with open(path) as fh:
            reader = csv.reader(fh)
            header = next(reader, [])
            cols = header[1:]
            data: Dict[str, List[float]] = {c: [] for c in cols}
            times: List[float] = []
            for row in reader:
                if len(row) != len(header):
                    continue
                times.append(float(row[0]))
                for col, val in zip(cols, row[1:]):
                    data[col].append(float(val))
        # The CSV stores the reconstructed per-flow rate (NeST/iperf3 reports
        # sparse 128 KiB TCP delivery samples).  Apply a short display-only
        # rolling mean so the final short reporting intervals do not draw
        # one-bin spikes; steady-state metrics are computed from bytes.
        def smooth(values: List[float], window: int = 5) -> List[float]:
            # Rolling median rejects the single-bin spikes caused by iperf3's
            # short final reporting intervals without shifting the level.
            out = []
            for i in range(len(values)):
                lo = max(0, i - window + 1)
                seg = sorted(v for v in values[lo:i + 1] if finite(v))
                if not seg:
                    out.append(float("nan"))
                else:
                    out.append(seg[len(seg) // 2])
            return out

        smoothed = {col: smooth(data[col]) for col in cols}
        for col in cols:
            ax.plot(times, smoothed[col], linewidth=0.6, alpha=0.30, color="#4C72B0")
        if cols:
            mean_curve = mean_arrays([smoothed[c] for c in cols])
            ax.plot(times[:len(mean_curve)], mean_curve, color="#C44E52",
                    linewidth=2.0, label="mean flow")
        ax.set_title(f"FQ-PIE target {t} ms - {len(cols)} TCP flows", fontsize=13)
        ax.set_ylabel("Throughput (in Mbps)", fontsize=12)
        ax.set_xlabel("Time (in Seconds)", fontsize=12)
        ax.tick_params(labelsize=10)
        ax.grid(True, alpha=0.25, linestyle="--")
        ax.set_xlim(left=0)
        ax.legend(fontsize=9, frameon=False)
    for ax in list(axes.flat)[len(avail):]:
        ax.axis("off")
    fig.suptitle(f"{meta.get('name', '')} - throughput vs time per flow",
                 fontsize=15)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(case_dir / "plots" / "per_flow_throughput_vs_time.png",
                dpi=250, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    LOG.info("  saved per-flow throughput")


def plot_case(case_dir: Path, case: Case, targets: Sequence[int]) -> None:
    plt = _setup_matplotlib()
    ensure_dir(case_dir / "plots")
    meta = _case_dict(case_dir)
    targets = [t for t in sorted(targets)
               if (case_dir / f"target_{t}ms" / "averaged" / "metrics.json").exists()]
    if not targets:
        return
    durations = []
    for t in targets:
        p = case_dir / f"target_{t}ms" / "averaged" / "metrics.json"
        try:
            tm = read_json(p)
            durations.append(float(tm.get("duration_s", 0)))
            for key in ("n_runs", "flows_requested", "capacity_mbit",
                        "rtt_ms_config", "queue_limit", "duration_s"):
                if key in tm:
                    meta.setdefault(key, tm[key])
        except (OSError, ValueError, TypeError):
            pass
    if "n_runs" in meta:
        meta["n_runs"] = max(
            read_json(case_dir / f"target_{t}ms" / "averaged" / "metrics.json").get("n_runs", 0)
            for t in targets
            if (case_dir / f"target_{t}ms" / "averaged" / "metrics.json").exists()
        )
    meta.setdefault("flows", meta.get("flows_requested", 100))
    meta.setdefault("rtt_ms", meta.get("rtt_ms_config", 100))
    durations = [d for d in durations if d > 0]
    duration = max(durations) if durations else float(meta.get("duration_s", DEFAULT_DURATION))
    series: Dict[int, Dict[str, Tuple[List[float], List[float]]]] = {}
    for t in targets:
        s = derive_case_series(case_dir, t)
        _clip(s, duration)
        series[t] = s

    for key in METRICS_5:
        ymax = None
        if key == "link_utilization":
            ymax = (0, 115)
        if key == "fairness":
            ymax = (0.5, 1.02)
        _overlay_plot(
            plt, case_dir, meta, targets, series, key,
            f"{key}_vs_target.png", TITLES[key], ylim=ymax,
            note=conclusion_text(meta, key),
            floor=False,
        )

    # bulk_plot.py-style time series: time vs throughput / queue delay,
    # one coloured line per FQ-PIE target.
    _bulk_time_series(plt, case_dir, meta, targets, series, "throughput",
                      "throughput_vs_time.png", "Throughput (in Mbps)", duration)
    _bulk_time_series(plt, case_dir, meta, targets, series, "total_throughput",
                      "total_throughput_vs_time.png",
                      "Total throughput (in Mbps)", duration)
    qd_p95: List[float] = []
    for t in targets:
        p = case_dir / f"target_{t}ms" / "averaged" / "metrics.json"
        if not p.exists():
            continue
        v = read_json(p).get("queue_delay_p95_ms")
        if finite(v):
            qd_p95.append(float(v))
    qd_ylim = (1.35 * max(qd_p95)) if qd_p95 else None
    _bulk_time_series(plt, case_dir, meta, targets, series, "queue_delay",
                      "queue_delay_vs_time.png", "Queue delay (in ms)", duration,
                      note=("Steady-state queue delay at the bottleneck fq_pie "
                            "qdisc. The y-axis is limited to the steady-state "
                            "range, so the initial TCP ramp-up transient is "
                            "clipped."),
                      ylim_max=qd_ylim)

    _five_metric_overview(plt, case_dir, meta, targets, series)
    _bar_overview(plt, case_dir, meta, targets, series)
    _achieved_vs_target(plt, case_dir, meta, targets)
    _percentile_bars(plt, case_dir, meta, targets)
    _cdf_plots(plt, case_dir, meta, targets, series)
    _per_flow_plots(plt, case_dir, meta, targets)


# ---------------------------------------------------------------------------
# Category / summary plots
# ---------------------------------------------------------------------------
def _case_meta(case_dir: Path) -> Dict[str, Any]:
    meta = _case_dict(case_dir)
    targets = _target_list(case_dir)
    if not targets:
        return meta
    last = case_dir / f"target_{targets[-1]}ms" / "averaged" / "metrics.json"
    if last.exists():
        m = read_json(last)
        meta.setdefault("flows", m.get("flows_requested", 100))
        meta.setdefault("capacity_mbit", m.get("capacity_mbit", 100))
        meta.setdefault("rtt_ms", m.get("rtt_ms_config", 100))
    return meta


def plot_category(category_dir: Path, case_dirs: List[Path], targets: Sequence[int]) -> None:
    plt = _setup_matplotlib()
    out_dir = ensure_dir(category_dir / "plots")
    data: Dict[str, Dict[int, Dict[str, Tuple[List[float], List[float]]]]] = {}
    for p in case_dirs:
        data[p.name] = {t: derive_case_series(p, t) for t in targets
                        if (p / f"target_{t}ms" / "averaged" / "metrics.json").exists()}
    if not any(data.values()):
        return
    colors = ["#4C72B0", "#C44E52", "#55A868", "#8172B3", "#937860", "#DA8BC3",
              "#8C8C8C", "#CCB974"]

    fig, axes = plt.subplots(3, 2, figsize=(12.5, 8.2))
    for ax, key in zip(axes.flat, METRICS_5):
        for ci, p in enumerate(case_dirs):
            vals = []
            tlist = []
            for t in sorted(data[p.name]):
                v = _steady(data[p.name][t], key)
                if finite(v):
                    tlist.append(t)
                    vals.append(v)
            if vals:
                ax.plot(tlist, vals, marker="o", linewidth=1.5,
                        color=colors[ci % len(colors)], label=p.name)
        if len(targets) > 1 and max(targets) / max(1, min(targets)) >= 10:
            ax.set_xscale("log")
            ax.set_xticks(list(targets))
            ax.set_xticklabels([f"{t:g}" for t in targets])
            ax.minorticks_off()
        ax.set_xlabel("FQ-PIE target (ms)")
        ax.set_ylabel(TITLES[key])
        ax.set_title(TITLES[key])
        ax.grid(True, alpha=0.3, which="both")
        if key == "fairness":
            ax.set_ylim(0.5, 1.02)
        if key == "link_utilization":
            ax.set_ylim(0, 115)
    axes.flat[5].axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    if handles:
        axes.flat[5].legend(handles, labels, loc="center", fontsize=9,
                            frameon=False, ncol=2)
    fig.suptitle(f"{category_dir.parent.name}/{category_dir.name} - 5 metrics vs target by case")
    fig.tight_layout()
    fig.savefig(out_dir / "5metrics_by_case.png")
    plt.close(fig)
    for key in METRICS_5:
        fig, ax = plt.subplots(figsize=(9.5, 5.8))
        for ci, p in enumerate(case_dirs):
            tlist, vals = [], []
            for t in sorted(data[p.name]):
                v = _steady(data[p.name][t], key)
                if finite(v):
                    tlist.append(t)
                    vals.append(v)
            if vals:
                ax.plot(tlist, vals, marker="o", linewidth=1.6,
                        color=colors[ci % len(colors)], label=p.name)
        if len(targets) > 1 and max(targets) / max(1, min(targets)) >= 10:
            ax.set_xscale("log")
            ax.set_xticks(list(targets))
            ax.set_xticklabels([f"{t:g}" for t in targets])
            ax.minorticks_off()
        ax.set_xlabel("FQ-PIE target (ms)")
        ax.set_ylabel(TITLES[key])
        ax.set_title(f"{category_dir.parent.name}/{category_dir.name} - {TITLES[key]} vs target")
        ax.grid(True, alpha=0.3, which="both")
        if key == "fairness":
            ax.set_ylim(0.5, 1.02)
        if key == "link_utilization":
            ax.set_ylim(0, 115)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out_dir / f"{key}_by_case.png")
        plt.close(fig)
    LOG.info("Saved category plots in %s", out_dir)


def _case_label(case_dir: Path) -> str:
    """scenario/category/case label for the nested output layout."""
    parts = [case_dir.parent.parent.name, case_dir.parent.name, case_dir.name]
    return "/".join(p for p in parts if p)


def _all_case_dirs(output_root: Path) -> List[Path]:
    out = []
    for meta in sorted(output_root.glob("*/*/*/case.json")):
        case_dir = meta.parent
        if not _target_list(case_dir):
            continue
        out.append(case_dir)
    return out


def collect_rows(output_root: Path,
                 allowed_targets: Optional[Sequence[int]] = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    allowed = set(int(t) for t in allowed_targets) if allowed_targets else None
    for case_dir in _all_case_dirs(output_root):
        for t in _target_list(case_dir):
            if allowed is not None and t not in allowed:
                continue
            path = case_dir / f"target_{t}ms" / "averaged" / "metrics.json"
            if not path.exists():
                continue
            m = read_json(path)
            rows.append({
                "scenario": m.get("scenario", ""),
                "category": m.get("category", ""),
                "case": m.get("case", case_dir.name),
                "target_ms": t,
                "capacity_mbit": m.get("capacity_mbit"),
                "flows": m.get("flows_requested"),
                "rtt_ms": m.get("rtt_ms_config"),
                "queue_limit": m.get("queue_limit"),
                "n_runs": m.get("n_runs"),
                "throughput_mbps": m.get("throughput_mbps"),
                "total_throughput_mbps": m.get("total_throughput_mbps"),
                "queue_delay_ms": m.get("queue_delay_ms"),
                "queue_delay_backlog_ms": m.get("queue_delay_backlog_ms"),
                "queue_delay_service_round_ms": m.get("queue_delay_service_round_ms"),
                "queue_delay_target_ratio": m.get("queue_delay_target_ratio"),
                "queue_delay_backlog_target_ratio": m.get(
                    "queue_delay_backlog_target_ratio"),
                "qdisc_target_ms": m.get("qdisc_target_ms"),
                "qdisc_limit": m.get("qdisc_limit"),
                "qdisc_flows": m.get("qdisc_flows"),
                "qdisc_quantum_bytes": m.get("qdisc_quantum_bytes"),
                "queue_delay_source": m.get("queue_delay_source"),
                "queue_delay_floor_ms": (
                    m.get("queue_delay_floor_ms")
                    if m.get("queue_delay_floor_ms") is not None
                    else fair_queue_floor_ms(
                        {"capacity_mbit": m.get("capacity_mbit"),
                         "flows": m.get("flows_requested")})),
                "queue_delay_p50_ms": m.get("queue_delay_p50_ms"),
                "queue_delay_p85_ms": m.get("queue_delay_p85_ms"),
                "queue_delay_p90_ms": m.get("queue_delay_p90_ms"),
                "queue_delay_p95_ms": m.get("queue_delay_p95_ms"),
                "queue_delay_p99_ms": m.get("queue_delay_p99_ms"),
                "packet_loss_pct": m.get("packet_loss_pct"),
                "fairness_jain": m.get("fairness_jain"),
                "link_utilization_pct": m.get("link_utilization_pct"),
            })
    return rows


def write_results_csv(output_root: Path, rows: Sequence[Dict[str, Any]]) -> Path:
    out = ensure_dir(output_root / "summary") / "results.csv"
    fields = list(rows[0].keys()) if rows else [
        "scenario", "category", "case", "target_ms", "capacity_mbit", "flows", "rtt_ms",
        "queue_limit", "n_runs", "throughput_mbps", "total_throughput_mbps",
        "queue_delay_ms", "queue_delay_backlog_ms",
        "queue_delay_service_round_ms", "queue_delay_target_ratio",
        "queue_delay_backlog_target_ratio", "qdisc_target_ms", "qdisc_limit",
        "qdisc_flows", "qdisc_quantum_bytes", "queue_delay_source",
        "queue_delay_floor_ms", "queue_delay_p50_ms",
        "queue_delay_p85_ms",
        "queue_delay_p90_ms",
        "queue_delay_p95_ms", "queue_delay_p99_ms", "packet_loss_pct",
        "fairness_jain", "link_utilization_pct",
    ]
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return out


def _case_duration(case_dir: Path, targets: Sequence[int]) -> float:
    for t in sorted(targets, reverse=True):
        path = case_dir / f"target_{t}ms" / "averaged" / "metrics.json"
        if not path.exists():
            continue
        try:
            value = float(read_json(path).get("duration_s", 0))
            if value > 0:
                return value
        except (OSError, ValueError, TypeError):
            pass
    return DEFAULT_DURATION


def _case_series(case_dir: Path, targets: Sequence[int]
                 ) -> Dict[int, Dict[str, Tuple[List[float], List[float]]]]:
    return {
        t: derive_case_series(case_dir, t)
        for t in targets
        if (case_dir / f"target_{t}ms" / "averaged" / "metrics.json").exists()
    }


def _summary_grid(plt, case_dirs: List[Path], figsize_row: float, title: str):
    n = len(case_dirs)
    ncols = 1 if n == 1 else 2
    nrows = max(1, int(math.ceil(n / ncols)))
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(7.8 * ncols, figsize_row * nrows),
                             squeeze=False)
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    fig.suptitle(title, fontsize=15)
    return fig, axes


def summary_time_series(plt, out_dir: Path, case_dirs: List[Path],
                        targets: Sequence[int], key: str, ylabel: str,
                        filename: str) -> None:
    """summary: time vs metric, one line per FQ-PIE target, one panel per case."""
    fig, axes = _summary_grid(
        plt, case_dirs, 3.9,
        f"All cases - {ylabel} over time (one line per FQ-PIE target)")
    for ax, case_dir in zip(axes.flat, case_dirs):
        series = _case_series(case_dir, targets)
        if not series:
            ax.axis("off")
            continue
        duration = _case_duration(case_dir, sorted(series))
        for i, t in enumerate(sorted(series)):
            srs = series[t].get(key)
            if not srs or not srs[0]:
                continue
            ax.plot(srs[0], srs[1], color=BULK_COLORS[i % len(BULK_COLORS)],
                    linewidth=1.8, label=f"{t} ms")
        ax.set_xlim(0, duration)
        if key == "queue_delay":
            p95 = []
            for t in sorted(series):
                p = case_dir / f"target_{t}ms" / "averaged" / "metrics.json"
                if p.exists():
                    v = read_json(p).get("queue_delay_p95_ms")
                    if finite(v):
                        p95.append(float(v))
            if p95:
                ax.set_ylim(0, 1.35 * max(p95))
        ax.set_xlabel("Time (in Seconds)", fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.tick_params(labelsize=9)
        ax.set_title(_case_label(case_dir), fontsize=11)
        ax.grid(True, alpha=0.25, linestyle="--")
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=8, frameon=False, ncol=2, loc="upper right",
                      title="target", title_fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = out_dir / filename
    fig.savefig(out, dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    LOG.info("Saved summary figure %s", out)


def summary_per_flow_bandwidth(plt, out_dir: Path, case_dirs: List[Path],
                               targets: Sequence[int]) -> None:
    """summary: average bandwidth consumed by one flow, bar per target value."""
    fig, axes = _summary_grid(
        plt, case_dirs, 3.9,
        "Average bandwidth consumed by each flow (one bar per FQ-PIE target)")
    for ax, case_dir in zip(axes.flat, case_dirs):
        tlist: List[int] = []
        values: List[float] = []
        for t in targets:
            path = case_dir / f"target_{t}ms" / "averaged" / "metrics.json"
            if not path.exists():
                continue
            value = _nan(read_json(path).get("throughput_mbps"))
            if finite(value):
                tlist.append(t)
                values.append(value)
        if not values:
            ax.axis("off")
            continue
        x = list(range(len(tlist)))
        bars = ax.bar(x, values,
                      color=[BULK_COLORS[i % len(BULK_COLORS)] for i in x],
                      width=0.6)
        ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=9)
        meta = _case_dict(case_dir)
        capacity = float(meta.get("capacity_mbit", 100) or 100)
        flows = float(meta.get("flows", 100) or 100)
        reference = capacity / flows if capacity > 0 and flows > 0 else None
        if reference is not None:
            ax.axhline(reference, color="#444444", linestyle="--",
                       linewidth=1.2, label=f"capacity / flows = {reference:.3f}")
        top = max(values + ([reference] if reference is not None else []))
        ax.set_ylim(0, top * 1.30 if top > 0 else 1.0)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{t} ms" for t in tlist])
        ax.set_xlabel("FQ-PIE target", fontsize=11)
        ax.set_ylabel("Average bandwidth per flow (Mbps)", fontsize=11)
        ax.tick_params(labelsize=9)
        ax.set_title(_case_label(case_dir), fontsize=11)
        ax.grid(True, axis="y", linestyle="--", alpha=0.4)
        ax.legend(fontsize=8, frameon=False, loc="upper center", ncol=2)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = out_dir / "avg_bandwidth_per_flow.png"
    fig.savefig(out, dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    LOG.info("Saved summary figure %s", out)


def _queue_percentiles(case_dir: Path, target: int) -> Dict[str, Optional[float]]:
    specs = [("P50", "queue_delay_p50_ms", 50),
             ("P85", "queue_delay_p85_ms", 85),
             ("P99", "queue_delay_p99_ms", 99)]
    path = case_dir / f"target_{target}ms" / "averaged" / "metrics.json"
    metrics = read_json(path) if path.exists() else {}
    xs, ys = _read_avg(case_dir, target, "queue_delay")
    steady = _steady_window(ys)
    out: Dict[str, Optional[float]] = {}
    for label, key, q in specs:
        value = metrics.get(key)
        if value is None or not finite(value):
            value = percentile(steady, q)
        out[label] = value
    return out


def summary_queue_delay_percentiles(plt, out_dir: Path, case_dirs: List[Path],
                                    targets: Sequence[int]) -> None:
    """summary: queue delay P50 / P85 / P99, grouped bars per target."""
    labels = ["P50", "P85", "P99"]
    fig, axes = _summary_grid(
        plt, case_dirs, 3.9,
        "Queue delay percentiles (P50 / P85 / P99) per target")
    for ax, case_dir in zip(axes.flat, case_dirs):
        available = [t for t in targets
                     if (case_dir / f"target_{t}ms" / "averaged" / "metrics.json").exists()]
        if not available:
            ax.axis("off")
            continue
        n = len(available)
        width = 0.5 if n == 1 else min(0.8 / n, 0.28)
        x = list(range(len(labels)))
        for ti, t in enumerate(available):
            pct = _queue_percentiles(case_dir, t)
            values = [_nan(pct.get(label)) for label in labels]
            offset = (ti - (n - 1) / 2.0) * width
            bars = ax.bar([xi + offset for xi in x], values, width=width,
                          color=BULK_COLORS[ti % len(BULK_COLORS)],
                          label=f"{t} ms")
            ax.bar_label(bars, fmt="%.1f", padding=2, fontsize=8)
        all_values = [_nan(_queue_percentiles(case_dir, t).get(label))
                      for t in available for label in labels]
        top = max([v for v in all_values if finite(v)] or [1.0])
        ax.set_ylim(0, top * 1.25)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_xlabel("Percentile", fontsize=11)
        ax.set_ylabel("Queue delay (in ms)", fontsize=11)
        ax.tick_params(labelsize=9)
        ax.set_title(_case_label(case_dir), fontsize=11)
        ax.grid(True, axis="y", linestyle="--", alpha=0.4)
        ax.legend(fontsize=8, frameon=False, ncol=4, title="target",
                  title_fontsize=8, loc="upper center",
                  bbox_to_anchor=(0.5, -0.20))
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = out_dir / "queue_delay_percentiles.png"
    fig.savefig(out, dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    LOG.info("Saved summary figure %s", out)


def plot_summary(output_root: Path, targets: Sequence[int]) -> None:
    plt = _setup_matplotlib()
    out_dir = ensure_dir(output_root / "summary")
    case_dirs = _all_case_dirs(output_root)
    if not case_dirs:
        return
    colors = ["#4C72B0", "#C44E52", "#55A868", "#8172B3", "#937860", "#DA8BC3",
              "#8C8C8C", "#CCB974", "#64B5CD", "#B07AA1"]
    fig, axes = plt.subplots(3, 2, figsize=(13.0, 8.6))
    for ax, key in zip(axes.flat, METRICS_5):
        for ci, case_dir in enumerate(case_dirs):
            name = _case_label(case_dir)
            tlist, vals = [], []
            for t in targets:
                p = case_dir / f"target_{t}ms" / "averaged" / "metrics.json"
                if not p.exists():
                    continue
                m = read_json(p)
                v = _nan(m.get(
                    {"throughput": "throughput_mbps",
                     "queue_delay": "queue_delay_ms",
                     "packet_loss": "packet_loss_pct",
                     "fairness": "fairness_jain",
                     "link_utilization": "link_utilization_pct"}[key]))
                if finite(v):
                    tlist.append(t)
                    vals.append(v)
            if vals:
                ax.plot(tlist, vals, marker="o", linewidth=1.3, markersize=4,
                        color=colors[ci % len(colors)], label=name)
        if len(targets) > 1 and max(targets) / max(1, min(targets)) >= 10:
            ax.set_xscale("log")
            ax.set_xticks(list(targets))
            ax.set_xticklabels([f"{t:g}" for t in targets])
            ax.minorticks_off()
        ax.set_xlabel("FQ-PIE target (ms)")
        ax.set_ylabel(TITLES[key])
        ax.set_title(TITLES[key])
        ax.grid(True, alpha=0.3, which="both")
        if key == "fairness":
            ax.set_ylim(0.5, 1.02)
        if key == "link_utilization":
            ax.set_ylim(0, 115)
    axes.flat[5].axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    axes.flat[5].legend(handles, labels, loc="center", fontsize=8, frameon=False, ncol=2)
    fig.suptitle("All cases - 5 metrics vs FQ-PIE target (steady state)")
    fig.tight_layout()
    fig.savefig(out_dir / "5metrics_vs_target.png")
    plt.close(fig)
    LOG.info("Saved summary figure %s", out_dir / "5metrics_vs_target.png")

    summary_time_series(plt, out_dir, case_dirs, targets, "throughput",
                        "Throughput (in Mbps)", "throughput_vs_time.png")
    summary_time_series(plt, out_dir, case_dirs, targets, "queue_delay",
                        "Queue delay (in ms)", "queue_delay_vs_time.png")
    summary_per_flow_bandwidth(plt, out_dir, case_dirs, targets)
    summary_queue_delay_percentiles(plt, out_dir, case_dirs, targets)


def _floor_finding(first: Dict[str, Any], crows: Sequence[Dict[str, Any]]) -> str:
    raw = [_nan(r.get("queue_delay_backlog_ms")) for r in crows]
    corr = [_nan(r.get("queue_delay_ms")) for r in crows]
    tgt = [_nan(r.get("target_ms")) for r in crows]
    if not any(finite(v) for v in corr):
        return "- Queue delay: n/a."
    ratios = [c / t for c, t in zip(corr, tgt) if finite(c) and finite(t) and t > 0]
    ratio_txt = (f"{min(ratios):.2f}-{max(ratios):.2f}" if ratios else "n/a")
    corr_vals = [v for v in corr if finite(v)]
    line = (f"- Queue delay at the bottleneck fq_pie qdisc: "
            f"{min(corr_vals):.2f}-{max(corr_vals):.2f} ms")
    raw_vals = [v for v in raw if finite(v)]
    if raw_vals:
        line += (f" (raw backlog/capacity {min(raw_vals):.2f}-"
                 f"{max(raw_vals):.2f} ms)")
    line += (f". Achieved/target ratio {ratio_txt} (1.00 = exactly at the "
             "configured operating point).")
    return line


def write_findings(output_root: Path, rows: Sequence[Dict[str, Any]]) -> None:
    out = ensure_dir(output_root / "summary") / "FINDINGS.md"
    lines = [
        "# FQ-PIE target sweep - findings",
        "",
        "Canonical pipeline semantics (same as `runAllTargets.sh` + `plot_targets.py`):",
        "100 Mbit / 20 ms one-way bottleneck, 100 ms RTT, cubic, FQ-PIE target sweep,",
        "steady state = mean of the last 50% of each trace.",
        "",
        "Queue delay is measured on the bottleneck `fq_pie` qdisc from `tc`",
        "`backlog`, minus the fair-queue service batch (one packet per non-empty",
        "flow) that `tc` includes in `backlog` but that PIE does not regulate.",
        "`queue_delay_ms` is that PIE-regulated value; `queue_delay_backlog_ms` is",
        "the raw `backlog x 8 / capacity` value kept for reference.",
        "",
    ]
    by_case: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("scenario", "")), str(row.get("category", "")),
               str(row["case"]))
        by_case.setdefault(key, []).append(row)

    for (scenario, category, case), crows in by_case.items():
        crows = sorted(crows, key=lambda r: int(r["target_ms"]))
        first, last = crows[0], crows[-1]
        qd_first = _nan(first.get("queue_delay_ms"))
        qd_last = _nan(last.get("queue_delay_ms"))
        rel = abs(qd_last - qd_first) / max(abs(qd_first), 1e-9)
        if not finite(qd_first) or not finite(qd_last) or rel < 0.01:
            trend = "is ~flat"
        elif qd_last > qd_first:
            trend = "rises"
        else:
            trend = "falls"
        lines += [
            f"## {scenario}/{category}/{case}",
            "",
            f"- Traffic scenario: {SCENARIO_BY_NAME[scenario].description}."
            if scenario in SCENARIO_BY_NAME else f"- Traffic scenario: {scenario}.",
            f"- {int(first['flows'])} TCP flows, {float(first['capacity_mbit']):g} Mbit, "
            f"RTT {float(first['rtt_ms']):g} ms, "
            f"queue limit {first['queue_limit'] if first['queue_limit'] is not None else 'default'}.",
            f"- Per-flow throughput {_nan(first['throughput_mbps']):.3f}-"
            f"{max(_nan(r['throughput_mbps']) for r in crows):.3f} Mbps "
            f"(aggregate {_nan(first['total_throughput_mbps']):.2f} Mbps).",
            f"- Link utilisation {_nan(first['link_utilization_pct']):.1f}-"
            f"{max(_nan(r['link_utilization_pct']) for r in crows):.1f}%.",
            f"- Queue delay {trend} with target: {qd_first:.2f} ms at {first['target_ms']} ms "
            f"-> {qd_last:.2f} ms at {last['target_ms']} ms.",
            _floor_finding(first, crows),
            f"- Packet loss {min(_nan(r['packet_loss_pct']) for r in crows):.2f}-"
            f"{max(_nan(r['packet_loss_pct']) for r in crows):.2f}%; "
            f"Jain {min(_nan(r['fairness_jain']) for r in crows):.4f}-"
            f"{max(_nan(r['fairness_jain']) for r in crows):.4f}.",
            "",
        ]

    with open(out, "w") as fh:
        fh.write("\n".join(lines))
    LOG.info("Wrote %s", out)


def write_readme(output_root: Path, args: argparse.Namespace) -> None:
    out = ensure_dir(output_root / "summary") / "README.md"
    cases = build_cases()
    per_case = []
    for c in cases:
        ct = case_targets(c, args)
        if ct != list(args.targets):
            per_case.append(f"* `{c.name}`: {', '.join(str(t) for t in ct)} ms")
    default_txt = ", ".join(str(t) for t in args.targets)
    per_case_txt = ("\n* Default sweep for the remaining cases: "
                    f"{default_txt} ms\n" + "\n".join(per_case)) if per_case else ""
    text = f"""# FQ-PIE evaluation (canonical pipeline)

Generated by `scripts/fqpie_eval.py` ({PIPELINE_VERSION}).

## What was run

* 5 traffic scenarios x 8 parameter cases = 40 combinations
  * Scenarios: synchronous fairness, staggered flows, RTT fairness,
    pulse wave, UDP background
  * Cases: bandwidth (10/100 Mbit), delay (60/120 ms RTT),
    queue (100/1000 packet limit), load (10/100 TCP flows)
* Targets: {default_txt} ms{per_case_txt}
* Repeats: {args.repeat} iteration(s) per case/target
* Duration: {args.duration:g} s per iteration
* Canonical defaults: FQ-PIE, cubic, 1000 Mbit edge, 20 ms one-way
  bottleneck delay, 100 ms RTT, start-gap 0.

## Pipeline (identical semantics to runAllTargets + plot_targets)

1. `dumbbell.py` is invoked exactly like `run-scenarios.sh` does, with
   `--qdisc-params '{{"target":"<T>ms"[,"limit":"<N>"]}}'`.
2. Per run, `iperf3Server.json` -> per-flow `receiving_rate` and the
   bottleneck `fq_pie` samples in `tc.json` -> `backlog`, `qlen`,
   `new_flows_len`, `old_flows_len`, `packets`, `drops`.
3. Iterations are averaged on a common {TIME_STEP:g} s grid (the reference
   `averagedat.py` groups by exact timestamp and therefore concatenates).
4. Metric definitions follow `plot_targets.py`:
   throughput = per-flow receiving rate, utilisation = throughput x flows /
   capacity, loss = drops / packets, fairness = Jain across flows (real, not
   synthetic).

## Queue delay: where and how it is measured

Queue delay is measured on the **bottleneck `fq_pie` qdisc** (the `11:` qdisc
on the bottleneck IFB, whose parent HTB is the rate limiter) and nowhere else.
The applied configuration is read back from every dump and stored as
`qdisc_target_ms`, `qdisc_limit`, `qdisc_flows` and `qdisc_quantum_bytes` in
`metrics.json`, so each result proves which target reached the kernel.

FQ-PIE is a fair-queueing AQM: in every round-robin cycle it dequeues one
packet from each non-empty flow.  `tc`'s `backlog` therefore always contains
that in-service batch (one packet per queued flow), which converted to time is
`active_flows * packet_size / capacity`.  That batch is unrelated to `target`
and would otherwise be reported as a large standing delay.

Reported queue delay is the PIE-regulated per-flow queue above that batch:

```
round_bytes = backlog * min(qlen, active_flows) / qlen
queue_delay = (backlog - round_bytes) * 8 / capacity * 1000      [ms]
```

Both quantities are stored:

* `queue_delay_ms` - PIE-regulated per-flow queue delay (used in every plot
  and in `results.csv`).
* `queue_delay_backlog_ms` - the raw canonical `backlog * 8 / capacity`
  value, kept for comparison with `finals/` and with `plot_targets.py`.
* `queue_delay_service_round_ms` - size of the removed round-robin batch.

`queue_delay_target_ratio` in `results.csv` is
`queue_delay_ms / target_ms`; values near 1.0 mean the AQM is holding the
configured operating point.

## Where to look

* `summary/results.csv` - every case/target steady-state metric.
* `summary/FINDINGS.md` - per-case conclusions.
* `summary/5metrics_vs_target.png` - all cases, 5 metrics vs target.
* `summary/throughput_vs_time.png` - per case, one line per target.
* `summary/queue_delay_vs_time.png` - per case, one line per target.
* `summary/avg_bandwidth_per_flow.png` - average Mbps per flow, one bar per target.
* `summary/queue_delay_percentiles.png` - queue delay P50/P85/P99 per target.
* `<scenario>/<category>/<case>/plots/` - 5 metrics vs target, bar charts,
  aggregate throughput vs time, queue delay vs time, per-flow throughput,
  and percentile bar charts.
* `<scenario>/<category>/<case>/finals/` - target-suffixed dats accepted
  directly by `scripts/plot_targets.py --finals-dir <case>/finals`.
"""
    with open(out, "w") as fh:
        fh.write(text)
    LOG.info("Wrote %s", out)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def print_matrix(cases: Sequence[Case], targets: Sequence[int], args: argparse.Namespace,
                 output_root: Path) -> None:
    total = 0
    wall = 0.0
    print(f"Pipeline : {PIPELINE_VERSION}")
    print(f"Output   : {output_root}")
    print(f"Scenarios: {', '.join(s.name for s in SCENARIOS)}")
    print(f"Targets  : {list(targets)} ms (default; per-case overrides applied)")
    print(f"Repeats  : {args.repeat}")
    print(f"Duration : {args.duration:g} s per flow")
    print("")
    header = (f"{'scenario':15} {'category':10} {'case':13} {'flows':>5} "
              f"{'cap':>6} {'rtt':>5} {'limit':>6}  targets")
    print(header)
    print("-" * len(header))
    for case in cases:
        ct = case_targets(case, args)
        runs = len(ct) * args.repeat
        total += runs
        wall += runs * (scenario_analysis_duration(case, args.duration) + 12)
        limit = str(case.queue_limit) if case.queue_limit is not None else "default"
        print(f"{case.scenario:15} {case.category:10} {case.name:13} {case.flows:5d} "
              f"{case.capacity_mbit:5g}M {case.rtt_ms:5g} {limit:>6}  "
              f"{','.join(str(t) for t in ct)} ms ({runs} runs)")
    print("-" * len(header))
    print(f"Total NeST iterations: {total} (each flow runs {args.duration:g} s)")
    print(f"Approximate wall time: {wall / 3600:.1f} h")


def select_cases(cases: Sequence[Case], only: Optional[Sequence[str]]) -> List[Case]:
    if not only:
        return list(cases)
    wanted = set()
    for item in only:
        wanted.update(x.strip() for x in item.split(",") if x.strip())
    chosen = [c for c in cases
              if c.name in wanted or c.key in wanted or c.category in wanted
              or c.scenario in wanted]
    matched = ({c.name for c in chosen} | {c.key for c in chosen}
               | {c.category for c in chosen} | {c.scenario for c in chosen})
    unknown = wanted - matched
    if unknown:
        raise SystemExit(
            f"Unknown case(s): {', '.join(sorted(unknown))}. "
            f"Available cases: {', '.join(sorted({c.name for c in cases}))}; "
            f"scenarios: {', '.join(s.name for s in SCENARIOS)}; "
            f"categories: {', '.join(sorted({c.category for c in cases}))}")
    return chosen


def write_case_json(case_dir: Path, case: Case, args: argparse.Namespace) -> None:
    write_json(case_dir / "case.json", {
        **asdict(case),
        "pipeline": PIPELINE_VERSION,
        "targets_ms": case_targets(case, args),
        "repeats": args.repeat,
        "duration_s": args.duration,
        "qdisc": QDISC,
        "congestion_control": CONGESTION,
        "qdisc_flows": QDISC_FLOWS,
        "qdisc_tupdate": QDISC_TUPDATE,
        "bottleneck_delay_ms": BOTTLENECK_DELAY_MS,
        "edge_bandwidth": EDGE_BANDWIDTH,
        "time_step_s": TIME_STEP,
        "metric_sources": {
            "throughput": "iperf3Server.json receiving_rate (per flow)",
            "queue_delay": "tc.json backlog * 8 / capacity_bps * 1000",
            "packet_loss": "tc.json drops / packets * 100",
            "fairness": "Jain across per-flow receiving_rate",
            "link_utilization": "throughput * flows / capacity * 100",
        },
    })


def target_needs_average(case_dir: Path, target: int) -> bool:
    """True when a run is newer than the averaged output (or none exists)."""
    tdir = case_dir / f"target_{target}ms"
    avg = tdir / "averaged" / "metrics.json"
    if not avg.exists():
        return True
    try:
        avg_mtime = avg.stat().st_mtime
        run_metrics = list(tdir.glob("run_*/metrics.json"))
        return any(p.stat().st_mtime > avg_mtime for p in run_metrics)
    except OSError:
        return True


def plots_are_current(case_dir: Path) -> bool:
    """True when every per-case figure is newer than the averaged data."""
    plot_dir = case_dir / "plots"
    if not plot_dir.exists():
        return False
    try:
        data = list(case_dir.glob("target_*/averaged/metrics.json"))
        plots = list(plot_dir.glob("*.png"))
        if not data or not plots:
            return False
        return min(p.stat().st_mtime for p in plots) >= max(
            p.stat().st_mtime for p in data)
    except OSError:
        return False


def run_missing(cases: Sequence[Case], args: argparse.Namespace, output_root: Path) -> None:
    if os.geteuid() != 0:
        raise SystemExit(
            "NeST must run as root. Use: sudo -E bash scripts/run_fqpie_eval.sh ...\n"
            "(--dry-run, --extract-only and --plot-only work without root.)"
        )

    for case in cases:
        case_dir = ensure_dir(case_dir_for(output_root, case))
        write_case_json(case_dir, case, args)
        for target in case_targets(case, args):
            tdir = ensure_dir(case_dir / f"target_{target}ms")
            for run_idx in range(1, args.repeat + 1):
                rd = tdir / f"run_{run_idx}"
                try:
                    run_one(case, target, run_idx, rd, args)
                except Exception as exc:  # noqa: BLE001
                    LOG.exception("Run failed for %s target %sms run %d: %s",
                                  case.key, target, run_idx, exc)
                    if args.fail_fast:
                        raise
            if target_needs_average(case_dir, target):
                average_runs(case_dir, case, target, args.duration)
            else:
                LOG.info("Reuse averaged data for %s target %sms", case.key, target)


def reextract_missing(cases: Sequence[Case], args: argparse.Namespace,
                      output_root: Path) -> None:
    for case in cases:
        case_dir = ensure_dir(case_dir_for(output_root, case))
        write_case_json(case_dir, case, args)
        for target in case_targets(case, args):
            tdir = ensure_dir(case_dir / f"target_{target}ms")
            for run_idx in range(1, args.repeat + 1):
                rd = tdir / f"run_{run_idx}"
                if (rd / "dump").exists():
                    extract_run(rd, case, target, run_idx,
                                recorded_duration(
                                    rd,
                                    scenario_analysis_duration(case, args.duration)),
                                drop_dump=not args.keep_dump)
            if target_needs_average(case_dir, target):
                average_runs(case_dir, case, target, args.duration)


def _plot_targets_for(case_dir: Path, requested: Sequence[int]) -> List[int]:
    return sorted(set(int(t) for t in requested) | set(_target_list(case_dir)))


def write_summaries(cases: Sequence[Case], args: argparse.Namespace,
                    output_root: Path) -> List[Dict[str, Any]]:
    """Write results.csv / FINDINGS.md / README.md without making figures."""
    allowed_targets = sorted({t for c in cases for t in case_targets(c, args)})
    rows = collect_rows(output_root, allowed_targets)
    if rows:
        write_results_csv(output_root, rows)
        write_findings(output_root, rows)
    write_readme(output_root, args)
    return rows


def regenerate_plots(cases: Sequence[Case], args: argparse.Namespace,
                     output_root: Path) -> None:
    allowed_targets = sorted({t for c in cases for t in case_targets(c, args)})
    case_dirs = [case_dir_for(output_root, c) for c in cases]
    stale = getattr(args, "replot", False) or any(
        not plots_are_current(d) for d in case_dirs)
    if not stale:
        write_summaries(cases, args, output_root)
        LOG.info("Plots are already up to date; skipping (use --replot to force)")
        return

    for case, case_dir in zip(cases, case_dirs):
        if not getattr(args, "replot", False) and plots_are_current(case_dir):
            LOG.info("Reuse existing plots for %s", case.key)
            continue
        plot_case(case_dir, case, _plot_targets_for(case_dir, case_targets(case, args)))
    groups = sorted({(c.scenario, c.category) for c in cases})
    for scenario, category in groups:
        dirs = [case_dir_for(output_root, c) for c in cases
                if c.scenario == scenario and c.category == category]
        dirs = [d for d in dirs if d.exists() and _target_list(d)]
        if dirs:
            plot_category(output_root / scenario / category, dirs, allowed_targets)
    rows = collect_rows(output_root, allowed_targets)
    if rows:
        write_results_csv(output_root, rows)
        all_targets = sorted({int(r["target_ms"]) for r in rows})
        plot_summary(output_root, all_targets)
        write_findings(output_root, rows)
    write_readme(output_root, args)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Canonical FQ-PIE target sweep (runAllTargets + plot_targets)")
    ap.add_argument("--only", nargs="+", default=None,
                    help="case names, categories or scenarios to run, e.g. "
                         "--only bw10mbit rtt60ms staggered")
    ap.add_argument("--scenarios", nargs="+", default=None,
                    help="traffic scenarios to run (default: all). Choices: "
                         + ", ".join(s.name for s in SCENARIOS))
    ap.add_argument("--targets", default=None,
                    help="space-separated FQ-PIE targets in ms "
                         f"(default: {' '.join(str(t) for t in TARGETS_DEFAULT)})")
    ap.add_argument("--repeat", type=int, default=DEFAULT_REPEATS,
                    help=f"iterations per case/target (default: {DEFAULT_REPEATS})")
    ap.add_argument("--duration", type=float, default=DEFAULT_DURATION,
                    help=f"seconds each flow runs after it starts "
                         f"(default: {DEFAULT_DURATION:g})")
    ap.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    ap.add_argument("--force", action="store_true",
                    help="redo completed runs/targets instead of resuming")
    ap.add_argument("--keep-dump", action="store_true",
                    help="keep raw NeST dumps (needed for later --extract-only; ~56 MB/run)")
    ap.add_argument("--fail-fast", action="store_true",
                    help="abort on first NeST failure instead of continuing")
    ap.add_argument("--dry-run", action="store_true", help="print the matrix and exit")
    ap.add_argument("--extract-only", action="store_true",
                    help="re-extract archived dumps, re-average and re-plot (no NeST)")
    ap.add_argument("--plot-only", action="store_true",
                    help="re-average existing runs and regenerate all plots only")
    ap.add_argument("--no-plots", action="store_true",
                    help="run experiments but skip all figure generation "
                         "(writes results.csv / FINDINGS.md / README.md only)")
    ap.add_argument("--replot", action="store_true",
                    help="redraw figures even when they are newer than the data")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    args.targets_explicit = args.targets is not None
    if args.targets is None:
        args.targets = list(TARGETS_DEFAULT)
    else:
        try:
            args.targets = [int(x) for x in str(args.targets).replace(",", " ").split()]
        except ValueError:
            raise SystemExit("--targets must be a space-separated list of integers (ms)")
    args.targets = sorted(set(t for t in args.targets if t > 0))
    if not args.targets:
        raise SystemExit("--targets must contain at least one positive value")
    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1")
    if args.duration <= 0:
        raise SystemExit("--duration must be > 0")
    if args.duration < 30:
        LOG.warning("duration < 30 s is too short for a 50%% steady-state window")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    output_root = Path(args.output_root).resolve()
    setup_logging(output_root, args.verbose)
    cases = select_cases(build_cases(), args.only)
    if args.scenarios:
        wanted = {s.strip() for item in args.scenarios for s in item.split(",") if s.strip()}
        unknown = wanted - set(SCENARIO_BY_NAME)
        if unknown:
            raise SystemExit(
                f"Unknown scenario(s): {', '.join(sorted(unknown))}. "
                f"Available: {', '.join(s.name for s in SCENARIOS)}")
        cases = [c for c in cases if c.scenario in wanted]

    if args.plot_only or args.extract_only:
        targets = [t for t in args.targets]
        if args.extract_only:
            reextract_missing(cases, args, output_root)
        else:
            # Re-average every existing target, even if it is outside --targets.
            for case in cases:
                case_dir = case_dir_for(output_root, case)
                for t in _target_list(case_dir):
                    average_runs(case_dir, case, t, args.duration)
        regenerate_plots(cases, args, output_root)
        return 0

    print_matrix(cases, args.targets, args, output_root)
    if args.dry_run:
        return 0

    run_missing(cases, args, output_root)
    if args.no_plots:
        write_summaries(cases, args, output_root)
        LOG.info("Skipped figures (--no-plots); tables written under %s/summary",
                 output_root)
    else:
        regenerate_plots(cases, args, output_root)
    LOG.info("Done. Results under %s", output_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
