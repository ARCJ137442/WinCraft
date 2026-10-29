use serde_json::json;
use wincraft_core::*;

fn setup() -> (Engine, uuid::Uuid, uuid::Uuid, Created) {
    let mut e = Engine::default();
    let a = e.register("A".into(), false).unwrap();
    let b = e.register("B".into(), false).unwrap();
    let w = e
        .create(a, WindowSpec::default(), JoinPolicy::Invite, true, false, 0)
        .unwrap();
    (e, a, b, w)
}

#[test]
fn concurrent_worlds_have_a_hard_host_quota() {
    let mut engine = Engine::default();
    let provider = engine.register("quota.test".into(), false).unwrap();
    for _ in 0..MAX_WORLDS {
        engine
            .create(
                provider,
                WindowSpec::default(),
                JoinPolicy::Invite,
                true,
                false,
                0,
            )
            .unwrap();
    }
    assert_eq!(engine.worlds.len(), MAX_WORLDS);
    assert_eq!(
        engine
            .create(
                provider,
                WindowSpec::default(),
                JoinPolicy::Invite,
                true,
                false,
                0,
            )
            .unwrap_err()
            .code,
        "LIMIT"
    );
}
#[test]
fn discovery_does_not_authorize_read() {
    let (mut e, a, b, invite) = setup();
    let operator = e.register("local.operator".into(), true).unwrap();
    let open = e
        .create(
            a,
            WindowSpec {
                title: "Open demo world".into(),
                ..WindowSpec::default()
            },
            JoinPolicy::OpenAuthenticated,
            false,
            false,
            1,
        )
        .unwrap();
    let system = e
        .create(
            operator,
            WindowSpec {
                title: "System manager".into(),
                ..WindowSpec::default()
            },
            JoinPolicy::Invite,
            false,
            true,
            1,
        )
        .unwrap();

    let discovered = e.list(b).unwrap();
    assert_eq!(discovered.len(), 1);
    assert_eq!(discovered[0].id, open.world.id);
    assert_eq!(discovered[0].join_policy, JoinPolicy::OpenAuthenticated);
    let metadata = serde_json::to_value(&discovered[0]).unwrap();
    for forbidden in ["join_key", "lease", "scene", "data"] {
        assert!(metadata.get(forbidden).is_none());
    }
    assert_eq!(e.read(b, open.world.id).unwrap_err().code, "FORBIDDEN");
    assert_eq!(e.read(b, invite.world.id).unwrap_err().code, "FORBIDDEN");
    assert!(!discovered.iter().any(|world| world.id == invite.world.id));
    assert!(!discovered.iter().any(|world| world.id == system.world.id));
    assert!(e
        .list(operator)
        .unwrap()
        .iter()
        .any(|world| world.id == system.world.id));
    e.join(b, open.world.id, None, JoinMode::Read, 2).unwrap();
    assert!(e.read(b, open.world.id).is_ok());
    assert!(!e
        .list(b)
        .unwrap()
        .iter()
        .any(|world| world.id == invite.world.id));
}

#[test]
fn world_list_keeps_same_display_names_as_distinct_instances() {
    let mut e = Engine::default();
    let owner = e.register("inventory.owner".into(), false).unwrap();
    let observer = e.register("inventory.observer".into(), false).unwrap();
    let mut ids = Vec::new();
    for _ in 0..2 {
        let created = e
            .create(
                owner,
                WindowSpec {
                    title: "Same display name".into(),
                    ..WindowSpec::default()
                },
                JoinPolicy::OpenAuthenticated,
                false,
                false,
                0,
            )
            .unwrap();
        ids.push(created.world.id);
    }

    let discovered = e.list(observer).unwrap();
    assert_eq!(discovered.len(), 2);
    assert!(discovered
        .iter()
        .all(|world| world.title == "Same display name"));
    assert_ne!(discovered[0].id, discovered[1].id);
    let discovered_ids: std::collections::BTreeSet<_> =
        discovered.iter().map(|world| world.id).collect();
    let expected_ids: std::collections::BTreeSet<_> = ids.into_iter().collect();
    assert_eq!(discovered_ids, expected_ids);
}

