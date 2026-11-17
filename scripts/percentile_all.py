import argparse
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Define the keys and corresponding y-axis titles
KEYS = ["cwnd", "rtt", "dev_rtt", "ssthresh", "rto", "delivery_rate", "pacing_rate"]
KEYS1 = ["bytes", "packets", "drops", "overlimits", "requeues", "backlog", "qlen",
         "count", "lastcount", "ldelay", "drop_next", "maxpacket", "drop_overlimit",
         "pkts_in", "overlimit", "overmemory", "dropped", "ecn_mark",
         "new_flow_count", "new_flows_len", "old_flows_len", "memory_used"]
EXTRA_FILES = ["netperf_sender", "netperf_receiver", "ping"]
LINK = ["link_utilization"]

# Combine all keys
ALL_KEYS = KEYS + KEYS1 + EXTRA_FILES + LINK

# Y-axis titles mapping
Y_AXIS_TITLES = {
    "netperf_sender": "Sending Rate (Mbps)",
    "netperf_receiver": "Throughput (Mbps)",
    "ping": "Ping Latency (ms)",
    "cwnd": "Congestion Window (Packets)",
    "rtt": "RTT (ms)",
    "dev_rtt": "Deviation RTT (ms)",
    "rto": "Retransmission Timeout (ms)",
    "delivery_rate": "Delivery Rate (Mbps)",
    "pacing_rate": "Pacing Rate (Mbps)",
    "bytes": "Bytes (Bytes)",
    "packets": "Packets (Count)",
    "drops": "Drops (Count)",
    "overlimits": "Overlimits (Count)",
    "requeues": "Requeues (Count)",
    "backlog": "Backlog (Bytes)",
    "qlen": "Queue Length (Packets)",
    "count": "Packet Drop Count",
    "lastcount": "Last Count (Events)",
    "ldelay": "Queue Delay (ms)",
    "drop_next": "Drop Next (ms)",
    "maxpacket": "Max Packet Size (Bytes)",
    "drop_overlimit": "Drops Over Limit (Count)",
    "link_utilization": "Link Utilization (%)"
}

