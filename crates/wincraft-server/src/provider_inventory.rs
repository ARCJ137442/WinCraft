use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;
use wincraft_core::Fault;

const INVENTORY_KIND: &str = "wincraft.inventory.draft";
const INVENTORY_SCHEMA_VERSION: &str = "draft-2026-10-29";
const REGISTRATION_KIND: &str = "wincraft.inventory.registration";
const REGISTRATION_SCHEMA_VERSION: &str = "draft-2026-10-29";
const INVENTORY_RESPONSE_TTL_SECONDS: u32 = 30;
const MAX_INVENTORY_VALID_FOR_SECONDS: u32 = 3600;
const MAX_SOURCE_FRESH_FOR_SECONDS: u32 = 86_400;
const MAX_PROVIDERS_PER_INVENTORY: usize = 128;

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum ProviderInventoryState {
    Online,
    Offline,
    Degraded,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ProviderInventoryRegistration {
    kind: String,
    schema_version: String,
    generation: u64,
    observed_at: String,
    valid_for_seconds: u32,
    providers: Vec<ProviderInventorySourceRegistration>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProviderInventorySourceRegistration {
    source_id: String,
    source_instance_id: String,
    provider_type: String,
    display_name: String,
    adapter_contract: u32,
    state: ProviderInventoryState,
    capabilities: Vec<String>,
    source_updated_at: String,
    fresh_for_seconds: u32,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct ProviderInventorySnapshot {
    kind: &'static str,
    schema_version: &'static str,
    endpoint_id: Uuid,
    generation: u64,
    observed_at: String,
    valid_for_seconds: u32,
    providers: Vec<ProviderInventorySource>,
}

impl ProviderInventorySnapshot {
    pub(crate) fn generation(&self) -> u64 {
        self.generation
    }
}

#[derive(Clone, Debug, Serialize)]
struct ProviderInventorySource {
    id: String,
    instance_id: String,
    provider_type: String,
    display_name: String,
    adapter_contract: u32,
    state: ProviderInventoryState,
    capabilities: Vec<String>,
    grants: Vec<String>,
    source_updated_at: String,
    fresh_for_seconds: u32,
}

struct SessionInventory {
    providers: Vec<ProviderInventorySource>,
    generation: u64,
    valid_for_seconds: u32,
    observed_at: OffsetDateTime,
    disconnected_at_ms: Option<u64>,
    degraded_for_snapshot_expiry: bool,
}

#[derive(Default)]
pub(crate) struct ProviderInventoryRegistry {
    generation: u64,
    sessions: BTreeMap<Uuid, SessionInventory>,
}

impl ProviderInventoryRegistry {
    pub(crate) fn register(
        &mut self,
        session: Uuid,
        endpoint_id: Uuid,
        registration: ProviderInventoryRegistration,
        now_ms: u64,
        now: OffsetDateTime,
    ) -> Result<ProviderInventorySnapshot, Fault> {
        let prepared = prepare_registration(registration, now)?;
        self.prune_expired(now_ms);
        let existing = self.sessions.get(&session);
        if existing.is_some_and(|current| prepared.generation <= current.generation) {
            return Err(Fault::new(
                "STALE_INVENTORY",
                "inventory generation must advance for each registration",
            ));
        }
        let providers_elsewhere: usize = self
            .sessions
            .iter()
            .filter(|(owner, _)| **owner != session)
            .map(|(_, inventory)| inventory.providers.len())
            .sum();
        if providers_elsewhere + prepared.providers.len() > MAX_PROVIDERS_PER_INVENTORY {
            return Err(Fault::new(
                "INVENTORY_LIMIT",
                "host inventory provider limit exceeded",
            ));
        }

        let identities: BTreeSet<String> = prepared
            .providers
            .iter()
            .map(|source| source.source_instance_id.clone())
            .collect();
        if self.sessions.iter().any(|(owner, inventory)| {
            *owner != session
                && inventory
                    .providers
                    .iter()
                    .any(|provider| identities.contains(&provider.instance_id))
        }) {
            return Err(Fault::new(
                "DUPLICATE_INVENTORY_IDENTITY",
                "provider instance id is already registered on this endpoint",
            ));
        }

        let mut providers = Vec::with_capacity(prepared.providers.len());
        for source in prepared.providers {
            let prior_grants = existing
                .and_then(|inventory| {
                    inventory.providers.iter().find(|provider| {
                        provider.id == source.source_id
                            && provider.instance_id == source.source_instance_id
                    })
                })
                .map(|provider| provider.grants.clone())
                .unwrap_or_default();
            let grants = prior_grants
                .into_iter()
                .filter(|permission| source.capabilities.contains(permission))
                .collect();
            providers.push(ProviderInventorySource {
                id: source.source_id,
                instance_id: source.source_instance_id,
                provider_type: source.provider_type,
                display_name: source.display_name,
                adapter_contract: source.adapter_contract,
                state: source.state,
                capabilities: source.capabilities,
                // Provider claims are descriptive; only a separate host action populates grants.
                grants,
                source_updated_at: source.source_updated_at,
                fresh_for_seconds: source.fresh_for_seconds,
            });
        }

        self.sessions.insert(
            session,
            SessionInventory {
                providers,
                generation: prepared.generation,
                valid_for_seconds: prepared.valid_for_seconds,
                observed_at: prepared.observed_at,
                disconnected_at_ms: None,
                degraded_for_snapshot_expiry: false,
            },
        );
        self.generation = self.generation.saturating_add(1).max(1);
        self.snapshot(endpoint_id, now_ms, now)
    }

    pub(crate) fn disconnect(&mut self, session: Uuid, now_ms: u64) {
        let Some(inventory) = self.sessions.get_mut(&session) else {
            return;
        };
        if inventory.disconnected_at_ms.is_none() {
            inventory.disconnected_at_ms = Some(now_ms);
            self.generation = self.generation.saturating_add(1).max(1);
        }
    }

    /// Grant only capabilities the identified live provider already declared.
    /// This method is host-internal; provider registration cannot set grants.
    pub(crate) fn grant_permissions(
        &mut self,
        instance_id: &str,
        permissions: &[String],
        endpoint_id: Uuid,
        now_ms: u64,
        now: OffsetDateTime,
    ) -> Result<ProviderInventorySnapshot, Fault> {
        if permissions.is_empty() || permissions.len() > 64 {
            return Err(Fault::new(
                "INVALID_GRANT",
                "at least one bounded permission is required",
            ));
        }
        let mut unique = BTreeSet::new();
        if permissions
            .iter()
            .any(|permission| !valid_inventory_id(permission) || !unique.insert(permission.clone()))
        {
            return Err(Fault::new(
                "INVALID_GRANT",
                "permission identifiers must be valid and unique",
            ));
        }
        self.prune_expired(now_ms);
        let mut changed = false;
        let mut found = false;
        for inventory in self.sessions.values_mut() {
            if inventory.disconnected_at_ms.is_some() {
                continue;
            }
            for provider in &mut inventory.providers {
                if provider.instance_id != instance_id {
                    continue;
                }
                found = true;
                let source_updated =
                    parse_timestamp(&provider.source_updated_at, "source_updated_at")?;
                if provider.state != ProviderInventoryState::Online
                    || now
                        >= source_updated
                            + time::Duration::seconds(i64::from(provider.fresh_for_seconds))
                {
                    return Err(Fault::new(
                        "PROVIDER_NOT_ONLINE",
                        "host permissions require an online and fresh provider instance",
                    ));
                }
                if permissions
                    .iter()
                    .any(|permission| !provider.capabilities.contains(permission))
                {
                    return Err(Fault::new(
                        "GRANT_NOT_DECLARED",
                        "host grants must match capabilities declared by this provider",
                    ));
                }
                for permission in permissions {
                    if !provider.grants.contains(permission) {
                        provider.grants.push(permission.clone());
                        changed = true;
                    }
                }
                provider.grants.sort();
                provider.grants.dedup();
            }
        }
        if !found {
            return Err(Fault::new(
                "PROVIDER_NOT_ONLINE",
                "the selected provider instance is no longer registered",
            ));
        }
        if changed {
            self.generation = self.generation.saturating_add(1).max(1);
        }
        self.snapshot(endpoint_id, now_ms, now)
    }

    pub(crate) fn session_for_instance(&self, instance_id: &str) -> Option<Uuid> {
        self.sessions.iter().find_map(|(session, inventory)| {
            (inventory.disconnected_at_ms.is_none()
                && inventory
                    .providers
                    .iter()
                    .any(|provider| provider.instance_id == instance_id))
            .then_some(*session)
        })
    }

    pub(crate) fn snapshot(
        &mut self,
        endpoint_id: Uuid,
        now_ms: u64,
        now: OffsetDateTime,
    ) -> Result<ProviderInventorySnapshot, Fault> {
        self.prune_expired(now_ms);

        let mut degraded_transitions = 0u64;
        for inventory in self.sessions.values_mut() {
            let snapshot_expired = (now - inventory.observed_at).whole_seconds()
                >= i64::from(inventory.valid_for_seconds);
            if inventory.disconnected_at_ms.is_none()
                && snapshot_expired
                && !inventory.degraded_for_snapshot_expiry
            {
                inventory.degraded_for_snapshot_expiry = true;
                degraded_transitions += 1;
            }
        }
        self.generation = self.generation.saturating_add(degraded_transitions);

        let mut providers = Vec::new();
        for inventory in self.sessions.values() {
            let disconnected = inventory.disconnected_at_ms.is_some();
            for source in &inventory.providers {
                let mut source = source.clone();
                if disconnected {
                    source.state = ProviderInventoryState::Offline;
                } else if inventory.degraded_for_snapshot_expiry
                    && source.state == ProviderInventoryState::Online
                {
                    source.state = ProviderInventoryState::Degraded;
                }
                providers.push(source);
            }
        }
        providers.sort_by(|left, right| {
            (&left.display_name, &left.id, &left.instance_id).cmp(&(
                &right.display_name,
                &right.id,
                &right.instance_id,
            ))
        });

        Ok(ProviderInventorySnapshot {
            kind: INVENTORY_KIND,
            schema_version: INVENTORY_SCHEMA_VERSION,
            endpoint_id,
            generation: self.generation.max(1),
            observed_at: format_timestamp(now)?,
            valid_for_seconds: INVENTORY_RESPONSE_TTL_SECONDS,
            providers,
        })
    }

    fn prune_expired(&mut self, now_ms: u64) {
        let expired_sessions: Vec<Uuid> = self
            .sessions
            .iter()
            .filter_map(|(session, inventory)| {
                inventory.disconnected_at_ms.and_then(|disconnected_at| {
                    let retention_ms = u64::from(inventory.valid_for_seconds) * 1000;
                    (now_ms.saturating_sub(disconnected_at) >= retention_ms).then_some(*session)
                })
            })
            .collect();
        if !expired_sessions.is_empty() {
            for session in expired_sessions {
                self.sessions.remove(&session);
            }
            self.generation = self.generation.saturating_add(1).max(1);
        }
    }
}

struct PreparedRegistration {
    generation: u64,
    observed_at: OffsetDateTime,
    valid_for_seconds: u32,
    providers: Vec<PreparedProvider>,
}

struct PreparedProvider {
    source_id: String,
    source_instance_id: String,
    provider_type: String,
    display_name: String,
    adapter_contract: u32,
    state: ProviderInventoryState,
    capabilities: Vec<String>,
    source_updated_at: String,
    fresh_for_seconds: u32,
}

fn prepare_registration(
    registration: ProviderInventoryRegistration,
    now: OffsetDateTime,
) -> Result<PreparedRegistration, Fault> {
    if registration.kind != REGISTRATION_KIND
        || registration.schema_version != REGISTRATION_SCHEMA_VERSION
        || registration.generation == 0
        || registration.valid_for_seconds == 0
        || registration.valid_for_seconds > MAX_INVENTORY_VALID_FOR_SECONDS
        || registration.providers.len() > MAX_PROVIDERS_PER_INVENTORY
    {
        return Err(Fault::new(
            "INVALID_INVENTORY",
            "inventory header is invalid",
        ));
    }

    let observed_at = parse_timestamp(&registration.observed_at, "observed_at")?;
    if observed_at > now {
        return Err(Fault::new(
            "INVALID_INVENTORY",
            "observed_at is in the future",
        ));
    }

    let mut identities = BTreeSet::new();
    let mut providers = Vec::with_capacity(registration.providers.len());
    for source in registration.providers {
        if !valid_inventory_id(&source.source_id)
            || !valid_inventory_id(&source.source_instance_id)
            || !valid_inventory_id(&source.provider_type)
            || source.display_name.trim().is_empty()
            || source.display_name.chars().count() > 256
            || source.adapter_contract == 0
            || source.capabilities.len() > 64
            || source.fresh_for_seconds == 0
            || source.fresh_for_seconds > MAX_SOURCE_FRESH_FOR_SECONDS
        {
            return Err(Fault::new(
                "INVALID_INVENTORY",
                "provider metadata is invalid",
            ));
        }
        if !identities.insert(source.source_instance_id.clone()) {
            return Err(Fault::new(
                "DUPLICATE_INVENTORY_IDENTITY",
                "provider instance ids must be unique within a registration",
            ));
        }

        let mut capability_ids = BTreeSet::new();
        for capability in &source.capabilities {
            if !valid_inventory_id(capability) || !capability_ids.insert(capability) {
                return Err(Fault::new(
                    "INVALID_INVENTORY",
                    "capability ids must be valid and unique",
                ));
            }
        }
        let source_updated_at = parse_timestamp(&source.source_updated_at, "source_updated_at")?;
        if source_updated_at > observed_at {
            return Err(Fault::new(
                "INVALID_INVENTORY",
                "source_updated_at is later than observed_at",
            ));
        }
        providers.push(PreparedProvider {
            source_id: source.source_id,
            source_instance_id: source.source_instance_id,
            provider_type: source.provider_type,
            display_name: source.display_name,
            adapter_contract: source.adapter_contract,
            state: source.state,
            capabilities: source.capabilities,
            source_updated_at: format_timestamp(source_updated_at)?,
            fresh_for_seconds: source.fresh_for_seconds,
        });
    }

    Ok(PreparedRegistration {
        generation: registration.generation,
        observed_at,
        valid_for_seconds: registration.valid_for_seconds,
        providers,
    })
}

fn valid_inventory_id(value: &str) -> bool {
    let mut characters = value.chars();
    characters
        .next()
        .is_some_and(|first| first.is_ascii_alphanumeric())
        && value.len() <= 96
        && characters.all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '_' | '.' | ':' | '-')
        })
}