#[test]
fn discovery_distinguishes_stale_vacant_and_unauthorized_invite_worlds() {
    let (mut e, owner, observer, invite) = setup();
    let open_online = e
        .create(
            owner,
            WindowSpec::default(),
            JoinPolicy::OpenAuthenticated,
            true,
            false,
            0,
        )
        .unwrap();
    let open_vacant = e
        .create(
            owner,
            WindowSpec::default(),
            JoinPolicy::OpenAuthenticated,
            false,
            false,
            0,
        )
        .unwrap();
    e.disconnect(owner);

    let discovered = e.list(observer).unwrap();
    let stale = discovered
        .iter()
        .find(|world| world.id == open_online.world.id)
        .unwrap();
    let vacant = discovered
        .iter()
        .find(|world| world.id == open_vacant.world.id)
        .unwrap();
    assert_eq!(stale.status, "stale");
    assert_eq!(vacant.status, "vacant");
    assert!(!discovered.iter().any(|world| world.id == invite.world.id));
    assert_eq!(
        e.join(observer, invite.world.id, None, JoinMode::Read, 1)
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
}
#[test]
fn invite_required_for_join() {
    let (mut e, _, b, c) = setup();
    assert_eq!(
        e.join(b, c.world.id, None, JoinMode::Read, 1)
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
    assert!(e
        .join(b, c.world.id, Some(&c.join_key), JoinMode::Read, 1)
        .is_ok());
}
#[test]
fn many_snapshot_readers_one_writer() {
    let (mut e, _, b, c) = setup();
    e.join(b, c.world.id, Some(&c.join_key), JoinMode::Read, 1)
        .unwrap();
    assert!(e.read(b, c.world.id).is_ok());
    assert_eq!(
        e.join(b, c.world.id, Some(&c.join_key), JoinMode::Write, 1)
            .unwrap_err()
            .code,
        "WRITE_CONFLICT"
    );
}
#[test]
fn fence_old_lease_after_release_and_reacquire() {
    let (mut e, a, b, c) = setup();
    let old = c.lease.unwrap();
    e.release(a, c.world.id, &old, 1).unwrap();
    let next = e
        .join(b, c.world.id, Some(&c.join_key), JoinMode::Write, 2)
        .unwrap();
    assert!(next.lease.unwrap().epoch > old.epoch);
    assert_eq!(
        e.set_data(a, c.world.id, &old, next.world.revision, json!({}), 3)
            .unwrap_err()
            .code,
        "STALE_LEASE"
    );
}
#[test]
fn disconnected_world_stays_stale_not_fake_online() {
    let (mut e, a, _, c) = setup();
    e.disconnect(a);
    assert_eq!(e.worlds[&c.world.id].snapshot().status, "stale");
    assert!(e.worlds[&c.world.id].writer.is_none());
}

#[test]
fn repeated_disconnect_is_idempotent_and_scoped_to_its_session() {
    let (mut e, a, b, c) = setup();
    let b_world = e
        .create(
            b,
            WindowSpec::default(),
            JoinPolicy::OpenAuthenticated,
            true,
            false,
            0,
        )
        .unwrap();
    e.join(b, c.world.id, Some(&c.join_key), JoinMode::Read, 1)
        .unwrap();
    let scene = Scene {
        root: Node::new(
            "root",
            Kind::Stack,
            json!({}),
            vec![Node::new(
                "confirm",
                Kind::Button,
                json!({"label":"Confirm","action":"confirm"}),
                vec![],
            )],
        ),
        ..Scene::default()
    };
    let current = e
        .replace_scene(a, c.world.id, &c.lease.unwrap(), c.world.revision, scene, 1)
        .unwrap();
    e.interact(
        c.world.id,
        "confirm",
        serde_json::Value::Null,
        false,
        current.revision,
        2,
    )
    .unwrap();

    let changed = e.disconnect(a);
    let revoked = e.worlds[&c.world.id].snapshot();
    assert_eq!(changed, vec![c.world.id]);
    assert_eq!(revoked.status, "stale");
    assert!(revoked.epoch > current.epoch);
    assert_eq!(revoked.actions[0].status, "error");
    assert!(e.read(b, c.world.id).is_ok());
    assert_eq!(
        e.worlds[&b_world.world.id].writer.as_ref().unwrap().session,
        b
    );

    let revoked_sequence = e.worlds[&c.world.id].sequence;
    let revoked_epoch = e.worlds[&c.world.id].epoch;
    assert!(e.disconnect(a).is_empty());
    assert_eq!(e.worlds[&c.world.id].sequence, revoked_sequence);
    assert_eq!(e.worlds[&c.world.id].epoch, revoked_epoch);
    e.leave(b, c.world.id).unwrap();
    e.leave(b, c.world.id).unwrap();
    assert_eq!(
        e.worlds[&b_world.world.id].writer.as_ref().unwrap().session,
        b
    );
}

#[test]
fn lease_handle_cannot_be_reused_by_a_new_session() {
    let (mut e, a, _, c) = setup();
    let old_lease = c.lease.unwrap();
    e.disconnect(a);
    let replacement = e.register("replacement-session".into(), false).unwrap();
    let joined = e
        .join(
            replacement,
            c.world.id,
            Some(&c.join_key),
            JoinMode::Write,
            2,
        )
        .unwrap();
    let new_lease = joined.lease.unwrap();
    assert!(new_lease.epoch > old_lease.epoch);
    assert_eq!(
        e.set_data(
            replacement,
            c.world.id,
            &old_lease,
            joined.world.revision,
            json!({"stale":"must not commit"}),
            3,
        )
        .unwrap_err()
        .code,
        "STALE_LEASE"
    );
    assert_eq!(
        e.read(replacement, c.world.id).unwrap().scene.data,
        serde_json::Value::Null
    );
}

#[test]
fn expiration_is_checked_even_before_reaper() {
    let (mut e, a, _, c) = setup();
    assert_eq!(
        e.set_data(
            a,
            c.world.id,
            &c.lease.unwrap(),
            c.world.revision,
            json!({}),
            LEASE_MS
        )
        .unwrap_err()
        .code,
        "LEASE_EXPIRED"
    );
    assert_eq!(e.expire(LEASE_MS), vec![c.world.id]);
}
#[test]
fn scene_update_is_atomic_and_validated() {
    let scene = Scene::default();
    let result = scene.patch(&[
        SceneOp::Props {
            node_id: "empty".into(),
            props: json!({"text":"changed"}).as_object().unwrap().clone(),
        },
        SceneOp::Remove {
            node_id: "not-there".into(),
        },
    ]);
    assert!(result.is_err());
    assert_eq!(scene, Scene::default());
}

#[test]
fn rich_key_value_rows_accept_bounded_data_bindings() {
    let scene = Scene {
        root: Node::new(
            "root",
            Kind::Stack,
            json!({}),
            vec![Node::new(
                "items",
                Kind::KeyValue,
                json!({"items":[{
                    "key":"01",
                    "value":{"$path":"/title"},
                    "secondary":{"$path":"/status"},
                    "icon":"pin",
                    "tone":"accent"
                }]}),
                vec![],
            )],
        ),
        data: json!({"title":"synthetic item", "status":"in progress"}),
        ..Scene::default()
    };
    assert!(scene.validate().is_ok());

    let invalid = Scene {
        root: Node::new(
            "root",
            Kind::KeyValue,
            json!({"items":[{"key":"01", "value":{"$path":"../title"}}]}),
            vec![],
        ),
        ..Scene::default()
    };
    assert_eq!(invalid.validate().unwrap_err().code, "INVALID_SCENE");
}

#[test]
fn native_window_action_is_allowlisted_bounded_and_user_triggered() {
    let (mut engine, provider, _, created) = setup();
    let lease = created.lease.clone().unwrap();
    let before = engine.read(provider, created.world.id).unwrap();
    let scene = Scene {
        root: Node::new(
            "root",
            Kind::Stack,
            json!({}),
            vec![
                Node::new(
                    "focus-obsidian",
                    Kind::Button,
                    json!({
                        "label":"Obsidian Workspace",
                        "action":"dashboard.focus",
                        "native_window_action":{"application":"obsidian","operation":"activate","title_contains":"Obsidian Workspace"},
                        "disabled":{"$path":"/disabled"}
                    }),
                    vec![],
                ),
                Node::new(
                    "maximize-traffic-monitor",
                    Kind::Button,
                    json!({
                        "label":"最大化 TrafficMonitor",
                        "action":"traffic_monitor.maximize",
                        "native_window_action":{"application":"traffic_monitor","operation":"maximize"}
                    }),
                    vec![],
                ),
            ],
        ),
        data: json!({"disabled":false}),
        ..Scene::default()
    };
    let updated = engine
        .replace_scene(
            provider,
            created.world.id,
            &lease,
            before.revision,
            scene,
            1,
        )
        .unwrap();
    assert_eq!(
        engine
            .native_window_action(
                created.world.id,
                "focus-obsidian",
                InteractionSource::Click,
                updated.revision,
                2,
            )
            .unwrap(),
        Some(NativeWindowAction {
            application: NativeWindowApplication::Obsidian,
            operation: NativeWindowOperation::Activate,
            title_contains: Some("Obsidian Workspace".into()),
        })
    );
    assert_eq!(
        engine
            .native_window_action(
                created.world.id,
                "maximize-traffic-monitor",
                InteractionSource::Click,
                updated.revision,
                2,
            )
            .unwrap(),
        Some(NativeWindowAction {
            application: NativeWindowApplication::TrafficMonitor,
            operation: NativeWindowOperation::Maximize,
            title_contains: None,
        })
    );
    assert!(engine
        .native_window_action(
            created.world.id,
            "focus-obsidian",
            InteractionSource::ContextMenu,
            updated.revision,
            2,
        )
        .unwrap()
        .is_none());
    assert_eq!(
        engine
            .native_window_action(
                created.world.id,
                "focus-obsidian",
                InteractionSource::Click,
                updated.revision.saturating_sub(1),
                2,
            )
            .unwrap_err()
            .code,
        "REVISION_CONFLICT"
    );
    assert_eq!(
        engine
            .native_window_action(
                created.world.id,
                "focus-obsidian",
                InteractionSource::Click,
                updated.revision,
                LEASE_MS + 1,
            )
            .unwrap_err()
            .code,
        "OFFLINE"
    );

    let disabled = engine
        .set_data(
            provider,
            created.world.id,
            &lease,
            updated.revision,
            json!({"disabled":true}),
            3,
        )
        .unwrap();
    assert_eq!(
        engine
            .native_window_action(
                created.world.id,
                "focus-obsidian",
                InteractionSource::Click,
                disabled.revision,
                4,
            )
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
    engine
        .release(provider, created.world.id, &lease, 5)
        .unwrap();
    let released = engine.read(provider, created.world.id).unwrap();
    assert_eq!(
        engine
            .native_window_action(
                created.world.id,
                "focus-obsidian",
                InteractionSource::Click,
                released.revision,
                6,
            )
            .unwrap_err()
            .code,
        "OFFLINE"
    );
}

#[test]
fn native_window_action_rejects_unknown_apps_operations_and_unbounded_title_filters() {
    let make_scene = |target: serde_json::Value| Scene {
        root: Node::new(
            "root",
            Kind::Button,
            json!({"label":"Window action","action":"window.action","native_window_action":target}),
            vec![],
        ),
        ..Scene::default()
    };
    assert_eq!(
        make_scene(json!({"application":"powershell","operation":"activate"}))
            .validate()
            .unwrap_err()
            .code,
        "INVALID_SCENE"
    );
    assert_eq!(
        make_scene(json!({"application":"obsidian","operation":"activate","title_contains":"x".repeat(129)}))
            .validate()
            .unwrap_err()
            .code,
        "INVALID_SCENE"
    );
    assert_eq!(
        make_scene(json!({"application":"obsidian","operation":"shell"}))
            .validate()
            .unwrap_err()
            .code,
        "INVALID_SCENE"
    );
    assert!(
        make_scene(json!({"application":"traffic_monitor","operation":"maximize"}))
            .validate()
            .is_ok()
    );
}

#[test]
fn theme_tokens_are_bounded_and_meet_text_contrast() {
    let theme = ThemeTokens {
        background: "#111827".into(),
        foreground: "#F9FAFB".into(),
        accent: "#67E8F9".into(),
        font_scale: 1.0,
        radius_px: 12,
        spacing_px: 12,
    };
    let scene = Scene {
        theme: Some(theme.clone()),
        ..Scene::default()
    };
    assert!(scene.validate().is_ok());

    let mut invalid_scale = theme.clone();
    invalid_scale.font_scale = 2.01;
    let invalid_scale_scene = Scene {
        theme: Some(invalid_scale),
        ..Scene::default()
    };
    assert_eq!(
        invalid_scale_scene.validate().unwrap_err().code,
        "INVALID_SCENE"
    );

    let mut invalid_color = theme.clone();
    invalid_color.background = "url(javascript:alert(1))".into();
    let invalid_color_scene = Scene {
        theme: Some(invalid_color),
        ..Scene::default()
    };
    assert_eq!(
        invalid_color_scene.validate().unwrap_err().code,
        "INVALID_SCENE"
    );

    let mut low_contrast = theme;
    low_contrast.foreground = low_contrast.background.clone();
    let low_contrast_scene = Scene {
        theme: Some(low_contrast),
        ..Scene::default()
    };
    assert_eq!(
        low_contrast_scene.validate().unwrap_err().code,
        "INVALID_SCENE"
    );
}

#[test]
fn invalid_theme_scene_replacement_is_atomic_and_keeps_the_lease() {
    let (mut engine, provider, _, created) = setup();
    let lease = created.lease.unwrap();
    let before = engine.read(provider, created.world.id).unwrap();
    let invalid_scene = Scene {
        root: before.scene.root.clone(),
        data: json!({"must_not_commit":true}),
        theme: Some(ThemeTokens {
            background: "#111827".into(),
            foreground: "#111827".into(),
            accent: "#67E8F9".into(),
            font_scale: 1.0,
            radius_px: 12,
            spacing_px: 12,
        }),
    };
    assert_eq!(
        engine
            .replace_scene(
                provider,
                created.world.id,
                &lease,
                before.revision,
                invalid_scene,
                1,
            )
            .unwrap_err()
            .code,
        "INVALID_SCENE"
    );
    let after = engine.read(provider, created.world.id).unwrap();
    assert_eq!(after.revision, before.revision);
    assert_eq!(after.scene, before.scene);
    let updated = engine
        .set_data(
            provider,
            created.world.id,
            &lease,
            after.revision,
            json!({"still_authorized":true}),
            2,
        )
        .unwrap();
    assert_eq!(updated.scene.data, json!({"still_authorized":true}));
}

#[test]
fn dynamic_insert_move_replace_remove() {
    let s = Scene::default()
        .patch(&[SceneOp::Insert {
            parent: "root".into(),
            index: 1,
            node: Node::new("metric", Kind::Metric, json!({"value":42}), vec![]),
        }])
        .unwrap();
    let s = s
        .patch(&[SceneOp::Move {
            node_id: "metric".into(),
            parent: "root".into(),
            index: 0,
        }])
        .unwrap();
    assert_eq!(s.root.children[0].id, "metric");
    let s = s
        .patch(&[SceneOp::Replace {
            node_id: "metric".into(),
            node: Node::new("done", Kind::Badge, json!({"text":"done"}), vec![]),
        }])
        .unwrap();
    let s = s
        .patch(&[SceneOp::Remove {
            node_id: "done".into(),
        }])
        .unwrap();
    assert_eq!(s, Scene::default());
}
#[test]
fn cannot_move_into_own_descendant() {
    let s = Scene {
        root: Node::new(
            "root",
            Kind::Stack,
            json!({}),
            vec![Node::new(
                "a",
                Kind::Stack,
                json!({}),
                vec![Node::new("b", Kind::Stack, json!({}), vec![])],
            )],
        ),
        data: json!({}),
        theme: None,
    };
    assert!(s
        .patch(&[SceneOp::Move {
            node_id: "a".into(),
            parent: "b".into(),
            index: 0
        }])
        .is_err());
}
#[test]
fn duplicate_ids_and_script_like_props_are_rejected() {
    let bad = Node::new("empty", Kind::Text, json!({"text":"x"}), vec![]);
    assert!(Scene::default()
        .patch(&[SceneOp::Insert {
            parent: "root".into(),
            index: 1,
            node: bad
        }])
        .is_err());
    let bad = Node::new("x", Kind::Text, json!({"innerHTML":"<script/>"}), vec![]);
    assert!(Scene {
        root: bad,
        data: json!({}),
        theme: None,
    }
    .validate()
    .is_err());
}
#[test]
fn human_mode_requires_explicit_handback() {
    let s = WindowSpec::default();
    let p = WindowPatch {
        position: Some(Position { x: 20, y: 30 }),
        ..Default::default()
    };
    assert_eq!(p.apply(&s).unwrap_err().code, "HUMAN_GEOMETRY");
    let p = WindowPatch {
        geometry_control: Some(GeometryControl::Provider),
        ..p
    };
    assert_eq!(
        p.apply(&s).unwrap().position,
        Some(Position { x: 20, y: 30 })
    );
}

#[test]
fn windows_default_to_topmost_and_provider_can_configure_it() {
    let (mut engine, provider, _, created) = setup();
    assert!(created.world.window.always_on_top);
    let lease = created.lease.unwrap();

    let lowered = engine
        .configure(
            provider,
            created.world.id,
            &lease,
            created.world.revision,
            &WindowPatch {
                always_on_top: Some(false),
                ..WindowPatch::default()
            },
            1,
        )
        .unwrap();
    assert!(!lowered.window.always_on_top);

    let raised = engine
        .configure(
            provider,
            created.world.id,
            &lease,
            lowered.revision,
            &WindowPatch {
                always_on_top: Some(true),
                ..WindowPatch::default()
            },
            2,
        )
        .unwrap();
    assert!(raised.window.always_on_top);
}

#[test]
fn provider_size_and_human_position_controls_are_independent() {
    let (mut engine, provider, _, created) = setup();
    let lease = created.lease.unwrap();
    let initial = engine.read(provider, created.world.id).unwrap();
    let controlled = engine
        .configure(
            provider,
            created.world.id,
            &lease,
            initial.revision,
            &WindowPatch {
                geometry_control: Some(GeometryControl::Provider),
                position_control: Some(GeometryControl::Human),
                resizable: Some(false),
                width: Some(480.0),
                height: Some(320.0),
                ..WindowPatch::default()
            },
            1,
        )
        .unwrap();
    assert_eq!(
        controlled.window.geometry_control,
        GeometryControl::Provider
    );
    assert_eq!(
        controlled.window.effective_position_control(),
        GeometryControl::Human
    );
    assert!(!controlled.window.resizable);

    let resized_by_provider = engine
        .configure(
            provider,
            created.world.id,
            &lease,
            controlled.revision,
            &WindowPatch {
                width: Some(500.0),
                height: Some(340.0),
                ..WindowPatch::default()
            },
            2,
        )
        .unwrap();
    assert_eq!(resized_by_provider.window.width, 500.0);
    assert_eq!(resized_by_provider.window.height, 340.0);
    assert_eq!(
        engine
            .configure(
                provider,
                created.world.id,
                &lease,
                resized_by_provider.revision,
                &WindowPatch {
                    position: Some(Position { x: 12, y: 24 }),
                    ..WindowPatch::default()
                },
                3,
            )
            .unwrap_err()
            .code,
        "HUMAN_GEOMETRY"
    );

    assert!(engine.native_report(
        created.world.id,
        resized_by_provider.window_revision,
        NativeReport {
            state: "applied".into(),
            applied_window_revision: Some(resized_by_provider.window_revision),
            error: None,
        },
    ));
    assert!(engine.observe_geometry(created.world.id, Position { x: 80, y: 96 }, 700.0, 600.0,));
    let moved = engine.read(provider, created.world.id).unwrap();
    assert_eq!(moved.window.position, Some(Position { x: 80, y: 96 }));
    assert_eq!(moved.window.width, 500.0);
    assert_eq!(moved.window.height, 340.0);
}

#[test]
fn provider_can_anchor_only_after_taking_geometry_control_and_operator_rescue_clears_it() {
    let (mut engine, provider, _, created) = setup();
    let lease = created.lease.unwrap();
    let initial = engine.read(provider, created.world.id).unwrap();
    let anchor = WorkAreaAnchor {
        corner: WorkAreaCorner::BottomRight,
        margin_x: 16.0,
        margin_y: 20.0,
    };

    let rejected = engine
        .configure(
            provider,
            created.world.id,
            &lease,
            initial.revision,
            &WindowPatch {
                anchor: Some(anchor),
                ..WindowPatch::default()
            },
            1,
        )
        .unwrap_err();
    assert_eq!(rejected.code, "HUMAN_GEOMETRY");

    let controlled = engine
        .configure(
            provider,
            created.world.id,
            &lease,
            initial.revision,
            &WindowPatch {
                geometry_control: Some(GeometryControl::Provider),
                anchor: Some(anchor),
                ..WindowPatch::default()
            },
            2,
        )
        .unwrap();
    assert_eq!(controlled.window.anchor, Some(anchor));
    assert_eq!(
        controlled.window.geometry_control,
        GeometryControl::Provider
    );

    let operator = engine.register("local.operator".into(), true).unwrap();
    let rescued = engine.rescue(operator, created.world.id).unwrap();
    assert_eq!(rescued.window.anchor, None);
    assert_eq!(rescued.window.geometry_control, GeometryControl::Human);
    assert!(rescued.write_blocked);
}

#[test]
fn work_area_anchor_rejects_unbounded_and_non_finite_margins() {
    let spec = WindowSpec {
        anchor: Some(WorkAreaAnchor {
            corner: WorkAreaCorner::TopLeft,
            margin_x: f64::INFINITY,
            margin_y: 0.0,
        }),
        ..WindowSpec::default()
    };
    assert_eq!(spec.validate().unwrap_err().code, "INVALID_WINDOW");
}
#[test]
fn operator_rescue_fences_writer_and_disables_clickthrough() {
    let (mut e, a, _, c) = setup();
    let op = e.register("host".into(), true).unwrap();
    let lease = c.lease.unwrap();
    let current = e.read(a, c.world.id).unwrap();
    e.configure(
        a,
        c.world.id,
        &lease,
        current.revision,
        &WindowPatch {
            title_bar_visible: Some(false),
            text_selectable: Some(false),
            click_through: Some(true),
            ..WindowPatch::default()
        },
        2,
    )
    .unwrap();
    let s = e.rescue(op, c.world.id).unwrap();
    assert!(!s.window.click_through);
    assert!(s.window.visible);
    assert!(s.window.title_bar_visible);
    assert!(s.window.text_selectable);
    assert_eq!(
        e.renew(a, c.world.id, &lease, 3).unwrap_err().code,
        "STALE_LEASE"
    );
    assert_eq!(e.rescue(a, c.world.id).unwrap_err().code, "FORBIDDEN");
}
#[test]
fn revision_conflict_does_not_commit() {
    let (mut e, a, _, c) = setup();
    assert_eq!(
        e.set_data(a, c.world.id, &c.lease.unwrap(), 0, json!({"bad":true}), 1)
            .unwrap_err()
            .code,
        "REVISION_CONFLICT"
    );
    assert!(e.worlds[&c.world.id].scene.data.is_null());
}
#[test]
fn action_is_routed_and_acknowledged_not_optimistically_completed() {
    let (mut e, a, _, c) = setup();
    let key = c.lease.unwrap();
    let scene = Scene {
        root: Node::new(
            "btn",
            Kind::Button,
            json!({"label":"暂停","action":"pause"}),
            vec![],
        ),
        data: json!({}),
        theme: None,
    };
    e.replace_scene(a, c.world.id, &key, c.world.revision, scene, 1)
        .unwrap();
    let revision = e.worlds[&c.world.id].revision;
    let (sid, event) = e
        .interact(c.world.id, "btn", json!(null), false, revision, 2)
        .unwrap();
    assert_eq!(sid, a);
    assert_eq!(e.worlds[&c.world.id].actions[0].status, "pending");
    e.acknowledge(
        a,
        c.world.id,
        &key,
        ActionAcknowledgement {
            event_id: event.id,
            ok: true,
            message: None,
        },
        3,
    )
    .unwrap();
    assert_eq!(e.worlds[&c.world.id].actions[0].status, "ok");
}
#[test]
fn node_action_must_be_static_and_leaf_cannot_have_children() {
    assert!(Scene {
        root: Node::new(
            "b",
            Kind::Button,
            json!({"action":{"$path":"/evil"}}),
            vec![]
        ),
        data: json!({}),
        theme: None,
    }
    .validate()
    .is_err());
    assert!(Scene {
        root: Node::new(
            "b",
            Kind::Button,
            json!({"action":"click","context_action":{"$path":"/dynamic"}}),
            vec![]
        ),
        data: json!({}),
        theme: None,
    }
    .validate()
    .is_err());
    assert!(Scene {
        root: Node::new(
            "b",
            Kind::Text,
            json!({}),
            vec![Node::new("c", Kind::Text, json!({}), vec![])]
        ),
        data: json!({}),
        theme: None,
    }
    .validate()
    .is_err());
}

#[test]
fn registered_context_action_is_selected_only_for_context_gesture() {
    let (mut e, a, _, c) = setup();
    let key = c.lease.unwrap();
    let scene = Scene {
        root: Node::new(
            "btn",
            Kind::Button,
            json!({"label":"操作","action":"primary","context_action":"context"}),
            vec![],
        ),
        data: json!({}),
        theme: None,
    };
    e.replace_scene(a, c.world.id, &key, c.world.revision, scene, 1)
        .unwrap();
    let revision = e.worlds[&c.world.id].revision;

    let (_, primary) = e
        .interact(c.world.id, "btn", json!(null), false, revision, 2)
        .unwrap();
    let (_, context) = e
        .interact(c.world.id, "btn", json!(null), true, revision, 3)
        .unwrap();

    assert_eq!(primary.action, "primary");
    assert_eq!(context.action, "context");
}

#[test]
fn unregistered_context_action_is_rejected() {
    let (mut e, a, _, c) = setup();
    let key = c.lease.unwrap();
    let scene = Scene {
        root: Node::new(
            "btn",
            Kind::Button,
            json!({"label":"操作","action":"primary"}),
            vec![],
        ),
        data: json!({}),
        theme: None,
    };
    e.replace_scene(a, c.world.id, &key, c.world.revision, scene, 1)
        .unwrap();
    let revision = e.worlds[&c.world.id].revision;

    assert_eq!(
        e.interact(c.world.id, "btn", json!(null), true, revision, 2)
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
}

#[test]
fn default_window_is_human_resizable() {
    let window = WindowSpec::default();

    assert_eq!(window.geometry_control, GeometryControl::Human);
    assert!(window.resizable);
    assert!(window.title_bar_visible);
    assert!(window.background_drag_enabled);
    assert!(window.text_selectable);
    assert!(window.visible);
    assert!(!window.click_through);
    assert_eq!(window.surface_opacity, 0.8);

    let partial: WindowSpec = serde_json::from_value(json!({"title":"Partial window"})).unwrap();
    assert!(partial.text_selectable);
    assert!(partial.background_drag_enabled);
}

#[test]
fn provider_can_configure_background_drag_without_changing_lease_or_geometry_owner() {
    let (mut e, provider, _, created) = setup();
    let lease = created.lease.unwrap();
    let initial = e.read(provider, created.world.id).unwrap();
    assert!(initial.window.background_drag_enabled);
    assert_eq!(initial.window.geometry_control, GeometryControl::Human);

    let locked = e
        .configure(
            provider,
            created.world.id,
            &lease,
            initial.revision,
            &WindowPatch {
                background_drag_enabled: Some(false),
                ..WindowPatch::default()
            },
            2,
        )
        .unwrap();
    assert!(!locked.window.background_drag_enabled);
    assert_eq!(locked.window.geometry_control, GeometryControl::Human);
    assert_eq!(locked.epoch, lease.epoch);

    let restored = e
        .configure(
            provider,
            created.world.id,
            &lease,
            locked.revision,
            &WindowPatch {
                background_drag_enabled: Some(true),
                ..WindowPatch::default()
            },
            3,
        )
        .unwrap();
    assert!(restored.window.background_drag_enabled);
    assert_eq!(restored.epoch, lease.epoch);
}

#[test]
fn provider_can_configure_titlebar_and_clickthrough() {
    let (mut e, provider, _, created) = setup();
    let lease = created.lease.unwrap();
    let initial = e.read(provider, created.world.id).unwrap();
    assert!(initial.window.title_bar_visible);
    assert!(!initial.window.click_through);

    let updated = e
        .configure(
            provider,
            created.world.id,
            &lease,
            initial.revision,
            &WindowPatch {
                title_bar_visible: Some(false),
                click_through: Some(true),
                ..WindowPatch::default()
            },
            2,
        )
        .unwrap();
    assert!(!updated.window.title_bar_visible);
    assert!(updated.window.click_through);
}

#[test]
fn provider_can_read_and_configure_default_text_selection() {
    let (mut e, provider, _, created) = setup();
    let lease = created.lease.unwrap();
    let initial = e.read(provider, created.world.id).unwrap();
    assert!(initial.window.text_selectable);

    let updated = e
        .configure(
            provider,
            created.world.id,
            &lease,
            initial.revision,
            &WindowPatch {
                text_selectable: Some(false),
                ..WindowPatch::default()
            },
            2,
        )
        .unwrap();
    assert!(!updated.window.text_selectable);

    let restored = e
        .configure(
            provider,
            created.world.id,
            &lease,
            updated.revision,
            &WindowPatch {
                text_selectable: Some(true),
                ..WindowPatch::default()
            },
            3,
        )
        .unwrap();
    assert!(restored.window.text_selectable);
}

#[test]
fn provider_can_read_and_configure_surface_opacity() {
    let (mut e, provider, _, created) = setup();
    let lease = created.lease.unwrap();
    let initial = e.read(provider, created.world.id).unwrap();
    assert_eq!(initial.window.surface_opacity, 0.8);

    let updated = e
        .configure(
            provider,
            created.world.id,
            &lease,
            initial.revision,
            &WindowPatch {
                surface_opacity: Some(0.5),
                ..WindowPatch::default()
            },
            2,
        )
        .unwrap();
    assert_eq!(updated.window.surface_opacity, 0.5);
}

#[test]
fn hidden_window_stays_observable_and_writer_can_show_it_again() {
    let (mut e, provider, _, created) = setup();
    let lease = created.lease.unwrap();
    let operator = e.register("host.manager".into(), true).unwrap();

    e.operator_visibility(operator, created.world.id, false)
        .unwrap();
    let hidden = e.read(provider, created.world.id).unwrap();
    assert!(!hidden.window.visible);
    e.renew(provider, created.world.id, &lease, 2).unwrap();

    let shown = e
        .configure(
            provider,
            created.world.id,
            &lease,
            hidden.revision,
            &WindowPatch {
                visible: Some(true),
                ..WindowPatch::default()
            },
            3,
        )
        .unwrap();
    assert!(shown.window.visible);
}
#[test]
fn system_world_cannot_be_claimed_by_external_provider() {
    let mut e = Engine::default();
    let h = e.register("host".into(), true).unwrap();
    let p = e.register("external".into(), false).unwrap();
    let c = e
        .create(
            h,
            WindowSpec::default(),
            JoinPolicy::OpenAuthenticated,
            true,
            true,
            0,
        )
        .unwrap();
    assert_eq!(
        e.join(p, c.world.id, Some(&c.join_key), JoinMode::Read, 1)
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
}
#[test]
fn operator_hold_prevents_immediate_reacquire() {
    let (mut e, a, _, c) = setup();
    let op = e.register("host".into(), true).unwrap();
    e.rescue(op, c.world.id).unwrap();
    assert_eq!(
        e.join(a, c.world.id, None, JoinMode::Write, 1)
            .unwrap_err()
            .code,
        "OPERATOR_HOLD"
    );
    e.operator_release_hold(op, c.world.id).unwrap();
    assert!(e.join(a, c.world.id, None, JoinMode::Write, 2).is_ok());
}
#[test]
fn stale_rendered_action_is_not_reinterpreted() {
    let (mut e, a, _, c) = setup();
    let key = c.lease.unwrap();
    let scene = Scene {
        root: Node::new(
            "btn",
            Kind::Button,
            json!({"label":"动作","action":"safe"}),
            vec![],
        ),
        data: json!({}),
        theme: None,
    };
    let before = e
        .replace_scene(a, c.world.id, &key, c.world.revision, scene, 1)
        .unwrap();
    e.set_data(a, c.world.id, &key, before.revision, json!({"new":true}), 2)
        .unwrap();
    assert_eq!(
        e.interact(c.world.id, "btn", json!(null), false, before.revision, 3,)
            .unwrap_err()
            .code,
        "REVISION_CONFLICT"
    );
}

#[test]
fn textarea_and_shortcut_actions_are_explicit_scene_capabilities() {
    let scene = Scene {
        root: Node::new(
            "root",
            Kind::Stack,
            json!({}),
            vec![
                Node::new(
                    "notes",
                    Kind::TextArea,
                    json!({"label":"备注","value":"第一行\n第二行","action":"notes.save","submit_label":"保存备注"}),
                    vec![],
                ),
                Node::new(
                    "cancel",
                    Kind::Button,
                    json!({"label":"取消","action":"cancel.button","shortcut":"escape","shortcut_action":"cancel.escape"}),
                    vec![],
                ),
            ],
        ),
        data: json!({}),
        theme: None,
    };
    assert!(scene.validate().is_ok());
    let encoded = serde_json::to_value(&scene).unwrap();
    assert_eq!(encoded["root"]["children"][0]["kind"], "textarea");
}

#[test]
fn click_and_escape_use_distinct_registered_actions() {
    let (mut e, provider, _, created) = setup();
    let lease = created.lease.unwrap();
    let scene = Scene {
        root: Node::new(
            "cancel",
            Kind::Button,
            json!({"label":"取消","action":"cancel.button","shortcut":"escape","shortcut_action":"cancel.escape"}),
            vec![],
        ),
        data: json!({}),
        theme: None,
    };
    e.replace_scene(
        provider,
        created.world.id,
        &lease,
        created.world.revision,
        scene,
        1,
    )
    .unwrap();
    let revision = e.worlds[&created.world.id].revision;
    let (_, click) = e
        .interact_with_source(
            created.world.id,
            "cancel",
            json!(null),
            InteractionSource::Click,
            revision,
            2,
        )
        .unwrap();
    let (_, escape) = e
        .interact_with_source(
            created.world.id,
            "cancel",
            json!(null),
            InteractionSource::Escape,
            revision,
            3,
        )
        .unwrap();
    assert_eq!(click.action, "cancel.button");
    assert_eq!(escape.action, "cancel.escape");
}

#[test]
fn ctrl_enter_textarea_routes_draft_to_a_distinct_submit_action() {
    let (mut e, provider, _, created) = setup();
    let lease = created.lease.unwrap();
    let scene = Scene {
        root: Node::new(
            "notes",
            Kind::TextArea,
            json!({"label":"备注","action":"notes.save","shortcut":"ctrl_enter","shortcut_action":"submit"}),
            vec![],
        ),
        data: json!({}),
        theme: None,
    };
    e.replace_scene(
        provider,
        created.world.id,
        &lease,
        created.world.revision,
        scene,
        1,
    )
    .unwrap();
    let revision = e.worlds[&created.world.id].revision;
    let (_, event) = e
        .interact_with_source(
            created.world.id,
            "notes",
            json!("note draft"),
            InteractionSource::ControlEnter,
            revision,
            2,
        )
        .unwrap();
    assert_eq!(event.action, "submit");
    assert_eq!(event.value, "note draft");
}

#[test]
fn option_button_group_has_one_tab_stop_and_consistent_mode() {
    let option = |id: &str, pressed: bool, mode: &str| {
        Node::new(
            id,
            Kind::Button,
            json!({"label":id,"action":"select","selection_group":"q0","selection_mode":mode,"pressed":pressed}),
            vec![],
        )
    };
    let scene = |children| Scene {
        root: Node::new("root", Kind::Stack, json!({}), children),
        data: json!({}),
        theme: None,
    };
    assert!(scene(vec![
        option("a", true, "single"),
        option("b", false, "single")
    ])
    .validate()
    .is_ok());
    assert!(scene(vec![
        option("a", true, "single"),
        option("b", true, "single")
    ])
    .validate()
    .is_err());
    assert!(scene(vec![
        option("a", true, "single"),
        option("b", false, "multiple")
    ])
    .validate()
    .is_err());
}

#[test]
fn escape_shortcut_is_unique_and_whitelisted() {
    let button = |id: &str, shortcut: &str| {
        Node::new(
            id,
            Kind::Button,
            json!({"label":"取消","action":"cancel.button","shortcut":shortcut,"shortcut_action":"cancel.escape"}),
            vec![],
        )
    };
    let scene = |children| Scene {
        root: Node::new("root", Kind::Stack, json!({}), children),
        data: json!({}),
        theme: None,
    };
    assert_eq!(
        scene(vec![button("a", "escape"), button("b", "escape")])
            .validate()
            .unwrap_err()
            .code,
        "INVALID_SCENE"
    );
    assert_eq!(
        scene(vec![button("a", "ctrl+q")])
            .validate()
            .unwrap_err()
            .code,
        "INVALID_SCENE"
    );
}

struct ScopedWorldSetup {
    engine: Engine,
    world_id: uuid::Uuid,
    owner: uuid::Uuid,
    writer_a: uuid::Uuid,
    writer_b: uuid::Uuid,
    observer: uuid::Uuid,
    operator: uuid::Uuid,
    world_join_key: String,
    legacy_lease: LeaseKey,
    authority_lease: LeaseKey,
    scope_a: ScopeGrant,
    scope_b: ScopeGrant,
}

fn setup_scoped_world() -> ScopedWorldSetup {
    let mut engine = Engine::default();
    let owner = engine
        .register_with_protocol(
            "scope.owner".into(),
            false,
            ProtocolVersion::ComponentLeasesPreview01,
        )
        .unwrap();
    let writer_a = engine
        .register_with_protocol(
            "scope.focus".into(),
            false,
            ProtocolVersion::ComponentLeasesPreview01,
        )
        .unwrap();
    let writer_b = engine
        .register_with_protocol(
            "scope.tasks".into(),
            false,
            ProtocolVersion::ComponentLeasesPreview01,
        )
        .unwrap();
    let observer = engine
        .register_with_protocol(
            "scope.reader".into(),
            false,
            ProtocolVersion::ComponentLeasesPreview01,
        )
        .unwrap();
    let operator = engine.register("scope.operator".into(), true).unwrap();
    let created = engine
        .create(
            owner,
            WindowSpec::default(),
            JoinPolicy::Invite,
            true,
            false,
            0,
        )
        .unwrap();
    let world_id = created.world.id;
    let world_join_key = created.join_key;
    let legacy_lease = created.lease.unwrap();
    let scene = Scene {
        root: Node::new(
            "root",
            Kind::Stack,
            json!({}),
            vec![
                Node::new(
                    "focus-panel",
                    Kind::Stack,
                    json!({}),
                    vec![Node::new(
                        "focus-value",
                        Kind::Text,
                        json!({"text":{"$path":"/focus/value"}}),
                        vec![],
                    )],
                ),
                Node::new(
                    "tasks-panel",
                    Kind::Stack,
                    json!({}),
                    vec![Node::new(
                        "tasks-value",
                        Kind::Text,
                        json!({"text":{"$path":"/tasks/value"}}),
                        vec![],
                    )],
                ),
            ],
        ),
        data: json!({
            "focus":{"value":"focus-private"},
            "tasks":{"value":"tasks-private"},
            "public":"layout-metadata"
        }),
        theme: None,
    };
    let updated = engine
        .replace_scene(
            owner,
            world_id,
            &legacy_lease,
            created.world.revision,
            scene,
            1,
        )
        .unwrap();
    let partition = engine
        .partition_scopes(
            owner,
            world_id,
            &legacy_lease,
            updated.revision,
            &[
                ScopeDefinition {
                    root_node_id: "focus-panel".into(),
                    data_namespace: "focus".into(),
                },
                ScopeDefinition {
                    root_node_id: "tasks-panel".into(),
                    data_namespace: "tasks".into(),
                },
            ],
            2,
        )
        .unwrap();
    let scope_a = partition
        .scopes
        .iter()
        .find(|scope| scope.root_node_id == "focus-panel")
        .unwrap()
        .clone();
    let scope_b = partition
        .scopes
        .iter()
        .find(|scope| scope.root_node_id == "tasks-panel")
        .unwrap()
        .clone();
    ScopedWorldSetup {
        engine,
        world_id,
        owner,
        writer_a,
        writer_b,
        observer,
        operator,
        world_join_key,
        legacy_lease,
        authority_lease: partition.authority_lease,
        scope_a,
        scope_b,
    }
}

#[test]
fn disjoint_component_scopes_use_independent_revisions_and_data_namespaces() {
    let mut state = setup_scoped_world();
    let joined_a = state
        .engine
        .join_scope(
            state.writer_a,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
            3,
        )
        .unwrap();
    let joined_b = state
        .engine
        .join_scope(
            state.writer_b,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_b, JoinMode::Write),
            3,
        )
        .unwrap();
    let lease_a = joined_a.lease.unwrap();
    let lease_b = joined_b.lease.unwrap();
    let props = |text: &str| json!({"text":text}).as_object().unwrap().clone();

    let updated_a = state
        .engine
        .patch_scope(
            state.writer_a,
            state.world_id,
            &lease_a,
            joined_a.snapshot.revision,
            &[SceneOp::Props {
                node_id: "focus-value".into(),
                props: props("focus updated"),
            }],
            4,
        )
        .unwrap();
    let updated_b = state
        .engine
        .patch_scope(
            state.writer_b,
            state.world_id,
            &lease_b,
            joined_b.snapshot.revision,
            &[SceneOp::Props {
                node_id: "tasks-value".into(),
                props: props("tasks updated"),
            }],
            4,
        )
        .unwrap();
    assert_eq!(updated_a.revision, joined_a.snapshot.revision + 1);
    assert_eq!(updated_b.revision, joined_b.snapshot.revision + 1);

    let data_a = state
        .engine
        .replace_scope_data(
            state.writer_a,
            state.world_id,
            &lease_a,
            updated_a.revision,
            json!({"value":"focus-updated"}),
            5,
        )
        .unwrap();
    let data_b = state
        .engine
        .replace_scope_data(
            state.writer_b,
            state.world_id,
            &lease_b,
            updated_b.revision,
            json!({"value":"tasks-updated"}),
            5,
        )
        .unwrap();
    assert_eq!(data_a.data, json!({"value":"focus-updated"}));
    assert_eq!(data_b.data, json!({"value":"tasks-updated"}));

    let full = state.engine.read(state.operator, state.world_id).unwrap();
    assert_eq!(full.scene.data["focus"]["value"], "focus-updated");
    assert_eq!(full.scene.data["tasks"]["value"], "tasks-updated");
    assert_eq!(
        full.scene.root.find("focus-value").unwrap().props["text"],
        "focus updated"
    );
    assert_eq!(
        full.scene.root.find("tasks-value").unwrap().props["text"],
        "tasks updated"
    );
}

#[test]
fn component_scope_reads_are_filtered_and_readers_get_no_write_alias() {
    let mut state = setup_scoped_world();
    let joined = state
        .engine
        .join_scope(
            state.observer,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Read),
            3,
        )
        .unwrap();
    assert!(joined.lease.is_none());
    assert_eq!(joined.snapshot.root.id, "focus-panel");
    assert_eq!(joined.snapshot.data, json!({"value":"focus-private"}));
    let projection = serde_json::to_string(&joined.snapshot).unwrap();
    assert!(!projection.contains("tasks-panel"));
    assert!(!projection.contains("tasks-private"));
    assert_eq!(
        state
            .engine
            .read(state.observer, state.world_id)
            .unwrap_err()
            .code,
        "SCOPE_REQUIRED"
    );
    assert_eq!(
        state
            .engine
            .read_scope(
                state.observer,
                state.world_id,
                state.scope_b.scope_id,
                state.scope_b.generation,
            )
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
    let fake_lease = ScopedLeaseKey {
        scope_id: state.scope_a.scope_id,
        lease_id: uuid::Uuid::new_v4(),
        epoch: 1,
        generation: state.scope_a.generation,
    };
    assert_eq!(
        state
            .engine
            .patch_scope(
                state.observer,
                state.world_id,
                &fake_lease,
                joined.snapshot.revision,
                &[SceneOp::Props {
                    node_id: "focus-value".into(),
                    props: json!({"text":"unauthorized"}).as_object().unwrap().clone(),
                }],
                4,
            )
            .unwrap_err()
            .code,
        "STALE_SCOPE_LEASE"
    );

    let authority_view = state.engine.read(state.owner, state.world_id).unwrap();
    assert!(authority_view.scene.data.get("focus").is_none());
    assert!(authority_view.scene.data.get("tasks").is_none());
    assert!(authority_view
        .scene
        .root
        .find("focus-panel")
        .unwrap()
        .children
        .is_empty());
}

#[test]
fn scoped_world_rejects_legacy_writers_and_fences_scope_disconnect() {
    let mut state = setup_scoped_world();
    assert_eq!(
        state
            .engine
            .patch_scene(state.owner, state.world_id, &state.legacy_lease, 1, &[], 3,)
            .unwrap_err()
            .code,
        "SCOPE_MODE"
    );
    let stable = state
        .engine
        .register("legacy.client".into(), false)
        .unwrap();
    assert_eq!(
        state
            .engine
            .join(
                stable,
                state.world_id,
                Some(&state.world_join_key),
                JoinMode::Write,
                3,
            )
            .unwrap_err()
            .code,
        "SCOPE_REQUIRED"
    );
    let authority_view = state.engine.read(state.owner, state.world_id).unwrap();
    assert!(authority_view.scene.data.get("focus").is_none());
    assert!(authority_view.scene.data.get("tasks").is_none());
    let unsupported = state
        .engine
        .register("legacy.partition".into(), false)
        .unwrap();
    assert_eq!(
        state
            .engine
            .partition_scopes(unsupported, state.world_id, &state.legacy_lease, 1, &[], 3,)
            .unwrap_err()
            .code,
        "PROTOCOL_MISMATCH"
    );

    let joined = state
        .engine
        .join_scope(
            state.writer_a,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
            4,
        )
        .unwrap();
    let old_key = joined.lease.unwrap();
    state.engine.disconnect(state.writer_a);
    assert_eq!(
        state
            .engine
            .patch_scope(
                state.writer_a,
                state.world_id,
                &old_key,
                joined.snapshot.revision,
                &[],
                5,
            )
            .unwrap_err()
            .code,
        "SESSION_GONE"
    );
    let replacement = state
        .engine
        .register_with_protocol(
            "scope.focus.reconnected".into(),
            false,
            ProtocolVersion::ComponentLeasesPreview01,
        )
        .unwrap();
    let new_join = state
        .engine
        .join_scope(
            replacement,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
            6,
        )
        .unwrap();
    assert_ne!(old_key, new_join.lease.unwrap());
}

#[test]
fn scoped_writer_cannot_target_a_sibling_or_change_scope_structure() {
    let mut state = setup_scoped_world();
    let joined = state
        .engine
        .join_scope(
            state.writer_a,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
            3,
        )
        .unwrap();
    let lease = joined.lease.unwrap();
    let expected = joined.snapshot.revision;
    let props = json!({"text":"unauthorized"}).as_object().unwrap().clone();
    assert_eq!(
        state
            .engine
            .patch_scope(
                state.writer_a,
                state.world_id,
                &lease,
                expected,
                &[SceneOp::Props {
                    node_id: "tasks-value".into(),
                    props: props.clone(),
                }],
                4,
            )
            .unwrap_err()
            .code,
        "SCOPE_FORBIDDEN"
    );
    assert_eq!(
        state
            .engine
            .patch_scope(
                state.writer_a,
                state.world_id,
                &lease,
                expected,
                &[SceneOp::Move {
                    node_id: "focus-value".into(),
                    parent: "tasks-panel".into(),
                    index: 0,
                }],
                4,
            )
            .unwrap_err()
            .code,
        "SCOPE_FORBIDDEN"
    );
    assert_eq!(
        state
            .engine
            .read_scope(
                state.writer_a,
                state.world_id,
                state.scope_a.scope_id,
                state.scope_a.generation,
            )
            .unwrap()
            .revision,
        expected,
        "rejected scope operations must be atomic"
    );
}

#[test]
fn scope_partition_rejects_overlap_without_revoking_legacy_lease() {
    let mut engine = Engine::default();
    let owner = engine
        .register_with_protocol(
            "scope.partition.owner".into(),
            false,
            ProtocolVersion::ComponentLeasesPreview01,
        )
        .unwrap();
    let created = engine
        .create(
            owner,
            WindowSpec::default(),
            JoinPolicy::Invite,
            true,
            false,
            0,
        )
        .unwrap();
    let lease = created.lease.unwrap();
    let scene = Scene {
        root: Node::new(
            "root",
            Kind::Stack,
            json!({}),
            vec![Node::new(
                "panel",
                Kind::Stack,
                json!({}),
                vec![Node::new(
                    "header",
                    Kind::Text,
                    json!({"text":"Header"}),
                    vec![],
                )],
            )],
        ),
        data: json!({"panel-data":{},"header-data":{}}),
        theme: None,
    };
    let updated = engine
        .replace_scene(
            owner,
            created.world.id,
            &lease,
            created.world.revision,
            scene,
            1,
        )
        .unwrap();
    assert_eq!(
        engine
            .partition_scopes(
                owner,
                created.world.id,
                &lease,
                updated.revision,
                &[
                    ScopeDefinition {
                        root_node_id: "panel".into(),
                        data_namespace: "panel-data".into(),
                    },
                    ScopeDefinition {
                        root_node_id: "header".into(),
                        data_namespace: "header-data".into(),
                    },
                ],
                2,
            )
            .unwrap_err()
            .code,
        "SCOPE_OVERLAP"
    );
    assert_eq!(
        engine.worlds[&created.world.id].ownership_mode,
        OwnershipMode::ExclusiveWorld
    );
    assert!(engine.worlds[&created.world.id].writer.is_some());
    assert!(engine
        .set_data(
            owner,
            created.world.id,
            &lease,
            updated.revision,
            json!({"still":"exclusive"}),
            3,
        )
        .is_ok());
}

#[test]
fn scoped_writer_can_change_structure_inside_its_owned_subtree() {
    let mut state = setup_scoped_world();
    let joined = state
        .engine
        .join_scope(
            state.writer_a,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
            3,
        )
        .unwrap();
    let lease = joined.lease.unwrap();

    let inserted = state
        .engine
        .patch_scope(
            state.writer_a,
            state.world_id,
            &lease,
            joined.snapshot.revision,
            &[SceneOp::Insert {
                parent: "focus-panel".into(),
                index: 1,
                node: Node::new(
                    "focus-extra",
                    Kind::Text,
                    json!({"text":{"$path":"/value"}}),
                    vec![],
                ),
            }],
            4,
        )
        .unwrap();
    assert_eq!(
        inserted.root.find("focus-extra").unwrap().props["text"],
        json!({"$path":"/value"})
    );
    assert_eq!(
        state.engine.worlds[&state.world_id]
            .scene
            .root
            .find("focus-extra")
            .unwrap()
            .props["text"],
        json!({"$path":"/focus/value"})
    );

    let replaced = state
        .engine
        .patch_scope(
            state.writer_a,
            state.world_id,
            &lease,
            inserted.revision,
            &[SceneOp::Replace {
                node_id: "focus-extra".into(),
                node: Node::new(
                    "focus-replaced",
                    Kind::Text,
                    json!({"text":"synthetic replacement"}),
                    vec![],
                ),
            }],
            5,
        )
        .unwrap();
    assert!(replaced.root.find("focus-extra").is_none());
    assert!(replaced.root.find("focus-replaced").is_some());

    let moved = state
        .engine
        .patch_scope(
            state.writer_a,
            state.world_id,
            &lease,
            replaced.revision,
            &[SceneOp::Move {
                node_id: "focus-replaced".into(),
                parent: "focus-panel".into(),
                index: 0,
            }],
            6,
        )
        .unwrap();
    assert_eq!(moved.root.children[0].id, "focus-replaced");

    let removed = state
        .engine
        .patch_scope(
            state.writer_a,
            state.world_id,
            &lease,
            moved.revision,
            &[SceneOp::Remove {
                node_id: "focus-replaced".into(),
            }],
            7,
        )
        .unwrap();
    assert!(removed.root.find("focus-replaced").is_none());
    assert!(removed.root.find("tasks-panel").is_none());
}

#[test]
fn cross_scope_move_fails_the_whole_scope_patch_without_revision_change() {
    let mut state = setup_scoped_world();
    let joined = state
        .engine
        .join_scope(
            state.writer_a,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
            3,
        )
        .unwrap();
    let lease = joined.lease.unwrap();
    let before_scene = serde_json::to_value(&state.engine.worlds[&state.world_id].scene).unwrap();
    let before_revision =
        state.engine.worlds[&state.world_id].scopes[&state.scope_a.scope_id].revision;

    let error = state
        .engine
        .patch_scope(
            state.writer_a,
            state.world_id,
            &lease,
            joined.snapshot.revision,
            &[
                SceneOp::Props {
                    node_id: "focus-value".into(),
                    props: json!({"text":"must not commit"})
                        .as_object()
                        .unwrap()
                        .clone(),
                },
                SceneOp::Move {
                    node_id: "tasks-value".into(),
                    parent: "focus-panel".into(),
                    index: 1,
                },
            ],
            4,
        )
        .unwrap_err();

    assert_eq!(error.code, "SCOPE_FORBIDDEN");
    assert_eq!(
        serde_json::to_value(&state.engine.worlds[&state.world_id].scene).unwrap(),
        before_scene
    );
    assert_eq!(
        state.engine.worlds[&state.world_id].scopes[&state.scope_a.scope_id].revision,
        before_revision
    );
}

#[test]
fn parent_structure_patch_removes_child_scope_and_fences_its_old_lease() {
    let mut state = setup_scoped_world();
    let focus = state
        .engine
        .join_scope(
            state.writer_a,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
            3,
        )
        .unwrap();
    let tasks = state
        .engine
        .join_scope(
            state.writer_b,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_b, JoinMode::Write),
            3,
        )
        .unwrap();
    let focus_lease = focus.lease.unwrap();
    let tasks_lease = tasks.lease.unwrap();
    let observer = state
        .engine
        .join_scope(
            state.observer,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Read),
            3,
        )
        .unwrap();

    let before_scene = serde_json::to_value(&state.engine.worlds[&state.world_id].scene).unwrap();
    let before_world_revision = state.engine.worlds[&state.world_id].revision;
    assert_eq!(
        state
            .engine
            .patch_scope_structure(
                state.owner,
                state.world_id,
                &state.authority_lease,
                before_world_revision,
                &[SceneOp::Props {
                    node_id: "root".into(),
                    props: json!({"gap":{"$path":"/focus/value"}})
                        .as_object()
                        .unwrap()
                        .clone(),
                }],
                4,
            )
            .unwrap_err()
            .code,
        "SCOPE_DATA_FORBIDDEN"
    );
    assert_eq!(
        serde_json::to_value(&state.engine.worlds[&state.world_id].scene).unwrap(),
        before_scene
    );
    assert_eq!(
        state
            .engine
            .patch_scope_structure(
                state.owner,
                state.world_id,
                &state.authority_lease,
                before_world_revision,
                &[SceneOp::Insert {
                    parent: "focus-panel".into(),
                    index: 1,
                    node: Node::new(
                        "parent-insert",
                        Kind::Text,
                        json!({"text":"wrong owner"}),
                        vec![]
                    ),
                }],
                4,
            )
            .unwrap_err()
            .code,
        "SCOPE_FORBIDDEN"
    );
    assert_eq!(
        serde_json::to_value(&state.engine.worlds[&state.world_id].scene).unwrap(),
        before_scene
    );
    assert!(state
        .engine
        .patch_scope_structure(
            state.owner,
            state.world_id,
            &state.authority_lease,
            before_world_revision,
            &[
                SceneOp::Remove {
                    node_id: "focus-panel".into(),
                },
                SceneOp::Move {
                    node_id: "missing-node".into(),
                    parent: "root".into(),
                    index: 0,
                },
            ],
            4,
        )
        .is_err());
    assert_eq!(
        serde_json::to_value(&state.engine.worlds[&state.world_id].scene).unwrap(),
        before_scene,
        "a failed root transaction must not remove the scope"
    );
    assert!(state.engine.worlds[&state.world_id]
        .scopes
        .contains_key(&state.scope_a.scope_id));

    let result = state
        .engine
        .patch_scope_structure(
            state.owner,
            state.world_id,
            &state.authority_lease,
            before_world_revision,
            &[SceneOp::Remove {
                node_id: "focus-panel".into(),
            }],
            5,
        )
        .unwrap();
    assert!(result.snapshot.scene.root.find("focus-panel").is_none());
    assert!(result.snapshot.scene.data.get("focus").is_none());
    assert!(result.snapshot.scene.root.find("tasks-panel").is_some());
    let revoked = result
        .revoked_scopes
        .iter()
        .find(|scope| scope.scope_id == state.scope_a.scope_id)
        .unwrap();
    assert!(revoked.sessions.contains(&state.writer_a));
    assert!(revoked.sessions.contains(&state.observer));

    assert_eq!(
        state
            .engine
            .patch_scope(
                state.writer_a,
                state.world_id,
                &focus_lease,
                focus.snapshot.revision,
                &[],
                6,
            )
            .unwrap_err()
            .code,
        "STALE_SCOPE"
    );
    assert!(state
        .engine
        .patch_scope(
            state.writer_b,
            state.world_id,
            &tasks_lease,
            tasks.snapshot.revision,
            &[],
            6,
        )
        .is_ok());
    assert!(state
        .engine
        .read_scope(
            state.observer,
            state.world_id,
            state.scope_a.scope_id,
            state.scope_a.generation,
        )
        .is_err());
    assert!(observer.lease.is_none());
}

#[test]
fn parent_authority_revocation_fences_all_child_scope_leases() {
    let mut state = setup_scoped_world();
    let focus = state
        .engine
        .join_scope(
            state.writer_a,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
            10_000,
        )
        .unwrap();
    let tasks = state
        .engine
        .join_scope(
            state.writer_b,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_b, JoinMode::Write),
            10_000,
        )
        .unwrap();
    let focus_lease = focus.lease.unwrap();
    let tasks_lease = tasks.lease.unwrap();
    let observer = state
        .engine
        .join_scope(
            state.observer,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Read),
            10_000,
        )
        .unwrap();

    state
        .engine
        .release(state.owner, state.world_id, &state.authority_lease, 10_001)
        .unwrap();
    let focus_generation =
        state.engine.worlds[&state.world_id].scopes[&state.scope_a.scope_id].generation;
    let tasks_generation =
        state.engine.worlds[&state.world_id].scopes[&state.scope_b.scope_id].generation;
    assert!(focus_generation > state.scope_a.generation);
    assert!(tasks_generation > state.scope_b.generation);
    assert_eq!(
        state
            .engine
            .patch_scope(
                state.writer_a,
                state.world_id,
                &focus_lease,
                focus.snapshot.revision,
                &[],
                10_002,
            )
            .unwrap_err()
            .code,
        "STALE_SCOPE"
    );
    assert_eq!(
        state
            .engine
            .patch_scope(
                state.writer_b,
                state.world_id,
                &tasks_lease,
                tasks.snapshot.revision,
                &[],
                10_002,
            )
            .unwrap_err()
            .code,
        "STALE_SCOPE"
    );
    let final_snapshot = state
        .engine
        .read_scope(
            state.observer,
            state.world_id,
            state.scope_a.scope_id,
            focus_generation,
        )
        .unwrap();
    assert_eq!(final_snapshot.status, "stale");
    assert!(observer.lease.is_none());
}

