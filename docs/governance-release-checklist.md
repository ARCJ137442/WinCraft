---
title: WinCraft governance and release checklist
updated_at: 2026-10-28
last_verified_at: 2026-10-28
protocol_baseline: 0.3
status: pre-release-material
audience: maintainers, release-validator, contributors
---

# Governance and release checklist

This checklist prepares a reviewable release; it is not release authorization. A local build, public source repository or passing automated tests does not by itself authorize publishing a release or changing permissions.

## Before merging source changes

- Preserve the current license, `LICENSE-NOTES.md`, upstream attribution and provenance records.
- Keep product/package names and historical paths stable unless the maintainer explicitly approves a migration.
- Review changed protocol/schema/core/native boundaries together; update tests and evidence.
- Scan changed files for runtime descriptors, bearer tokens, user notes, private paths, telemetry and restricted skill text.
- Record whether an independent review was performed for lease, IPC, auth or native-window changes; do not claim a second review when none occurred.

## Before a release artifact

- Choose `stable` or `preview`; do not imply both.
- Build from a clean, recorded commit in an isolated target directory.
- Record artifact path, byte size, SHA-256, toolchain, OS build and signed/unsigned status.
- Run the current validation matrix; do not reuse a previous release's PASS after requirements or code changed.
- List native/manual gates as PASS, FAIL, BLOCKED or NOT_RUN.
- State permissions, runtime descriptor handling, upgrade path and rollback path.
- Confirm the release package contains no descriptor, token, business data, private logs or unreviewed third-party source.
- Keep macOS/Linux claims separate from Windows; untested platforms remain NOT_RUN.

## Publication boundary

Until the user explicitly authorizes publishing, this repository may produce local source, evidence and build artifacts only. Do not create a release, upload an artifact, alter collaborators, change the license or push a release tag. A future release note must link to the exact validation evidence and enumerate known limits.

## Current WinCraft status

- Public source repository exists, but no release publication is authorized by this checklist.
- Windows native/manual gates, cross-platform builds, signing and long-run performance remain incomplete.
- The current task audit is the source of truth for VERIFIED, IMPLEMENTED_UNVERIFIED, IN_PROGRESS, BLOCKED and NOT_STARTED work.