fn parse_timestamp(value: &str, field: &str) -> Result<OffsetDateTime, Fault> {
    OffsetDateTime::parse(value, &Rfc3339)
        .map_err(|_| Fault::new("INVALID_INVENTORY", format!("{field} must be RFC3339")))
}

fn format_timestamp(value: OffsetDateTime) -> Result<String, Fault> {
    value
        .format(&Rfc3339)
        .map_err(|_| Fault::new("INTERNAL", "could not format inventory timestamp"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn now() -> OffsetDateTime {
        OffsetDateTime::parse("2026-10-29T12:00:00Z", &Rfc3339).unwrap()
    }

    fn registration(generation: u64, valid_for_seconds: u32) -> ProviderInventoryRegistration {
        serde_json::from_value(json!({
            "kind": REGISTRATION_KIND,
            "schema_version": REGISTRATION_SCHEMA_VERSION,
            "generation": generation,
            "observed_at": "2026-10-29T12:00:00Z",
            "valid_for_seconds": valid_for_seconds,
            "providers": [
                {
                    "source_id": "source.codex-app",
                    "source_instance_id": "codex-instance-a",
                    "provider_type": "codex-app",
                    "display_name": "Same display name",
                    "adapter_contract": 1,
                    "state": "online",
                    "capabilities": ["activity.read"],
                    "source_updated_at": "2026-10-29T11:59:59Z",
                    "fresh_for_seconds": 60
                },
                {
                    "source_id": "source.codex-app",
                    "source_instance_id": "codex-instance-b",
                    "provider_type": "codex-app",
                    "display_name": "Same display name",
                    "adapter_contract": 1,
                    "state": "degraded",
                    "capabilities": ["activity.read"],
                    "source_updated_at": "2026-10-29T11:59:00Z",
                    "fresh_for_seconds": 30
                }
            ]
        }))
        .unwrap()
    }

    #[test]
    fn registration_preserves_instance_identity_and_never_turns_claims_into_grants() {
        let mut registry = ProviderInventoryRegistry::default();
        let session = Uuid::new_v4();
        let snapshot = registry
            .register(session, Uuid::from_u128(1), registration(1, 60), 100, now())
            .unwrap();

        assert_eq!(snapshot.endpoint_id, Uuid::from_u128(1));
        assert_eq!(snapshot.providers.len(), 2);
        assert_eq!(
            snapshot.providers[0].display_name,
            snapshot.providers[1].display_name
        );
        assert_eq!(snapshot.providers[0].id, snapshot.providers[1].id);
        assert_ne!(
            snapshot.providers[0].instance_id,
            snapshot.providers[1].instance_id
        );
        assert!(snapshot
            .providers
            .iter()
            .all(|provider| provider.grants.is_empty()));
        let serialized = serde_json::to_string(&snapshot).unwrap();
        for forbidden in ["token", "lease", "scene", "data"] {
            assert!(!serialized.contains(forbidden));
        }
    }

    #[test]
    fn only_host_approval_grants_declared_permissions_and_same_session_refresh_preserves_them() {
        let mut registry = ProviderInventoryRegistry::default();
        let session = Uuid::new_v4();
        registry
            .register(session, Uuid::from_u128(1), registration(1, 60), 100, now())
            .unwrap();
        let granted = registry
            .grant_permissions(
                "codex-instance-a",
                &["activity.read".into()],
                Uuid::from_u128(1),
                101,
                now(),
            )
            .unwrap();
        let approved = granted
            .providers
            .iter()
            .find(|provider| provider.instance_id == "codex-instance-a")
            .unwrap();
        let unapproved = granted
            .providers
            .iter()
            .find(|provider| provider.instance_id == "codex-instance-b")
            .unwrap();
        assert_eq!(approved.grants, vec!["activity.read"]);
        assert!(unapproved.grants.is_empty());

        let refreshed = registry
            .register(session, Uuid::from_u128(1), registration(2, 60), 102, now())
            .unwrap();
        assert_eq!(
            refreshed
                .providers
                .iter()
                .find(|provider| provider.instance_id == "codex-instance-a")
                .unwrap()
                .grants,
            vec!["activity.read"]
        );
    }

    #[test]
    fn instance_id_is_unique_across_sources_on_the_endpoint() {
        let mut registry = ProviderInventoryRegistry::default();
        registry
            .register(
                Uuid::new_v4(),
                Uuid::from_u128(1),
                registration(1, 60),
                100,
                now(),
            )
            .unwrap();
        let mut duplicate = registration(1, 60);
        duplicate.providers.truncate(1);
        duplicate.providers[0].source_id = "source.other".into();
        assert_eq!(
            registry
                .register(Uuid::new_v4(), Uuid::from_u128(1), duplicate, 101, now())
                .unwrap_err()
                .code,
            "DUPLICATE_INVENTORY_IDENTITY"
        );
    }

    #[test]
    fn disconnected_sources_are_offline_then_expire_from_the_ephemeral_registry() {
        let mut registry = ProviderInventoryRegistry::default();
        let session = Uuid::new_v4();
        registry
            .register(session, Uuid::from_u128(1), registration(1, 2), 100, now())
            .unwrap();
        registry.disconnect(session, 200);

        let offline = registry.snapshot(Uuid::from_u128(1), 201, now()).unwrap();
        assert!(offline
            .providers
            .iter()
            .all(|provider| provider.state == ProviderInventoryState::Offline));
        let expired = registry.snapshot(Uuid::from_u128(1), 2200, now()).unwrap();
        assert!(expired.providers.is_empty());
    }

    #[test]
    fn host_inventory_has_a_global_provider_bound() {
        let mut registry = ProviderInventoryRegistry::default();
        let first_session = Uuid::new_v4();
        let mut full = registration(1, 60);
        full.providers = (0..MAX_PROVIDERS_PER_INVENTORY)
            .map(|index| ProviderInventorySourceRegistration {
                source_id: format!("source.{index}"),
                source_instance_id: format!("instance.{index}"),
                provider_type: "fixture".into(),
                display_name: format!("Source {index}"),
                adapter_contract: 1,
                state: ProviderInventoryState::Online,
                capabilities: vec!["status.read".into()],
                source_updated_at: "2026-10-29T12:00:00Z".into(),
                fresh_for_seconds: 60,
            })
            .collect();
        let snapshot = registry
            .register(first_session, Uuid::from_u128(1), full, 100, now())
            .unwrap();
        assert_eq!(snapshot.providers.len(), MAX_PROVIDERS_PER_INVENTORY);

        let mut additional = registration(1, 60);
        additional.providers.truncate(1);
        assert_eq!(
            registry
                .register(Uuid::new_v4(), Uuid::from_u128(1), additional, 101, now())
                .unwrap_err()
                .code,
            "INVENTORY_LIMIT"
        );
    }

    #[test]
    fn expired_registration_snapshot_becomes_degraded_not_offline() {
        let mut registry = ProviderInventoryRegistry::default();
        let session = Uuid::new_v4();
        let mut stale_registration = registration(1, 1);
        stale_registration.observed_at = "2026-10-29T11:59:58Z".into();
        for provider in &mut stale_registration.providers {
            provider.source_updated_at = "2026-10-29T11:59:57Z".into();
        }

        let snapshot = registry
            .register(session, Uuid::from_u128(1), stale_registration, 100, now())
            .unwrap();

        assert!(snapshot
            .providers
            .iter()
            .all(|provider| provider.state == ProviderInventoryState::Degraded));
    }

    #[test]
    fn inventory_generation_and_timestamps_fail_closed() {
        let mut registry = ProviderInventoryRegistry::default();
        let session = Uuid::new_v4();
        registry
            .register(session, Uuid::from_u128(1), registration(2, 60), 100, now())
            .unwrap();
        assert_eq!(
            registry
                .register(session, Uuid::from_u128(1), registration(2, 60), 101, now())
                .unwrap_err()
                .code,
            "STALE_INVENTORY"
        );

        let invalid_grant_claim = json!({
            "kind": REGISTRATION_KIND,
            "schema_version": REGISTRATION_SCHEMA_VERSION,
            "generation": 1,
            "observed_at": "2026-10-29T12:00:00Z",
            "valid_for_seconds": 60,
            "providers": [{
                "source_id": "source.one",
                "source_instance_id": "instance.one",
                "provider_type": "example",
                "display_name": "Example",
                "adapter_contract": 1,
                "state": "online",
                "capabilities": ["example.read"],
                "grants": ["example.read"],
                "source_updated_at": "2026-10-29T11:59:00Z",
                "fresh_for_seconds": 60
            }]
        });
        assert!(
            serde_json::from_value::<ProviderInventoryRegistration>(invalid_grant_claim).is_err()
        );
    }
}