#[test]
fn parent_authority_disconnect_and_expiry_revoke_unexpired_child_leases() {
    for expire_parent in [false, true] {
        let mut state = setup_scoped_world();
        let joined = state
            .engine
            .join_scope(
                state.writer_a,
                ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
                10_000,
            )
            .unwrap();
        let lease = joined.lease.unwrap();
        if expire_parent {
            state.engine.expire(LEASE_MS + 3);
        } else {
            state.engine.disconnect(state.owner);
        }
        assert_eq!(
            state
                .engine
                .patch_scope(
                    state.writer_a,
                    state.world_id,
                    &lease,
                    joined.snapshot.revision,
                    &[],
                    15_004,
                )
                .unwrap_err()
                .code,
            "STALE_SCOPE"
        );
    }
}

#[test]
fn scope_partition_rejects_parent_layout_binding_into_private_scope_data() {
    let mut engine = Engine::default();
    let owner = engine
        .register_with_protocol(
            "scope.binding.owner".into(),
            false,
            ProtocolVersion::ComponentLeasesPreview01,
        )
        .unwrap();
    let created = engine
        .create(
            owner,
            WindowSpec::default(),
            JoinPolicy::Invite,
            true,
            false,
            0,
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
                    "focus-panel",
                    Kind::Stack,
                    json!({}),
                    vec![Node::new(
                        "focus-value",
                        Kind::Text,
                        json!({"text":{"$path":"/focus/value"}}),
                        vec![],
                    )],
                ),
                Node::new(
                    "tasks-panel",
                    Kind::Stack,
                    json!({}),
                    vec![Node::new(
                        "tasks-value",
                        Kind::Text,
                        json!({"text":{"$path":"/tasks/value"}}),
                        vec![],
                    )],
                ),
                Node::new(
                    "parent-leak",
                    Kind::Text,
                    json!({"text":{"$path":"/focus/value"}}),
                    vec![],
                ),
            ],
        ),
        data: json!({
            "focus":{"value":"private"},
            "tasks":{"value":"also-private"}
        }),
        theme: None,
    };
    let updated = engine
        .replace_scene(
            owner,
            created.world.id,
            &lease,
            created.world.revision,
            scene,
            1,
        )
        .unwrap();
    assert_eq!(
        engine
            .partition_scopes(
                owner,
                created.world.id,
                &lease,
                updated.revision,
                &[
                    ScopeDefinition {
                        root_node_id: "focus-panel".into(),
                        data_namespace: "focus".into(),
                    },
                    ScopeDefinition {
                        root_node_id: "tasks-panel".into(),
                        data_namespace: "tasks".into(),
                    },
                ],
                2,
            )
            .unwrap_err()
            .code,
        "SCOPE_DATA_FORBIDDEN"
    );
    assert_eq!(
        engine.worlds[&created.world.id].ownership_mode,
        OwnershipMode::ExclusiveWorld
    );
    assert!(engine.worlds[&created.world.id].writer.is_some());
}

