# FQ-PIE Setup

This document lists all changes required to configure the repository `scripts/` for `fq_pie` (Flow Queue PIE) and the edits already applied in this workspace.

NeST already supports `fq_pie` (`nest/nest/topology/interface/base_interface.py:580` -> `qdisc_list = ["choke","codel","fq_codel","pie","fq_pie","pfifo","red"]`) and provides reference example `nest/examples/qdiscs/fq-pie-point-to-point.py:77-82` (`qdisc="fq_pie"`, `{"limit":"100","flows":"2","target":"2ms"}`).

## 1. Changes Overview

| File | Before | After | Reason |
|------|--------|-------|--------|
| `scripts/dumbbell.py:103-105` | `default="fq_codel"` `choices=["fq_codel","codel","pie","red","pfifo"]` | `default="fq_pie"` `choices=["fq_codel","codel","pie","fq_pie","red","pfifo"]` | Accept `fq_pie` from CLI, make it default |
| `scripts/dumbbell.py:141-168` | `DEFAULT_QDISC_PARAMS` had 5 entries | Added `fq_pie` entry (see below) | Provide sane defaults for `fq_pie` |
| `scripts/pulseWave.py:88-89` | same as dumbbell | `default="fq_pie"` + `fq_pie` in choices | Consistency for pulse-wave topology |
| `scripts/pulseWave.py:114-142` | same 5 entries | Added `fq_pie` entry | Same |
| `scripts/run-scenarios.sh:40` | `QDISCS=("fq_codel")` | `QDISCS=("fq_pie")` | Single-run driver uses `fq_pie` |
| `scripts/runPulseWave.sh:37` | `QDISCS=("fq_codel")` | `QDISCS=("fq_pie")` | Pulse scenario uses `fq_pie` |
| `scripts/runExperiment.sh` | `OUTPUT_FOLDER="fq_codelpp_dat_files"`, paths `results/synchronous/fq_codel`, `RENAMED_DIR=.../fq_codelpp_$i`, `FOLDER_PATH=...fq_codelpp...`, `OUTPUT_FILE=comparison/fq_codelpp_*.dat` | `fq_pie_dat_files`, `results/synchronous/fq_pie`, `fq_pie_$i`, `FOLDER_PATH=fq_pie_dat_files`, `comparison/fq_pie_*.dat` | Output directories/prefixes match `fq_pie` |
| `scripts/runExperiment_original.sh` | `fq_codel_dat_files`, `results/.../fq_codel`, `fq_codel_$i`, `comparison/fq_codel_*.dat` | `fq_pie_dat_files` (same as above) | Both 25x harnesses now target `fq_pie`; previously one was `fq_codel` baseline, one `fq_codelpp` modified |

Files intentionally **not** changed (no functional impact, only plot labels):
- `scripts/plot:9-36`, `scripts/plot_script:11-282` still reference `fq_codel`/`fq_codelpp` filenames - update if you want EPS titles to say `fq_pie`.
- `scripts/percentile_all.py:43-44` (`fq_codel_*.dat` vs `fq_codelpp_*.dat`) - update to `fq_pie_*.dat` vs custom variant if comparing two `fq_pie` configs.
- `scripts/bulk_plot.py:1933` example tuple `("fq_codel","FQ-CoDel")` - change to `("fq_pie","FQ-PIE")` when doing multi-algo comparison.
- `scripts/link.py:35-40` hardcoded `/home/deepa/...` paths - unchanged; adapt to your `$PWD` when testing link utilization.

## 2. Detailed Diff

### 2.1 `scripts/dumbbell.py:141-168` and `scripts/pulseWave.py:114-142`
Added:
```python
"fq_pie": {
    "limit": "100",
    "flows": "1024",
    "target": "5ms",
    "tupdate": "15ms",
    "alpha": "2",
    "beta": "20",
},
```
Values align with `nest/examples/qdiscs/fq-pie-point-to-point.py:78-82` (`limit 100`, `target 2ms` default) plus PIE tuning (`tupdate 15ms`, `alpha 2`, `beta 20` from `man tc-fq_pie`). `flows 1024` matches `fq_codel` default for 100-flow experiments (`plan.md` traffic-load up to 12 Mbit/s, 100 TCP flows in `run-scenarios.sh:52`). Override per experiment via CLI:
```bash
sudo python3 scripts/dumbbell.py --qdisc fq_pie --qdisc-params '{"target":"1ms","limit":"50"}'
```

### 2.2 `scripts/dumbbell.py:102-105` / `pulseWave.py:86-89`
```diff
- default="fq_codel" choices=["fq_codel","codel","pie","red","pfifo"]
+ default="fq_pie"   choices=["fq_codel","codel","pie","fq_pie","red","pfifo"]
```

### 2.3 `scripts/run-scenarios.sh:40` / `runPulseWave.sh:37`
```diff
- QDISCS=("fq_codel")
+ QDISCS=("fq_pie")
```
No change to `SCENARIOS` or `SCENARIO_ARGS`; `run-scenarios.sh:52` still `"-n 100 --start-gap 0"` synchronous case. For `plan.md` matrix, run multiple times with different args (see §4).

