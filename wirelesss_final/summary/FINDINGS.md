# FQ-PIE target sweep - findings

Canonical pipeline semantics (same as `runAllTargets.sh` + `plot_targets.py`):
100 Mbit / 20 ms one-way bottleneck, 100 ms RTT, cubic, FQ-PIE target sweep,
steady state = mean of the last 50% of each trace.

Queue delay is measured on the bottleneck `fq_pie` qdisc from `tc`
`backlog`, minus the fair-queue service batch (one packet per non-empty
flow) that `tc` includes in `backlog` but that PIE does not regulate.
`queue_delay_ms` is that PIE-regulated value; `queue_delay_backlog_ms` is
the raw `backlog x 8 / capacity` value kept for reference.

## pulse_wave/bandwidth/bw100mbit

- Traffic scenario: Pulse Wave - bottleneck toggles between 100% and 50% capacity.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.955-0.959 Mbps (aggregate 95.47 Mbps).
- Link utilisation 95.5-95.9%.
- Queue delay rises with target: 2.12 ms at 5 ms -> 27.39 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 2.12-27.39 ms (raw backlog/capacity 21.56-48.19 ms). Achieved/target ratio 0.42-0.91 (1.00 = exactly at the configured operating point).
- Packet loss 3.21-3.24%; Jain 0.9973-0.9993.

## pulse_wave/bandwidth/bw10mbit

- Traffic scenario: Pulse Wave - bottleneck toggles between 100% and 50% capacity.
- 10 TCP flows, 10 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.952-0.952 Mbps (aggregate 9.52 Mbps).
- Link utilisation 95.2-95.2%.
- Queue delay rises with target: 4.36 ms at 5 ms -> 26.34 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 4.36-26.34 ms (raw backlog/capacity 23.11-47.80 ms). Achieved/target ratio 0.55-0.88 (1.00 = exactly at the configured operating point).
- Packet loss 1.80-1.85%; Jain 0.9999-1.0000.

## pulse_wave/delay/rtt120ms

- Traffic scenario: Pulse Wave - bottleneck toggles between 100% and 50% capacity.
- 100 TCP flows, 100 Mbit, RTT 120 ms, queue limit default.
- Per-flow throughput 0.953-0.956 Mbps (aggregate 95.32 Mbps).
- Link utilisation 95.3-95.6%.
- Queue delay rises with target: 1.31 ms at 5 ms -> 26.76 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.31-26.76 ms (raw backlog/capacity 21.93-48.11 ms). Achieved/target ratio 0.26-0.89 (1.00 = exactly at the configured operating point).
- Packet loss 3.05-3.23%; Jain 0.9990-0.9997.

## pulse_wave/delay/rtt60ms

- Traffic scenario: Pulse Wave - bottleneck toggles between 100% and 50% capacity.
- 100 TCP flows, 100 Mbit, RTT 60 ms, queue limit default.
- Per-flow throughput 0.968-0.968 Mbps (aggregate 96.77 Mbps).
- Link utilisation 96.8-96.8%.
- Queue delay rises with target: 8.79 ms at 5 ms -> 22.67 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 8.79-22.67 ms (raw backlog/capacity 29.13-43.68 ms). Achieved/target ratio 0.76-1.76 (1.00 = exactly at the configured operating point).
- Packet loss 3.28-3.51%; Jain 0.9977-0.9983.

## pulse_wave/load/load100flows

- Traffic scenario: Pulse Wave - bottleneck toggles between 100% and 50% capacity.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.960-0.964 Mbps (aggregate 95.99 Mbps).
- Link utilisation 96.0-96.4%.
- Queue delay rises with target: 2.16 ms at 5 ms -> 27.88 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 2.16-27.88 ms (raw backlog/capacity 21.58-48.86 ms). Achieved/target ratio 0.40-0.93 (1.00 = exactly at the configured operating point).
- Packet loss 3.52-3.59%; Jain 0.9974-0.9986.

## pulse_wave/load/load10flows

- Traffic scenario: Pulse Wave - bottleneck toggles between 100% and 50% capacity.
- 10 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 9.535-9.556 Mbps (aggregate 95.35 Mbps).
- Link utilisation 95.4-95.6%.
- Queue delay rises with target: 3.18 ms at 5 ms -> 11.96 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.18-11.96 ms (raw backlog/capacity 4.94-13.96 ms). Achieved/target ratio 0.40-0.64 (1.00 = exactly at the configured operating point).
- Packet loss 0.68-0.70%; Jain 0.9968-0.9999.