#[test]
fn typed_state_slots_use_owner_cas_and_explicit_reader_grants() {
    let mut state = setup_scoped_world();
    let owner_join = state
        .engine
        .join_scope(
            state.writer_a,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
            3,
        )
        .unwrap();
    let reader_writer_join = state
        .engine
        .join_scope(
            state.writer_b,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_b, JoinMode::Write),
            3,
        )
        .unwrap();
    state
        .engine
        .join_scope(
            state.observer,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_b, JoinMode::Read),
            3,
        )
        .unwrap();
    let owner_lease = owner_join.lease.unwrap();
    let other_scope_lease = reader_writer_join.lease.unwrap();
    let initial_revision = state.engine.worlds[&state.world_id].revision;

    assert_eq!(
        state
            .engine
            .create_state_slot(
                state.observer,
                StateSlotCreateRequest {
                    world_id: state.world_id,
                    lease: owner_lease.clone(),
                    name: "focus.progress".into(),
                    schema: StateSlotSchema::Integer {
                        min: Some(0),
                        max: Some(100),
                    },
                    initial_value: json!({"value": 10}),
                    reader_scopes: vec![],
                },
                4,
            )
            .unwrap_err()
            .code,
        "STALE_SCOPE_LEASE",
        "the host must authenticate the scope lease before validating slot details"
    );

    let invalid_initial = state
        .engine
        .create_state_slot(
            state.writer_a,
            StateSlotCreateRequest {
                world_id: state.world_id,
                lease: owner_lease.clone(),
                name: "focus.progress".into(),
                schema: StateSlotSchema::Integer {
                    min: Some(0),
                    max: Some(100),
                },
                initial_value: json!({"value": 10}),
                reader_scopes: vec![],
            },
            4,
        )
        .unwrap_err();
    assert_eq!(invalid_initial.code, "INVALID_STATE_SLOT_VALUE");
    assert!(state.engine.worlds[&state.world_id].state_slots.is_empty());
    assert_eq!(
        state.engine.worlds[&state.world_id].revision,
        initial_revision
    );

    let slot = state
        .engine
        .create_state_slot(
            state.writer_a,
            StateSlotCreateRequest {
                world_id: state.world_id,
                lease: owner_lease.clone(),
                name: "focus.progress".into(),
                schema: StateSlotSchema::Integer {
                    min: Some(0),
                    max: Some(100),
                },
                initial_value: json!(10),
                reader_scopes: vec![],
            },
            4,
        )
        .unwrap();
    let reader_request = StateSlotReadRequest {
        world_id: state.world_id,
        slot_id: slot.slot_id,
        generation: slot.generation,
        reader_scope_id: state.scope_b.scope_id,
        reader_scope_generation: state.scope_b.generation,
    };
    assert_eq!(
        state
            .engine
            .read_state_slot(state.observer, reader_request.clone())
            .unwrap_err()
            .code,
        "STATE_SLOT_FORBIDDEN",
        "scope membership alone must not grant slot access"
    );

    let committed = state
        .engine
        .compare_and_set_state_slot(
            state.writer_a,
            StateSlotCompareAndSetRequest {
                world_id: state.world_id,
                lease: owner_lease.clone(),
                slot_id: slot.slot_id,
                generation: slot.generation,
                expected_revision: slot.revision,
                value: json!(25),
            },
            5,
        )
        .unwrap();
    assert_eq!(committed.value, json!(25));
    assert_eq!(committed.revision, slot.revision + 1);

    let competing_write = state
        .engine
        .compare_and_set_state_slot(
            state.writer_a,
            StateSlotCompareAndSetRequest {
                world_id: state.world_id,
                lease: owner_lease.clone(),
                slot_id: slot.slot_id,
                generation: slot.generation,
                expected_revision: slot.revision,
                value: json!(40),
            },
            5,
        )
        .unwrap_err();
    assert_eq!(competing_write.code, "STATE_REVISION_CONFLICT");

    let wrong_type = state
        .engine
        .compare_and_set_state_slot(
            state.writer_a,
            StateSlotCompareAndSetRequest {
                world_id: state.world_id,
                lease: owner_lease.clone(),
                slot_id: slot.slot_id,
                generation: slot.generation,
                expected_revision: committed.revision,
                value: json!("not an integer"),
            },
            5,
        )
        .unwrap_err();
    assert_eq!(wrong_type.code, "INVALID_STATE_SLOT_VALUE");

    let unauthorized_writer = state
        .engine
        .compare_and_set_state_slot(
            state.writer_b,
            StateSlotCompareAndSetRequest {
                world_id: state.world_id,
                lease: other_scope_lease,
                slot_id: slot.slot_id,
                generation: slot.generation,
                expected_revision: committed.revision,
                value: json!(50),
            },
            5,
        )
        .unwrap_err();
    assert_eq!(unauthorized_writer.code, "STATE_SLOT_FORBIDDEN");

    let shared = state
        .engine
        .set_state_slot_readers(
            state.writer_a,
            StateSlotSetReadersRequest {
                world_id: state.world_id,
                lease: owner_lease.clone(),
                slot_id: slot.slot_id,
                generation: slot.generation,
                expected_revision: committed.revision,
                reader_scopes: vec![StateSlotScopeRef {
                    scope_id: state.scope_b.scope_id,
                    generation: state.scope_b.generation,
                }],
            },
            6,
        )
        .unwrap();
    let reader_snapshot = state
        .engine
        .read_state_slot(state.observer, reader_request.clone())
        .unwrap();
    assert_eq!(reader_snapshot.value, json!(25));
    assert_eq!(reader_snapshot.revision, shared.revision);

    let operator_snapshot = state.engine.read(state.operator, state.world_id).unwrap();
    let serialized_world = serde_json::to_string(&operator_snapshot).unwrap();
    assert!(
        !serialized_world.contains("focus.progress")
            && !serialized_world.contains(&slot.slot_id.to_string()),
        "state slots must not leak through aggregate world snapshots"
    );

    let revoked = state
        .engine
        .set_state_slot_readers(
            state.writer_a,
            StateSlotSetReadersRequest {
                world_id: state.world_id,
                lease: owner_lease,
                slot_id: slot.slot_id,
                generation: slot.generation,
                expected_revision: shared.revision,
                reader_scopes: vec![],
            },
            7,
        )
        .unwrap();
    assert!(revoked.revision > shared.revision);
    assert_eq!(
        state
            .engine
            .read_state_slot(state.observer, reader_request)
            .unwrap_err()
            .code,
        "STATE_SLOT_FORBIDDEN"
    );
}

