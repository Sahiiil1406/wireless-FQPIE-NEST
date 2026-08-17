# FQ-PIE Target Value and Experiment Setup

## 1. Objective

The purpose of these experiments is to evaluate the behavior of **FQ-PIE** under different network conditions by changing the **target delay** and one network parameter at a time.

The FQ-PIE target parameter is configured as:

```python
fq_pie_parameters = {
    "limit": "100",
    "flows": "2",
    "target": "2ms",
}
```

The `target` value will be changed for different experiments.

---

# 2. Target Values

The following target delay values will be evaluated:

| Target Case | Target Value |
| ----------- | -----------: |
| Target 1    |         1 ms |
| Target 2    |         2 ms |
| Target 3    |         5 ms |
| Target 4    |        10 ms |

For each experiment scenario, all four target values should be tested.

---

# 3. Experiment Scenarios

There are four main experiment scenarios.

### Case 1: Bottleneck Bandwidth

In this scenario, the bottleneck bandwidth is changed while the other parameters remain fixed.

Bandwidth values:

```text
5 Mbit/s
10 Mbit/s
20 Mbit/s
50 Mbit/s
```

The experiment is performed for each target value:

```text
Target = 1 ms
Target = 2 ms
Target = 5 ms
Target = 10 ms
```

### Case 2: Propagation Delay

In this scenario, the propagation delay is changed while the other parameters remain fixed.

Delay values:

```text
1 ms
5 ms
10 ms
20 ms
50 ms
```

Each delay value is tested with all four FQ-PIE target values.

### Case 3: Queue Size

In this scenario, the queue size is changed.

Queue-size values:

```text
50 packets
100 packets
200 packets
500 packets
```

Each queue size is tested with all four FQ-PIE target values.

### Case 4: Traffic Load

In this scenario, the offered traffic load is changed.

Traffic-load values:

```text
2 Mbit/s
5 Mbit/s
7 Mbit/s
9 Mbit/s
12 Mbit/s
```

Each traffic-load value is tested with all four FQ-PIE target values.

---

# 4. Experiment Matrix

Each scenario contains four target values.

| Scenario             | Parameter Values          | Target Values  |
| -------------------- | ------------------------- | -------------- |
| Bottleneck Bandwidth | 5, 10, 20, 50 Mbit/s      | 1, 2, 5, 10 ms |
| Propagation Delay    | 1, 5, 10, 20, 50 ms       | 1, 2, 5, 10 ms |
| Queue Size           | 50, 100, 200, 500 packets | 1, 2, 5, 10 ms |
| Traffic Load         | 2, 5, 7, 9, 12 Mbit/s     | 1, 2, 5, 10 ms |

The target value is the FQ-PIE parameter being evaluated, while the scenario parameter is varied according to the experiment.

---


# 5. Number of Experiments

The total number of runs is:

```text
Bandwidth: 4 × 4 = 16
Delay:     5 × 4 = 20
Queue:     4 × 4 = 16
Traffic:   5 × 4 = 20
```

Therefore:

```text
Total = 16 + 20 + 16 + 20
      = 72 experiments
```

So, **72 experimental runs** are required to cover all combinations.

---

# 6. Summary

The experiment evaluates FQ-PIE using four target delay values:

```text
1 ms
2 ms
5 ms
10 ms
```

Four network conditions are independently varied:

```text
1. Bottleneck Bandwidth
2. Propagation Delay
3. Queue Size
4. Traffic Load
```

The complete experiment consists of **72 runs**.

The main objective is to observe how changing the FQ-PIE target value affects performance under different bandwidth, propagation-delay, queue-size, and traffic-load conditions.
