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

## 2026-10-31 five-minute visible refresh soak

**Given** the same Windows Tauri release and a synthetic Provider; **when** the Provider keeps its 320 × 200 world visible and replaces one synthetic counter every five seconds for five minutes while the process-tree sampler runs; **then** all 60 updates complete, the Provider destroys only its own world, and the WebView child exits. This is a bounded refresh sample, not a leak-free guarantee.

The release artifact was the same 13,600,256-byte `9073b3b` build recorded above. The actual sampler ran 333.434 seconds and collected 56 samples at a requested five-second interval; WMI query time made the observed median/p95 interval 5.940/6.237 seconds. The process tree peaked at 7 processes, 367,558,656 bytes working set, 202,756,096 private bytes, 3,655 handles, and 297 threads; p95 CPU was 0.050% machine-normalized and 1.607% one-core-normalized. During active refresh, first-five versus last-five sample medians were: working set 355,131,392 → 366,673,920 bytes; private bytes 202,338,304 → 186,630,144 bytes; handles 3,562 → 3,583; threads 289 → 277. After world cleanup, eight consecutive samples contained only the tray host (28,262,400 bytes working set, 7,020,544 private bytes, 353 handles, 40 threads). The active power plan remained `Turbo`; battery and ACPI power-source devices were not reported, so the physical power source is unknown. No sleep/wake transition was exercised.

The 60 `data.replace` transaction latencies were p50 1.524 ms, p95 12.018 ms, p99/max 35.939 ms. They are local sequential loopback timings, not UI latency or throughput. The aggregate-only local evidence is [`summary.json`](../evidence/local/nextgen-2026-10-31/b11-01-soak-1793417556075/summary.json) and [`process-tree-samples.json`](../evidence/local/nextgen-2026-10-31/b11-01-soak-1793417556075/process-tree-samples.json); runtime descriptor, raw Provider output, logs and PID files were removed.

## 2026-10-31 fifteen-minute visible refresh soak

**Given** the same Windows Tauri release and a synthetic Provider; **when** the Provider keeps a 320 × 200 world visible and replaces a synthetic counter every five seconds for 15 minutes while the process tree is sampled; **then** all 180 updates complete, the Provider destroys its world, and the WebView child exits. This extends the bounded active-refresh observation; it does not establish long-term leak freedom.

The process-tree sample ran 931.6 seconds and collected 152 samples. WMI query time made the requested five-second cadence a 6.122/6.434-second median/p95. Peak usage was 7 processes, 377,720,832 bytes working set, 207,622,144 private bytes, 3,680 handles and 303 threads; p95 CPU was 0.049% machine-normalized and 1.555% one-core-normalized. During active refresh, the first-five versus last-five sample medians were: working set 359,313,408 → 376,774,656 bytes; private bytes 206,450,688 → 196,370,432 bytes; handles 3,549 → 3,568; threads 290 → 271. Five consecutive samples after world cleanup contained only the tray Host (31,748,096 bytes working set, 7,995,392 private bytes, 336 handles, 40 threads). `Turbo` remained the active power plan; WMI reported no battery or ACPI power-source provider, leaving the physical power source unknown. No sleep/wake transition was exercised.

The 180 `data.replace` transactions had p50 1.683 ms, p95 6.653 ms, p99 23.050 ms and max 41.275 ms. These local sequential timings are not UI latency or throughput. Aggregate evidence is [`summary.json`](../evidence/local/nextgen-2026-10-31/b11-01-refresh-long-20261031-121838/summary.json) and [`process-tree-samples.json`](../evidence/local/nextgen-2026-10-31/b11-01-refresh-long-20261031-121838/process-tree-samples.json); the runtime descriptor, PID and raw Provider output were removed.

## 2026-10-31 abrupt synthetic Provider crash recovery

**Given** a release headless Rust Host and a synthetic Provider child that creates its own authenticated world; **when** the parent forcibly terminates only that child process; **then** a separate Provider observes the world as `stale`, joins as a new writer with a strictly advanced lease epoch, destroys the world, and verifies `world.snapshot` returns `NOT_FOUND`. The Host and exact runtime descriptor are then stopped and removed. This verifies one provider-process crash/reacquire path; it does not exercise a Host crash or repeated crash cycles.

