---
title: WinCraft performance measurement protocol
updated_at: 2026-10-31
last_verified_at: 2026-10-31
protocol_baseline: 0.3
status: partial-measured
audience: maintainer, release-validator
---

# Performance measurement protocol

This document defines how B11-01 measurements must be collected. It intentionally contains no promotional performance numbers. A result is valid only when the machine, OS build, Rust/Node/Python versions, commit, release artifact hash, provider fixture, world count, message rate, run duration and power/sleep state are recorded.

## Required measurements

- process tree and handle count for host/WebView/native helper processes;
- private bytes, working set, CPU and thread count;
- provider-to-host request latency and tail percentiles under a fixed synthetic load;
- world create/destroy and reconnect latency;
- long-running idle and refresh runs;
- cleanup after provider crash, host shutdown and sleep/wake.

## 2026-10-31 short Windows Tauri process-tree sample

This is one short synthetic measurement of the release and its visible internal Manager window while the real release Host handled `lease_probe.py`. It is a first baseline, not evidence of long-term stability or low resource use.

| Field | Observed value |
|---|---|
| Source commit / artifact | `9073b3b`; `target/release/wincraft-desktop.exe`, 13,600,256 bytes, SHA-256 `7E910E01057DADB17991B00D2A51CE63419628F818C35C06C1EE3D0C3179D691` |
| Machine | Windows 11 Pro build 22000; AMD Ryzen 9 9950X 16-Core Processor; 32 logical processors |
| Toolchain | Rust/Cargo 1.93.0; Python 3.11.4; Node 22.23.4; npm 11.19.0 |
| Workload | Tauri release started with `--open-manager`; synthetic Python `lease_probe.py` completed 41 checks. Its slow-reader subtest is configured for 1,024 snapshots of 32 KiB with a 20 ms minimum request interval; achieved message rate was not separately measured. A separate synthetic `tests/performance_probe.py` run measured 10 create/destroy cycles, 100 snapshots, 50 raw 1-KiB `data.replace` calls, and 5 reconnect/write joins with a 25 ms inter-call pacing interval. No external accounts or user data were used. |
| Sampling | 60.092 seconds, 29 samples. Requested sleep interval was 1,000 ms; observed median interval was 2.110 s and p95 interval 2.278 s because each WMI process-tree query also takes time. |
| Process tree | Peak 8 processes: `wincraft-desktop.exe`, `msedgewebview2.exe` |
| Peak resources | Working set 579,964,928 bytes; private bytes 388,829,184; 4,237 handles; 348 threads |
| CPU | p95 machine-normalized 1.257%; p95 one-core-normalized 40.231% |
| Provider request/lifecycle latency | Two 50/200/100/20-cycle runs produced p95 ms (run 1 / run 2): `world.create` 11.754/1.624; `world.destroy` 1.353/1.572; `world.snapshot` 1.346/1.296; raw `data.replace` 1.502/1.518; reconnect + writer join 1.860/1.841. Maximum observed sample across both runs: 20.474/22.493/35.785/43.430/3.061 ms respectively. These are paced sequential loopback round trips on this machine, not UI latency or concurrent throughput. Tail spikes varied between runs and are retained rather than averaged away. |
| Cleanup | The synthetic Provider cleaned its worlds; the Tauri process was stopped; only its exact runtime descriptor was removed. Descriptor contents, bearer credentials, PIDs, and absolute paths were not recorded. |

Aggregate samples, request percentiles, and run metadata are in the ignored local evidence files [`summary.json`](../evidence/local/nextgen-2026-10-31/b11-01-runtime-1793411883613/summary.json), [`process-tree-samples.json`](../evidence/local/nextgen-2026-10-31/b11-01-runtime-1793411883613/process-tree-samples.json), [`perf-probe-output-large.json`](../evidence/local/nextgen-2026-10-31/b11-01-latency-final-1793412870532/perf-probe-output-large.json), and [`perf-probe-output-large-2.json`](../evidence/local/nextgen-2026-10-31/b11-01-latency-final-1793412870532/perf-probe-output-large-2.json). Runtime descriptors, credentials, and raw provider logs were removed. The tools are [`tests/measure_windows_process_tree.ps1`](../tests/measure_windows_process_tree.ps1) and [`tests/performance_probe.py`](../tests/performance_probe.py).

## Current evidence boundary

`B11-01-A1` is `PASS` for this captured sample: machine/toolchain/artifact, synthetic workload, iteration counts, duration, process tree, handles, memory, CPU and sequential request/lifecycle percentiles are recorded. The sample does not define a release threshold. `B11-01-A2` remains `NOT_RUN`: this 60-second run cannot establish leak trends, crash recovery, sleep/wake cleanup or a resource threshold ADR. `B11-01-A3` is `PASS`: unmeasured performance is not advertised. No “lightweight”, memory, CPU, latency, throughput or leak claim follows from this short run.

## Reproduction entry points

```powershell
cargo test --workspace --no-fail-fast
npm run check
python -m unittest discover -s tests -v
python scripts/check_contracts.py
```

These commands validate correctness and contracts; they do not substitute for the native measurement campaign. A future campaign must use an isolated release target, synthetic providers, an explicit stop time, and redacted evidence. It must not include runtime descriptors, tokens, note bodies or live business telemetry.

For the Windows process-tree sampler, start the release with `--open-manager`, run the synthetic `lease_probe.py` concurrently, then sample the Tauri root PID with:

```powershell
tests/measure_windows_process_tree.ps1 -RootProcessId <tauri-pid> -DurationSeconds 60 -SampleIntervalMilliseconds 1000
```

The script emits aggregate process names and counters only. Do not save its root PID, runtime descriptor path, descriptor contents, or provider output in committed evidence. Longer idle/load, provider-latency, crash/reconnect, and sleep/wake campaigns remain separate runs.

Against the same actual descriptor, the request probe can be run with:

```powershell
python tests/performance_probe.py --runtime "<actual local descriptor>" --world-cycles 10 --snapshot-iterations 100 --data-iterations 50 --payload-bytes 1024 --reconnect-cycles 5 --inter-call-interval-ms 25
```

It creates hidden synthetic worlds, records nearest-rank p50/p95/p99 latency for create/destroy, snapshot, raw data.replace, and reconnect plus writer join, and destroys only its own worlds. Output contains aggregate timing and workload fields, never world IDs or leases.
