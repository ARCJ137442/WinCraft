#[cfg(test)]
use crate::pack_import::parse_loaded_json;
use crate::pack_import::{
    build_preview, load_pack_file, materialize_world, ImportBatch, ImportReceipt, ImportedWorld,
    ImportedWorldSummary, PackImportRegistry, PackPreview, PlanStatus, RollbackReceipt,
};
use crate::presentation_groups::PresentationGroupRegistry;
use crate::provider_inventory::{ProviderInventoryRegistration, ProviderInventoryRegistry};
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
    sync::{Arc, Mutex, MutexGuard},
    time::Instant,
};
use time::OffsetDateTime;
use tokio::{
    sync::{broadcast, watch},
    task::JoinHandle,
};
use uuid::Uuid;
use wincraft_core::*;

#[derive(Clone, Debug)]
pub enum Notice {
    Directed(Uuid, Value),
    Deleted { world_id: Uuid, members: Vec<Uuid> },
}

#[derive(Clone, Debug)]
pub struct StateChange {
    pub world_id: Uuid,
    pub sequence: u64,
    pub source: EventSource,
    pub cause_id: Option<String>,
}

#[cfg(test)]
mod capability_tests {
    use super::{Hub, StateChange};
    use serde_json::json;
    use wincraft_core::{
        EventSource, Fault, InteractionSource, JoinPolicy, Kind, NativeWindowApplication,
        NativeWindowOperation, Node, ProtocolVersion, Scene, ShortcutSpec, WindowSpec,
    };

    fn native_action_world(hub: &Hub) -> (uuid::Uuid, uuid::Uuid, wincraft_core::LeaseKey, u64) {
        let mut core = hub.lock();
        let session = core.register("native-action.test".into(), false).unwrap();
        let created = core
            .create(
                session,
                WindowSpec::default(),
                JoinPolicy::Invite,
                true,
                false,
                hub.now(),
            )
            .unwrap();
        let lease = created.lease.unwrap();
        let scene = Scene {
            root: Node::new(
                "root",
                Kind::Stack,
                json!({}),
                vec![
                    Node::new(
                        "activate-app",
                        Kind::Button,
                        json!({
                            "label":"Activate app",
                            "action":"app.activate",
                            "context_action":"app.context",
                            "native_window_action":{"application":"obsidian","operation":"activate"}
                        }),
                        vec![],
                    ),
                    Node::new(
                        "note-input",
                        Kind::Input,
                        json!({"label":"Message","action":"message.submit"}),
                        vec![],
                    ),
                    Node::new(
                        "open-codex-thread",
                        Kind::Button,
                        json!({
                            "label":"Open Codex thread",
                            "appearance":"link",
                            "action":"codex_app.open_thread",
                            "native_window_action":{"application":"codex_app","operation":"open_thread",
                                "thread_id":"00000000-0000-4000-8000-000000000001"}
                        }),
                        vec![],
                    ),
                ],
            ),
            ..Scene::default()
        };
        let updated = core
            .replace_scene(
                session,
                created.world.id,
                &lease,
                created.world.revision,
                scene,
                hub.now(),
            )
            .unwrap();
        (session, updated.id, lease, updated.revision)
    }

    #[test]
    fn host_advertises_multiline_text_and_escape_shortcut_capabilities() {
        let capabilities = Hub::new(false).capabilities();
        assert!(capabilities["components"]
            .as_array()
            .unwrap()
            .iter()
            .any(|component| component == "textarea"));
        assert!(capabilities["keyboard_shortcuts"]
            .as_array()
            .unwrap()
            .iter()
            .any(|shortcut| shortcut == "escape"));
        assert!(capabilities["keyboard_shortcuts"]
            .as_array()
            .unwrap()
            .iter()
            .any(|shortcut| shortcut == "ctrl_enter"));
        assert!(capabilities["button_features"]
            .as_array()
            .unwrap()
            .iter()
            .any(|feature| feature == "selection_groups"));
        assert!(capabilities["window_properties"]
            .as_array()
            .unwrap()
            .iter()
            .any(|property| property == "position_control"));
        assert!(capabilities["scene_features"]
            .as_array()
            .unwrap()
            .iter()
            .any(|feature| feature == "theme_tokens"));
        assert!(!capabilities["button_features"]
            .as_array()
            .unwrap()
            .iter()
            .any(|feature| feature == "external_window_actions"));
        let native_capabilities = Hub::new(true).capabilities();
        assert!(native_capabilities["button_features"]
            .as_array()
            .unwrap()
            .iter()
            .any(|feature| feature == "external_window_actions"));
        assert_eq!(
            native_capabilities["button_features"]
                .as_array()
                .unwrap()
                .iter()
                .any(|feature| feature == "codex_thread_navigation"),
            cfg!(windows)
        );
        assert!(native_capabilities["event_subscriptions"]["events"]
            .as_array()
            .unwrap()
            .iter()
            .any(
                |event| event["type"] == "window.geometry_changed" && event["delivery"] == "state"
            ));
    }

    #[test]
    fn provider_inventory_is_preview_only_and_discovery_does_not_grant_world_access() {
        let hub = Hub::new(false);
        let stable_capabilities = hub.capabilities_for(ProtocolVersion::Stable03);
        assert!(stable_capabilities.get("provider_inventory").is_none());
        assert!(stable_capabilities.get("provider_import").is_none());
        assert!(stable_capabilities.get("presentation_groups").is_none());
        let preview_capabilities = hub.capabilities_for(ProtocolVersion::ComponentLeasesPreview01);
        assert_eq!(
            preview_capabilities["provider_inventory"]["status"],
            "preview"
        );
        assert_eq!(preview_capabilities["provider_inventory"]["version"], 1);
        assert_eq!(preview_capabilities["provider_import"]["status"], "preview");
        assert_eq!(preview_capabilities["provider_import"]["version"], 1);
        assert_eq!(
            preview_capabilities["provider_import"]["schema_version"],
            "draft-2026-10-26"
        );
        assert_eq!(
            preview_capabilities["provider_import"]["event"],
            "world.import.joined"
        );
        assert_eq!(
            preview_capabilities["provider_import"]["required_claim"],
            "world.import.accept"
        );
        assert_eq!(
            preview_capabilities["provider_import"]["writer_scope"],
            "exclusive_world_lease"
        );
        assert_eq!(
            preview_capabilities["provider_import"]["requires_local_confirmation"],
            true
        );
        assert_eq!(
            preview_capabilities["presentation_groups"]["status"],
            "preview"
        );
        assert_eq!(preview_capabilities["presentation_groups"]["version"], 1);
        assert_eq!(preview_capabilities["presentation_groups"]["atomic"], false);
        assert_eq!(
            preview_capabilities["presentation_groups"]["apply_semantics"],
            "per_member_independent"
        );
        assert_eq!(
            preview_capabilities["presentation_groups"]["lease_required_per_member"],
            true
        );
        assert_eq!(
            preview_capabilities["presentation_groups"]["discovery_grants_operation_right"],
            false
        );

        let invitation = {
            let mut core = hub.lock();
            let owner = core.register("inventory.owner".into(), false).unwrap();
            core.create(
                owner,
                WindowSpec::default(),
                JoinPolicy::Invite,
                false,
                false,
                hub.now(),
            )
            .unwrap()
        };
        let source_provider = hub
            .lock()
            .register_with_protocol(
                "inventory.source".into(),
                false,
                ProtocolVersion::ComponentLeasesPreview01,
            )
            .unwrap();
        let observer = hub
            .lock()
            .register_with_protocol(
                "inventory.observer".into(),
                false,
                ProtocolVersion::ComponentLeasesPreview01,
            )
            .unwrap();
        let observed_at = time::OffsetDateTime::now_utc()
            .format(&time::format_description::well_known::Rfc3339)
            .unwrap();
        let registration = json!({
            "kind":"wincraft.inventory.registration",
            "schema_version":"draft-2026-10-29",
            "generation":1,
            "observed_at":observed_at,
            "valid_for_seconds":60,
            "providers":[
                {
                    "source_id":"source.codex",
                    "source_instance_id":"instance-a",
                    "provider_type":"agent-board",
                    "display_name":"Same source label",
                    "adapter_contract":1,
                    "state":"online",
                    "capabilities":["activity.read"],
                    "source_updated_at":observed_at,
                    "fresh_for_seconds":60
                },
                {
                    "source_id":"source.codex",
                    "source_instance_id":"instance-b",
                    "provider_type":"agent-board",
                    "display_name":"Same source label",
                    "adapter_contract":1,
                    "state":"degraded",
                    "capabilities":["activity.read"],
                    "source_updated_at":observed_at,
                    "fresh_for_seconds":30
                }
            ]
        });
        let mut forged_grants = registration.clone();
        forged_grants["providers"][0]["grants"] = json!(["activity.read"]);
        assert_eq!(
            hub.dispatch(
                source_provider,
                "provider.inventory.register",
                forged_grants,
            )
            .unwrap_err()
            .code,
            "INVALID_PARAMS"
        );
        hub.dispatch(
            source_provider,
            "provider.inventory.register",
            registration.clone(),
        )
        .unwrap();

        let listed = hub
            .dispatch(observer, "provider.inventory.list", json!({}))
            .unwrap();
        assert_eq!(listed["endpoint_id"], hub.host_id.to_string());
        let providers = listed["providers"].as_array().unwrap();
        assert_eq!(providers.len(), 2);
        assert_eq!(providers[0]["display_name"], providers[1]["display_name"]);
        assert_eq!(providers[0]["id"], providers[1]["id"]);
        assert_ne!(providers[0]["instance_id"], providers[1]["instance_id"]);
        assert!(providers
            .iter()
            .all(|provider| provider["grants"] == json!([])));
        let serialized = listed.to_string();
        for private_field in ["token", "lease", "scene", "data"] {
            assert!(!serialized.contains(private_field));
        }

        assert_eq!(
            hub.dispatch(
                observer,
                "world.join",
                json!({"world_id":invitation.world.id,"mode":"read"}),
            )
            .unwrap_err()
            .code,
            "FORBIDDEN"
        );
        let stable_provider = hub
            .lock()
            .register("inventory.stable".into(), false)
            .unwrap();
        assert_eq!(
            hub.dispatch(stable_provider, "provider.inventory.list", json!({}))
                .unwrap_err()
                .code,
            "UNSUPPORTED_CAPABILITY"
        );
    }

    #[test]
    fn native_window_action_runs_before_provider_ack_only_on_native_hosts() {
        let headless = Hub::new(false);
        let (session, world_id, _lease, revision) = native_action_world(&headless);
        let mut notices = headless.subscribe();
        let mut called = false;
        let error = headless
            .interact_with_source_with_native_window_action(
                world_id,
                "activate-app",
                serde_json::Value::Null,
                InteractionSource::Click,
                revision,
                |_| {
                    called = true;
                    Ok(())
                },
            )
            .unwrap_err();
        assert_eq!(error.code, "UNSUPPORTED_CAPABILITY");
        assert!(!called);
        assert!(matches!(
            notices.try_recv(),
            Err(tokio::sync::broadcast::error::TryRecvError::Empty)
        ));
        headless.disconnect(session);

        let native = Hub::new(true);
        let (session, world_id, _lease, revision) = native_action_world(&native);
        let mut called = false;
        let event_id = native
            .interact_with_source_with_native_window_action(
                world_id,
                "activate-app",
                serde_json::Value::Null,
                InteractionSource::Click,
                revision,
                |action| {
                    assert_eq!(action.operation, NativeWindowOperation::Activate);
                    called = true;
                    Ok(())
                },
            )
            .unwrap();
        assert!(called);
        assert!(!event_id.is_nil());
        native.disconnect(session);

        let native = Hub::new(true);
        let (session, world_id, _lease, revision) = native_action_world(&native);
        if cfg!(windows) {
            let mut called = false;
            native
                .interact_with_source_with_native_window_action(
                    world_id,
                    "open-codex-thread",
                    serde_json::Value::Null,
                    InteractionSource::Click,
                    revision,
                    |action| {
                        assert_eq!(action.application, NativeWindowApplication::CodexApp);
                        assert_eq!(action.operation, NativeWindowOperation::OpenThread);
                        assert_eq!(
                            action.thread_id.unwrap().to_string(),
                            "00000000-0000-4000-8000-000000000001"
                        );
                        called = true;
                        Ok(())
                    },
                )
                .unwrap();
            assert!(called);
        } else {
            let mut called = false;
            let error = native
                .interact_with_source_with_native_window_action(
                    world_id,
                    "open-codex-thread",
                    serde_json::Value::Null,
                    InteractionSource::Click,
                    revision,
                    |_| {
                        called = true;
                        Ok(())
                    },
                )
                .unwrap_err();
            assert_eq!(error.code, "UNSUPPORTED_CAPABILITY");
            assert!(!called);
        }
        native.disconnect(session);
    }