#[test]
fn state_slot_grants_and_owned_values_follow_scope_and_parent_revocation() {
    let mut state = setup_scoped_world();
    let owner_join = state
        .engine
        .join_scope(
            state.writer_a,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
            3,
        )
        .unwrap();
    let other_join = state
        .engine
        .join_scope(
            state.writer_b,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_b, JoinMode::Write),
            3,
        )
        .unwrap();
    state
        .engine
        .join_scope(
            state.observer,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_b, JoinMode::Read),
            3,
        )
        .unwrap();
    let owner_lease = owner_join.lease.unwrap();
    let other_lease = other_join.lease.unwrap();
    let owner_slot = state
        .engine
        .create_state_slot(
            state.writer_a,
            StateSlotCreateRequest {
                world_id: state.world_id,
                lease: owner_lease,
                name: "focus.value".into(),
                schema: StateSlotSchema::String { max_chars: 64 },
                initial_value: json!("focus value"),
                reader_scopes: vec![StateSlotScopeRef {
                    scope_id: state.scope_b.scope_id,
                    generation: state.scope_b.generation,
                }],
            },
            4,
        )
        .unwrap();
    let other_slot = state
        .engine
        .create_state_slot(
            state.writer_b,
            StateSlotCreateRequest {
                world_id: state.world_id,
                lease: other_lease,
                name: "tasks.value".into(),
                schema: StateSlotSchema::Boolean,
                initial_value: json!(true),
                reader_scopes: vec![StateSlotScopeRef {
                    scope_id: state.scope_a.scope_id,
                    generation: state.scope_a.generation,
                }],
            },
            4,
        )
        .unwrap();
    let before_revision = state.engine.worlds[&state.world_id].revision;
    let result = state
        .engine
        .patch_scope_structure(
            state.owner,
            state.world_id,
            &state.authority_lease,
            before_revision,
            &[SceneOp::Remove {
                node_id: "focus-panel".into(),
            }],
            5,
        )
        .unwrap();
    assert!(result
        .revoked_scopes
        .iter()
        .any(|scope| scope.scope_id == state.scope_a.scope_id));
    let world = &state.engine.worlds[&state.world_id];
    assert!(!world.state_slots.contains_key(&owner_slot.slot_id));
    let retained_slot = &world.state_slots[&other_slot.slot_id];
    assert!(!retained_slot
        .reader_scopes
        .contains_key(&state.scope_a.scope_id));

    assert_eq!(
        state
            .engine
            .read_state_slot(
                state.observer,
                StateSlotReadRequest {
                    world_id: state.world_id,
                    slot_id: other_slot.slot_id,
                    generation: other_slot.generation,
                    reader_scope_id: state.scope_a.scope_id,
                    reader_scope_generation: state.scope_a.generation,
                },
            )
            .unwrap_err()
            .code,
        "STALE_SCOPE"
    );

    let mut expired = setup_scoped_world();
    let owner_join = expired
        .engine
        .join_scope(
            expired.writer_a,
            ScopeJoinRequest::from_grant(expired.world_id, &expired.scope_a, JoinMode::Write),
            3,
        )
        .unwrap();
    let expiring_slot = expired
        .engine
        .create_state_slot(
            expired.writer_a,
            StateSlotCreateRequest {
                world_id: expired.world_id,
                lease: owner_join.lease.unwrap(),
                name: "focus.expiring".into(),
                schema: StateSlotSchema::Boolean,
                initial_value: json!(true),
                reader_scopes: vec![StateSlotScopeRef {
                    scope_id: expired.scope_b.scope_id,
                    generation: expired.scope_b.generation,
                }],
            },
            4,
        )
        .unwrap();
    let old_scope_generation = expired.scope_a.generation;
    let old_scope_join_key = expired.scope_a.join_key.clone();
    expired.engine.expire(u64::MAX / 2);
    assert!(expired.engine.worlds[&expired.world_id]
        .state_slots
        .is_empty());
    let fenced_scope = &expired.engine.worlds[&expired.world_id].scopes[&expired.scope_a.scope_id];
    assert_eq!(fenced_scope.generation, old_scope_generation + 1);
    assert_ne!(fenced_scope.join_key, old_scope_join_key);
    assert!(fenced_scope.writer.is_none());
    assert_eq!(
        expired
            .engine
            .join_scope(
                expired.writer_a,
                ScopeJoinRequest::from_grant(expired.world_id, &expired.scope_a, JoinMode::Write,),
                u64::MAX / 2,
            )
            .unwrap_err()
            .code,
        "STALE_SCOPE"
    );
    assert_eq!(
        expired
            .engine
            .read_state_slot(
                expired.observer,
                StateSlotReadRequest {
                    world_id: expired.world_id,
                    slot_id: expiring_slot.slot_id,
                    generation: expiring_slot.generation,
                    reader_scope_id: expired.scope_b.scope_id,
                    reader_scope_generation: expired.scope_b.generation,
                },
            )
            .unwrap_err()
            .code,
        "STALE_SCOPE"
    );
}