## pulse_wave/queue/queue1000pkt

- Traffic scenario: Pulse Wave - bottleneck toggles between 100% and 50% capacity.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit 1000.
- Per-flow throughput 0.958-0.961 Mbps (aggregate 95.84 Mbps).
- Link utilisation 95.8-96.1%.
- Queue delay rises with target: 1.77 ms at 5 ms -> 27.18 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.77-27.18 ms (raw backlog/capacity 20.95-48.39 ms). Achieved/target ratio 0.35-0.91 (1.00 = exactly at the configured operating point).
- Packet loss 2.66-2.79%; Jain 0.9957-0.9981.

## pulse_wave/queue/queue100pkt

- Traffic scenario: Pulse Wave - bottleneck toggles between 100% and 50% capacity.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit 100.
- Per-flow throughput 0.963-0.964 Mbps (aggregate 96.32 Mbps).
- Link utilisation 96.3-96.4%.
- Queue delay rises with target: 1.09 ms at 5 ms -> 1.76 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.09-1.76 ms (raw backlog/capacity 16.75-17.27 ms). Achieved/target ratio 0.06-0.22 (1.00 = exactly at the configured operating point).
- Packet loss 2.14-2.22%; Jain 0.9930-0.9957.

## rtt_fairness/bandwidth/bw100mbit

- Traffic scenario: RTT fairness - flows get mixed RTTs (0.5x / 1x / 2x the case RTT).
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.961-1.124 Mbps (aggregate 96.11 Mbps).
- Link utilisation 96.1-112.4%.
- Queue delay rises with target: 3.29 ms at 5 ms -> 24.16 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.29-24.16 ms (raw backlog/capacity 22.71-44.10 ms). Achieved/target ratio 0.66-0.81 (1.00 = exactly at the configured operating point).
- Packet loss 3.66-3.78%; Jain 0.9515-0.9979.

## rtt_fairness/bandwidth/bw10mbit

- Traffic scenario: RTT fairness - flows get mixed RTTs (0.5x / 1x / 2x the case RTT).
- 10 TCP flows, 10 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.953-0.956 Mbps (aggregate 9.53 Mbps).
- Link utilisation 95.3-95.6%.
- Queue delay rises with target: 4.65 ms at 5 ms -> 22.79 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 4.65-22.79 ms (raw backlog/capacity 23.72-43.95 ms). Achieved/target ratio 0.74-0.93 (1.00 = exactly at the configured operating point).
- Packet loss 2.60-2.75%; Jain 0.9992-0.9996.

## rtt_fairness/delay/rtt120ms

- Traffic scenario: RTT fairness - flows get mixed RTTs (0.5x / 1x / 2x the case RTT).
- 100 TCP flows, 100 Mbit, RTT 120 ms, queue limit default.
- Per-flow throughput 0.958-0.960 Mbps (aggregate 95.85 Mbps).
- Link utilisation 95.8-96.0%.
- Queue delay rises with target: 3.94 ms at 5 ms -> 23.89 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.94-23.89 ms (raw backlog/capacity 23.43-44.63 ms). Achieved/target ratio 0.78-0.82 (1.00 = exactly at the configured operating point).
- Packet loss 3.63-3.79%; Jain 0.9949-0.9983.

## rtt_fairness/delay/rtt60ms

- Traffic scenario: RTT fairness - flows get mixed RTTs (0.5x / 1x / 2x the case RTT).
- 100 TCP flows, 100 Mbit, RTT 60 ms, queue limit default.
- Per-flow throughput 1.035-1.035 Mbps (aggregate 103.46 Mbps).
- Link utilisation 103.5-103.5%.
- Queue delay rises with target: 5.91 ms at 5 ms -> 22.44 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 5.91-22.44 ms (raw backlog/capacity 25.85-43.43 ms). Achieved/target ratio 0.75-1.18 (1.00 = exactly at the configured operating point).
- Packet loss 3.41-3.60%; Jain 0.9856-0.9981.

## rtt_fairness/load/load100flows

