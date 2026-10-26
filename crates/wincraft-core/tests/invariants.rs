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
fn discovery_does_not_authorize_read() {
    let (e, _, b, c) = setup();
    assert_eq!(e.list(b).unwrap().len(), 1);
    assert_eq!(e.read(b, c.world.id).unwrap_err().code, "FORBIDDEN");
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
        data: json!({})
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
fn operator_rescue_fences_writer_and_disables_clickthrough() {
    let (mut e, a, _, c) = setup();
    let op = e.register("host".into(), true).unwrap();
    let s = e.rescue(op, c.world.id).unwrap();
    assert!(!s.window.click_through);
    assert!(s.window.visible);
    assert!(s.window.title_bar_visible);
    assert_eq!(
        e.renew(a, c.world.id, &c.lease.unwrap(), 1)
            .unwrap_err()
            .code,
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
        data: json!({})
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
        data: json!({})
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
        data: json!({})
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
    assert!(window.visible);
    assert!(!window.click_through);
    assert_eq!(window.surface_opacity, 0.8);
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