    #[test]
    fn native_window_action_failure_does_not_dispatch_or_ack_the_provider_event() {
        let native = Hub::new(true);
        let (session, world_id, _lease, revision) = native_action_world(&native);
        let mut notices = native.subscribe();
        let mut attempts = 0;
        let error = native
            .interact_with_source_with_native_window_action(
                world_id,
                "activate-app",
                serde_json::Value::Null,
                InteractionSource::Click,
                revision,
                |_| {
                    attempts += 1;
                    Err(Fault::new(
                        "NATIVE_WINDOW_ACTION_FAILED",
                        "Windows rejected foreground activation",
                    ))
                },
            )
            .unwrap_err();

        assert_eq!(attempts, 1);
        assert_eq!(error.code, "NATIVE_WINDOW_ACTION_FAILED");
        assert_eq!(error.message, "Windows rejected foreground activation");
        assert!(matches!(
            notices.try_recv(),
            Err(tokio::sync::broadcast::error::TryRecvError::Empty)
        ));
        assert!(native
            .renderer_snapshot(world_id)
            .unwrap()
            .actions
            .is_empty());
        native.disconnect(session);
    }

    #[test]
    fn native_window_action_without_host_work_still_dispatches_static_provider_action() {
        let native = Hub::new(true);
        let (session, world_id, _lease, revision) = native_action_world(&native);
        let mut notices = native.subscribe();
        let event_id = native
            .interact_with_source_with_native_window_action(
                world_id,
                "activate-app",
                serde_json::Value::Null,
                InteractionSource::ContextMenu,
                revision,
                |_| panic!("context gestures must not execute a click-only host action"),
            )
            .unwrap();
        assert!(!event_id.is_nil());
        assert!(matches!(
            notices.try_recv(),
            Ok(super::Notice::Directed(
                target_session,
                ref message
            )) if target_session == session && message["event"] == "interaction"
        ));
        let snapshot = native.renderer_snapshot(world_id).unwrap();
        assert_eq!(snapshot.actions.len(), 1);
        assert_eq!(snapshot.actions[0].status, "pending");
        native.disconnect(session);
    }

    #[test]
    fn ordinary_input_action_is_not_rejected_by_native_window_action_guard() {
        let native = Hub::new(true);
        let (session, world_id, _lease, revision) = native_action_world(&native);
        let mut notices = native.subscribe();

        let event_id = native
            .interact_with_source_with_native_window_action(
                world_id,
                "note-input",
                json!("synthetic input"),
                InteractionSource::Click,
                revision,
                |_| panic!("ordinary inputs do not request native window actions"),
            )
            .expect("ordinary input interaction should reach the provider");

        assert!(!event_id.is_nil());
        assert!(matches!(
            notices.try_recv(),
            Ok(super::Notice::Directed(
                target_session,
                ref message
            )) if target_session == session && message["event"] == "interaction"
        ));
        let snapshot = native.renderer_snapshot(world_id).unwrap();
        assert_eq!(snapshot.actions.len(), 1);
        assert_eq!(snapshot.actions[0].status, "pending");
        native.disconnect(session);
    }

    #[test]
    fn scoped_interactions_route_to_the_component_owner_and_require_its_lease() {
        let hub = Hub::new(false);
        let register = |name: &str| {
            hub.lock()
                .register_with_protocol(
                    name.into(),
                    false,
                    ProtocolVersion::ComponentLeasesPreview01,
                )
                .unwrap()
        };
        let authority = register("scope-action-authority");
        let focus_writer = register("scope-action-focus");
        let tasks_writer = register("scope-action-tasks");
        let late_reader = register("scope-action-late-reader");
        let created = hub
            .dispatch(
                authority,
                "world.create",
                json!({"window":{"title":"Scope action fixture"},"claim":true}),
            )
            .unwrap();
        let world_id = uuid::Uuid::parse_str(created["world"]["id"].as_str().unwrap()).unwrap();
        let world_lease = created["lease"].clone();
        let scene = json!({
            "root":{"id":"root","kind":"stack","children":[
                {"id":"focus-panel","kind":"stack","children":[
                    {"id":"focus-action","kind":"button","props":{"label":"Refresh focus","action":"focus.refresh"},"children":[]}
                ]},
                {"id":"tasks-panel","kind":"stack","children":[
                    {"id":"tasks-action","kind":"button","props":{"label":"Refresh tasks","action":"tasks.refresh"},"children":[]}
                ]}
            ]},
            "data":{"focus":{},"tasks":{}}
        });
        let replaced = hub
            .dispatch(
                authority,
                "scene.replace",
                json!({
                    "world_id":world_id,
                    "lease":world_lease,
                    "expected_revision":created["world"]["revision"],
                    "scene":scene
                }),
            )
            .unwrap();
        let partitioned = hub
            .dispatch(
                authority,
                "scope.partition",
                json!({
                    "world_id":world_id,
                    "lease":world_lease,
                    "expected_revision":replaced["revision"],
                    "scopes":[
                        {"root_node_id":"focus-panel","data_namespace":"focus"},
                        {"root_node_id":"tasks-panel","data_namespace":"tasks"}
                    ]
                }),
            )
            .unwrap();
        let grants = partitioned["scopes"].as_array().unwrap();
        let focus_grant = grants
            .iter()
            .find(|grant| grant["root_node_id"] == "focus-panel")
            .unwrap();
        let tasks_grant = grants
            .iter()
            .find(|grant| grant["root_node_id"] == "tasks-panel")
            .unwrap();
        let focus_join = hub
            .dispatch(
                focus_writer,
                "scope.join",
                json!({
                    "world_id":world_id,
                    "scope_id":focus_grant["scope_id"],
                    "generation":focus_grant["generation"],
                    "join_key":focus_grant["join_key"],
                    "mode":"write"
                }),
            )
            .unwrap();
        let tasks_join = hub
            .dispatch(
                tasks_writer,
                "scope.join",
                json!({
                    "world_id":world_id,
                    "scope_id":tasks_grant["scope_id"],
                    "generation":tasks_grant["generation"],
                    "join_key":tasks_grant["join_key"],
                    "mode":"write"
                }),
            )
            .unwrap();
        hub.dispatch(
            late_reader,
            "scope.join",
            json!({
                "world_id":world_id,
                "scope_id":focus_grant["scope_id"],
                "generation":focus_grant["generation"],
                "join_key":focus_grant["join_key"],
                "mode":"read"
            }),
        )
        .unwrap();
        assert_eq!(
            hub.dispatch(
                late_reader,
                "scope.join",
                json!({
                    "world_id":world_id,
                    "scope_id":focus_grant["scope_id"],
                    "generation":focus_grant["generation"],
                    "join_key":focus_grant["join_key"],
                    "mode":"write"
                }),
            )
            .unwrap_err()
            .code,
            "WRITE_CONFLICT"
        );

        let mut notices = hub.subscribe();
        let snapshot = hub.renderer_snapshot(world_id).unwrap();
        let focus_event = hub
            .interact_with_source(
                world_id,
                "focus-action",
                serde_json::Value::Null,
                InteractionSource::Click,
                snapshot.revision,
            )
            .unwrap();
        let (target, routed) = match notices.try_recv().unwrap() {
            super::Notice::Directed(target, message) => (target, message),
            other => panic!("unexpected notice: {other:?}"),
        };
        assert_eq!(target, focus_writer);
        assert_eq!(routed["event"], "scope.interaction");
        assert_eq!(routed["data"]["scope_id"], focus_grant["scope_id"]);
        assert_eq!(routed["data"]["component_id"], "focus-action");
        assert_eq!(routed["data"]["action"], "focus.refresh");
        assert_eq!(routed["data"]["id"], focus_event.to_string());

        assert_eq!(
            hub.dispatch(
                tasks_writer,
                "scope.action.result",
                json!({
                    "world_id":world_id,
                    "lease":tasks_join["lease"],
                    "event_id":focus_event,
                    "ok":true
                }),
            )
            .unwrap_err()
            .code,
            "SCOPE_ACTION_FORBIDDEN"
        );
        hub.dispatch(
            focus_writer,
            "scope.action.result",
            json!({
                "world_id":world_id,
                "lease":focus_join["lease"],
                "event_id":focus_event,
                "ok":true,
                "message":"focus updated"
            }),
        )
        .unwrap();
        let action = hub
            .renderer_snapshot(world_id)
            .unwrap()
            .actions
            .into_iter()
            .find(|action| action.id == focus_event)
            .unwrap();
        assert_eq!(action.status, "ok");
        assert_eq!(action.message.as_deref(), Some("focus updated"));

        let current = hub.renderer_snapshot(world_id).unwrap();
        let tasks_event_id = hub
            .interact_with_source(
                world_id,
                "tasks-action",
                serde_json::Value::Null,
                InteractionSource::Click,
                current.revision,
            )
            .unwrap();
        let (target, routed) = match notices.try_recv().unwrap() {
            super::Notice::Directed(target, message) => (target, message),
            other => panic!("unexpected notice: {other:?}"),
        };
        assert_eq!(target, tasks_writer);
        assert_eq!(routed["event"], "scope.interaction");
        assert_eq!(routed["data"]["scope_id"], tasks_grant["scope_id"]);
        assert_eq!(routed["data"]["id"], tasks_event_id.to_string());

        let before_revoke = hub.renderer_snapshot(world_id).unwrap();
        hub.dispatch(
            authority,
            "scope.structure.patch",
            json!({
                "world_id":world_id,
                "authority_lease":partitioned["authority_lease"],
                "expected_revision":before_revoke.revision,
                "ops":[{"op":"remove","node_id":"tasks-panel"}]
            }),
        )
        .unwrap();
        assert_eq!(
            hub.dispatch(
                tasks_writer,
                "scope.action.result",
                json!({
                    "world_id":world_id,
                    "lease":tasks_join["lease"],
                    "event_id":tasks_event_id,
                    "ok":true
                }),
            )
            .unwrap_err()
            .code,
            "STALE_SCOPE"
        );
        hub.lock().expire(hub.now() + 1);
        let revoked_action = hub
            .renderer_snapshot(world_id)
            .unwrap()
            .actions
            .into_iter()
            .find(|action| action.id == tasks_event_id)
            .unwrap();
        assert_eq!(revoked_action.status, "error");
        assert_eq!(
            revoked_action.message.as_deref(),
            Some("component scope writer was revoked before acknowledgement")
        );

        hub.disconnect(late_reader);
        hub.disconnect(tasks_writer);
        hub.disconnect(focus_writer);
        hub.disconnect(authority);
    }