- Traffic scenario: RTT fairness - flows get mixed RTTs (0.5x / 1x / 2x the case RTT).
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.958-0.964 Mbps (aggregate 95.77 Mbps).
- Link utilisation 95.8-96.4%.
- Queue delay rises with target: 3.56 ms at 5 ms -> 23.60 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.56-23.60 ms (raw backlog/capacity 22.84-44.35 ms). Achieved/target ratio 0.71-0.79 (1.00 = exactly at the configured operating point).
- Packet loss 3.51-3.71%; Jain 0.9964-0.9976.

## rtt_fairness/load/load10flows

- Traffic scenario: RTT fairness - flows get mixed RTTs (0.5x / 1x / 2x the case RTT).
- 10 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 9.549-9.572 Mbps (aggregate 95.49 Mbps).
- Link utilisation 95.5-95.7%.
- Queue delay rises with target: 3.47 ms at 5 ms -> 16.33 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.47-16.33 ms (raw backlog/capacity 5.35-18.40 ms). Achieved/target ratio 0.54-0.69 (1.00 = exactly at the configured operating point).
- Packet loss 0.41-0.42%; Jain 0.9912-0.9948.

## rtt_fairness/queue/queue1000pkt

- Traffic scenario: RTT fairness - flows get mixed RTTs (0.5x / 1x / 2x the case RTT).
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit 1000.
- Per-flow throughput 0.964-0.965 Mbps (aggregate 96.38 Mbps).
- Link utilisation 96.4-96.5%.
- Queue delay rises with target: 3.98 ms at 5 ms -> 24.22 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.98-24.22 ms (raw backlog/capacity 23.11-44.85 ms). Achieved/target ratio 0.73-0.81 (1.00 = exactly at the configured operating point).
- Packet loss 3.16-3.23%; Jain 0.9958-0.9978.

## rtt_fairness/queue/queue100pkt

- Traffic scenario: RTT fairness - flows get mixed RTTs (0.5x / 1x / 2x the case RTT).
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit 100.
- Per-flow throughput 0.966-0.969 Mbps (aggregate 96.58 Mbps).
- Link utilisation 96.6-96.9%.
- Queue delay rises with target: 1.12 ms at 5 ms -> 4.14 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.12-4.14 ms (raw backlog/capacity 16.59-17.79 ms). Achieved/target ratio 0.14-0.22 (1.00 = exactly at the configured operating point).
- Packet loss 2.10-2.20%; Jain 0.8920-0.9588.

## staggered/bandwidth/bw100mbit

- Traffic scenario: Staggered flows - 250 ms gap between flow starts (capped at 10 s total).
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.785-0.798 Mbps (aggregate 78.48 Mbps).
- Link utilisation 78.5-79.8%.
- Queue delay rises with target: 1.29 ms at 5 ms -> 23.44 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.29-23.44 ms (raw backlog/capacity 16.47-41.17 ms). Achieved/target ratio 0.26-0.78 (1.00 = exactly at the configured operating point).
- Packet loss 3.08-3.16%; Jain 0.9670-0.9778.

## staggered/bandwidth/bw10mbit

- Traffic scenario: Staggered flows - 250 ms gap between flow starts (capped at 10 s total).
- 10 TCP flows, 10 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.907-0.909 Mbps (aggregate 9.07 Mbps).
- Link utilisation 90.7-90.9%.
- Queue delay rises with target: 3.18 ms at 5 ms -> 24.86 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.18-24.86 ms (raw backlog/capacity 20.59-45.36 ms). Achieved/target ratio 0.52-0.83 (1.00 = exactly at the configured operating point).
- Packet loss 2.66-2.75%; Jain 0.9992-0.9998.

## staggered/delay/rtt120ms

- Traffic scenario: Staggered flows - 250 ms gap between flow starts (capped at 10 s total).
- 100 TCP flows, 100 Mbit, RTT 120 ms, queue limit default.
- Per-flow throughput 0.787-0.794 Mbps (aggregate 78.67 Mbps).
- Link utilisation 78.7-79.4%.
- Queue delay rises with target: 1.47 ms at 5 ms -> 22.09 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.47-22.09 ms (raw backlog/capacity 16.08-39.47 ms). Achieved/target ratio 0.29-0.74 (1.00 = exactly at the configured operating point).
- Packet loss 2.92-2.98%; Jain 0.9675-0.9762.

## staggered/delay/rtt60ms