The Host was built from checkout `71d92fd` with `cargo build --locked --release -p wincraft-server --bin wincraft-headless`, artifact SHA-256 `1BB21942FA052A900088624095438ACA9ACCF9B5D6E3B1E3C954D3E6EF8131B4`. The ignored local [`summary.json`](../evidence/local/nextgen-2026-10-31/b11-01-crash-20261031-121253/summary.json) records only aggregate results; its temporary world ID, join key, PID and runtime descriptor were not retained.

## 2026-10-31 forced headless Host shutdown

**Given** the release `wincraft-headless` Host and a synthetic Provider holding a disposable world; **when** the parent forcibly terminates that exact Host process; **then** the Provider receives the SDK's `connection.error` event and exits. The process descriptor and ready marker are then removed. This verifies the transport disconnect signal for one headless Host shutdown; it does not verify Tauri/WebView child cleanup or repeated restarts.

The headless artifact was `target/release/wincraft-headless.exe`, SHA-256 `1BB21942FA052A900088624095438ACA9ACCF9B5D6E3B1E3C954D3E6EF8131B4`. The local ignored [`summary.json`](../evidence/local/nextgen-2026-10-31/b11-01-host-crash-20261031-124420/summary.json) contains only aggregate status and cleanup results; no Provider IDs, runtime path, PID or event error text was retained.

## 2026-10-31 forced Tauri Host shutdown

**Given** the `9073b3b` Tauri release and a visible synthetic world owned by a test Provider; **when** the parent forcibly terminates only the Tauri root process; **then** the Provider observes `connection.error`, and all six recorded WebView descendants exit within three seconds. The exact Tauri descriptor is removed. This verifies process-tree cleanup for one forced shutdown, not window pixels or repeated restart behavior.

The release SHA-256 was `7E910E01057DADB17991B00D2A51CE63419628F818C35C06C1EE3D0C3179D691`. The ignored local [`summary.json`](../evidence/local/nextgen-2026-10-31/b11-01-tauri-crash-20261031-130240/summary.json) records aggregate process counts only; it contains no PIDs, descriptor path, world IDs or Provider output.

## Current evidence boundary

`B11-01-A1` is `PASS` for the context-complete latency samples and visible refresh soaks: machine/toolchain/artifact, synthetic workload and iteration counts, durations, process tree, handles, memory, CPU, active power plan and sequential request/lifecycle percentiles are recorded. WMI reported no battery or ACPI power-source device, so the exact AC/battery source is unknown; no sleep transition was exercised. The samples do not define a release threshold. `B11-01-A2` is `PARTIAL`: five- and 15-minute visible refresh runs completed 60 and 180 updates, respectively, and returned to a single tray-host process after world cleanup; first/last active-window private-byte medians did not rise. One abrupt synthetic Provider exit passed stale detection, epoch fencing, writer reacquisition and world cleanup; one forced headless shutdown emitted `connection.error`; one forced Tauri shutdown had six WebView descendants all exit within three seconds. These bounded checks cannot establish long-term leak absence, repeated crash/restart recovery, sleep/wake cleanup or a resource threshold ADR. `B11-01-A3` is `PASS`: unmeasured performance is not advertised. No “lightweight”, memory, CPU, latency, throughput or leak claim follows from these machine-specific samples.

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

For a bounded visible refresh sample, add `--soak-seconds 300` or `--soak-seconds 900` with `--refresh-interval-seconds 5 --soak-visible` and use an isolated release Host. The probe opens a small synthetic window, updates only synthetic counter data, and destroys its own world in a `finally` path. Run the process-tree sampler concurrently; stop the exact test Host and remove its runtime descriptor after the measurement.

For the abrupt Provider-exit case, build `wincraft-headless`, start it with no arguments, and pass its actual printed runtime descriptor to [`tests/crash_recovery_probe.py`](../tests/crash_recovery_probe.py). The probe creates a child Provider, kills only that child, verifies stale/reacquire/epoch advancement, and cleans only its own world. Stop the exact disposable Host and remove its descriptor after the run.
