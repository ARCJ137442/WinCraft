---
title: WinCraft performance measurement protocol
updated_at: 2026-10-27
last_verified_at: 2026-10-27
protocol_baseline: 0.3
status: measurement-protocol
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

## Current evidence boundary

Rust, Node, Python and protocol correctness checks pass, but the repository has not run a controlled long-running performance campaign, process-handle audit, sleep/wake run or threshold-setting ADR. Therefore no CPU, memory, latency, throughput or leak claim is made. The current release remains `NOT_RUN` for B11-01-A1/A2 and `PASS` only for A3's rule that unmeasured performance must not be advertised.

## Reproduction entry points

```powershell
cargo test --workspace --no-fail-fast
npm run check
python -m unittest discover -s tests -v
python scripts/check_contracts.py
```

These commands validate correctness and contracts; they do not substitute for the native measurement campaign. A future campaign must use an isolated release target, synthetic providers, an explicit stop time, and redacted evidence. It must not include runtime descriptors, tokens, note bodies or live business telemetry.