- Traffic scenario: Staggered flows - 250 ms gap between flow starts (capped at 10 s total).
- 100 TCP flows, 100 Mbit, RTT 60 ms, queue limit default.
- Per-flow throughput 0.793-0.798 Mbps (aggregate 79.33 Mbps).
- Link utilisation 79.3-79.8%.
- Queue delay rises with target: 7.10 ms at 5 ms -> 21.70 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 7.10-21.70 ms (raw backlog/capacity 23.67-39.03 ms). Achieved/target ratio 0.69-1.42 (1.00 = exactly at the configured operating point).
- Packet loss 2.54-2.81%; Jain 0.9660-0.9723.

## staggered/load/load100flows

- Traffic scenario: Staggered flows - 250 ms gap between flow starts (capped at 10 s total).
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.784-0.799 Mbps (aggregate 78.35 Mbps).
- Link utilisation 78.4-79.9%.
- Queue delay rises with target: 1.08 ms at 5 ms -> 23.17 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.08-23.17 ms (raw backlog/capacity 15.98-40.43 ms). Achieved/target ratio 0.22-0.77 (1.00 = exactly at the configured operating point).
- Packet loss 3.05-3.16%; Jain 0.9642-0.9789.

## staggered/load/load10flows

- Traffic scenario: Staggered flows - 250 ms gap between flow starts (capped at 10 s total).
- 10 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 8.959-9.009 Mbps (aggregate 89.59 Mbps).
- Link utilisation 89.6-90.1%.
- Queue delay rises with target: 2.87 ms at 5 ms -> 11.94 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 2.87-11.94 ms (raw backlog/capacity 4.47-13.85 ms). Achieved/target ratio 0.40-0.57 (1.00 = exactly at the configured operating point).
- Packet loss 0.36-0.40%; Jain 0.9995-0.9998.

## staggered/queue/queue1000pkt

- Traffic scenario: Staggered flows - 250 ms gap between flow starts (capped at 10 s total).
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit 1000.
- Per-flow throughput 0.784-0.948 Mbps (aggregate 78.43 Mbps).
- Link utilisation 78.4-94.8%.
- Queue delay rises with target: 1.31 ms at 5 ms -> 26.04 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.31-26.04 ms (raw backlog/capacity 16.31-44.47 ms). Achieved/target ratio 0.26-0.87 (1.00 = exactly at the configured operating point).
- Packet loss 2.97-3.07%; Jain 0.8434-0.9780.

## staggered/queue/queue100pkt

- Traffic scenario: Staggered flows - 250 ms gap between flow starts (capped at 10 s total).
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit 100.
- Per-flow throughput 0.787-0.796 Mbps (aggregate 78.67 Mbps).
- Link utilisation 78.7-79.6%.
- Queue delay rises with target: 1.00 ms at 5 ms -> 1.98 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.00-1.98 ms (raw backlog/capacity 14.00-14.25 ms). Achieved/target ratio 0.07-0.20 (1.00 = exactly at the configured operating point).
- Packet loss 1.87-1.89%; Jain 0.9684-0.9756.

## synchronous/bandwidth/bw100mbit

- Traffic scenario: Synchronous Fairness - all flows start together with equal RTT.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.956-0.963 Mbps (aggregate 95.61 Mbps).
- Link utilisation 95.6-96.3%.
- Queue delay rises with target: 2.05 ms at 5 ms -> 28.19 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 2.05-28.19 ms (raw backlog/capacity 21.65-49.33 ms). Achieved/target ratio 0.41-0.94 (1.00 = exactly at the configured operating point).
- Packet loss 3.08-3.50%; Jain 0.9984-0.9988.

## synchronous/bandwidth/bw10mbit

- Traffic scenario: Synchronous Fairness - all flows start together with equal RTT.
- 10 TCP flows, 10 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.952-0.952 Mbps (aggregate 9.52 Mbps).
- Link utilisation 95.2-95.2%.
- Queue delay rises with target: 3.71 ms at 5 ms -> 27.23 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.71-27.23 ms (raw backlog/capacity 22.40-48.52 ms). Achieved/target ratio 0.47-0.91 (1.00 = exactly at the configured operating point).
- Packet loss 1.80-1.88%; Jain 0.9999-1.0000.

## synchronous/delay/rtt120ms

