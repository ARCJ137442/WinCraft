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
