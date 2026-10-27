#!/usr/bin/env python3
"""Generate a deterministic, review-only plan from explicit JSON inputs.

This is a planning demonstrator, NOT a WinCraft client or a security sandbox.
Schema checking is performed by scripts/validate_handoff.py; runtime revalidates
all authority before any future apply operation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DRAFT = "draft-2026-10-26"
MAX_INPUT_BYTES = 1_048_576


def timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if result.tzinfo is None:
        raise ValueError("timestamp needs an explicit timezone")
    return result.astimezone(timezone.utc)


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _unique(items: list[dict[str, Any]], key: str, label: str) -> None:
    ids = [item[key] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate {label}")


def plan(pack: dict[str, Any], inventory: dict[str, Any], now: str,
         selections: dict[str, str] | None = None) -> dict[str, Any]:
    """Pure function: reads explicit authorized metadata, returns no host actions."""
    selections = dict(selections or {})
    current = timestamp(now)
    if pack.get("kind") != "wincraft.pack.draft" or inventory.get("kind") != "wincraft.inventory.draft":
        raise ValueError("wrong proposal kind")
    if pack.get("schema_version") != DRAFT or inventory.get("schema_version") != DRAFT:
        raise ValueError("unsupported draft version")
    allowed_pack = {"kind", "schema_version", "id", "version", "title", "bindings", "blueprint", "theme_id", "fallback_policy", "adapter"}
    allowed_inventory = {"kind", "schema_version", "generation", "observed_at", "valid_for_seconds", "providers"}
    if set(pack) - allowed_pack or set(inventory) - allowed_inventory:
        raise ValueError("unexpected top-level field; validate against proposal schemas")
    if len(pack["bindings"]) > 32 or len(inventory["providers"]) > 128:
        raise ValueError("planning input exceeds bounds")
    _unique(pack["bindings"], "id", "binding id")
    _unique(inventory["providers"], "instance_id", "provider instance")
    known_bindings = {b["id"] for b in pack["bindings"]}
    if set(selections) - known_bindings:
        raise ValueError("selection names an unknown binding")
    observed = timestamp(inventory["observed_at"])
    if observed > current:
        raise ValueError("inventory from the future requires clock reconciliation")
    duration = inventory["valid_for_seconds"]
    if not isinstance(duration, int) or not 1 <= duration <= 3600:
        raise ValueError("inventory validity is out of bounds")
    inventory_expires = observed + timedelta(seconds=duration)
    expired = current >= inventory_expires
    for p in inventory["providers"]:
        if timestamp(p["source_updated_at"]) > current:
            raise ValueError("source timestamp is in the future")
        if not isinstance(p["fresh_for_seconds"], int) or not 1 <= p["fresh_for_seconds"] <= 86400:
            raise ValueError("source freshness duration is out of bounds")
    bindings: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    if expired:
        blockers.append("inventory_expired")
    # The adapter is a reference, never imported or run by this planner.
    if pack.get("adapter") is not None:
        warnings.append("external_adapter_not_executed")
    earliest_expiry = min(inventory_expires, current + timedelta(seconds=60))
    for b in pack["bindings"]:
        candidates = []
        for p in inventory["providers"]:
            if expired or p["state"] != "online":
                continue
            if p["provider_type"] not in b["provider_types"]:
                continue
            if p["adapter_contract"] < b["min_adapter_contract"]:
                continue
            if not set(b["capabilities"]).issubset(p["capabilities"]):
                continue
            if not set(b["permissions"]).issubset(p["grants"]):
                continue
            if current >= timestamp(p["source_updated_at"]) + timedelta(seconds=p["fresh_for_seconds"]):
                continue
            candidates.append(p)
        chosen = None
        if b["id"] in selections:
            chosen = next((p for p in candidates if p["instance_id"] == selections[b["id"]]), None)
            if chosen is None:
                state, reason = "blocked", "explicit_selection_not_eligible"
                blockers.append(b["id"] + ":explicit_selection_not_eligible")
            else:
                state, reason = "selected", "explicit_authorized_selection"
        elif len(candidates) == 1:
            chosen = candidates[0]
            state, reason = "selected", "unique_eligible_provider"
        elif len(candidates) > 1:
            state, reason = "ambiguous", "multiple_eligible_providers_need_user_choice"
            (blockers if b["required"] else warnings).append(b["id"] + ":ambiguous")
        else:
            state, reason = "missing", "no_online_fresh_authorized_compatible_provider"
            (blockers if b["required"] else warnings).append(b["id"] + ":missing")
        if chosen is not None:
            earliest_expiry = min(earliest_expiry, timestamp(chosen["source_updated_at"]) + timedelta(seconds=chosen["fresh_for_seconds"]))
        bindings.append({"binding_id": b["id"], "provider_instance_id": chosen["instance_id"] if chosen else None,
                         "status": state, "reason": reason})
    digest_input = {"pack": pack, "inventory": inventory, "selections": selections, "now": utc(current)}
    digest = hashlib.sha256(json.dumps(digest_input, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"kind": "wincraft.plan.draft", "schema_version": DRAFT, "pack_id": pack["id"],
            "inventory_generation": inventory["generation"], "input_digest": digest,
            "created_at": utc(current), "expires_at": utc(max(current, earliest_expiry)),
            "status": "blocked" if blockers else "degraded" if warnings else "ready",
            "mutates_host": False, "requires_confirmation": True, "bindings": bindings,
            "blockers": blockers, "warnings": warnings}


def check_submission_eligibility(plan_result: dict[str, Any], *, pack_id: str,
                                  inventory_generation: int, now: str,
                                  confirmed: bool) -> tuple[bool, list[str]]:
    """Pure preflight only; never creates worlds or invokes a provider."""
    reasons: list[str] = []
    current = timestamp(now)
    if plan_result.get("kind") != "wincraft.plan.draft" or plan_result.get("schema_version") != DRAFT:
        reasons.append("unsupported_plan")
    if plan_result.get("pack_id") != pack_id:
        reasons.append("pack_mismatch")
    if plan_result.get("inventory_generation") != inventory_generation:
        reasons.append("inventory_generation_changed")
    if plan_result.get("status") != "ready":
        reasons.append("plan_not_ready")
    if plan_result.get("mutates_host") is not False:
        reasons.append("plan_mutation_flag_invalid")
    if plan_result.get("requires_confirmation") is not True or not confirmed:
        reasons.append("user_confirmation_required")
    try:
        if current >= timestamp(plan_result["expires_at"]):
            reasons.append("plan_expired")
    except (KeyError, ValueError, TypeError):
        reasons.append("invalid_expiry")
    return (not reasons, reasons)


def load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("input file exceeds 1 MiB")
    result = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(result, dict):
        raise ValueError("input must be a JSON object")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--now", required=True, help="explicit ISO8601 time, e.g. 2026-10-26T12:00:10Z")
    parser.add_argument("--selections", type=Path, help="optional explicit binding-id to provider-instance-id mapping")
    args = parser.parse_args()
    try:
        result = plan(load(args.pack), load(args.inventory), args.now, load(args.selections) if args.selections else None)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print("Planning failed: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("ready", "degraded") else 3


if __name__ == "__main__":
    raise SystemExit(main())