    #[test]
    fn scoped_interactions_reject_unowned_layout_and_native_window_actions() {
        let hub = Hub::new(true);
        let authority = hub
            .lock()
            .register_with_protocol(
                "scope-safety-authority".into(),
                false,
                ProtocolVersion::ComponentLeasesPreview01,
            )
            .unwrap();
        let created = hub
            .dispatch(
                authority,
                "world.create",
                json!({"window":{"title":"Scope safety fixture"},"claim":true}),
            )
            .unwrap();
        let world_id = created["world"]["id"].as_str().unwrap();
        let lease = created["lease"].clone();
        let unowned_action_scene = json!({
            "root":{"id":"root","kind":"stack","children":[
                {"id":"layout-action","kind":"button","props":{"label":"Unowned","action":"layout.run"},"children":[]},
                {"id":"focus-panel","kind":"stack","children":[
                    {"id":"focus-action","kind":"button","props":{"label":"Refresh","action":"focus.refresh"},"children":[]}
                ]},
                {"id":"tasks-panel","kind":"stack","children":[]}
            ]},
            "data":{"focus":{},"tasks":{}}
        });
        let replaced = hub
            .dispatch(
                authority,
                "scene.replace",
                json!({
                    "world_id":world_id,
                    "lease":lease,
                    "expected_revision":created["world"]["revision"],
                    "scene":unowned_action_scene
                }),
            )
            .unwrap();
        let unowned_partition = hub
            .dispatch(
                authority,
                "scope.partition",
                json!({
                    "world_id":world_id,
                    "lease":lease,
                    "expected_revision":replaced["revision"],
                    "scopes":[
                        {"root_node_id":"focus-panel","data_namespace":"focus"},
                        {"root_node_id":"tasks-panel","data_namespace":"tasks"}
                    ]
                }),
            )
            .unwrap_err();
        assert_eq!(unowned_partition.code, "SCOPE_INTERACTIONS_UNOWNED");

        let owned_native_action_scene = json!({
            "root":{"id":"root","kind":"stack","children":[
                {"id":"focus-panel","kind":"stack","children":[
                    {"id":"focus-action","kind":"button","props":{
                        "label":"Activate Obsidian",
                        "action":"focus.refresh",
                        "native_window_action":{"application":"obsidian","operation":"activate"}
                    },"children":[]}
                ]},
                {"id":"tasks-panel","kind":"stack","children":[]}
            ]},
            "data":{"focus":{},"tasks":{}}
        });
        let refreshed = hub
            .dispatch(
                authority,
                "scene.replace",
                json!({
                    "world_id":world_id,
                    "lease":lease,
                    "expected_revision":replaced["revision"],
                    "scene":owned_native_action_scene
                }),
            )
            .unwrap();
        let native_scope = hub
            .dispatch(
                authority,
                "scope.partition",
                json!({
                    "world_id":world_id,
                    "lease":lease,
                    "expected_revision":refreshed["revision"],
                    "scopes":[
                        {"root_node_id":"focus-panel","data_namespace":"focus"},
                        {"root_node_id":"tasks-panel","data_namespace":"tasks"}
                    ]
                }),
            )
            .unwrap_err();
        assert_eq!(native_scope.code, "SCOPE_NATIVE_ACTION_UNAVAILABLE");
        hub.disconnect(authority);
    }

    #[test]
    fn disconnect_revokes_session_shortcuts_without_touching_another_session() {
        let hub = Hub::new(false);
        let (first, second) = {
            let mut core = hub.lock();
            (
                core.register("shortcut-a".into(), false).unwrap(),
                core.register("shortcut-b".into(), false).unwrap(),
            )
        };
        hub.register_shortcut(
            first,
            ShortcutSpec {
                chord: "Ctrl+Shift+W".into(),
                action: "recall".into(),
            },
        )
        .unwrap();
        hub.register_shortcut(
            second,
            ShortcutSpec {
                chord: "Ctrl+Shift+T".into(),
                action: "toggle".into(),
            },
        )
        .unwrap();
        assert!(hub.shortcut_registered("Ctrl+Shift+W"));
        hub.disconnect(first);
        assert!(!hub.shortcut_registered("Ctrl+Shift+W"));
        assert!(hub.shortcut_registered("Ctrl+Shift+T"));
        hub.disconnect(second);
        assert!(!hub.shortcut_registered("Ctrl+Shift+T"));
    }

    #[test]
    fn coalescible_state_updates_do_not_consume_the_occurrence_queue() {
        let hub = Hub::new(false);
        let (_session, world_id, _lease, _revision) = native_action_world(&hub);
        let mut occurrences = hub.subscribe();
        let mut state_updates = hub.subscribe_state();

        for sequence in 1..=512 {
            hub.publish_state_change(StateChange {
                world_id,
                sequence,
                source: EventSource::Human,
                cause_id: None,
            });
        }
        hub.publish_state_change(StateChange {
            world_id,
            sequence: 511,
            source: EventSource::Provider,
            cause_id: Some("stale".into()),
        });

        let latest = hub.latest_state_changes();
        assert_eq!(latest.len(), 1);
        assert_eq!(latest[0].world_id, world_id);
        assert_eq!(latest[0].sequence, 512);
        assert_eq!(latest[0].source, EventSource::Human);
        assert_eq!(*state_updates.borrow_and_update(), 512);
        assert!(matches!(
            occurrences.try_recv(),
            Err(tokio::sync::broadcast::error::TryRecvError::Empty)
        ));
    }

    #[test]
    fn host_locale_is_shared_and_rejects_unknown_values() {
        let first = Hub::new(false);
        let second = first.clone();
        assert_eq!(first.locale(), "zh-CN");
        first.set_locale("en-US").unwrap();
        assert_eq!(second.locale(), "en-US");
        assert_eq!(
            first.set_locale("fr-FR").unwrap_err().code,
            "INVALID_LOCALE"
        );
    }
}

#[cfg(test)]
mod presentation_group_tests {
    use super::Hub;
    use serde_json::json;
    use uuid::Uuid;
    use wincraft_core::ProtocolVersion;

    fn preview_session(hub: &Hub, name: &str) -> Uuid {
        hub.lock()
            .register_with_protocol(
                name.into(),
                false,
                ProtocolVersion::ComponentLeasesPreview01,
            )
            .unwrap()
    }

    fn create_world(hub: &Hub, session: Uuid, title: &str) -> (Uuid, wincraft_core::LeaseKey, u64) {
        let created = hub
            .dispatch(
                session,
                "world.create",
                json!({"window":{"title":title,"width":300.0,"height":200.0},"claim":true}),
            )
            .unwrap();
        let world_id = Uuid::parse_str(created["world"]["id"].as_str().unwrap()).unwrap();
        let revision = created["world"]["revision"].as_u64().unwrap();
        let lease = created["lease"].clone();
        (
            world_id,
            serde_json::from_value(lease).expect("lease payload"),
            revision,
        )
    }

