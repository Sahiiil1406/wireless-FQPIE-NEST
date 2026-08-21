# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2022 NITK Surathkal

########################
# SHOULD BE RUN AS ROOT
########################
import argparse
import json
import sys
import threading


from nest.topology import *
from nest.experiment import *
from nest.topology.network import Network
from nest.topology.address_helper import AddressHelper


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "AQM evalutation"
        )
    )

    parser.add_argument(
        "-n", "--tcp-flows", type=int, default=10,
        help="Number of TCP flows",
    )
    parser.add_argument(
        "-k", "--udp-flows", type=int, default=0,
        help="Number of UDP flows",
    )
    parser.add_argument(
        "--start-gap", type=float, default=250,
        help=(
            "Gap in milliseconds between the start times of consecutively "
            "started flows (default: 250ms). Flows are staggered in the "
            "order: all TCP flows first, then all UDP flows."
        ),
    )
    parser.add_argument(
        "--duration", type=float, default=100,
        help="Number of seconds each flow runs for, after it starts (default: 100)",
    )

    parser.add_argument(
        "--edge-bandwidth", type=str, default="1000mbit",
        help="Bandwidth of each host<->router access link (default: 1000mbit)",
    )
    parser.add_argument(
        "--bottleneck-bandwidth", type=str, default="100mbit",
        help="Bandwidth of the r1<->r2 bottleneck link (default: 10mbit)",
    )
    parser.add_argument(
        "--bottleneck-delay", type=float, default=20,
        help="One-way propagation delay of the bottleneck link, in ms (default: 40)",
    )
    parser.add_argument(
        "--pulsebw", action="store_true", default=False,
        help="Enable pulse wave bottleneck bandwidth toggling",
    )
    parser.add_argument(
        "--high-bw", type=str, default="100mbit",
        help="High bandwidth phase for pulse wave scenario (default: 100mbit)",
    )
    parser.add_argument(
        "--low-bw", type=str, default="50mbit",
        help="Low bandwidth phase for pulse wave scenario (default: 50mbit)",
    )
    parser.add_argument(
        "--pulse-interval", type=float, default=10.0,
        help="Interval in seconds between bandwidth toggles (default: 10.0s)",
    )


    parser.add_argument(
        "--tcp-rtts", type=str, default=None,
        help=(
            "Comma-separated list of target RTTs (ms) for the TCP flows, "
            "e.g. '20,40,60'. Values are recycled if fewer than --tcp-flows "
            "are given. Defaults to 40ms for every TCP flow."
        ),
    )
    parser.add_argument(
        "--udp-rtts", type=str, default=None,
        help=(
            "Comma-separated list of target RTTs (ms) for the UDP flows. "
            "Same recycling rule as --tcp-rtts. Defaults to 40ms for every "
            "UDP flow."
        ),
    )
    parser.add_argument(
        "--udp-rates", type=str, default="10mbit",
        help=(
            "Comma-separated list of target bandwidths for the UDP flows "
            "(e.g. '9mbit,4mbit'). Recycled if fewer than --udp-flows are "
            "given (default: 9mbit for every UDP flow)."
        ),
    )

    parser.add_argument(
        "--qdisc", type=str, default="fq_codel",
        choices=["fq_codel", "codel", "pie", "red", "pfifo"],
        help="Queuing discipline to install on the bottleneck link (default: fq_codel)",
    )
    parser.add_argument(
        "--qdisc-params", type=str, default=None,
        help=(
            "JSON object of qdisc parameters, e.g. "
            '\'{"limit": "100", "target": "5ms"}\'. Overrides/extends the '
            "built-in defaults for the chosen --qdisc."
        ),
    )

    parser.add_argument(
        "--experiment-name", type=str, default="dumbbell",
        help="Name used for the experiment / output dump directory",
    )

    return parser.parse_args()


def parse_csv_list(raw, count, cast, default):
    """
    Parse a comma-separated string into a list of length `count`, casting
    each element with `cast`. If `raw` is None, every element is `default`.
    If fewer values than `count` are supplied, the given values are recycled
    (cycled through) to fill the remaining slots.
    """
    if count <= 0:
        return []
    if raw is None:
        return [default] * count
    values = [cast(v.strip()) for v in raw.split(",") if v.strip() != ""]
    if not values:
        return [default] * count
    return [values[i % len(values)] for i in range(count)]


