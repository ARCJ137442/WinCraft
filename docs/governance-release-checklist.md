---
title: WinCraft governance and release checklist
updated_at: 2026-10-29
last_verified_at: 2026-10-29
protocol_baseline: 0.3
status: pre-release-material
audience: maintainers, release-validator, contributors
---

# Governance and release checklist

This checklist prepares a reviewable release; it is not release authorization. A local build, repository ownership transfer or passing automated tests does not by itself authorize publishing a release or changing permissions. The long-term intent to make WinCraft repositories public does not make them public now.

## Repository boundaries and visibility

- The core repository is `exomind-team/WinCraft`; it is currently private.
- Keep the core separate from providers/applications with an independent version and release lifecycle. Name each subproject repository `wincraft-XXX`; keep each private until its own source, history, dependencies and evidence pass this checklist. Tutorials and synthetic fixtures may remain in core; avoid a duplicated second source of truth.
- A world repository may contain only reviewed, data-free blueprints and synthetic fixtures. Never commit actual world/session state, Obsidian content, notification bodies, external account data or telemetry.
- Do not change repository visibility as a side effect of source work. Public visibility is a separate release operation after the exact repository and commit pass review and the user authorizes that operation.

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

## Before changing a repository to public

- Start from a clean worktree and review the exact staged diff plus all untracked files; do not use blanket staging without inspecting the file list.
- Scan the current candidate and every reachable branch/tag history, including Git LFS, release attachments, screenshots and generated evidence. Keep secrets redacted in scanner output. `.gitignore` is not a sanitization result.
- Scan the working tree in place; do not copy runtime descriptors or other secret-bearing files to a temporary staging directory.
- Review for tokens/keys, `.runtime.json` and environment files, local paths/usernames, account/profile/session identifiers, user notes, real world state, telemetry, private logs, hidden image content, and third-party license/provenance obligations.
- Treat any credential found in history as exposed; revoke/rotate it and remove it from all history before publication. Removing it from the latest file is insufficient. Remove personal data from history or publish from a separately reviewed clean history.
- Keep raw `evidence/local/` private and ignored. Publish only a reviewed summary that contains no descriptor contents, user data or machine-specific path.
- Record the scanner/version, scope, exit code, findings disposition and remaining limits. Any unresolved finding makes the visibility change BLOCKED.

## Current WinCraft status (2026-10-29)

- `exomind-team/WinCraft` is private. The user intends future public repositories after sanitization; no visibility change or product release is authorized by this checklist.
- Full-history Gitleaks preflight had no credential findings, but a prior public commit contains a local checkout path and ignored local evidence contains stale runtime descriptors. History cleanup and a final clean-candidate scan are required before publication.
- Windows native/manual gates, cross-platform builds, signing and long-run performance remain incomplete.
- The current task audit is the source of truth for VERIFIED, IMPLEMENTED_UNVERIFIED, IN_PROGRESS, BLOCKED and NOT_STARTED work.