- Traffic scenario: Synchronous Fairness - all flows start together with equal RTT.
- 100 TCP flows, 100 Mbit, RTT 120 ms, queue limit default.
- Per-flow throughput 0.957-1.021 Mbps (aggregate 95.66 Mbps).
- Link utilisation 95.7-102.1%.
- Queue delay rises with target: 1.30 ms at 5 ms -> 26.72 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.30-26.72 ms (raw backlog/capacity 20.41-48.13 ms). Achieved/target ratio 0.26-0.89 (1.00 = exactly at the configured operating point).
- Packet loss 3.36-4.39%; Jain 0.9904-0.9994.

## synchronous/delay/rtt60ms

- Traffic scenario: Synchronous Fairness - all flows start together with equal RTT.
- 100 TCP flows, 100 Mbit, RTT 60 ms, queue limit default.
- Per-flow throughput 0.975-0.976 Mbps (aggregate 97.46 Mbps).
- Link utilisation 97.5-97.6%.
- Queue delay rises with target: 8.59 ms at 5 ms -> 23.92 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 8.59-23.92 ms (raw backlog/capacity 28.97-44.76 ms). Achieved/target ratio 0.79-1.72 (1.00 = exactly at the configured operating point).
- Packet loss 3.31-3.66%; Jain 0.9965-0.9991.

## synchronous/load/load100flows

- Traffic scenario: Synchronous Fairness - all flows start together with equal RTT.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.957-0.957 Mbps (aggregate 95.67 Mbps).
- Link utilisation 95.7-95.7%.
- Queue delay rises with target: 2.52 ms at 5 ms -> 27.44 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 2.52-27.44 ms (raw backlog/capacity 22.54-48.28 ms). Achieved/target ratio 0.46-0.91 (1.00 = exactly at the configured operating point).
- Packet loss 3.28-3.39%; Jain 0.9974-0.9996.

## synchronous/load/load10flows

- Traffic scenario: Synchronous Fairness - all flows start together with equal RTT.
- 10 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 9.535-9.554 Mbps (aggregate 95.35 Mbps).
- Link utilisation 95.4-95.5%.
- Queue delay rises with target: 3.14 ms at 5 ms -> 11.99 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.14-11.99 ms (raw backlog/capacity 4.88-14.03 ms). Achieved/target ratio 0.40-0.63 (1.00 = exactly at the configured operating point).
- Packet loss 0.69-0.73%; Jain 0.9995-0.9999.

## synchronous/queue/queue1000pkt

- Traffic scenario: Synchronous Fairness - all flows start together with equal RTT.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit 1000.
- Per-flow throughput 0.962-0.968 Mbps (aggregate 96.22 Mbps).
- Link utilisation 96.2-96.8%.
- Queue delay rises with target: 1.92 ms at 5 ms -> 27.71 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.92-27.71 ms (raw backlog/capacity 20.98-48.61 ms). Achieved/target ratio 0.35-0.92 (1.00 = exactly at the configured operating point).
- Packet loss 2.68-2.84%; Jain 0.9962-0.9987.

## synchronous/queue/queue100pkt

- Traffic scenario: Synchronous Fairness - all flows start together with equal RTT.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit 100.
- Per-flow throughput 0.967-0.967 Mbps (aggregate 96.65 Mbps).
- Link utilisation 96.7-96.7%.
- Queue delay rises with target: 1.13 ms at 5 ms -> 2.19 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.13-2.19 ms (raw backlog/capacity 16.75-17.54 ms). Achieved/target ratio 0.07-0.23 (1.00 = exactly at the configured operating point).
- Packet loss 2.12-2.20%; Jain 0.9950-0.9971.

## udp_background/bandwidth/bw100mbit

- Traffic scenario: UDP background - bulk UDP flows compete with the TCP flows.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.876-0.987 Mbps (aggregate 96.36 Mbps).
- Link utilisation 96.4-108.5%.
- Queue delay rises with target: 3.94 ms at 5 ms -> 24.07 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.94-24.07 ms (raw backlog/capacity 24.12-46.25 ms). Achieved/target ratio 0.58-0.80 (1.00 = exactly at the configured operating point).
- Packet loss 11.72-13.74%; Jain 0.9745-0.9989.

## udp_background/bandwidth/bw10mbit