DEFAULT_QDISC_PARAMS = {
    "fq_codel": {
        "flows": "1024",
        "target": "5ms",
        "interval": "100ms", 
        "ecn": " ",
    },
    "codel": {
        "limit": "1000",
        "target": "5ms",
        "interval": "100ms",
    },
    "pie": {
        "limit": "100",
        "target": "2ms",
        "tupdate": "15ms",
    },
    "red": {
        "limit": "100",
        "min": "10",
        "max": "90",
        "avpkt": "1000",
        "burst": "30",
    },
    "pfifo": {
        "limit": "100",
    },
}


def resolve_qdisc_params(qdisc_name, override_json, flow_count):
    # CRITICAL FIX: fq_codel crashes in NeST when custom 'flows' string is passed.
    # Passing an empty dictionary forces NeST to issue 'tc qdisc add dev ... fq_codel'
    # using native Linux kernel defaults    #if qdisc_name == "fq_codel" and not override_json:
    #    return {}

    params = dict(DEFAULT_QDISC_PARAMS.get(qdisc_name, {}))

    if override_json:
        try:
            overrides = json.loads(override_json)
        except json.JSONDecodeError as exc:
            print(f"Invalid --qdisc-params JSON: {exc}", file=sys.stderr)
            sys.exit(1)
        #params.update(overrides)
        params.update({k: str(v) for k, v in overrides.items()})

    return params

def edge_link_delay_for_rtt(rtt_ms, bottleneck_delay_ms):
    """
    Path (one way): sender -> r1 -> r2 -> receiver, i.e.
        one_way = edge_delay + bottleneck_delay + edge_delay
    RTT = 2 * one_way = 4*edge_delay + 2*bottleneck_delay
    => edge_delay = (rtt_ms - 2*bottleneck_delay_ms) / 4
    """
    edge_delay = (rtt_ms - 2 * bottleneck_delay_ms) / 4
    if edge_delay < 1:
        print(
            f"Warning: requested RTT {rtt_ms}ms is too small",
            file=sys.stderr,
        )
        edge_delay = 1
    return edge_delay

def start_pulse_wave(interface, high_bw, low_bw, interval, duration):
    """Background worker to periodically toggle bottleneck link bandwidth."""
    def pulse_loop():
        start_time = time.time()
        is_high = True
        
        # Wait initial interval before starting pulse toggles
        while (time.time() - start_time) < duration:
            time.sleep(interval)
            if (time.time() - start_time) >= duration:
                break
            
            is_high = not is_high
            new_bw = high_bw if is_high else low_bw
            print(f"[Pulse Wave] Toggling Bottleneck Bandwidth to: {new_bw}")
            try:
                interface.set_attributes(bandwidth=new_bw)
            except Exception as e:
                print(f"[Pulse Wave Error]: {e}", file=sys.stderr)

    thread = threading.Thread(target=pulse_loop, daemon=True)
    thread.start()

def main():
    args = parse_args()

    n_tcp = args.tcp_flows
    k_udp = args.udp_flows
    total_flows = n_tcp + k_udp

    if total_flows == 0:
        print("At least one TCP or UDP flow must be requested.", file=sys.stderr)
        sys.exit(1)

    tcp_rtts = parse_csv_list(args.tcp_rtts, n_tcp, float, 100.0)
    udp_rtts = parse_csv_list(args.udp_rtts, k_udp, float, 100.0)
    udp_rates = parse_csv_list(args.udp_rates, k_udp, str, "9mbit")

    qdisc_params = resolve_qdisc_params(args.qdisc, args.qdisc_params, total_flows)

    gap_seconds = args.start_gap / 1000.0
    duration = args.duration

    #Topology

    r1 = Router("r1")
    r2 = Router("r2")

    net_counter = [0]

    def next_network():
        net_counter[0] += 1
        idx = net_counter[0]
        return Network(f"192.168.{idx}.0/24")

   
    bottleneck_net = next_network()
    (etr1_r2, etr2_r1) = connect(r1, r2, network=bottleneck_net)

    tcp_flow_conns = []  # (sender, receiver, eth_s, etr1_s, etr2_r, eth_r, rtt_ms)
    for i in range(n_tcp):
        sender = Node(f"ts{i + 1}")
        receiver = Node(f"tr{i + 1}")
        (eth_s, etr1_s) = connect(sender, r1, network=next_network())
        (etr2_r, eth_r) = connect(r2, receiver, network=next_network())
        tcp_flow_conns.append((sender, receiver, eth_s, etr1_s, etr2_r, eth_r, tcp_rtts[i]))

    udp_flow_conns = []  # (sender, receiver, eth_s, etr1_s, etr2_r, eth_r, rtt_ms, rate)
    for j in range(k_udp):
        sender = Node(f"us{j + 1}")
        receiver = Node(f"ur{j + 1}")
        (eth_s, etr1_s) = connect(sender, r1, network=next_network())
        (etr2_r, eth_r) = connect(r2, receiver, network=next_network())
        udp_flow_conns.append(
            (sender, receiver, eth_s, etr1_s, etr2_r, eth_r, udp_rtts[j], udp_rates[j])
        )




