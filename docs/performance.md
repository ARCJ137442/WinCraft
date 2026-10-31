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
| Workload | Tauri release started with `--open-manager`; synthetic Python `lease_probe.py` completed 41 checks. Its slow-reader subtest is configured for 1,024 snapshots of 32 KiB with a 20 ms minimum request interval; achieved message rate was not separately measured. Two separate synthetic `tests/performance_probe.py` runs each measured 50 create/destroy cycles, 200 snapshots, 100 raw 1-KiB `data.replace` calls, and 20 reconnect/write joins with a 25 ms inter-call pacing interval. No external accounts or user data were used. |
| Power/sleep context | `powercfg /getactivescheme` reported `Turbo` before and after both process-tree sampling and the latency runs. WMI reported 0 battery devices and no ACPI power-source provider; actual AC/battery source is therefore unknown. No sleep/wake transition was injected or verified. |
| Sampling | 61.203 seconds, 32 samples. Requested sleep interval was 1,000 ms; observed median interval was 1.919 s and p95 interval 2.145 s because each WMI process-tree query also takes time. |
| Process tree | Peak 8 processes: `wincraft-desktop.exe`, `msedgewebview2.exe` |
| Peak resources | Working set 580,329,472 bytes; private bytes 394,821,632; 4,262 handles; 357 threads |
| CPU | p95 machine-normalized 1.489%; p95 one-core-normalized 47.632% |
| Provider request/lifecycle latency | Two 50/200/100/20-cycle runs produced p95 ms (run 1 / run 2): `world.create` 9.778/1.710; `world.destroy` 1.325/1.353; `world.snapshot` 1.409/1.280; raw `data.replace` 1.592/1.513; reconnect + writer join 2.760/2.999. Maximum observed sample across both runs: 36.156/41.855/26.206/35.827/3.763 ms respectively. These are paced sequential loopback round trips on this machine, not UI latency or concurrent throughput. Tail spikes varied between runs and are retained rather than averaged away. |
| Cleanup | The synthetic Provider cleaned its worlds; the Tauri process was stopped; only its exact runtime descriptor was removed. Descriptor contents, bearer credentials, PIDs, and absolute paths were not recorded. |

Aggregate samples, power context, request percentiles, and run metadata are in the ignored local evidence files [`summary.json`](../evidence/local/nextgen-2026-10-31/b11-01-contextual-1793415605844/summary.json), [`process-tree-samples.json`](../evidence/local/nextgen-2026-10-31/b11-01-contextual-1793415605844/process-tree-samples.json), [`perf-context-run1.json`](../evidence/local/nextgen-2026-10-31/b11-01-contextual-1793415605844/perf-context-run1.json), and [`perf-context-run2.json`](../evidence/local/nextgen-2026-10-31/b11-01-contextual-1793415605844/perf-context-run2.json). Runtime descriptors, credentials, and raw provider logs were removed. The tools are [`tests/measure_windows_process_tree.ps1`](../tests/measure_windows_process_tree.ps1) and [`tests/performance_probe.py`](../tests/performance_probe.py).

## Current evidence boundary

`B11-01-A1` is `PASS` for this context-complete sample: machine/toolchain/artifact, synthetic workload and iteration counts, duration, process tree, handles, memory, CPU, active power plan and sequential request/lifecycle percentiles are recorded. WMI reported no battery or ACPI power-source device, so the exact AC/battery source is unknown; no sleep transition was exercised. The sample does not define a release threshold. `B11-01-A2` remains `NOT_RUN`: these short runs cannot establish leak trends, crash recovery, sleep/wake cleanup or a resource threshold ADR. `B11-01-A3` is `PASS`: unmeasured performance is not advertised. No “lightweight”, memory, CPU, latency, throughput or leak claim follows from these short runs.

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