- Traffic scenario: UDP background - bulk UDP flows compete with the TCP flows.
- 10 TCP flows, 10 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.795-0.799 Mbps (aggregate 9.54 Mbps).
- Link utilisation 95.4-95.9%.
- Queue delay rises with target: 8.44 ms at 5 ms -> 24.90 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 8.44-24.90 ms (raw backlog/capacity 30.35-48.79 ms). Achieved/target ratio 0.83-1.69 (1.00 = exactly at the configured operating point).
- Packet loss 5.09-5.27%; Jain 0.9997-0.9999.

## udp_background/delay/rtt120ms

- Traffic scenario: UDP background - bulk UDP flows compete with the TCP flows.
- 100 TCP flows, 100 Mbit, RTT 120 ms, queue limit default.
- Per-flow throughput 0.872-0.873 Mbps (aggregate 95.90 Mbps).
- Link utilisation 95.9-96.1%.
- Queue delay rises with target: 6.70 ms at 5 ms -> 27.12 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 6.70-27.12 ms (raw backlog/capacity 26.30-49.24 ms). Achieved/target ratio 0.84-1.34 (1.00 = exactly at the configured operating point).
- Packet loss 13.24-13.75%; Jain 0.9975-0.9992.

## udp_background/delay/rtt60ms

- Traffic scenario: UDP background - bulk UDP flows compete with the TCP flows.
- 100 TCP flows, 100 Mbit, RTT 60 ms, queue limit default.
- Per-flow throughput 0.881-0.886 Mbps (aggregate 96.86 Mbps).
- Link utilisation 96.9-97.4%.
- Queue delay rises with target: 8.78 ms at 5 ms -> 21.89 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 8.78-21.89 ms (raw backlog/capacity 29.44-43.11 ms). Achieved/target ratio 0.73-1.76 (1.00 = exactly at the configured operating point).
- Packet loss 13.29-14.19%; Jain 0.9950-0.9989.

## udp_background/load/load100flows

- Traffic scenario: UDP background - bulk UDP flows compete with the TCP flows.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 0.872-0.880 Mbps (aggregate 95.93 Mbps).
- Link utilisation 95.9-96.8%.
- Queue delay rises with target: 3.82 ms at 5 ms -> 23.98 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.82-23.98 ms (raw backlog/capacity 23.93-46.30 ms). Achieved/target ratio 0.57-0.80 (1.00 = exactly at the configured operating point).
- Packet loss 13.18-13.68%; Jain 0.9983-0.9990.

## udp_background/load/load10flows

- Traffic scenario: UDP background - bulk UDP flows compete with the TCP flows.
- 10 TCP flows, 100 Mbit, RTT 100 ms, queue limit default.
- Per-flow throughput 7.986-7.990 Mbps (aggregate 95.83 Mbps).
- Link utilisation 95.8-95.9%.
- Queue delay rises with target: 3.44 ms at 5 ms -> 16.12 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 3.44-16.12 ms (raw backlog/capacity 5.44-18.16 ms). Achieved/target ratio 0.54-0.69 (1.00 = exactly at the configured operating point).
- Packet loss 2.66-3.28%; Jain 0.9982-0.9991.

## udp_background/queue/queue1000pkt

- Traffic scenario: UDP background - bulk UDP flows compete with the TCP flows.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit 1000.
- Per-flow throughput 0.881-0.882 Mbps (aggregate 96.92 Mbps).
- Link utilisation 96.9-97.0%.
- Queue delay rises with target: 4.05 ms at 5 ms -> 24.11 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 4.05-24.11 ms (raw backlog/capacity 24.19-46.18 ms). Achieved/target ratio 0.57-0.81 (1.00 = exactly at the configured operating point).
- Packet loss 12.70-13.12%; Jain 0.9972-0.9978.

## udp_background/queue/queue100pkt

- Traffic scenario: UDP background - bulk UDP flows compete with the TCP flows.
- 100 TCP flows, 100 Mbit, RTT 100 ms, queue limit 100.
- Per-flow throughput 0.893-0.895 Mbps (aggregate 98.26 Mbps).
- Link utilisation 98.3-98.4%.
- Queue delay rises with target: 1.01 ms at 5 ms -> 1.85 ms at 30 ms.
- Queue delay at the bottleneck fq_pie qdisc: 1.01-1.85 ms (raw backlog/capacity 15.35-15.84 ms). Achieved/target ratio 0.06-0.20 (1.00 = exactly at the configured operating point).
- Packet loss 8.50-9.09%; Jain 0.9784-0.9842.