def plot_percentiles(key, qdisc_prefix="fq_pie", single_mode=True, compare_prefix=None):
    """
    If single_mode: plot percentiles for one qdisc file (qdisc_prefix_key.dat) as single bar set.
    If compare mode (two files): compare qdisc_prefix vs compare_prefix.
    Defaults to single_mode for FQ-PIE default (fq_pie_*.dat averaged over 25 runs).
    """
    # Resolve filenames - try comparison dir first, then cwd
    candidates = [Path(f"{qdisc_prefix}_{key}.dat"), Path(f"comparison/{qdisc_prefix}_{key}.dat"),
                  Path(f"../nest/comparison/{qdisc_prefix}_{key}.dat")]
    # If compare mode, need two files
    if compare_prefix:
        file1 = f"{compare_prefix}_{key}.dat"
        file2 = f"{qdisc_prefix}_{key}.dat"
        cands1 = [Path(file1), Path(f"comparison/{file1}"), Path(f"../nest/comparison/{file1}")]
        cands2 = [Path(file2), Path(f"comparison/{file2}"), Path(f"../nest/comparison/{file2}")]
        p1 = next((p for p in cands1 if p.exists()), None)
        p2 = next((p for p in cands2 if p.exists()), None)
        if not p1 or not p2:
            print(f"Files for compare key '{key}' not found ({file1}, {file2}). Skipping.")
            return
        try:
            data1 = np.loadtxt(str(p1), usecols=(1,))
            data2 = np.loadtxt(str(p2), usecols=(1,))
            if key == "ldelay":
                data1 = data1 / 1000.0
                data2 = data2 / 1000.0
            # Filter NaN
            data1 = data1[~np.isnan(data1)]
            data2 = data2[~np.isnan(data2)]
            if len(data1)==0 or len(data2)==0:
                print(f"No valid data for key '{key}'")
                return
            metrics = ['Median', '95th Percentile', '99th Percentile']
            original_values = [np.median(data1), np.percentile(data1,95), np.percentile(data1,99)]
            modified_values = [np.median(data2), np.percentile(data2,95), np.percentile(data2,99)]
            x = np.arange(len(metrics))
            width = 0.35
            fig, ax = plt.subplots()
            ax.bar(x - width/2, original_values, width, label=compare_prefix, color='red')
            ax.bar(x + width/2, modified_values, width, label=qdisc_prefix, color='blue')
            ax.set_ylabel(Y_AXIS_TITLES.get(key, "Values"))
            ax.set_title(f'Percentile Comparison: {key} ({compare_prefix} vs {qdisc_prefix})')
            ax.set_xticks(x)
            ax.set_xticklabels(metrics)
            ax.legend()
            if key == "link_utilization":
                ax.legend(loc='upper left')
            output_filename = f"percentile_{key}_graph.png"
            plt.savefig(output_filename)
            print(f"Plot saved as '{output_filename}'")
            plt.close(fig)
        except Exception as e:
            print(f"An error occurred for compare key '{key}': {e}")
        return
    else:
        # Single-mode
        p = next((p for p in candidates if p.exists()), None)
        if p is None:
            # Try any matching file in comparison dir
            import glob
            globs = glob.glob(f"comparison/{qdisc_prefix}_{key}.dat") + glob.glob(f"../nest/comparison/{qdisc_prefix}_{key}.dat") + glob.glob(f"{qdisc_prefix}_{key}.dat")
            if globs:
                p = Path(globs[0])
            else:
                print(f"File for key '{key}' not found ({qdisc_prefix}_{key}.dat). Skipping.")
                return
        try:
            data = np.loadtxt(str(p), usecols=(1,))
            if key == "ldelay":
                data = data / 1000.0
            data = data[~np.isnan(data)]
            if len(data)==0:
                print(f"No valid data for key '{key}' in {p}")
                return
            metrics = ['Median', '95th Percentile', '99th Percentile']
            values = [np.median(data), np.percentile(data,95), np.percentile(data,99)]
            x = np.arange(len(metrics))
            width = 0.5
            fig, ax = plt.subplots(figsize=(6,4))
            bars = ax.bar(x, values, width, label=qdisc_prefix, color='tab:blue')
            ax.bar_label(bars, fmt='%.2f', padding=3)
            ax.set_ylabel(Y_AXIS_TITLES.get(key, "Values"))
            ax.set_title(f'{qdisc_prefix} - {key} Percentiles (avg over 25 runs)')
            ax.set_xticks(x)
            ax.set_xticklabels(metrics)
            ax.legend()
            if key == "link_utilization":
                ax.set_ylim(bottom=0, top=100)
            plt.tight_layout()
            output_filename = f"percentile_{key}_graph.png"
            # Also save to comparison/plots if those dirs exist
            plt.savefig(output_filename)
            for alt in [Path("comparison")/output_filename, Path("plots")/output_filename, Path("../nest/comparison")/output_filename]:
                try:
                    if alt.parent.exists():
                        plt.savefig(str(alt))
                except: pass
            print(f"Plot saved as '{output_filename}' (from {p})")
            plt.close(fig)
        except FileNotFoundError:
            print(f"Files for key '{key}' not found. Skipping.")
        except Exception as e:
            print(f"An error occurred for key '{key}': {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate percentile plots for FQ-PIE (or compare two qdiscs)")
    parser.add_argument("--qdisc", default="fq_pie", help="Primary qdisc prefix (default fq_pie)")
    parser.add_argument("--compare", default=None, help="Optional second qdisc prefix to compare against (e.g. fq_codel)")
    parser.add_argument("--key", default=None, help="Only plot this key (e.g. backlog)")
    args = parser.parse_args()
    if args.key:
        plot_percentiles(args.key, qdisc_prefix=args.qdisc, single_mode=(args.compare is None), compare_prefix=args.compare)
    else:
        for key in ALL_KEYS:
            plot_percentiles(key, qdisc_prefix=args.qdisc, single_mode=(args.compare is None), compare_prefix=args.compare)
