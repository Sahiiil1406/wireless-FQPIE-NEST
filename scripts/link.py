import argparse
import sys
from pathlib import Path
import pandas as pd

# Function to process delivery rate and compute instantaneous link utilization
def calculate_instantaneous_utilization(file_path, link_capacity=10, output_file_path=None):
    """
    Calculate the instantaneous link utilization from the given file containing time and bytes/throughput.
    Supports two modes:
      - if input is tc bytes (cumulative bytes): utilization = bytes*8 / (cap_bps * time) *100
      - if input is throughput (Mbps) already: utilization = throughput / cap *100 (handled by caller)
    For backwards compat, we detect: if first data row's second column > capacity*1.5, treat as bytes.

    Parameters:
    - file_path: str, path to input file (time value)
    - link_capacity: int/float, link capacity in Mbps (default 100 for dumbbell bottleneck)
    - output_file_path: str, path to save output
    Returns: DataFrame with time and utilization
    """
    data = pd.read_csv(file_path, sep=r"\s+", header=None, names=["time", "value"])
    # Heuristic: if values look like bytes (>1e6), use byte formula; else treat as throughput Mbps
    # Safer: provide explicit mode via --throughput flag; here we support both by checking magnitude
    # For fq_pie_bytes.dat, bytes is cumulative and grows; for throughput it is 0-100
    sample = data["value"].dropna().iloc[:5].mean() if len(data) else 0
    # If sample > 5000, likely bytes (since throughput max ~100 Mbps)
    if sample > 5000:
        link_capacity_bytes_per_sec = link_capacity * 10**6 / 8
        # Avoid divide by zero: if time is 0, skip
        data = data[data["time"] > 0]
        data["instantaneous_utilization"] = (data["value"] / (link_capacity_bytes_per_sec * data["time"])) * 100
    else:
        # throughput Mbps -> utilization %
        data["instantaneous_utilization"] = (data["value"] / link_capacity * 100).clip(upper=100)
    link_utilization_data = data[["time", "instantaneous_utilization"]]
    if output_file_path:
        link_utilization_data.to_csv(output_file_path, sep=" ", header=False, index=False)
    return link_utilization_data

def calculate_from_throughput(throughput_file, link_capacity_mbit, output_file):
    """Simple throughput (Mbps) -> utilization (%) conversion, used for fq_pie."""
    import pandas as pd
    data = pd.read_csv(throughput_file, sep=r"\s+", header=None, names=["time", "throughput"])
    data["util"] = (data["throughput"] / link_capacity_mbit * 100).clip(upper=100)
    out = data[["time", "util"]]
    out.to_csv(output_file, sep=" ", header=False, index=False)
    return out

def main():
    parser = argparse.ArgumentParser(description="Compute link utilization for FQ-PIE (and legacy CoDel) results")
    parser.add_argument("-i", "--input", help="Input .dat file (time value) - bytes or throughput")
    parser.add_argument("-o", "--output", help="Output .dat file")
    parser.add_argument("-c", "--capacity", type=float, default=100, help="Link capacity in Mbps (default 100)")
    parser.add_argument("--throughput", action="store_true", help="Force throughput mode (value is Mbps)")
    args = parser.parse_args()

    # Auto-detect project layout if no args given (legacy behaviour, now for fq_pie)
    if not args.input or not args.output:
        # Default: process comparison/fq_pie_* files if they exist
        script_dir = Path(__file__).resolve().parent
        project = script_dir.parent
        nest_dir = project / "nest"
        comp = nest_dir / "comparison"
        # Prefer throughput file for fq_pie (more accurate)
        thr_in = comp / "fq_pie_netperf_receiver.dat"
        bytes_in = comp / "fq_pie_bytes.dat"
        thr_out = comp / "fq_pie_link_utilization.dat"
        if thr_in.exists():
            print(f"[link.py] No args given, using throughput file: {thr_in} -> {thr_out} (cap {args.capacity} Mbit)")
            calculate_from_throughput(str(thr_in), args.capacity, str(thr_out))
            print(calculate_from_throughput(str(thr_in), args.capacity, str(thr_out)).head())
            return
        elif bytes_in.exists():
            print(f"[link.py] Using bytes file: {bytes_in} -> {thr_out}")
            df = calculate_instantaneous_utilization(str(bytes_in), link_capacity=args.capacity, output_file_path=str(thr_out))
            print(df.head())
            return
        else:
            # Fallback to throughput path even if not found, for error message
            if args.input and args.output:
                pass
            else:
                parser.print_help()
                # Also try legacy two-file mode for backwards compat if legacy files exist
                legacy_orig = Path("/home/deepa/ALL_Traffic/nest/examples/qdiscs/modified_results/original_bytes.dat")
                if legacy_orig.exists():
                    print("[link.py] Legacy mode: found /home/deepa/... original_bytes.dat, processing legacy files")
                    for inp, out in [
                        (legacy_orig, Path("/home/deepa/ALL_Traffic/nest/examples/qdiscs/modified_results/original_link_utilization.dat")),
                        (Path("/home/deepa/ALL_Traffic/nest/examples/qdiscs/modified_results/modified_bytes.dat"),
                         Path("/home/deepa/ALL_Traffic/nest/examples/qdiscs/modified_results/modified_link_utilization.dat")),
                    ]:
                        if inp.exists():
                            calculate_instantaneous_utilization(str(inp), link_capacity=args.capacity, output_file_path=str(out))
                sys.exit(1 if not args.input else 0)

    # Explicit input/output mode
    inp = args.input
    out = args.output
    if args.throughput:
        df = calculate_from_throughput(inp, args.capacity, out)
    else:
        df = calculate_instantaneous_utilization(inp, link_capacity=args.capacity, output_file_path=out)
    print(f"Link utilization saved to {out} (capacity {args.capacity} Mbit)")
    print(df.head())

if __name__ == "__main__":
    main()