#[test]
fn state_slot_scope_and_reader_quotas_are_enforced_without_global_name_collisions() {
    let mut state = setup_scoped_world();
    let owner_join = state
        .engine
        .join_scope(
            state.writer_a,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_a, JoinMode::Write),
            3,
        )
        .unwrap();
    let reader_join = state
        .engine
        .join_scope(
            state.writer_b,
            ScopeJoinRequest::from_grant(state.world_id, &state.scope_b, JoinMode::Write),
            3,
        )
        .unwrap();

    for index in 0..MAX_STATE_SLOTS_PER_SCOPE {
        state
            .engine
            .create_state_slot(
                state.writer_a,
                StateSlotCreateRequest {
                    world_id: state.world_id,
                    lease: owner_join.lease.clone().unwrap(),
                    name: format!("value.{index}"),
                    schema: StateSlotSchema::Boolean,
                    initial_value: json!(true),
                    reader_scopes: vec![],
                },
                4,
            )
            .unwrap();
    }
    assert_eq!(
        state.engine.worlds[&state.world_id].state_slots.len(),
        MAX_STATE_SLOTS_PER_SCOPE
    );
    assert_eq!(
        state
            .engine
            .create_state_slot(
                state.writer_a,
                StateSlotCreateRequest {
                    world_id: state.world_id,
                    lease: owner_join.lease.unwrap(),
                    name: "value.overflow".into(),
                    schema: StateSlotSchema::Boolean,
                    initial_value: json!(true),
                    reader_scopes: vec![],
                },
                4,
            )
            .unwrap_err()
            .code,
        "LIMIT"
    );

    let oversized_grants = (0..=MAX_STATE_SLOT_READERS)
        .map(|_| StateSlotScopeRef {
            scope_id: state.scope_a.scope_id,
            generation: state.scope_a.generation,
        })
        .collect();
    assert_eq!(
        state
            .engine
            .create_state_slot(
                state.writer_b,
                StateSlotCreateRequest {
                    world_id: state.world_id,
                    lease: reader_join.lease.clone().unwrap(),
                    name: "value.0".into(),
                    schema: StateSlotSchema::Boolean,
                    initial_value: json!(true),
                    reader_scopes: oversized_grants,
                },
                4,
            )
            .unwrap_err()
            .code,
        "LIMIT"
    );
    let distinct_scope_name = state
        .engine
        .create_state_slot(
            state.writer_b,
            StateSlotCreateRequest {
                world_id: state.world_id,
                lease: reader_join.lease.unwrap(),
                name: "value.0".into(),
                schema: StateSlotSchema::Boolean,
                initial_value: json!(true),
                reader_scopes: vec![],
            },
            4,
        )
        .unwrap();
    assert_eq!(distinct_scope_name.name, "value.0");
    assert_eq!(
        state.engine.worlds[&state.world_id].state_slots.len(),
        MAX_STATE_SLOTS_PER_SCOPE + 1
    );
}