# Enable ECN on the host nodes
    sender.configure_tcp_param("ecn", "1")
    receiver.configure_tcp_param("ecn", "1")
    AddressHelper.assign_addresses()
    initial_bw = args.high_bw if args.pulsebw else args.bottleneck_bandwidth
    etr1_r2.set_attributes(
        args.bottleneck_bandwidth,
        f"{args.bottleneck_delay}ms",
        args.qdisc,
        **qdisc_params,
    )
    etr2_r1.set_attributes(args.bottleneck_bandwidth, f"{args.bottleneck_delay}ms")
    r1.add_route("DEFAULT", etr1_r2)
    r2.add_route("DEFAULT", etr2_r1)

    tcp_flows_info = []  # (flow_obj, start_time)
    udp_flows_info = []  # (flow_obj, start_time, target_bandwidth)

    flow_index = 0  # used for staggered start times, across all flows

    for (sender, receiver, eth_s, etr1_s, etr2_r, eth_r, rtt_ms) in tcp_flow_conns:
        edge_delay = edge_link_delay_for_rtt(rtt_ms, args.bottleneck_delay)

        eth_s.set_attributes(args.edge_bandwidth, f"{edge_delay}ms")
        etr1_s.set_attributes(args.edge_bandwidth, f"{edge_delay}ms")
        etr2_r.set_attributes(args.edge_bandwidth, f"{edge_delay}ms")
        eth_r.set_attributes(args.edge_bandwidth, f"{edge_delay}ms")

        sender.add_route("DEFAULT", eth_s)
        receiver.add_route("DEFAULT", eth_r)

        start_time = int(flow_index * gap_seconds)
        end_time = int(start_time + duration)
        flow = Flow(sender, receiver, eth_r.get_address(), start_time, end_time, 1)
        tcp_flows_info.append((flow, start_time))

        flow_index += 1

    for (sender, receiver, eth_s, etr1_s, etr2_r, eth_r, rtt_ms, rate) in udp_flow_conns:
        edge_delay = edge_link_delay_for_rtt(rtt_ms, args.bottleneck_delay)

        eth_s.set_attributes(args.edge_bandwidth, f"{edge_delay}ms")
        etr1_s.set_attributes(args.edge_bandwidth, f"{edge_delay}ms")
        etr2_r.set_attributes(args.edge_bandwidth, f"{edge_delay}ms")
        eth_r.set_attributes(args.edge_bandwidth, f"{edge_delay}ms")

        sender.add_route("DEFAULT", eth_s)
        receiver.add_route("DEFAULT", eth_r)

        start_time = int(flow_index * gap_seconds)
        end_time = int(start_time + duration)
        flow = Flow(sender, receiver, eth_r.get_address(), start_time, end_time, 1)
        udp_flows_info.append((flow, start_time, rate))

        flow_index += 1

    exp = Experiment(args.experiment_name)

    for flow, _start_time in tcp_flows_info:
        exp.add_tcp_flow(flow,tool="iperf3")

    for flow, _start_time, target_bandwidth in udp_flows_info:
        exp.add_udp_flow(flow, target_bandwidth=target_bandwidth)

    exp.require_qdisc_stats(etr1_r2)
    if args.pulsebw:
        total_exp_duration = (flow_index * gap_seconds) + duration
        start_pulse_wave(
            etr1_r2,
            args.high_bw,
            args.low_bw,
            args.pulse_interval,
            total_exp_duration,
        )
    exp.run()

if __name__ == "__main__":
    main()