### 2.4 `scripts/runExperiment.sh` / `runExperiment_original.sh`
Full sed applied:
```
s/fq_codelpp_dat_files/fq_pie_dat_files/g
s|results/.../fq_codel|results/.../fq_pie|g  (all 5 scenario dirs)
s/fq_codel_$i/fq_pie_$i/g
s|comparison/fq_codel|comparison/fq_pie|g
s/FOLDER_PATH=.*fq_codel/FOLDER_PATH=...fq_pie/
```
Example after edit `runExperiment.sh:20-50`:
```bash
OUTPUT_FOLDER="fq_pie_dat_files"
cd /home/deepa/nest/fq_pie_dat_files
cd /home/deepa/nest/results/synchronous/fq_pie
RENAMED_DIR="/home/deepa/nest/results/synchronous/fq_pie/fq_pie_$i"
FOLDER_PATH="/home/deepa/nest/fq_pie_dat_files"
OUTPUT_FILE="./comparison/fq_pie_${BASENAME}.dat"
```

## 3. How to Run (FQ-PIE)

### 3.1 Single run (quick test)
```bash
cd /path/to/wireless-FQPIE-NEST
sudo python3 scripts/dumbbell.py -n 10 --qdisc fq_pie --duration 20 --experiment-name test_fq_pie
# or via wrapper
sudo ./scripts/run-scenarios.sh scripts/dumbbell.py
# pulse bandwidth toggle
sudo ./scripts/runPulseWave.sh scripts/pulseWave.py
# with custom target (plan.md Target 1..4)
sudo python3 scripts/dumbbell.py --qdisc fq_pie --qdisc-params '{"target":"1ms"}' --bottleneck-bandwidth 10mbit
```

### 3.2 Repeated 25 runs (statistics)
Edit absolute paths `/home/deepa/nest` in both `runExperiment*.sh` to your repo root if different, then:
```bash
sudo bash scripts/runExperiment.sh
# produces fq_pie_dat_files/<key>/*.dat -> comparison/fq_pie_*.dat (averaged via scripts/averagedat.py:31)
```
`runExperiment.sh` and `runExperiment_original.sh` are now identical (both `fq_pie`); keep one or rename second to `runExperiment_fq_pie_1ms.sh` for baseline.

### 3.3 Target sweep for plan.md (72 experiments)
`plan.md:10-14` defines targets `1ms,2ms,5ms,10ms` across 4 scenarios (bandwidth 5/10/20/50 Mbit, delay 1/5/10/20/50 ms, queue 50/100/200/500 pkts, load 2/5/7/9/12 Mbit). Example nested loop:
```bash
for target in 1ms 2ms 5ms 10ms; do
  for bw in 5mbit 10mbit 20mbit 50mbit; do
    sudo python3 scripts/dumbbell.py --qdisc fq_pie \
      --qdisc-params "{\"target\":\"$target\",\"limit\":\"100\"}" \
      --bottleneck-bandwidth $bw --bottleneck-delay 20 \
      --experiment-name bw_${bw}_target_${target}
  done
done
```
Adapt for delay (`--bottleneck-delay`), queue (`--qdisc-params '{"limit":"50"}'` etc.), load (`--udp-rates` or `-n`/`-k`).

## 4. Verification

```bash
# syntax check
python3 -m py_compile scripts/dumbbell.py scripts/pulseWave.py
bash -n scripts/run-scenarios.sh scripts/runPulseWave.sh scripts/runExperiment.sh scripts/runExperiment_original.sh

# check qdisc choices
grep -n "fq_pie" scripts/dumbbell.py scripts/pulseWave.py
# should show choices and DEFAULT_QDISC_PARAMS

# check shell QDISCS
grep -n "QDISCS" scripts/run-scenarios.sh scripts/runPulseWave.sh

# check no stale fq_codel paths in harnesses
grep -n "fq_codel" scripts/runExperiment.sh scripts/runExperiment_original.sh
# only comments about NeST crash for fq_codel (line 180) should remain
```

## 5. Notes

- `scripts/dumbbell.py:287-288` has pre-existing bug: `sender.configure_tcp_param` outside loop uses last-iteration variable. Works for `fq_pie` but ideally iterate over all `tcp_flow_conns`/`udp_flow_conns`.
- `scripts/pulseWave.py:211,219` calls `interface.set_bandwidth` twice per toggle (duplicate). Not changed for minimal diff.
- `RESULTS_DIR="results"` permissions `chmod 777` at end of `run-scenarios.sh:91` / `runPulseWave.sh:85` retained.
- If you need `ECN` for `fq_pie` (disabled by default), add `"ecn": " "` or `"ecn":"1"` in `DEFAULT_QDISC_PARAMS["fq_pie"]` or via `--qdisc-params`.