    #[test]
    fn group_apply_reports_each_member_separately() {
        let hub = Hub::new(false);
        let session = preview_session(&hub, "group.owner");
        let (first, first_lease, first_revision) = create_world(&hub, session, "first");
        let (second, _second_lease, second_revision) = create_world(&hub, session, "second");

        let group = hub
            .dispatch(
                session,
                "presentation.group.create",
                json!({
                    "name":"hud",
                    "members":[
                        {"world_id":first,"order":0},
                        {"world_id":second,"order":1}
                    ],
                    "roles":[{"name":"primary","member":null}]
                }),
            )
            .unwrap();
        let group_id = Uuid::parse_str(group["id"].as_str().unwrap()).unwrap();

        // The second member's lease is deliberately wrong, so only the first
        // member may accept the patch.
        let response = hub
            .dispatch(
                session,
                "presentation.group.apply",
                json!({
                    "group_id":group_id,
                    "leases":{
                        first.to_string():first_lease,
                        second.to_string():{
                            "id":Uuid::new_v4().to_string(),
                            "epoch":999
                        }
                    },
                    "expected_revisions":{
                        first.to_string():first_revision,
                        second.to_string():second_revision
                    },
                    "patch":{"visible":false}
                }),
            )
            .unwrap();

        assert_eq!(response["atomic"], json!(false));
        assert_eq!(response["result"]["applied"], json!(1));
        assert_eq!(response["result"]["refused"], json!(1));
        assert_eq!(response["result"]["results"].as_array().unwrap().len(), 2);
        let results = response["result"]["results"].as_array().unwrap();
        assert_eq!(results[0]["outcome"]["status"], json!("applied"));
        assert_eq!(results[1]["outcome"]["status"], json!("refused"));
        // The refusal keeps the machine-readable fault code, so a caller can
        // tell "not writable" apart from "missing".
        assert_eq!(results[1]["outcome"]["code"], json!("STALE_LEASE"));
        // Only the member that accepted the operation is reported as changed.
        assert_eq!(response["changed"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn a_group_cannot_be_used_by_another_session() {
        let hub = Hub::new(false);
        let owner = preview_session(&hub, "group.owner");
        let other = preview_session(&hub, "group.other");
        let (world, lease, revision) = create_world(&hub, owner, "owned");
        let group = hub
            .dispatch(
                owner,
                "presentation.group.create",
                json!({"name":"hud","members":[{"world_id":world,"order":0}]}),
            )
            .unwrap();
        let group_id = Uuid::parse_str(group["id"].as_str().unwrap()).unwrap();

        // Discovery grants no operation right: another session cannot even
        // see the group, let alone apply to it.
        let listed = hub
            .dispatch(other, "presentation.group.list", json!({}))
            .unwrap();
        assert_eq!(listed.as_array().unwrap().len(), 0);
        let apply = hub
            .dispatch(
                other,
                "presentation.group.apply",
                json!({
                    "group_id":group_id,
                    "leases":{world.to_string():lease},
                    "expected_revisions":{world.to_string():revision},
                    "patch":{"visible":false}
                }),
            )
            .unwrap_err();
        assert_eq!(apply.code, "NOT_FOUND");
    }

    #[test]
    fn stable_protocol_sessions_cannot_use_presentation_groups() {
        let hub = Hub::new(false);
        let session = hub
            .lock()
            .register("stable.provider".into(), false)
            .unwrap();
        let error = hub
            .dispatch(session, "presentation.group.create", json!({"name":"hud"}))
            .unwrap_err();
        assert_eq!(error.code, "UNSUPPORTED_CAPABILITY");
    }
}
#[derive(Clone)]
pub struct Hub {
    core: Arc<Mutex<Engine>>,
    locale: Arc<Mutex<String>>,
    born: Instant,
    pub host_id: Uuid,
    pub native_windows: bool,
    events: broadcast::Sender<Notice>,
    state_changes: Arc<Mutex<BTreeMap<Uuid, StateChange>>>,
    state_updates: watch::Sender<u64>,
    shortcuts: Arc<Mutex<ShortcutRegistry>>,
    provider_inventory: Arc<Mutex<ProviderInventoryRegistry>>,
    pack_imports: Arc<Mutex<PackImportRegistry>>,
    presentation_groups: Arc<Mutex<PresentationGroupRegistry>>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub id: String,
    pub method: String,
    #[serde(default)]
    pub params: Value,
}
fn decode<T: DeserializeOwned>(v: Value) -> Result<T> {
    serde_json::from_value(v).map_err(|e| Fault::new("INVALID_PARAMS", e.to_string()))
}
fn encode<T: Serialize>(v: T) -> Result<Value> {
    serde_json::to_value(v).map_err(|e| Fault::new("INTERNAL", e.to_string()))
}

fn import_world_unchanged(core: &Engine, expected: &ImportedWorld) -> bool {
    core.worlds.get(&expected.world_id).is_some_and(|world| {
        world.revision == expected.expected_revision
            && world.epoch == expected.expected_epoch
            && world.window == expected.window
            && world.scene == expected.scene
            && world.writer.as_ref().map(|writer| writer.session) == expected.expected_writer
            && world.readers.keys().copied().collect::<BTreeSet<_>>() == expected.expected_readers
            && !world.write_blocked
            && world.ownership_mode == OwnershipMode::ExclusiveWorld
            && world.scopes.is_empty()
            && world.authority.is_none()
            && world.actions.is_empty()
    })
}

fn imported_world_summaries(worlds: &[ImportedWorld]) -> Vec<ImportedWorldSummary> {
    worlds
        .iter()
        .map(|world| ImportedWorldSummary {
            blueprint_world_id: world.blueprint_world_id.clone(),
            world_id: world.world_id,
            title: world.title.clone(),
        })
        .collect()
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CreateParams {
    #[serde(default)]
    window: WindowSpec,
    #[serde(default)]
    join_policy: JoinPolicy,
    #[serde(default = "yes")]
    claim: bool,
}
fn yes() -> bool {
    true
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct JoinParams {
    world_id: Uuid,
    #[serde(default)]
    join_key: Option<String>,
    mode: JoinMode,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WorldParams {
    world_id: Uuid,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LeaseParams {
    world_id: Uuid,
    lease: LeaseKey,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SceneParams {
    world_id: Uuid,
    lease: LeaseKey,
    expected_revision: u64,
    scene: Scene,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PatchParams {
    world_id: Uuid,
    lease: LeaseKey,
    expected_revision: u64,
    ops: Vec<SceneOp>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DataParams {
    world_id: Uuid,
    lease: LeaseKey,
    expected_revision: u64,
    data: Value,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ScopePartitionParams {
    world_id: Uuid,
    lease: LeaseKey,
    expected_revision: u64,
    scopes: Vec<ScopeDefinition>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ScopeReadParams {
    world_id: Uuid,
    scope_id: Uuid,
    generation: u64,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ScopeStatusParams {
    world_id: Uuid,
    scope_id: Uuid,
    generation: u64,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ScopeLeaseParams {
    world_id: Uuid,
    lease: ScopedLeaseKey,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ScopePatchParams {
    world_id: Uuid,
    lease: ScopedLeaseKey,
    expected_scope_revision: u64,
    ops: Vec<SceneOp>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ScopeStructureParams {
    world_id: Uuid,
    authority_lease: LeaseKey,
    expected_revision: u64,
    ops: Vec<SceneOp>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ScopeDataParams {
    world_id: Uuid,
    lease: ScopedLeaseKey,
    expected_scope_revision: u64,
    data: Value,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ScopeLeaveParams {
    world_id: Uuid,
    scope_id: Uuid,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WindowParams {
    world_id: Uuid,
    lease: LeaseKey,
    expected_revision: u64,
    patch: WindowPatch,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GroupCreateParams {
    #[serde(default)]
    name: String,
    #[serde(default)]
    members: Vec<GroupMember>,
    #[serde(default)]
    roles: Vec<GroupRole>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GroupIdParams {
    group_id: Uuid,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GroupMemberParams {
    world_id: Uuid,
    #[serde(default)]
    order: i64,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GroupPatchParams {
    group_id: Uuid,
    #[serde(default)]
    add_members: Vec<GroupMemberParams>,
    #[serde(default)]
    remove_members: Vec<Uuid>,
    #[serde(default)]
    add_roles: Vec<GroupRole>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GroupApplyParams {
    group_id: Uuid,
    /// One lease per member world. A member without a lease is refused.
    #[serde(default)]
    leases: BTreeMap<Uuid, LeaseKey>,
    #[serde(default)]
    expected_revisions: BTreeMap<Uuid, u64>,
    patch: WindowPatch,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AckParams {
    world_id: Uuid,
    lease: LeaseKey,
    event_id: Uuid,
    ok: bool,
    #[serde(default)]
    message: Option<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ScopeAckParams {
    world_id: Uuid,
    lease: ScopedLeaseKey,
    event_id: Uuid,
    ok: bool,
    #[serde(default)]
    message: Option<String>,
}

impl Hub {
    pub fn new(native_windows: bool) -> Self {
        let (events, _) = broadcast::channel(256);
        let (state_updates, _) = watch::channel(0);
        Self {
            core: Arc::new(Mutex::new(Engine::default())),
            locale: Arc::new(Mutex::new("zh-CN".into())),
            born: Instant::now(),
            host_id: Uuid::new_v4(),
            native_windows,
            events,
            state_changes: Arc::new(Mutex::new(BTreeMap::new())),
            state_updates,
            shortcuts: Arc::new(Mutex::new(ShortcutRegistry::default())),
            provider_inventory: Arc::new(Mutex::new(ProviderInventoryRegistry::default())),
            pack_imports: Arc::new(Mutex::new(PackImportRegistry::default())),
            presentation_groups: Arc::new(Mutex::new(PresentationGroupRegistry::default())),
        }
    }
    pub fn lock(&self) -> MutexGuard<'_, Engine> {
        self.core.lock().expect("engine mutex poisoned")
    }
    pub fn locale(&self) -> String {
        self.locale.lock().expect("locale mutex poisoned").clone()
    }
    pub fn set_locale(&self, locale: &str) -> Result<()> {
        if !matches!(locale, "zh-CN" | "en-US") {
            return Err(Fault::new(
                "INVALID_LOCALE",
                "locale must be zh-CN or en-US",
            ));
        }
        *self.locale.lock().expect("locale mutex poisoned") = locale.into();
        Ok(())
    }
    pub fn now(&self) -> u64 {
        self.born.elapsed().as_millis().min(u64::MAX as u128) as u64
    }
    pub fn subscribe(&self) -> broadcast::Receiver<Notice> {
        self.events.subscribe()
    }
    pub fn subscribe_state(&self) -> watch::Receiver<u64> {
        self.state_updates.subscribe()
    }
    pub fn latest_state_changes(&self) -> Vec<StateChange> {
        self.state_changes
            .lock()
            .expect("state changes mutex poisoned")
            .values()
            .cloned()
            .collect()
    }
    pub fn changed(&self, id: Uuid) {
        self.changed_with_source(id, EventSource::Host, None);
    }
    pub fn changed_with_source(&self, id: Uuid, source: EventSource, cause_id: Option<String>) {
        let sequence = self.lock().worlds.get(&id).map(|world| world.sequence);
        if let Some(sequence) = sequence {
            self.changed_at(id, sequence, source, cause_id);
        }
    }
    pub fn apply_state_change<F>(
        &self,
        id: Uuid,
        source: EventSource,
        cause_id: Option<String>,
        update: F,
    ) -> Result<bool>
    where
        F: FnOnce(&mut Engine) -> Result<bool>,
    {
        let (changed, sequence) = {
            let mut core = self.lock();
            let before = core.worlds.get(&id).map(|world| world.sequence);
            let changed = update(&mut core)?;
            let sequence = core.worlds.get(&id).map(|world| world.sequence);
            (changed && before != sequence, sequence)
        };
        if let Some(sequence) = sequence.filter(|_| changed) {
            self.changed_at(id, sequence, source, cause_id);
        }
        Ok(changed)
    }
    pub fn changed_at(
        &self,
        id: Uuid,
        sequence: u64,
        source: EventSource,
        cause_id: Option<String>,
    ) {
        let core = self.lock();
        if core.worlds.get(&id).map(|world| world.sequence) != Some(sequence) {
            return;
        }
        self.publish_state_change(StateChange {
            world_id: id,
            sequence,
            source,
            cause_id,
        });
    }
    fn publish_state_change(&self, change: StateChange) {
        let publish = {
            let mut changes = self
                .state_changes
                .lock()
                .expect("state changes mutex poisoned");
            if changes
                .get(&change.world_id)
                .is_some_and(|current| current.sequence >= change.sequence)
            {
                false
            } else {
                changes.insert(change.world_id, change);
                true
            }
        };
        if publish {
            self.state_updates
                .send_modify(|generation| *generation = generation.wrapping_add(1));
        }
    }
    pub fn deleted(&self, id: Uuid, members: Vec<Uuid>) {
        self.state_changes
            .lock()
            .expect("state changes mutex poisoned")
            .remove(&id);
        self.state_updates
            .send_modify(|generation| *generation = generation.wrapping_add(1));
        let _ = self.events.send(Notice::Deleted {
            world_id: id,
            members,
        });
    }
    pub fn disconnect(&self, sid: Uuid) {
        self.shortcuts
            .lock()
            .expect("shortcut registry mutex poisoned")
            .revoke_session(sid);
        let changes = {
            let mut core = self.lock();
            core.disconnect(sid)
                .into_iter()
                .filter_map(|id| core.worlds.get(&id).map(|world| (id, world.sequence)))
                .collect::<Vec<_>>()
        };
        self.provider_inventory
            .lock()
            .expect("provider inventory mutex poisoned")
            .disconnect(sid, self.now());
        for (id, sequence) in changes {
            self.changed_at(id, sequence, EventSource::System, None);
        }
    }

    pub(crate) fn register_shortcut(&self, session: Uuid, spec: ShortcutSpec) -> Result<String> {
        self.shortcuts
            .lock()
            .expect("shortcut registry mutex poisoned")
            .register(session, spec)
    }

    pub(crate) fn unregister_shortcut(&self, session: Uuid, chord: &str) -> Result<bool> {
        self.shortcuts
            .lock()
            .expect("shortcut registry mutex poisoned")
            .unregister(session, chord)
    }

    #[allow(dead_code)]
    pub(crate) fn shortcut_registered(&self, chord: &str) -> bool {
        self.shortcuts
            .lock()
            .expect("shortcut registry mutex poisoned")
            .contains(chord)
    }
    pub(crate) fn disconnect_providers(&self) {
        let providers: Vec<_> = self
            .lock()
            .sessions
            .values()
            .filter(|session| !session.operator)
            .map(|session| session.id)
            .collect();
        for session in providers {
            self.disconnect(session);
        }
    }
    pub fn snapshots(&self) -> Vec<Snapshot> {
        self.lock().worlds.values().map(World::snapshot).collect()
    }
    pub fn renderer_snapshot(&self, id: Uuid) -> Result<Snapshot> {
        self.lock()
            .worlds
            .get(&id)
            .map(World::snapshot)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))
    }
    pub fn read_scopes(&self, session: Uuid, id: Uuid) -> Result<Vec<ScopeSnapshot>> {
        self.lock().read_scopes(session, id)
    }

    fn require_local_operator(core: &Engine, session: Uuid) -> Result<()> {
        if !core.sessions.contains_key(&session) {
            return Err(Fault::new("SESSION_GONE", "session missing"));
        }
        if !core.operator(session) {
            return Err(Fault::new(
                "FORBIDDEN",
                "local operator confirmation is required for configuration imports",
            ));
        }
        Ok(())
    }

    pub(crate) fn preview_pack_file(
        &self,
        session: Uuid,
        path: &Path,
        selections: BTreeMap<String, String>,
    ) -> Result<PackPreview> {
        let loaded = load_pack_file(path)?;
        self.preview_loaded_pack(session, loaded, selections)
    }

    #[cfg(test)]
    pub(crate) fn preview_pack_values(
        &self,
        session: Uuid,
        pack: Value,
        blueprint: Value,
        selections: BTreeMap<String, String>,
    ) -> Result<PackPreview> {
        let loaded = parse_loaded_json(pack, blueprint)?;
        self.preview_loaded_pack(session, loaded, selections)
    }

    fn preview_loaded_pack(
        &self,
        session: Uuid,
        loaded: crate::pack_import::LoadedPack,
        selections: BTreeMap<String, String>,
    ) -> Result<PackPreview> {
        let core = self.lock();
        Self::require_local_operator(&core, session)?;
        let now_ms = self.now();
        let inventory = self
            .provider_inventory
            .lock()
            .expect("provider inventory mutex poisoned")
            .snapshot(self.host_id, now_ms, OffsetDateTime::now_utc())?;
        let inventory = encode(inventory)?;
        let pending = build_preview(
            loaded,
            inventory,
            selections,
            OffsetDateTime::now_utc(),
            now_ms,
        )?;
        let preview = pending.preview.clone();
        self.pack_imports
            .lock()
            .expect("pack import registry mutex poisoned")
            .insert_plan(pending, now_ms);
        Ok(preview)
    }

    /// A local operator explicitly grants only permissions named by the selected pack binding.
    /// The grant changes inventory generation, so the previous preview is invalidated.
    pub(crate) fn authorize_pack_binding(
        &self,
        session: Uuid,
        preview_id: Uuid,
        binding_id: &str,
        instance_id: &str,
    ) -> Result<u64> {
        let core = self.lock();
        Self::require_local_operator(&core, session)?;
        let now_ms = self.now();
        let now = OffsetDateTime::now_utc();
        let mut inventory = self
            .provider_inventory
            .lock()
            .expect("provider inventory mutex poisoned");
        let snapshot = inventory.snapshot(self.host_id, now_ms, now)?;
        let plan = self
            .pack_imports
            .lock()
            .expect("pack import registry mutex poisoned")
            .plan(preview_id)
            .ok_or_else(|| {
                Fault::new("PLAN_NOT_FOUND", "configuration preview expired or missing")
            })?;
        if plan.expires_at_mono_ms <= now_ms
            || snapshot.generation() != plan.preview.inventory_generation
        {
            self.pack_imports
                .lock()
                .expect("pack import registry mutex poisoned")
                .cancel(preview_id);
            return Err(Fault::new(
                "STALE_PLAN",
                "provider inventory changed; review a new preview",
            ));
        }
        let binding = plan
            .preview
            .bindings
            .iter()
            .find(|binding| binding.binding_id == binding_id)
            .ok_or_else(|| Fault::new("INVALID_GRANT", "binding is not part of this preview"))?;
        let candidate = binding
            .candidates
            .iter()
            .find(|candidate| candidate.instance_id == instance_id)
            .ok_or_else(|| Fault::new("INVALID_GRANT", "provider is not a compatible candidate"))?;
        if candidate.missing_permissions.is_empty() {
            return Err(Fault::new(
                "NO_PERMISSION_REQUIRED",
                "this provider has no pending permission request",
            ));
        }
        let updated = inventory.grant_permissions(
            instance_id,
            &candidate.missing_permissions,
            self.host_id,
            now_ms,
            now,
        )?;
        self.pack_imports
            .lock()
            .expect("pack import registry mutex poisoned")
            .cancel(preview_id);
        Ok(updated.generation())
    }

    pub(crate) fn cancel_pack_preview(&self, session: Uuid, preview_id: Uuid) -> Result<()> {
        let core = self.lock();
        Self::require_local_operator(&core, session)?;
        self.pack_imports
            .lock()
            .expect("pack import registry mutex poisoned")
            .cancel(preview_id);
        Ok(())
    }

    pub(crate) fn apply_pack_preview(
        &self,
        session: Uuid,
        preview_id: Uuid,
        confirmed: bool,
    ) -> Result<ImportReceipt> {
        if !confirmed {
            return Err(Fault::new(
                "CONFIRMATION_REQUIRED",
                "explicit local confirmation is required",
            ));
        }
        let now_ms = self.now();
        let now = OffsetDateTime::now_utc();
        let mut changed_worlds = Vec::new();
        let mut directed = Vec::<(Uuid, Value)>::new();
        let receipt = {
            // Lock order is core -> inventory -> import ledger, matching the existing dispatch path.
            let mut core = self.lock();
            Self::require_local_operator(&core, session)?;
            let mut inventory = self
                .provider_inventory
                .lock()
                .expect("provider inventory mutex poisoned");
            let inventory_snapshot = inventory.snapshot(self.host_id, now_ms, now)?;
            let inventory_value = encode(inventory_snapshot.clone())?;
            let mut registry = self
                .pack_imports
                .lock()
                .expect("pack import registry mutex poisoned");
            if let Some(previous) = registry.batch_for_preview(preview_id) {
                let mut replay = previous.receipt;
                replay.idempotent_replay = true;
                return Ok(replay);
            }
            let plan = registry.plan(preview_id).ok_or_else(|| {
                Fault::new("PLAN_NOT_FOUND", "configuration preview expired or missing")
            })?;
            if plan.preview.status == PlanStatus::Blocked {
                return Err(Fault::new(
                    "PLAN_BLOCKED",
                    "blocked configuration plans cannot be applied",
                ));
            }
            if plan.expires_at_mono_ms <= now_ms
                || inventory_snapshot.generation() != plan.preview.inventory_generation
            {
                registry.cancel(preview_id);
                return Err(Fault::new(
                    "STALE_PLAN",
                    "provider inventory changed; review a new preview",
                ));
            }
            let current = build_preview(
                plan.loaded.clone(),
                inventory_value,
                plan.selections.clone(),
                now,
                now_ms,
            )?;
            if current.preview.status == PlanStatus::Blocked
                || current.preview.status != plan.preview.status
                || current.preview.bindings != plan.preview.bindings
            {
                registry.cancel(preview_id);
                return Err(Fault::new(
                    "STALE_PLAN",
                    "provider eligibility changed; review a new preview",
                ));
            }
            if !matches!(
                plan.preview.status,
                PlanStatus::Ready | PlanStatus::Degraded
            ) {
                return Err(Fault::new(
                    "PLAN_BLOCKED",
                    "blocked configuration plans cannot be applied",
                ));
            }

            let locale = self.locale();
            let prepared_worlds = plan
                .loaded
                .blueprint
                .worlds
                .iter()
                .map(|world| {
                    Ok((
                        world,
                        materialize_world(&plan.loaded, world, &plan.preview.bindings, &locale)?,
                    ))
                })
                .collect::<Result<Vec<_>>>()?;
            let mut created = Vec::new();
            let mut failure = None;
            for (blueprint_world, (window, scene)) in prepared_worlds {
                let created_world = match core.create(
                    session,
                    window.clone(),
                    JoinPolicy::Invite,
                    false,
                    false,
                    now_ms,
                ) {
                    Ok(created) => created,
                    Err(error) => {
                        failure = Some(error.code);
                        break;
                    }
                };
                let world_id = created_world.world.id;
                if let Some(world) = core.worlds.get_mut(&world_id) {
                    world.scene = scene.clone();
                    world.touch();
                    if !self.native_windows {
                        world.native = NativeReport {
                            state: "unavailable".into(),
                            applied_window_revision: None,
                            error: Some("headless host: no native renderer".into()),
                        };
                    }
                }
                let initial = core
                    .worlds
                    .get(&world_id)
                    .expect("created world remains in engine");
                created.push(ImportedWorld {
                    blueprint_world_id: blueprint_world.id.clone(),
                    world_id,
                    title: window.title.clone(),
                    scene: scene.clone(),
                    window: window.clone(),
                    expected_revision: initial.revision,
                    expected_epoch: initial.epoch,
                    expected_writer: None,
                    expected_readers: initial.readers.keys().copied().collect(),
                });

                let slots: BTreeSet<&str> = blueprint_world
                    .binding_slots
                    .iter()
                    .map(String::as_str)
                    .collect();
                let source_instances: BTreeSet<&str> = plan
                    .preview
                    .bindings
                    .iter()
                    .filter(|binding| slots.contains(binding.binding_id.as_str()))
                    .filter_map(|binding| binding.provider_instance_id.as_deref())
                    .collect();
                if source_instances.len() > 1 {
                    failure = Some("EXCLUSIVE_WORLD_WRITER_CONFLICT".into());
                    break;
                }
                if let Some(instance_id) = source_instances.iter().next().copied() {
                    let Some(provider_session) = inventory.session_for_instance(instance_id) else {
                        failure = Some("PROVIDER_NOT_ONLINE".into());
                        break;
                    };
                    match core.join(
                        provider_session,
                        world_id,
                        Some(&created_world.join_key),
                        JoinMode::Write,
                        now_ms,
                    ) {
                        Ok(joined) => {
                            let lease = joined.lease.clone();
                            if let Some(expected) = created.last_mut() {
                                if let Some(world) = core.worlds.get(&world_id) {
                                    expected.expected_revision = world.revision;
                                    expected.expected_epoch = world.epoch;
                                    expected.expected_writer = Some(provider_session);
                                    expected.expected_readers =
                                        world.readers.keys().copied().collect();
                                }
                            }
                            let binding_ids = plan
                                .preview
                                .bindings
                                .iter()
                                .filter(|binding| {
                                    binding.provider_instance_id.as_deref() == Some(instance_id)
                                })
                                .map(|binding| binding.binding_id.clone())
                                .collect::<Vec<_>>();
                            let approved_permissions = plan
                                .preview
                                .bindings
                                .iter()
                                .filter(|binding| {
                                    binding.provider_instance_id.as_deref() == Some(instance_id)
                                })
                                .flat_map(|binding| binding.requested_permissions.iter().cloned())
                                .collect::<BTreeSet<_>>();
                            directed.push((
                                provider_session,
                                json!({
                                    "event":"world.import.joined",
                                    "data":{
                                        "kind":"wincraft.provider-import.event",
                                        "schema_version":"draft-2026-10-26",
                                        "host_id":self.host_id,
                                        "pack_id":plan.loaded.pack.id,
                                        "pack_version":plan.loaded.pack.version,
                                        "blueprint_world_id":blueprint_world.id,
                                        "binding_ids":binding_ids,
                                        "approved_permissions":approved_permissions,
                                        "world":joined.world,
                                        "lease":lease
                                    }
                                }),
                            ));
                        }
                        Err(error) => {
                            failure = Some(error.code);
                            break;
                        }
                    }
                }
            }

            if let Some(failure_code) = failure {
                // No provider receives an invitation until every world has been created.
                directed.clear();
                let mut cleanup_removed = Vec::new();
                let mut retained_worlds = Vec::new();
                for created_world in created.iter().rev() {
                    if import_world_unchanged(&core, created_world) {
                        match core.operator_destroy(session, created_world.world_id) {
                            Ok(_) => cleanup_removed.push(created_world.world_id),
                            Err(_) => retained_worlds.push(created_world.world_id),
                        }
                    } else {
                        retained_worlds.push(created_world.world_id);
                    }
                }
                let batch_id = Uuid::new_v4();
                let status = if retained_worlds.is_empty() {
                    "failed_rolled_back"
                } else {
                    "partial"
                };
                let receipt = ImportReceipt {
                    batch_id,
                    preview_id,
                    pack_id: plan.loaded.pack.id.clone(),
                    pack_version: plan.loaded.pack.version.clone(),
                    status: status.into(),
                    idempotent_replay: false,
                    failure_code: Some(failure_code),
                    cleanup_removed,
                    retained_worlds,
                    bindings: plan.preview.bindings.clone(),
                    worlds: imported_world_summaries(&created),
                };
                registry.cancel(preview_id);
                registry.record_batch(ImportBatch {
                    receipt: receipt.clone(),
                    expected_worlds: created,
                });
                receipt
            } else {
                let batch_id = Uuid::new_v4();
                let receipt = ImportReceipt {
                    batch_id,
                    preview_id,
                    pack_id: plan.loaded.pack.id.clone(),
                    pack_version: plan.loaded.pack.version.clone(),
                    status: "applied".into(),
                    idempotent_replay: false,
                    failure_code: None,
                    cleanup_removed: Vec::new(),
                    retained_worlds: Vec::new(),
                    bindings: plan.preview.bindings.clone(),
                    worlds: imported_world_summaries(&created),
                };
                changed_worlds = created.iter().map(|world| world.world_id).collect();
                registry.cancel(preview_id);
                registry.record_batch(ImportBatch {
                    receipt: receipt.clone(),
                    expected_worlds: created,
                });
                receipt
            }
        };
        for world_id in changed_worlds {
            self.changed(world_id);
        }
        for (target, message) in directed {
            let _ = self.events.send(Notice::Directed(target, message));
        }
        Ok(receipt)
    }

    pub(crate) fn rollback_pack_import(
        &self,
        session: Uuid,
        batch_id: Uuid,
    ) -> Result<RollbackReceipt> {
        let mut deleted = Vec::new();
        let result = {
            let mut core = self.lock();
            Self::require_local_operator(&core, session)?;
            let mut registry = self
                .pack_imports
                .lock()
                .expect("pack import registry mutex poisoned");
            let mut batch = registry.batch(batch_id).ok_or_else(|| {
                Fault::new(
                    "IMPORT_BATCH_NOT_FOUND",
                    "configuration import is unavailable",
                )
            })?;
            if batch.receipt.status == "rolled_back" {
                return Ok(RollbackReceipt {
                    batch_id,
                    status: "rolled_back".into(),
                    removed: batch.receipt.cleanup_removed,
                    already_missing: Vec::new(),
                    retained: batch.receipt.retained_worlds,
                });
            }
            let mut removed = Vec::new();
            let mut already_missing = Vec::new();
            let mut retained = Vec::new();
            for world in &batch.expected_worlds {
                if !core.worlds.contains_key(&world.world_id) {
                    already_missing.push(world.world_id);
                } else if import_world_unchanged(&core, world) {
                    match core.operator_destroy(session, world.world_id) {
                        Ok(members) => {
                            removed.push(world.world_id);
                            deleted.push((world.world_id, members));
                        }
                        Err(_) => retained.push(world.world_id),
                    }
                } else {
                    retained.push(world.world_id);
                }
            }
            let status = if retained.is_empty() {
                "rolled_back"
            } else {
                "partial_rollback"
            };
            batch.receipt.status = status.into();
            batch.receipt.cleanup_removed = removed.clone();
            batch.receipt.retained_worlds = retained.clone();
            registry.update_batch(batch);
            RollbackReceipt {
                batch_id,
                status: status.into(),
                removed,
                already_missing,
                retained,
            }
        };
        for (world_id, members) in deleted {
            self.deleted(world_id, members);
        }
        Ok(result)
    }

    pub(crate) fn recent_pack_imports(&self, session: Uuid) -> Result<Vec<ImportReceipt>> {
        let core = self.lock();
        Self::require_local_operator(&core, session)?;
        Ok(self
            .pack_imports
            .lock()
            .expect("pack import registry mutex poisoned")
            .recent_batches())
    }
    pub fn capabilities(&self) -> Value {
        self.capabilities_for(ProtocolVersion::Stable03)
    }
    pub fn capabilities_for(&self, protocol: ProtocolVersion) -> Value {
        let mut button_features = vec![
            "selection_groups",
            "appearance_variants",
            "key_value_actions",
        ];
        if self.native_windows {
            button_features.push("external_window_actions");
            if cfg!(windows) {
                button_features.push("codex_thread_navigation");
            }
        }
        let component_leases = if protocol.supports_component_leases() {
            json!({"status":"preview","version":1,"scope_snapshots":"filtered","scope_revision":true,
                "scope_patch_operations":["props","insert","remove","replace","move"],
                "root_structure_patch":"scope.structure.patch","filtered_scope_events":true,
                "scope_interactions":{"status":"preview","version":1,"event":"scope.interaction",
                    "acknowledge_method":"scope.action.result","routing":"component_scope_owner",
                    "native_window_actions":false},
                "scope_status":{"status":"preview","version":1,"method":"scope.status",
                    "data":"lifecycle_metadata_only","authorization":"local_operator_or_active_world_authority_or_scope_member",
                    "states":["online","stale","vacant","revoked","unknown"]},
                "parent_revocation":"generation_fence",
                "state_slots":{"status":"preview","version":1,"schema_types":["boolean","integer","number","string","enum"],
                    "max_slots_per_world":MAX_STATE_SLOTS_PER_WORLD,"max_slots_per_scope":MAX_STATE_SLOTS_PER_SCOPE,
                    "max_readers_per_slot":MAX_STATE_SLOT_READERS,"value_bytes":MAX_STATE_SLOT_VALUE_BYTES,
                    "writes":"owner_scope_cas","reads":"explicit_scope_grants"}})
        } else {
            json!(false)
        };
        let not_implemented = if protocol.supports_component_leases() {
            json!([
                "cross_scope_structure",
                "follow_cursor",
                "attach_to_foreign_window",
                "native_opacity",
                "arbitrary_code",
                "builtin_tls"
            ])
        } else {
            json!([
                "component_leases",
                "follow_cursor",
                "attach_to_foreign_window",
                "native_opacity",
                "arbitrary_code",
                "builtin_tls"
            ])
        };
        let window_scope = if protocol.supports_component_leases() {
            "world_authority_and_component_scopes"
        } else {
            "exclusive_writer"
        };
        let mut capabilities = json!({"protocol":protocol.as_str(),"transport":["websocket"],"window_scope":window_scope,
            "read_model":"immutable_snapshots","dynamic_scene":true,"component_leases":component_leases,
            "event_subscriptions":{"scope":"session","max_subscriptions":32,"events":[
                {"type":"window.geometry_changed","delivery":"state"},
                {"type":"window.visibility_changed","delivery":"state"}
            ]},
            "native_windows":self.native_windows,"remote":"authenticated_ssh_tunnel",
            "max_worlds":MAX_WORLDS,"max_message_bytes":MAX_PAYLOAD,"lease_ms":LEASE_MS,
            "components":["stack","row","text","metric","progress","badge","button","input","textarea","key_value","icon","bar_chart","divider"],
            "keyboard_shortcuts":["escape","ctrl_enter"],
            "button_features":button_features,
            "scene_features":["theme_tokens","rich_key_value"],
            "window_properties":["title","width","height","position","anchor","always_on_top","visible","resizable","title_bar_visible","background_drag_enabled","text_selectable","decorations","skip_taskbar","click_through","geometry_control","position_control","surface_opacity"],
            "not_implemented":not_implemented});
        if protocol.supports_provider_inventory() {
            capabilities["provider_inventory"] = json!({
                "status":"preview",
                "version":1,
                "registration_method":"provider.inventory.register",
                "list_method":"provider.inventory.list",
                "scope":"authenticated_provider_sessions",
                "registration_grants":"never_accepted"
            });
            capabilities["provider_import"] = json!({
                "status":"preview",
                "version":1,
                "schema_version":"draft-2026-10-26",
                "event":"world.import.joined",
                "required_claim":"world.import.accept",
                "writer_scope":"exclusive_world_lease",
                "requires_local_confirmation":true
            });
        }
        if protocol.supports_component_leases() {
            capabilities["presentation_groups"] = json!({
                "status":"preview",
                "version":1,
                "schema_version":"draft-2026-10-31",
                "methods":["presentation.group.create","presentation.group.list",
                           "presentation.group.patch","presentation.group.delete",
                           "presentation.group.apply"],
                "membership":"ordered_set_of_worlds",
                "member_limit":MAX_GROUP_MEMBERS,
                "roles":"descriptive_labels_without_authority",
                "apply_semantics":"per_member_independent",
                "atomic":false,
                "partial_failure":"per_member_outcome_reported",
                "lease_required_per_member":true,
                "discovery_grants_operation_right":false
            });
        }
        capabilities
    }
    pub fn reply(&self, sid: Uuid, req: Request) -> Value {
        if req.id.is_empty() || req.id.len() > 80 || req.method.len() > 80 {
            return json!({"id":req.id,"ok":false,"error":Fault::new("INVALID_REQUEST","id and method too long or empty")});
        }
        match self.dispatch_with_cause(sid, &req.method, req.params, Some(req.id.clone())) {
            Ok(result) => json!({"id":req.id,"ok":true,"result":result}),
            Err(error) => json!({"id":req.id,"ok":false,"error":error}),
        }
    }
    pub fn dispatch(&self, sid: Uuid, method: &str, params: Value) -> Result<Value> {
        self.dispatch_with_cause(sid, method, params, None)
    }
    fn dispatch_with_cause(
        &self,
        sid: Uuid,
        method: &str,
        params: Value,
        cause_id: Option<String>,
    ) -> Result<Value> {
        let now = self.now();
        let mut e = self.lock();
        if !e.sessions.contains_key(&sid) {
            return Err(Fault::new("SESSION_GONE", "session missing"));
        }
        let source = if e.operator(sid) {
            EventSource::Operator
        } else {
            EventSource::Provider
        };
        let mut changed = None;
        let mut changed_many: Vec<Uuid> = Vec::new();
        let mut deleted = None;
        let mut directed = Vec::new();
        let value = match method {
            "session.ping" => {
                let mut renewed = vec![];
                let mut renewed_authorities = Vec::new();
                let mut renewed_scopes = Vec::new();
                let preview = e.sessions[&sid].protocol.supports_component_leases();
                for w in e.worlds.values_mut() {
                    if let Some(l) = &mut w.writer {
                        if l.session == sid && l.expires_at > now {
                            l.expires_at = now + LEASE_MS;
                            renewed.push(w.id);
                        }
                    }
                    if preview {
                        if let Some(authority) = &mut w.authority {
                            if authority.session == sid && authority.expires_at > now {
                                authority.expires_at = now + LEASE_MS;
                                renewed_authorities.push(w.id);
                            }
                        }
                        for scope in w.scopes.values_mut() {
                            if let Some(writer) = &mut scope.writer {
                                if writer.session == sid && writer.expires_at > now {
                                    writer.expires_at = now + LEASE_MS;
                                    renewed_scopes.push(scope.id);
                                }
                            }
                        }
                    }
                }
                if preview {
                    json!({"renewed":renewed,"authorities_renewed":renewed_authorities,"scopes_renewed":renewed_scopes,"lease_ms":LEASE_MS})
                } else {
                    json!({"renewed":renewed,"lease_ms":LEASE_MS})
                }
            }
            "host.capabilities" => self.capabilities_for(e.sessions[&sid].protocol),
            "world.list" => encode(e.list(sid)?)?,
            "presentation.group.create" => {
                if !e.sessions[&sid].protocol.supports_component_leases() {
                    return Err(Fault::new(
                        "UNSUPPORTED_CAPABILITY",
                        "presentation groups require the 0.4-preview.1 capability",
                    ));
                }
                let p: GroupCreateParams = decode(params)?;
                let mut group = PresentationGroup::new(Uuid::new_v4(), p.name);
                for member in p.members {
                    group.add_member(member.world_id, member.order)?;
                }
                for role in p.roles {
                    group.add_role(role)?;
                }
                self.presentation_groups
                    .lock()
                    .expect("presentation group mutex poisoned")
                    .insert(sid, group.clone())?;
                encode(group)?
            }
            "presentation.group.list" => {
                if !e.sessions[&sid].protocol.supports_component_leases() {
                    return Err(Fault::new(
                        "UNSUPPORTED_CAPABILITY",
                        "presentation groups require the 0.4-preview.1 capability",
                    ));
                }
                let groups = self
                    .presentation_groups
                    .lock()
                    .expect("presentation group mutex poisoned")
                    .list(sid);
                encode(groups)?
            }
            "presentation.group.patch" => {
                if !e.sessions[&sid].protocol.supports_component_leases() {
                    return Err(Fault::new(
                        "UNSUPPORTED_CAPABILITY",
                        "presentation groups require the 0.4-preview.1 capability",
                    ));
                }
                let p: GroupPatchParams = decode(params)?;
                let mut registry = self
                    .presentation_groups
                    .lock()
                    .expect("presentation group mutex poisoned");
                let group = registry.update(sid, p.group_id, |group| {
                    for member in p.add_members {
                        group.add_member(member.world_id, member.order)?;
                    }
                    for world_id in p.remove_members {
                        group.remove_member(world_id);
                    }
                    for role in p.add_roles {
                        group.add_role(role)?;
                    }
                    Ok(())
                })?;
                encode(group)?
            }
            "presentation.group.delete" => {
                if !e.sessions[&sid].protocol.supports_component_leases() {
                    return Err(Fault::new(
                        "UNSUPPORTED_CAPABILITY",
                        "presentation groups require the 0.4-preview.1 capability",
                    ));
                }
                let p: GroupIdParams = decode(params)?;
                self.presentation_groups
                    .lock()
                    .expect("presentation group mutex poisoned")
                    .remove(sid, p.group_id)?;
                json!({})
            }
            "presentation.group.apply" => {
                if !e.sessions[&sid].protocol.supports_component_leases() {
                    return Err(Fault::new(
                        "UNSUPPORTED_CAPABILITY",
                        "presentation groups require the 0.4-preview.1 capability",
                    ));
                }
                let p: GroupApplyParams = decode(params)?;
                let group = self
                    .presentation_groups
                    .lock()
                    .expect("presentation group mutex poisoned")
                    .get(sid, p.group_id)?;
                // Each member is operated on independently. A member whose
                // lease is missing, stale or mismatched refuses; the rest
                // still run, and the caller sees exactly which ones applied.
                let mut snapshots = BTreeMap::new();
                let result = group.apply_to_members(group.id, |world_id| {
                    let lease = p.leases.get(&world_id).ok_or_else(|| {
                        Fault::new("STALE_LEASE", "member lease was not supplied")
                    })?;
                    let expected = p.expected_revisions.get(&world_id).copied().unwrap_or(0);
                    // Each member is configured independently, so a refusal on
                    // one member does not abort the others.
                    let snapshot = e.configure(sid, world_id, lease, expected, &p.patch, now)?;
                    snapshots.insert(world_id, snapshot);
                    Ok(())
                });
                let mut changed_members = Vec::new();
                for member in &result.results {
                    if member.outcome.is_applied() {
                        changed_members.push(member.world_id);
                    }
                }
                changed_many = changed_members.clone();
                encode(json!({
                    "result": result,
                    "changed": changed_members,
                    "snapshots": snapshots,
                    "atomic": false,
                }))?
            }
            "provider.inventory.register" => {
                if !e.sessions[&sid].protocol.supports_provider_inventory() {
                    return Err(Fault::new(
                        "UNSUPPORTED_CAPABILITY",
                        "provider inventory requires the 0.4-preview.1 capability",
                    ));
                }
                let registration: ProviderInventoryRegistration = decode(params)?;
                let snapshot = self
                    .provider_inventory
                    .lock()
                    .expect("provider inventory mutex poisoned")
                    .register(
                        sid,
                        self.host_id,
                        registration,
                        now,
                        OffsetDateTime::now_utc(),
                    )?;
                encode(snapshot)?
            }
            "provider.inventory.list" => {
                if !e.sessions[&sid].protocol.supports_provider_inventory() {
                    return Err(Fault::new(
                        "UNSUPPORTED_CAPABILITY",
                        "provider inventory requires the 0.4-preview.1 capability",
                    ));
                }
                let snapshot = self
                    .provider_inventory
                    .lock()
                    .expect("provider inventory mutex poisoned")
                    .snapshot(self.host_id, now, OffsetDateTime::now_utc())?;
                encode(snapshot)?
            }
            "world.create" => {
                let p: CreateParams = decode(params)?;
                let mut c = e.create(sid, p.window, p.join_policy, p.claim, false, now)?;
                if !self.native_windows {
                    e.native_report(
                        c.world.id,
                        c.world.window_revision,
                        NativeReport {
                            state: "unavailable".into(),
                            applied_window_revision: None,
                            error: Some("headless host: no native renderer".into()),
                        },
                    );
                    c.world = e.read(sid, c.world.id)?;
                }
                changed = Some(c.world.id);
                encode(c)?
            }
            "world.join" => {
                let p: JoinParams = decode(params)?;
                let r = e.join(sid, p.world_id, p.join_key.as_deref(), p.mode, now)?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "world.snapshot" => {
                let p: WorldParams = decode(params)?;
                encode(e.read(sid, p.world_id)?)?
            }
            "world.leave" => {
                let p: WorldParams = decode(params)?;
                e.leave(sid, p.world_id)?;
                changed = Some(p.world_id);
                json!({})
            }
            "lease.renew" => {
                let p: LeaseParams = decode(params)?;
                e.renew(sid, p.world_id, &p.lease, now)?;
                json!({"lease_ms":LEASE_MS})
            }
            "lease.release" => {
                let p: LeaseParams = decode(params)?;
                let r = e.release(sid, p.world_id, &p.lease, now)?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "scene.replace" => {
                let p: SceneParams = decode(params)?;
                let r =
                    e.replace_scene(sid, p.world_id, &p.lease, p.expected_revision, p.scene, now)?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "scene.patch" => {
                let p: PatchParams = decode(params)?;
                let r =
                    e.patch_scene(sid, p.world_id, &p.lease, p.expected_revision, &p.ops, now)?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "data.replace" => {
                let p: DataParams = decode(params)?;
                let r = e.set_data(sid, p.world_id, &p.lease, p.expected_revision, p.data, now)?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "window.configure" => {
                let p: WindowParams = decode(params)?;
                let r = e.configure(
                    sid,
                    p.world_id,
                    &p.lease,
                    p.expected_revision,
                    &p.patch,
                    now,
                )?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "action.result" => {
                let p: AckParams = decode(params)?;
                e.acknowledge(
                    sid,
                    p.world_id,
                    &p.lease,
                    ActionAcknowledgement {
                        event_id: p.event_id,
                        ok: p.ok,
                        message: p.message,
                    },
                    now,
                )?;
                changed = Some(p.world_id);
                json!({})
            }
            "scope.action.result" => {
                let p: ScopeAckParams = decode(params)?;
                e.acknowledge_scope(
                    sid,
                    p.world_id,
                    &p.lease,
                    ActionAcknowledgement {
                        event_id: p.event_id,
                        ok: p.ok,
                        message: p.message,
                    },
                    now,
                )?;
                changed = Some(p.world_id);
                json!({})
            }
            "world.destroy" => {
                let p: LeaseParams = decode(params)?;
                let members = e.destroy(sid, p.world_id, &p.lease, now)?;
                deleted = Some((p.world_id, members));
                json!({})
            }
            "scope.partition" => {
                let p: ScopePartitionParams = decode(params)?;
                let result = e.partition_scopes(
                    sid,
                    p.world_id,
                    &p.lease,
                    p.expected_revision,
                    &p.scopes,
                    now,
                )?;
                changed = Some(p.world_id);
                encode(result)?
            }
            "scope.join" => {
                let p: ScopeJoinRequest = decode(params)?;
                let result = e.join_scope(sid, p, now)?;
                changed = Some(result.snapshot.world_id);
                encode(result)?
            }
            "scope.snapshot" => {
                let p: ScopeReadParams = decode(params)?;
                encode(e.read_scope(sid, p.world_id, p.scope_id, p.generation)?)?
            }
            "scope.status" => {
                let p: ScopeStatusParams = decode(params)?;
                encode(e.scope_status(sid, p.world_id, p.scope_id, p.generation, now)?)?
            }
            "scope.patch" => {
                let p: ScopePatchParams = decode(params)?;
                let result = e.patch_scope(
                    sid,
                    p.world_id,
                    &p.lease,
                    p.expected_scope_revision,
                    &p.ops,
                    now,
                )?;
                changed = Some(p.world_id);
                encode(result)?
            }
            "scope.structure.patch" => {
                let p: ScopeStructureParams = decode(params)?;
                let result = e.patch_scope_structure(
                    sid,
                    p.world_id,
                    &p.authority_lease,
                    p.expected_revision,
                    &p.ops,
                    now,
                )?;
                for revoked in result.revoked_scopes {
                    for target in revoked.sessions {
                        directed.push((
                            target,
                            json!({"event":"scope.revoked","data":{
                                "world_id":p.world_id,
                                "scope_id":revoked.scope_id,
                                "generation":revoked.generation,
                                "reason":"parent_structure_removed"
                            }}),
                        ));
                    }
                }
                changed = Some(p.world_id);
                encode(result.snapshot)?
            }
            "scope.data.replace" => {
                let p: ScopeDataParams = decode(params)?;
                let result = e.replace_scope_data(
                    sid,
                    p.world_id,
                    &p.lease,
                    p.expected_scope_revision,
                    p.data,
                    now,
                )?;
                changed = Some(p.world_id);
                encode(result)?
            }
            "scope.renew" => {
                let p: ScopeLeaseParams = decode(params)?;
                e.renew_scope(sid, p.world_id, &p.lease, now)?;
                json!({"lease_ms":LEASE_MS})
            }
            "scope.leave" => {
                let p: ScopeLeaveParams = decode(params)?;
                e.leave_scope(sid, p.world_id, p.scope_id)?;
                changed = Some(p.world_id);
                json!({})
            }
            "state.slot.create" => {
                let p: StateSlotCreateRequest = decode(params)?;
                let world_id = p.world_id;
                let result = e.create_state_slot(sid, p, now)?;
                changed = Some(world_id);
                encode(result)?
            }
            "state.slot.set_readers" => {
                let p: StateSlotSetReadersRequest = decode(params)?;
                let world_id = p.world_id;
                let result = e.set_state_slot_readers(sid, p, now)?;
                changed = Some(world_id);
                encode(result)?
            }
            "state.slot.read" => {
                let p: StateSlotReadRequest = decode(params)?;
                encode(e.read_state_slot(sid, p)?)?
            }
            "state.slot.compare_and_set" => {
                let p: StateSlotCompareAndSetRequest = decode(params)?;
                let world_id = p.world_id;
                let result = e.compare_and_set_state_slot(sid, p, now)?;
                changed = Some(world_id);
                encode(result)?
            }
            "state.slot.delete" => {
                let p: StateSlotDeleteRequest = decode(params)?;
                let world_id = p.world_id;
                e.delete_state_slot(sid, p, now)?;
                changed = Some(world_id);
                json!({"deleted":true})
            }
            _ => return Err(Fault::new("METHOD_NOT_FOUND", method)),
        };
        let changed = changed.and_then(|id| e.worlds.get(&id).map(|world| (id, world.sequence)));
        let changed_many: Vec<(Uuid, u64)> = changed_many
            .iter()
            .filter_map(|id| e.worlds.get(id).map(|world| (*id, world.sequence)))
            .collect();
        drop(e);
        if let Some((id, sequence)) = changed {
            self.changed_at(id, sequence, source, cause_id.clone());
        }
        for (id, sequence) in changed_many {
            self.changed_at(id, sequence, source, cause_id.clone());
        }
        for (target, event) in directed {
            let _ = self.events.send(Notice::Directed(target, event));
        }
        if let Some((id, members)) = deleted {
            self.deleted(id, members);
        }
        Ok(value)
    }
    pub fn interact(
        &self,
        id: Uuid,
        node: &str,
        value: Value,
        context_action: bool,
        expected_revision: u64,
    ) -> Result<Uuid> {
        self.interact_with_source(
            id,
            node,
            value,
            if context_action {
                InteractionSource::ContextMenu
            } else {
                InteractionSource::Click
            },
            expected_revision,
        )
    }
    pub fn interact_with_source(
        &self,
        id: Uuid,
        node: &str,
        value: Value,
        source: InteractionSource,
        expected_revision: u64,
    ) -> Result<Uuid> {
        self.interact_with_source_with_native_window_action(
            id,
            node,
            value,
            source,
            expected_revision,
            |_| Ok(()),
        )
    }
    pub fn interact_with_source_with_native_window_action<F>(
        &self,
        id: Uuid,
        node: &str,
        value: Value,
        source: InteractionSource,
        expected_revision: u64,
        focus: F,
    ) -> Result<Uuid>
    where
        F: FnOnce(&NativeWindowAction) -> Result<()>,
    {
        let now = self.now();
        let mut core = self.lock();
        let ownership_mode = core
            .worlds
            .get(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?
            .ownership_mode;
        let (sid, event_id, event_message) = match ownership_mode {
            OwnershipMode::ExclusiveWorld => {
                if let Some(action) =
                    core.native_window_action(id, node, source, expected_revision, now)?
                {
                    if !self.native_windows {
                        return Err(Fault::new(
                            "UNSUPPORTED_CAPABILITY",
                            "native external window actions are not available on this host",
                        ));
                    }
                    if action.application == NativeWindowApplication::CodexApp && !cfg!(windows) {
                        return Err(Fault::new(
                            "UNSUPPORTED_CAPABILITY",
                            "Codex App thread navigation is only available on Windows hosts",
                        ));
                    }
                    focus(&action)?;
                }
                let (target, event) =
                    core.interact_with_source(id, node, value, source, expected_revision, now)?;
                let event_id = event.id;
                (
                    target,
                    event_id,
                    json!({"event":"interaction","data":event}),
                )
            }
            OwnershipMode::ScopedSubtrees => {
                let (target, event) = core.interact_in_scope_with_source(
                    id,
                    node,
                    value,
                    source,
                    expected_revision,
                    now,
                )?;
                let event_id = event.id;
                (
                    target,
                    event_id,
                    json!({"event":"scope.interaction","data":event}),
                )
            }
        };
        let sequence = core.worlds.get(&id).map(|world| world.sequence);
        drop(core);
        let _ = self.events.send(Notice::Directed(sid, event_message));
        if let Some(sequence) = sequence {
            self.changed_at(id, sequence, EventSource::Human, None);
        }
        Ok(event_id)
    }
    pub fn start_housekeeping(&self, mut shutdown: watch::Receiver<bool>) -> JoinHandle<()> {
        let hub = self.clone();
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(std::time::Duration::from_millis(200));
            loop {
                tokio::select! {
                    _ = shutdown.changed() => break,
                    _ = interval.tick() => {
                        let expired = {
                            let mut core = hub.lock();
                            core.expire(hub.now())
                                .into_iter()
                                .filter_map(|id| core.worlds.get(&id).map(|world| (id, world.sequence)))
                                .collect::<Vec<_>>()
                        };
                        for (id, sequence) in expired {
                            hub.changed_at(id, sequence, EventSource::System, None);
                        }
                    }
                }
            }
        })
    }
}

#[cfg(test)]
mod pack_import_tests {
    use super::*;
    use crate::self_provider::ManagerProvider;
    use serde_json::json;
    use time::format_description::well_known::Rfc3339;
    use wincraft_core::{ProtocolVersion, WindowSpec};

    fn pack(required: bool, permissions: &[&str]) -> Value {
        json!({
            "kind":"wincraft.pack.draft",
            "schema_version":"draft-2026-10-26",
            "id":"test.import-pack",
            "version":"1.0",
            "title":{"zh-CN":"测试配置包","en-US":"Test configuration pack"},
            "bindings":[{
                "id":"agents",
                "required":required,
                "provider_types":["agent-board"],
                "capabilities":["activity.read","world.import.accept"],
                "permissions":permissions,
                "min_adapter_contract":1
            }],
            "blueprint":"blueprints/test.json",
            "fallback_policy":"explain_missing",
            "adapter":null
        })
    }

    fn blueprint(worlds: usize) -> Value {
        json!({
            "kind":"wincraft.blueprint.draft",
            "schema_version":"draft-2026-10-26",
            "id":"test.blueprint",
            "worlds":(0..worlds).map(|index|json!({
                "id":format!("world-{index}"),
                "title":{"zh-CN":format!("测试世界 {index}")},
                "binding_slots":["agents"],
                "layout_hint":"stack",
                "scene":{"root":{"id":"root","kind":"stack","children":[
                    {"id":"title","kind":"text","props":{"text":format!("测试世界 {index}")}}
                ]}}
            })).collect::<Vec<_>>()
        })
    }

    fn source_registration(instance: &str, generation: u64, now: &str) -> Value {
        json!({
            "kind":"wincraft.inventory.registration",
            "schema_version":"draft-2026-10-29",
            "generation":generation,
            "observed_at":now,
            "valid_for_seconds":60,
            "providers":[{
                "source_id":"source.agents",
                "source_instance_id":instance,
                "provider_type":"agent-board",
                "display_name":"Agent board",
                "adapter_contract":1,
                "state":"online",
                "capabilities":["activity.read","world.import.accept"],
                "source_updated_at":now,
                "fresh_for_seconds":45
            }]
        })
    }

    fn add_source(hub: &Hub, instance: &str, generation: u64) -> Uuid {
        let session = hub
            .lock()
            .register_with_protocol(
                format!("provider-{instance}"),
                false,
                ProtocolVersion::ComponentLeasesPreview01,
            )
            .unwrap();
        let now = time::OffsetDateTime::now_utc().format(&Rfc3339).unwrap();
        hub.dispatch(
            session,
            "provider.inventory.register",
            source_registration(instance, generation, &now),
        )
        .unwrap();
        session
    }

    fn world_count(hub: &Hub) -> usize {
        hub.lock().worlds.len()
    }

    #[test]
    fn inventory_change_invalidates_preview_before_any_world_is_created() {
        let hub = Hub::new(false);
        let manager = ManagerProvider::install(&hub).unwrap();
        add_source(&hub, "instance-a", 1);
        let preview = hub
            .preview_pack_values(
                manager.session,
                pack(true, &[]),
                blueprint(1),
                BTreeMap::new(),
            )
            .unwrap();
        assert_eq!(preview.status, PlanStatus::Ready);
        add_source(&hub, "instance-b", 1);
        let error = hub
            .apply_pack_preview(manager.session, preview.preview_id, true)
            .unwrap_err();
        assert_eq!(error.code, "STALE_PLAN");
        assert_eq!(world_count(&hub), 1);
    }

    #[test]
    fn cancelling_preview_preserves_existing_worlds_and_does_not_apply() {
        let hub = Hub::new(false);
        let manager = ManagerProvider::install(&hub).unwrap();
        let existing = hub
            .dispatch(
                manager.session,
                "world.create",
                json!({"window":{"title":"existing"},"join_policy":"invite","claim":false}),
            )
            .unwrap()["world"]["id"]
            .as_str()
            .unwrap()
            .to_owned();
        let preview = hub
            .preview_pack_values(
                manager.session,
                pack(false, &[]),
                blueprint(1),
                BTreeMap::new(),
            )
            .unwrap();
        assert_eq!(preview.status, PlanStatus::Degraded);
        hub.cancel_pack_preview(manager.session, preview.preview_id)
            .unwrap();
        assert_eq!(
            hub.apply_pack_preview(manager.session, preview.preview_id, true)
                .unwrap_err()
                .code,
            "PLAN_NOT_FOUND"
        );
        assert_eq!(world_count(&hub), 2);
        assert_eq!(
            hub.renderer_snapshot(existing.parse().unwrap())
                .unwrap()
                .window
                .title,
            "existing"
        );
    }

    #[test]
    fn confirmation_creates_new_worlds_and_assigns_only_the_selected_provider() {
        let hub = Hub::new(false);
        let manager = ManagerProvider::install(&hub).unwrap();
        let provider = add_source(&hub, "instance-a", 1);
        let preview = hub
            .preview_pack_values(
                manager.session,
                pack(true, &[]),
                blueprint(1),
                BTreeMap::new(),
            )
            .unwrap();
        assert_eq!(preview.status, PlanStatus::Ready);
        let initial = world_count(&hub);
        assert_eq!(
            hub.apply_pack_preview(manager.session, preview.preview_id, false)
                .unwrap_err()
                .code,
            "CONFIRMATION_REQUIRED"
        );
        assert_eq!(world_count(&hub), initial);
        let mut notices = hub.subscribe();
        let receipt = hub
            .apply_pack_preview(manager.session, preview.preview_id, true)
            .unwrap();
        assert_eq!(receipt.status, "applied");
        assert_eq!(receipt.worlds.len(), 1);
        assert_eq!(world_count(&hub), initial + 1);
        let world_id = receipt.worlds[0].world_id;
        let snapshot = hub.renderer_snapshot(world_id).unwrap();
        assert_eq!(snapshot.writer, Some(provider));
        assert!(serde_json::to_string(&snapshot.scene)
            .unwrap()
            .contains("测试世界 0"));
        assert!(matches!(
            notices.try_recv(),
            Ok(Notice::Directed(target, ref event))
                if target == provider && event["event"] == "world.import.joined"
        ));

        let replay = hub
            .apply_pack_preview(manager.session, preview.preview_id, true)
            .unwrap();
        assert!(replay.idempotent_replay);
        assert_eq!(world_count(&hub), initial + 1);
    }

    #[test]
    fn permission_requires_a_separate_local_approval_and_repreview() {
        let hub = Hub::new(false);
        let manager = ManagerProvider::install(&hub).unwrap();
        let provider = add_source(&hub, "instance-a", 1);
        let preview = hub
            .preview_pack_values(
                manager.session,
                pack(true, &["activity.read"]),
                blueprint(1),
                BTreeMap::new(),
            )
            .unwrap();
        assert_eq!(preview.status, PlanStatus::Blocked);
        assert_eq!(
            preview.bindings[0].candidates[0].missing_permissions,
            vec!["activity.read"]
        );
        hub.authorize_pack_binding(manager.session, preview.preview_id, "agents", "instance-a")
            .unwrap();
        assert_eq!(
            hub.apply_pack_preview(manager.session, preview.preview_id, true)
                .unwrap_err()
                .code,
            "PLAN_NOT_FOUND"
        );
        let updated = hub
            .preview_pack_values(
                manager.session,
                pack(true, &["activity.read"]),
                blueprint(1),
                BTreeMap::new(),
            )
            .unwrap();
        assert_eq!(updated.status, PlanStatus::Ready);
        let receipt = hub
            .apply_pack_preview(manager.session, updated.preview_id, true)
            .unwrap();
        assert_eq!(
            hub.renderer_snapshot(receipt.worlds[0].world_id)
                .unwrap()
                .writer,
            Some(provider)
        );
    }

    #[test]
    fn provider_without_import_claim_cannot_be_selected_or_receive_a_world_lease() {
        let hub = Hub::new(false);
        let manager = ManagerProvider::install(&hub).unwrap();
        let provider = hub
            .lock()
            .register_with_protocol(
                "provider-without-import-event".into(),
                false,
                ProtocolVersion::ComponentLeasesPreview01,
            )
            .unwrap();
        let now = time::OffsetDateTime::now_utc().format(&Rfc3339).unwrap();
        let mut registration = source_registration("instance-no-import", 1, &now);
        registration["providers"][0]["capabilities"] = json!(["activity.read"]);
        hub.dispatch(provider, "provider.inventory.register", registration)
            .unwrap();
        let preview = hub
            .preview_pack_values(
                manager.session,
                pack(true, &[]),
                blueprint(1),
                BTreeMap::new(),
            )
            .unwrap();
        assert_eq!(preview.status, PlanStatus::Blocked);
        assert_eq!(preview.bindings[0].status, "missing");
        assert_eq!(
            hub.apply_pack_preview(manager.session, preview.preview_id, true)
                .unwrap_err()
                .code,
            "PLAN_BLOCKED"
        );
        assert_eq!(hub.lock().worlds.len(), 1);
    }

    #[test]
    fn mid_apply_failure_reports_cleanup_without_removing_existing_worlds() {
        let hub = Hub::new(false);
        let manager = ManagerProvider::install(&hub).unwrap();
        {
            let mut core = hub.lock();
            for index in 0..14 {
                core.create(
                    manager.session,
                    WindowSpec {
                        title: format!("existing-{index}"),
                        ..WindowSpec::default()
                    },
                    JoinPolicy::Invite,
                    false,
                    false,
                    hub.now(),
                )
                .unwrap();
            }
        }
        assert_eq!(world_count(&hub), 15);
        let preview = hub
            .preview_pack_values(
                manager.session,
                pack(false, &[]),
                blueprint(2),
                BTreeMap::new(),
            )
            .unwrap();
        let receipt = hub
            .apply_pack_preview(manager.session, preview.preview_id, true)
            .unwrap();
        assert_eq!(receipt.status, "failed_rolled_back");
        assert_eq!(receipt.failure_code.as_deref(), Some("LIMIT"));
        assert_eq!(receipt.cleanup_removed.len(), 1);
        assert!(receipt.retained_worlds.is_empty());
        assert_eq!(world_count(&hub), 15);
    }

    #[test]
    fn rollback_preserves_worlds_that_a_user_or_provider_changed() {
        let hub = Hub::new(false);
        let manager = ManagerProvider::install(&hub).unwrap();
        let preview = hub
            .preview_pack_values(
                manager.session,
                pack(false, &[]),
                blueprint(1),
                BTreeMap::new(),
            )
            .unwrap();
        let receipt = hub
            .apply_pack_preview(manager.session, preview.preview_id, true)
            .unwrap();
        let world_id = receipt.worlds[0].world_id;
        hub.lock()
            .operator_visibility(manager.session, world_id, false)
            .unwrap();
        let rollback = hub
            .rollback_pack_import(manager.session, receipt.batch_id)
            .unwrap();
        assert_eq!(rollback.status, "partial_rollback");
        assert_eq!(rollback.retained, vec![world_id]);
        assert!(hub.renderer_snapshot(world_id).is_ok());
    }
}
