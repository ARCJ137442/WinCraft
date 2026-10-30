use crate::{Hub, Notice, Request};
use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet, HashMap},
    io::Write,
    net::SocketAddr,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};
use tokio::{sync::watch, task::JoinHandle, time::timeout};
use uuid::Uuid;
use wincraft_core::{
    EventDeliveryClass, EventSource, Fault, ProtocolVersion, Snapshot, TypedWindowEvent,
    WindowEventType, COMPONENT_LEASES_PREVIEW_PROTOCOL, MAX_PAYLOAD, PROTOCOL,
};

const MAX_EVENT_SUBSCRIPTIONS_PER_SESSION: usize = 32;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SubscribeEventsParams {
    world_id: Uuid,
    types: Vec<WindowEventType>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct UnsubscribeEventsParams {
    subscription_id: Uuid,
}

struct EventSubscription {
    world_id: Uuid,
    types: BTreeSet<WindowEventType>,
    last_snapshot: Snapshot,
}

fn connection_reply(
    hub: &Hub,
    sid: Uuid,
    request: Request,
    subscriptions: &mut BTreeMap<Uuid, EventSubscription>,
) -> Value {
    if request.id.is_empty() || request.id.len() > 80 || request.method.len() > 80 {
        return json!({"id":request.id,"ok":false,"error":Fault::new("INVALID_REQUEST","id and method too long or empty")});
    }
    let method = request.method.clone();
    let params = request.params.clone();
    let response = match method.as_str() {
        "event.subscribe" => {
            match serde_json::from_value::<SubscribeEventsParams>(params.clone()) {
                Ok(params) => subscribe_events(hub, sid, params, subscriptions)
                    .map(|result| json!({"id":request.id,"ok":true,"result":result}))
                    .unwrap_or_else(|error| json!({"id":request.id,"ok":false,"error":error})),
                Err(error) => {
                    json!({"id":request.id,"ok":false,"error":Fault::new("INVALID_PARAMS",error.to_string())})
                }
            }
        }
        "event.unsubscribe" => {
            match serde_json::from_value::<UnsubscribeEventsParams>(params.clone()) {
                Ok(params) => {
                    let removed = subscriptions.remove(&params.subscription_id).is_some();
                    json!({"id":request.id,"ok":true,"result":{"removed":removed}})
                }
                Err(error) => {
                    json!({"id":request.id,"ok":false,"error":Fault::new("INVALID_PARAMS",error.to_string())})
                }
            }
        }
        _ => hub.reply(sid, request),
    };
    if response["ok"] == true && matches!(method.as_str(), "world.leave" | "world.destroy") {
        if let Some(world_id) = params
            .get("world_id")
            .and_then(Value::as_str)
            .and_then(|value| Uuid::parse_str(value).ok())
        {
            subscriptions.retain(|_, subscription| subscription.world_id != world_id);
        }
    }
    response
}

fn subscribe_events(
    hub: &Hub,
    sid: Uuid,
    params: SubscribeEventsParams,
    subscriptions: &mut BTreeMap<Uuid, EventSubscription>,
) -> std::result::Result<Value, Fault> {
    if params.types.is_empty() || params.types.len() > 2 {
        return Err(Fault::new(
            "INVALID_PARAMS",
            "types must contain one or two supported window state events",
        ));
    }
    let types: BTreeSet<_> = params.types.iter().copied().collect();
    if types.len() != params.types.len() {
        return Err(Fault::new(
            "INVALID_PARAMS",
            "types must not contain duplicates",
        ));
    }
    if subscriptions.len() >= MAX_EVENT_SUBSCRIPTIONS_PER_SESSION {
        return Err(Fault::new(
            "LIMIT",
            "maximum 32 event subscriptions per session",
        ));
    }
    let snapshot = hub.lock().read(sid, params.world_id)?;
    let subscription_id = Uuid::new_v4();
    let sequence = snapshot.sequence;
    let window_revision = snapshot.window_revision;
    subscriptions.insert(
        subscription_id,
        EventSubscription {
            world_id: params.world_id,
            types,
            last_snapshot: snapshot,
        },
    );
    Ok(
        json!({"subscription_id":subscription_id,"world_id":params.world_id,"types":params.types,"sequence":sequence,"window_revision":window_revision}),
    )
}

fn events_for_snapshot(
    subscription_id: Uuid,
    subscription: &mut EventSubscription,
    current: &Snapshot,
    source: EventSource,
    cause_id: Option<String>,
) -> Vec<TypedWindowEvent> {
    if current.sequence <= subscription.last_snapshot.sequence {
        return Vec::new();
    }
    let previous = &subscription.last_snapshot;
    let mut events = Vec::new();
    if subscription
        .types
        .contains(&WindowEventType::GeometryChanged)
        && (previous.window.position != current.window.position
            || previous.window.anchor != current.window.anchor
            || previous.window.width != current.window.width
            || previous.window.height != current.window.height
            || previous.window.geometry_control != current.window.geometry_control
            || previous.window.position_control != current.window.position_control)
    {
        events.push(TypedWindowEvent {
            event_id: Uuid::new_v4(),
            subscription_id,
            world_id: current.id,
            event_type: WindowEventType::GeometryChanged,
            delivery: EventDeliveryClass::State,
            source,
            cause_id: cause_id.clone(),
            sequence: current.sequence,
            window_revision: current.window_revision,
            payload: json!({
                "position":&current.window.position,
                "anchor":&current.window.anchor,
                "width":current.window.width,
                "height":current.window.height,
                "geometry_control":current.window.geometry_control,
                "position_control":current.window.position_control
            }),
        });
    }
    if subscription
        .types
        .contains(&WindowEventType::VisibilityChanged)
        && previous.window.visible != current.window.visible
    {
        events.push(TypedWindowEvent {
            event_id: Uuid::new_v4(),
            subscription_id,
            world_id: current.id,
            event_type: WindowEventType::VisibilityChanged,
            delivery: EventDeliveryClass::State,
            source,
            cause_id,
            sequence: current.sequence,
            window_revision: current.window_revision,
            payload: json!({"visible":current.window.visible}),
        });
    }
    subscription.last_snapshot = current.clone();
    events
}

#[derive(Clone)]
struct Transport {
    hub: Hub,
    token: String,
    shutdown: watch::Receiver<bool>,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Descriptor {
    pub protocol: String,
    pub supported_protocols: Vec<String>,
    pub host_id: Uuid,
    pub http_url: String,
    pub ws_url: String,
    pub token: String,
    pub pid: u32,
    pub native_windows: bool,
}
pub struct RunningServer {
    pub descriptor: Descriptor,
    pub file: PathBuf,
    hub: Hub,
    shutdown: watch::Sender<bool>,
    server_task: Option<JoinHandle<()>>,
    housekeeping_task: Option<JoinHandle<()>>,
    stopped: bool,
}
impl RunningServer {
    pub async fn shutdown(mut self) {
        self.shutdown.send_replace(true);
        self.hub.disconnect_providers();
        if let Some(task) = self.server_task.take() {
            await_shutdown(task).await;
        }
        if let Some(task) = self.housekeeping_task.take() {
            await_shutdown(task).await;
        }
        self.remove_descriptor();
        self.stopped = true;
    }

    fn remove_descriptor(&self) {
        let _ = std::fs::remove_file(&self.file);
    }
}

async fn await_shutdown(mut task: JoinHandle<()>) {
    if timeout(Duration::from_secs(3), &mut task).await.is_err() {
        task.abort();
        let _ = task.await;
    }
}

impl Drop for RunningServer {
    fn drop(&mut self) {
        if !self.stopped {
            self.shutdown.send_replace(true);
            self.hub.disconnect_providers();
            if let Some(task) = &self.server_task {
                task.abort();
            }
            if let Some(task) = &self.housekeeping_task {
                task.abort();
            }
            self.remove_descriptor();
        }
    }
}

pub async fn start(
    hub: Hub,
    bind: SocketAddr,
    runtime_dir: &Path,
) -> std::io::Result<RunningServer> {
    if !bind.ip().is_loopback() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::PermissionDenied,
            "v0.1 binds loopback only; use an authenticated SSH tunnel for remote providers",
        ));
    }
    let listener = tokio::net::TcpListener::bind(bind).await?;
    let addr = listener.local_addr()?;
    let token = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
    let descriptor = Descriptor {
        protocol: PROTOCOL.into(),
        supported_protocols: vec![PROTOCOL.into(), COMPONENT_LEASES_PREVIEW_PROTOCOL.into()],
        host_id: hub.host_id,
        http_url: format!("http://{addr}"),
        ws_url: format!("ws://{addr}/v1/ws"),
        token: token.clone(),
        pid: std::process::id(),
        native_windows: hub.native_windows,
    };
    let (shutdown, shutdown_rx) = watch::channel(false);
    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/discovery", get(discovery))
        .route("/v1/ws", get(upgrade))
        .with_state(Transport {
            hub: hub.clone(),
            token,
            shutdown: shutdown_rx.clone(),
        });

    // Write credentials before spawning tasks, so a filesystem error cannot leave a live listener.
    std::fs::create_dir_all(runtime_dir)?;
    let file = runtime_dir.join(format!("{}.runtime.json", hub.host_id));
    write_descriptor(&file, &descriptor)?;

    let housekeeping_task = hub.start_housekeeping(shutdown_rx.clone());
    let mut server_shutdown = shutdown_rx;
    let server_task = tokio::spawn(async move {
        let signal = async move {
            if !*server_shutdown.borrow() {
                let _ = server_shutdown.changed().await;
            }
        };
        if let Err(e) = axum::serve(listener, app)
            .with_graceful_shutdown(signal)
            .await
        {
            eprintln!("WinCraft server stopped: {e}");
        }
    });
    // Descriptor contains a bearer credential. Log only its path, never its contents.
    eprintln!("WinCraft runtime descriptor: {}", file.display());
    Ok(RunningServer {
        descriptor,
        file,
        hub,
        shutdown,
        server_task: Some(server_task),
        housekeeping_task: Some(housekeeping_task),
        stopped: false,
    })
}
fn write_descriptor(file: &Path, descriptor: &Descriptor) -> std::io::Result<()> {
    let mut opts = std::fs::OpenOptions::new();
    opts.create_new(true).write(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        opts.mode(0o600);
    }
    let mut out = opts.open(file)?;
    let bytes = serde_json::to_vec_pretty(descriptor).map_err(std::io::Error::other)?;
    out.write_all(&bytes)?;
    out.sync_all()?;
    Ok(())
}
fn token_matches(a: &str, b: &str) -> bool {
    if a.len() != b.len() {
        return false;
    }
    a.bytes()
        .zip(b.bytes())
        .fold(0u8, |acc, (x, y)| acc | (x ^ y))
        == 0
}
fn authorized(headers: &HeaderMap, token: &str) -> bool {
    // Native clients have no Origin. Web pages/extensions need a future explicit origin policy.
    if headers.contains_key("origin") {
        return false;
    }
    headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.strip_prefix("Bearer "))
        .map(|s| token_matches(s, token))
        .unwrap_or(false)
}
async fn health(State(t): State<Transport>) -> Json<Value> {
    Json(
        json!({"ready":true,"protocol":PROTOCOL,"host_id":t.hub.host_id,"native_windows":t.hub.native_windows}),
    )
}
async fn discovery(State(t): State<Transport>, headers: HeaderMap) -> Response {
    if !authorized(&headers, &t.token) {
        return StatusCode::UNAUTHORIZED.into_response();
    }
    Json(json!({"host_id":t.hub.host_id,"capabilities":t.hub.capabilities(),"websocket_path":"/v1/ws"})).into_response()
}
async fn upgrade(State(t): State<Transport>, headers: HeaderMap, ws: WebSocketUpgrade) -> Response {
    if !authorized(&headers, &t.token) {
        return StatusCode::UNAUTHORIZED.into_response();
    }
    let hub = t.hub.clone();
    let shutdown = t.shutdown.clone();
    ws.max_message_size(MAX_PAYLOAD)
        .max_frame_size(MAX_PAYLOAD)
        .on_upgrade(move |socket| serve_socket(socket, hub, shutdown))
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Hello {
    protocol: String,
    provider_name: String,
}
async fn send(socket: &mut WebSocket, value: Value) -> bool {
    matches!(
        timeout(
            Duration::from_secs(3),
            socket.send(Message::Text(value.to_string().into()))
        )
        .await,
        Ok(Ok(()))
    )
}
async fn serve_socket(mut socket: WebSocket, hub: Hub, mut shutdown: watch::Receiver<bool>) {
    let first = match timeout(Duration::from_secs(5), socket.recv()).await {
        Ok(Some(Ok(Message::Text(text)))) => text,
        _ => return,
    };
    let req: Request = match serde_json::from_str(first.as_str()) {
        Ok(v) => v,
        Err(_) => return,
    };
    if req.method != "hello" || req.id.is_empty() || req.id.len() > 80 {
        return;
    }
    let hello: Hello = match serde_json::from_value(req.params) {
        Ok(v) => v,
        Err(_) => return,
    };
    let Some(protocol) = ProtocolVersion::parse(&hello.protocol) else {
        let _ = send(
            &mut socket,
            json!({"id":req.id,"ok":false,"error":Fault::new("PROTOCOL_MISMATCH",format!("supported protocols: {PROTOCOL}, {COMPONENT_LEASES_PREVIEW_PROTOCOL}"))}),
        )
        .await;
        return;
    };
    let sid_result = hub
        .lock()
        .register_with_protocol(hello.provider_name, false, protocol);
    let sid = match sid_result {
        Ok(id) => id,
        Err(e) => {
            let _ = send(&mut socket, json!({"id":req.id,"ok":false,"error":e})).await;
            return;
        }
    };
    let mut events = hub.subscribe();
    let mut state_updates = hub.subscribe_state();
    if !send(&mut socket,json!({"id":req.id,"ok":true,"result":{"session_id":sid,"host_id":hub.host_id,"protocol":protocol.as_str(),"capabilities":hub.capabilities_for(protocol)}})).await{
        hub.disconnect(sid);return;
    }
    let mut idle = tokio::time::interval(Duration::from_secs(2));
    let mut last_seen = Instant::now();
    let mut rate_start = Instant::now();
    let mut count = 0u32;
    let mut subscriptions = BTreeMap::new();
    let mut last_snapshot_sequences = HashMap::<Uuid, u64>::new();
    let mut last_scope_snapshots = HashMap::<(Uuid, Uuid), (u64, u64)>::new();
    'connection: loop {
        tokio::select! {
            incoming=socket.recv()=>{
                match incoming{
                    Some(Ok(Message::Text(text)))=>{
                        if rate_start.elapsed()>=Duration::from_secs(1){rate_start=Instant::now();count=0;}
                        count+=1;if count>120{break;}
                        last_seen=Instant::now();
                        let request=match serde_json::from_str::<Request>(text.as_str()){
                            Ok(r)=>r,Err(e)=>{if !send(&mut socket,json!({"event":"protocol.error","error":Fault::new("INVALID_REQUEST",e.to_string())})).await{break;}continue;}
                        };
                        let reply=connection_reply(&hub,sid,request,&mut subscriptions);
                        if !send(&mut socket,reply).await{break 'connection;}
                    },
                    Some(Ok(Message::Ping(_)))|Some(Ok(Message::Pong(_)))=>{last_seen=Instant::now();},
                    Some(Ok(Message::Close(_)))|None|Some(Err(_))=>break,
                    Some(Ok(Message::Binary(_)))=>break,
                }
            },
            state_update=state_updates.changed()=>{
                if state_update.is_err(){break 'connection;}
                for change in hub.latest_state_changes(){
                    if last_snapshot_sequences.get(&change.world_id).is_some_and(|last|change.sequence<=*last){
                        continue;
                    }
                    let snapshot_result = { hub.lock().read(sid,change.world_id) };
                    match snapshot_result {
                        Ok(snapshot) if snapshot.sequence==change.sequence=>{
                            last_snapshot_sequences.insert(change.world_id,snapshot.sequence);
                            if !send(&mut socket,json!({"event":"world.snapshot","data":snapshot})).await{break 'connection;}
                            let typed:Vec<_>=subscriptions.iter_mut()
                                .filter(|(_,subscription)|subscription.world_id==change.world_id)
                                .flat_map(|(subscription_id,subscription)|events_for_snapshot(
                                    *subscription_id,subscription,&snapshot,change.source,change.cause_id.clone()))
                                .collect();
                            for event in typed{
                                if !send(&mut socket,json!({"event":"window.event","data":event})).await{break 'connection;}
                            }
                        },
                        Ok(_)=>{},
                        Err(_)=>subscriptions.retain(|_,subscription|subscription.world_id!=change.world_id),
                    }
                    let scope_snapshots = hub.read_scopes(sid, change.world_id).unwrap_or_default();
                    last_scope_snapshots.retain(|(world_id, scope_id), _| {
                        *world_id != change.world_id
                            || scope_snapshots.iter().any(|snapshot| snapshot.scope_id == *scope_id)
                    });
                    for snapshot in scope_snapshots {
                        let key = (snapshot.world_id, snapshot.scope_id);
                        let version = (snapshot.generation, snapshot.revision);
                        if last_scope_snapshots
                            .get(&key)
                            .is_some_and(|previous| *previous >= version)
                        {
                            continue;
                        }
                        last_scope_snapshots.insert(key, version);
                        if !send(&mut socket, json!({"event":"scope.snapshot","data":snapshot})).await {
                            break 'connection;
                        }
                    }
                }
            },
            notice=events.recv()=>{
                match notice {
                    Ok(Notice::Directed(target,event)) if target==sid=>{
                        if event.get("event").and_then(Value::as_str)==Some("scope.revoked") {
                            if let (Some(world_id),Some(scope_id))=(
                                event.pointer("/data/world_id").and_then(Value::as_str).and_then(|id|Uuid::parse_str(id).ok()),
                                event.pointer("/data/scope_id").and_then(Value::as_str).and_then(|id|Uuid::parse_str(id).ok()),
                            ) {
                                last_scope_snapshots.remove(&(world_id,scope_id));
                            }
                        }
                        if !send(&mut socket,event).await{break 'connection;}
                    },
                    Ok(Notice::Deleted{world_id,members})=>{
                        subscriptions.retain(|_,subscription|subscription.world_id!=world_id);
                        last_snapshot_sequences.remove(&world_id);
                        last_scope_snapshots.retain(|(id,_),_|*id!=world_id);
                        if members.contains(&sid) && !send(&mut socket,json!({"event":"world.deleted","world_id":world_id})).await{break 'connection;}
                    },
                    Ok(_)=>{},
                    // Do not silently lose a human action. Fail the session; the provider must reconnect.
                    Err(tokio::sync::broadcast::error::RecvError::Lagged(_))=>{
                        let _=send(&mut socket,json!({"event":"resync_required","reason":"slow consumer; reconnect and reacquire"})).await;break;
                    },
                    Err(_)=>break,
                }
            },
            _=shutdown.changed()=>{
                let _=timeout(Duration::from_secs(1),socket.send(Message::Close(None))).await;
                break;
            },
            _=idle.tick()=>{if last_seen.elapsed()>Duration::from_secs(20){break;}}
        }
    }
    hub.disconnect(sid);
}
#[cfg(test)]
mod tests {
    use super::*;
    use futures_util::{SinkExt, StreamExt};
    use tokio::net::TcpStream;
    use tokio_tungstenite::{
        connect_async,
        tungstenite::{client::IntoClientRequest, http::header::AUTHORIZATION, Message},
        MaybeTlsStream, WebSocketStream,
    };
    use wincraft_core::{
        GeometryControl, JoinPolicy, Position, WindowSpec, WorkAreaAnchor, WorkAreaCorner,
    };

    type TestSocket = WebSocketStream<MaybeTlsStream<TcpStream>>;

    struct TestRuntimeDirectory(PathBuf);
    impl Drop for TestRuntimeDirectory {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    async fn connect_test_provider(descriptor: &Descriptor, name: &str) -> (TestSocket, Uuid) {
        connect_test_provider_with_protocol(descriptor, name, PROTOCOL).await
    }

    async fn connect_test_provider_with_protocol(
        descriptor: &Descriptor,
        name: &str,
        protocol: &str,
    ) -> (TestSocket, Uuid) {
        let mut request = descriptor
            .ws_url
            .clone()
            .into_client_request()
            .expect("WebSocket request");
        request.headers_mut().insert(
            AUTHORIZATION,
            format!("Bearer {}", descriptor.token)
                .parse()
                .expect("bearer header"),
        );
        let (mut socket, _) = connect_async(request).await.expect("provider connects");
        let response = rpc(
            &mut socket,
            "hello",
            "hello",
            json!({"protocol":protocol,"provider_name":name}),
        )
        .await;
        assert_eq!(response["ok"], true);
        let session = response["result"]["session_id"]
            .as_str()
            .expect("session ID")
            .parse()
            .expect("session UUID");
        (socket, session)
    }

    async fn rpc(socket: &mut TestSocket, id: &str, method: &str, params: Value) -> Value {
        socket
            .send(Message::Text(
                json!({"id":id,"method":method,"params":params})
                    .to_string()
                    .into(),
            ))
            .await
            .expect("request sends");
        loop {
            let message = timeout(Duration::from_secs(2), socket.next())
                .await
                .expect("response arrives")
                .expect("socket remains open")
                .expect("WebSocket message is valid");
            let Message::Text(text) = message else {
                continue;
            };
            let value: Value = serde_json::from_str(text.as_str()).expect("JSON response");
            if value.get("id").and_then(Value::as_str) == Some(id) {
                return value;
            }
        }
    }

    async fn next_event_matching(
        socket: &mut TestSocket,
        event_name: &str,
        mut predicate: impl FnMut(&Value) -> bool,
    ) -> Value {
        timeout(Duration::from_secs(2), async {
            loop {
                let message = socket
                    .next()
                    .await
                    .expect("socket remains open")
                    .expect("WebSocket message is valid");
                let Message::Text(text) = message else {
                    continue;
                };
                let value: Value = serde_json::from_str(text.as_str()).expect("JSON event");
                if value.get("event").and_then(Value::as_str) == Some(event_name)
                    && predicate(&value)
                {
                    return value;
                }
            }
        })
        .await
        .expect("matching event arrives")
    }

    #[test]
    fn comparison() {
        assert!(token_matches("abc", "abc"));
        assert!(!token_matches("abc", "abd"));
        assert!(!token_matches("abc", "abcd"));
    }
    #[test]
    fn browser_origins_are_not_silently_trusted() {
        let mut h = HeaderMap::new();
        h.insert("authorization", "Bearer abc".parse().unwrap());
        assert!(authorized(&h, "abc"));
        h.insert("origin", "https://example.org".parse().unwrap());
        assert!(!authorized(&h, "abc"));
    }

    #[test]
    fn state_event_uses_the_latest_snapshot_and_coalesces_duplicate_sequences() {
        let mut engine = wincraft_core::Engine::default();
        let provider = engine
            .register("event-coalesce.test".into(), false)
            .unwrap();
        let created = engine
            .create(
                provider,
                WindowSpec::default(),
                JoinPolicy::OpenAuthenticated,
                true,
                false,
                0,
            )
            .unwrap();
        let baseline = created.world;
        let mut current = baseline.clone();
        current.sequence += 4;
        current.window_revision += 1;
        current.window.position = Some(Position { x: 900, y: -30 });
        current.window.width = 540.0;
        let subscription_id = Uuid::new_v4();
        let mut subscription = EventSubscription {
            world_id: current.id,
            types: BTreeSet::from([WindowEventType::GeometryChanged]),
            last_snapshot: baseline,
        };

        let events = events_for_snapshot(
            subscription_id,
            &mut subscription,
            &current,
            EventSource::Human,
            None,
        );
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].sequence, current.sequence);
        assert_eq!(events[0].window_revision, current.window_revision);
        assert_eq!(events[0].delivery, EventDeliveryClass::State);
        assert_eq!(events[0].payload["position"]["x"], 900);
        assert_eq!(events[0].payload["width"], 540.0);
        assert_eq!(events[0].payload["geometry_control"], "human");
        assert_eq!(events[0].payload["position_control"], Value::Null);
        assert!(events_for_snapshot(
            subscription_id,
            &mut subscription,
            &current,
            EventSource::Human,
            None,
        )
        .is_empty());
    }

    #[test]
    fn geometry_state_event_tracks_anchor_changes_and_serializes_the_latest_anchor() {
        let mut engine = wincraft_core::Engine::default();
        let provider = engine.register("anchor-event.test".into(), false).unwrap();
        let created = engine
            .create(
                provider,
                WindowSpec::default(),
                JoinPolicy::OpenAuthenticated,
                true,
                false,
                0,
            )
            .unwrap();
        let baseline = created.world.clone();
        let mut current = baseline.clone();
        current.sequence += 1;
        current.window_revision += 1;
        current.window.geometry_control = GeometryControl::Provider;
        current.window.anchor = Some(WorkAreaAnchor {
            corner: WorkAreaCorner::BottomRight,
            margin_x: 24.0,
            margin_y: 32.0,
        });
        let subscription_id = Uuid::new_v4();
        let mut subscription = EventSubscription {
            world_id: current.id,
            types: BTreeSet::from([WindowEventType::GeometryChanged]),
            last_snapshot: baseline,
        };

        let events = events_for_snapshot(
            subscription_id,
            &mut subscription,
            &current,
            EventSource::Provider,
            Some("anchor.configure".into()),
        );
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].payload["position"], Value::Null);
        assert_eq!(events[0].payload["anchor"]["corner"], "bottom_right");
        assert_eq!(events[0].payload["anchor"]["margin_x"], 24.0);
        assert_eq!(events[0].payload["geometry_control"], "provider");
        assert_eq!(events[0].payload["position_control"], Value::Null);
    }

    #[tokio::test]
    async fn window_event_subscription_is_read_scoped_cancellable_and_non_reactive() {
        let runtime_dir =
            std::env::temp_dir().join(format!("wincraft-event-subscription-{}", Uuid::new_v4()));
        let _cleanup = TestRuntimeDirectory(runtime_dir.clone());
        let hub = Hub::new(false);
        let server = start(hub, "127.0.0.1:0".parse().unwrap(), &runtime_dir)
            .await
            .expect("loopback server starts");
        let (mut writer, _) = connect_test_provider(&server.descriptor, "event.writer").await;
        let created = rpc(
            &mut writer,
            "create",
            "world.create",
            json!({"window":{"title":"event fixture"},"claim":true}),
        )
        .await;
        assert_eq!(created["ok"], true);
        let world_id = created["result"]["world"]["id"]
            .as_str()
            .expect("world id")
            .to_owned();
        let lease = created["result"]["lease"].clone();
        let join_key = created["result"]["join_key"].clone();
        let initial_revision = created["result"]["world"]["revision"].as_u64().unwrap();

        let (mut reader, _) = connect_test_provider(&server.descriptor, "event.reader").await;
        let before_join = rpc(
            &mut reader,
            "subscribe-before-join",
            "event.subscribe",
            json!({"world_id":world_id,"types":["window.visibility_changed"]}),
        )
        .await;
        assert_eq!(before_join["ok"], false);
        assert_eq!(before_join["error"]["code"], "FORBIDDEN");

        let joined = rpc(
            &mut reader,
            "join-read",
            "world.join",
            json!({"world_id":world_id,"mode":"read","join_key":join_key}),
        )
        .await;
        assert_eq!(joined["ok"], true);
        assert!(joined["result"]["lease"].is_null());
        let subscribed = rpc(
            &mut reader,
            "subscribe",
            "event.subscribe",
            json!({"world_id":world_id,"types":["window.visibility_changed"]}),
        )
        .await;
        assert_eq!(subscribed["ok"], true);
        let subscription_id = subscribed["result"]["subscription_id"]
            .as_str()
            .expect("subscription ID")
            .to_owned();
        assert_eq!(
            subscribed["result"]["sequence"],
            joined["result"]["world"]["sequence"]
        );

        let reader_write = rpc(
            &mut reader,
            "reader-write",
            "window.configure",
            json!({
                "world_id":world_id,"lease":lease,"expected_revision":initial_revision,
                "patch":{"visible":false}
            }),
        )
        .await;
        assert_eq!(reader_write["ok"], false);
        assert_eq!(reader_write["error"]["code"], "STALE_LEASE");

        let changed = rpc(
            &mut writer,
            "set-hidden",
            "window.configure",
            json!({
                "world_id":world_id,"lease":lease,"expected_revision":initial_revision,
                "patch":{"visible":false}
            }),
        )
        .await;
        assert_eq!(changed["ok"], true);

        let event = timeout(Duration::from_secs(2), async {
            loop {
                let message = timeout(Duration::from_secs(2), reader.next())
                    .await
                    .expect("state event arrives")
                    .expect("reader socket remains open")
                    .expect("WebSocket event is valid");
                let Message::Text(text) = message else {
                    continue;
                };
                let value: Value = serde_json::from_str(text.as_str()).expect("event JSON");
                if value["event"] == "window.event"
                    && value["data"]["subscription_id"] == subscription_id
                {
                    break value;
                }
            }
        })
        .await
        .expect("typed window event is delivered");
        assert_eq!(event["data"]["type"], "window.visibility_changed");
        assert_eq!(event["data"]["delivery"], "state");
        assert_eq!(event["data"]["source"], "provider");
        assert_eq!(event["data"]["cause_id"], "set-hidden");
        assert_eq!(event["data"]["payload"]["visible"], false);
        assert_eq!(event["data"]["sequence"], changed["result"]["sequence"]);

        let unsubscribed = rpc(
            &mut reader,
            "unsubscribe",
            "event.unsubscribe",
            json!({"subscription_id":subscription_id}),
        )
        .await;
        assert_eq!(unsubscribed["result"]["removed"], true);
        let revision = changed["result"]["revision"].as_u64().unwrap();
        let shown = rpc(
            &mut writer,
            "set-visible",
            "window.configure",
            json!({"world_id":world_id,"lease":lease,"expected_revision":revision,"patch":{"visible":true}}),
        )
        .await;
        assert_eq!(shown["ok"], true);
        let after_unsubscribe = timeout(Duration::from_millis(250), async {
            loop {
                let message = reader.next().await;
                let Some(Ok(Message::Text(text))) = message else {
                    continue;
                };
                let value: Value = serde_json::from_str(text.as_str()).expect("event JSON");
                assert_ne!(
                    value["event"], "window.event",
                    "unsubscribed session received a state event"
                );
            }
        })
        .await;
        assert!(
            after_unsubscribe.is_err(),
            "no typed event should arrive after unsubscribe"
        );

        reader.close(None).await.expect("reader closes");
        writer.close(None).await.expect("writer closes");
        server.shutdown().await;
    }

    #[tokio::test]
    async fn graceful_shutdown_disconnects_sessions_closes_listener_and_removes_descriptor() {
        let runtime_dir =
            std::env::temp_dir().join(format!("wincraft-server-shutdown-{}", Uuid::new_v4()));
        let _cleanup = TestRuntimeDirectory(runtime_dir.clone());
        let hub = Hub::new(false);
        let bind: SocketAddr = "127.0.0.1:0".parse().unwrap();
        let server = start(hub.clone(), bind, &runtime_dir)
            .await
            .expect("loopback server starts");
        let descriptor = server.descriptor.clone();
        let descriptor_file = server.file.clone();
        let address: SocketAddr = descriptor
            .http_url
            .strip_prefix("http://")
            .expect("HTTP URL prefix")
            .parse()
            .expect("server address");

        let mut request = descriptor
            .ws_url
            .clone()
            .into_client_request()
            .expect("WebSocket request");
        request.headers_mut().insert(
            AUTHORIZATION,
            format!("Bearer {}", descriptor.token)
                .parse()
                .expect("bearer header"),
        );
        let (mut socket, _) = connect_async(request)
            .await
            .expect("provider connects to the loopback server");
        socket
            .send(Message::Text(
                json!({
                    "id": "hello",
                    "method": "hello",
                    "params": {"protocol": PROTOCOL, "provider_name": "shutdown.test"}
                })
                .to_string()
                .into(),
            ))
            .await
            .expect("hello sends");
        let hello = timeout(Duration::from_secs(2), socket.next())
            .await
            .expect("hello response arrives")
            .expect("socket remains open")
            .expect("hello response is valid");
        let Message::Text(hello) = hello else {
            panic!("expected hello response");
        };
        let hello: Value = serde_json::from_str(hello.as_str()).expect("hello JSON");
        assert_eq!(hello["ok"], true);
        let session_id: Uuid = hello["result"]["session_id"]
            .as_str()
            .expect("session id")
            .parse()
            .expect("session UUID");

        socket
            .send(Message::Text(
                json!({
                    "id": "create",
                    "method": "world.create",
                    "params": {
                        "window": {"title": "shutdown fixture"},
                        "join_policy": "open_authenticated",
                        "claim": true
                    }
                })
                .to_string()
                .into(),
            ))
            .await
            .expect("world.create sends");
        let created = timeout(Duration::from_secs(2), socket.next())
            .await
            .expect("create response arrives")
            .expect("socket remains open")
            .expect("create response is valid");
        let Message::Text(created) = created else {
            panic!("expected world.create response");
        };
        let created: Value = serde_json::from_str(created.as_str()).expect("create JSON");
        assert_eq!(created["ok"], true);
        let world_id: Uuid = created["result"]["world"]["id"]
            .as_str()
            .expect("world id")
            .parse()
            .expect("world UUID");
        assert!(hub.lock().sessions.contains_key(&session_id));

        server.shutdown().await;

        assert!(
            !descriptor_file.exists(),
            "descriptor is removed on shutdown"
        );
        assert!(!hub.lock().sessions.contains_key(&session_id));
        let world = hub
            .renderer_snapshot(world_id)
            .expect("world remains stale for local state");
        assert_eq!(world.status, "stale");
        assert!(world.writer.is_none());
        assert!(tokio::net::TcpStream::connect(address).await.is_err());
        let socket_result = timeout(Duration::from_secs(2), socket.next()).await;
        assert!(
            socket_result.is_ok(),
            "provider socket is closed by shutdown"
        );
    }

    #[tokio::test]
    async fn preview_provider_inventory_registers_metadata_without_world_authority() {
        let runtime_dir =
            std::env::temp_dir().join(format!("wincraft-provider-inventory-{}", Uuid::new_v4()));
        let _cleanup = TestRuntimeDirectory(runtime_dir.clone());
        let hub = Hub::new(false);
        let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap(), &runtime_dir)
            .await
            .expect("loopback server starts");
        let (mut source, _) = connect_test_provider_with_protocol(
            &server.descriptor,
            "inventory.source",
            COMPONENT_LEASES_PREVIEW_PROTOCOL,
        )
        .await;
        let (mut observer, _) = connect_test_provider_with_protocol(
            &server.descriptor,
            "inventory.observer",
            COMPONENT_LEASES_PREVIEW_PROTOCOL,
        )
        .await;
        let (mut stable, _) = connect_test_provider(&server.descriptor, "inventory.stable").await;

        let preview_capabilities = rpc(&mut source, "caps", "host.capabilities", json!({})).await;
        assert_eq!(
            preview_capabilities["result"]["provider_inventory"]["version"],
            1
        );
        let stable_capabilities =
            rpc(&mut stable, "stable-caps", "host.capabilities", json!({})).await;
        assert!(stable_capabilities["result"]
            .get("provider_inventory")
            .is_none());

        let created = rpc(
            &mut source,
            "invite",
            "world.create",
            json!({"window":{"title":"inventory invite"},"join_policy":"invite","claim":false}),
        )
        .await;
        assert_eq!(created["ok"], true);
        let invite_world_id = created["result"]["world"]["id"].as_str().unwrap();

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
                    "source_id":"source.codex-app",
                    "source_instance_id":"instance-a",
                    "provider_type":"codex-app",
                    "display_name":"Same label",
                    "adapter_contract":1,
                    "state":"online",
                    "capabilities":["activity.read"],
                    "source_updated_at":observed_at,
                    "fresh_for_seconds":60
                },
                {
                    "source_id":"source.codex-app",
                    "source_instance_id":"instance-b",
                    "provider_type":"codex-app",
                    "display_name":"Same label",
                    "adapter_contract":1,
                    "state":"degraded",
                    "capabilities":["activity.read"],
                    "source_updated_at":observed_at,
                    "fresh_for_seconds":30
                }
            ]
        });
        let registered = rpc(
            &mut source,
            "inventory-register",
            "provider.inventory.register",
            registration,
        )
        .await;
        assert_eq!(registered["ok"], true);
        let listed = rpc(
            &mut observer,
            "inventory-list",
            "provider.inventory.list",
            json!({}),
        )
        .await;
        assert_eq!(listed["ok"], true);
        assert_eq!(
            listed["result"]["endpoint_id"],
            server.descriptor.host_id.to_string()
        );
        let providers = listed["result"]["providers"].as_array().unwrap();
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

        let join = rpc(
            &mut observer,
            "join-invite-without-key",
            "world.join",
            json!({"world_id":invite_world_id,"mode":"read"}),
        )
        .await;
        assert_eq!(join["error"]["code"], "FORBIDDEN");
        let stable_list = rpc(
            &mut stable,
            "stable-inventory-list",
            "provider.inventory.list",
            json!({}),
        )
        .await;
        assert_eq!(stable_list["error"]["code"], "UNSUPPORTED_CAPABILITY");

        source.close(None).await.expect("source closes");
        observer.close(None).await.expect("observer closes");
        stable.close(None).await.expect("stable client closes");
        server.shutdown().await;
    }

    #[tokio::test]
    async fn preview_websocket_scopes_allow_disjoint_writers_and_filter_readers() {
        let runtime_dir =
            std::env::temp_dir().join(format!("wincraft-scope-preview-{}", Uuid::new_v4()));
        let _cleanup = TestRuntimeDirectory(runtime_dir.clone());
        let hub = Hub::new(false);
        let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap(), &runtime_dir)
            .await
            .expect("loopback server starts");
        assert!(server
            .descriptor
            .supported_protocols
            .contains(&COMPONENT_LEASES_PREVIEW_PROTOCOL.to_owned()));

        let (mut owner, _) = connect_test_provider_with_protocol(
            &server.descriptor,
            "scope.owner",
            COMPONENT_LEASES_PREVIEW_PROTOCOL,
        )
        .await;
        let capabilities = rpc(&mut owner, "capabilities", "host.capabilities", json!({})).await;
        assert_eq!(capabilities["ok"], true);
        assert_eq!(
            capabilities["result"]["component_leases"]["status"],
            "preview"
        );
        assert_eq!(capabilities["result"]["component_leases"]["version"], 1);
        assert_eq!(
            capabilities["result"]["component_leases"]["root_structure_patch"],
            "scope.structure.patch"
        );
        assert_eq!(
            capabilities["result"]["component_leases"]["filtered_scope_events"],
            true
        );
        assert_eq!(
            capabilities["result"]["component_leases"]["scope_status"]["version"],
            1
        );
        assert_eq!(
            capabilities["result"]["component_leases"]["scope_status"]["data"],
            "lifecycle_metadata_only"
        );
        assert_eq!(
            capabilities["result"]["component_leases"]["scope_status"]["authorization"],
            "local_operator_or_active_world_authority_or_scope_member"
        );
        assert_eq!(
            capabilities["result"]["component_leases"]["state_slots"]["status"],
            "preview"
        );
        assert_eq!(
            capabilities["result"]["component_leases"]["state_slots"]["writes"],
            "owner_scope_cas"
        );
        assert_eq!(
            capabilities["result"]["component_leases"]["state_slots"]["reads"],
            "explicit_scope_grants"
        );
        assert_eq!(
            capabilities["result"]["component_leases"]["state_slots"]["max_readers_per_slot"],
            wincraft_core::MAX_STATE_SLOT_READERS
        );
        assert!(!capabilities["result"]["not_implemented"]
            .as_array()
            .unwrap()
            .iter()
            .any(|feature| feature == "state_slots"));

        let created = rpc(
            &mut owner,
            "create",
            "world.create",
            json!({"window":{"title":"scope preview"},"join_policy":"invite","claim":true}),
        )
        .await;
        assert_eq!(created["ok"], true);
        let world_id = created["result"]["world"]["id"].as_str().unwrap();
        let world_join_key = created["result"]["join_key"].as_str().unwrap();
        let lease = created["result"]["lease"].clone();
        let initial_revision = created["result"]["world"]["revision"].as_u64().unwrap();
        let scene = json!({
            "root":{"id":"root","kind":"stack","props":{},"children":[
                {"id":"focus-panel","kind":"stack","props":{},"children":[
                    {"id":"focus-value","kind":"text","props":{"text":{"$path":"/focus/value"}}}
                ]},
                {"id":"tasks-panel","kind":"stack","props":{},"children":[
                    {"id":"tasks-value","kind":"text","props":{"text":{"$path":"/tasks/value"}}}
                ]}
            ]},
            "data":{"focus":{"value":"focus-secret"},"tasks":{"value":"tasks-secret"}}
        });
        let replaced = rpc(
            &mut owner,
            "replace",
            "scene.replace",
            json!({"world_id":world_id,"lease":lease,"expected_revision":initial_revision,"scene":scene}),
        )
        .await;
        assert_eq!(replaced["ok"], true);

        let partitioned = rpc(
            &mut owner,
            "partition",
            "scope.partition",
            json!({
                "world_id":world_id,
                "lease":lease,
                "expected_revision":replaced["result"]["revision"],
                "scopes":[
                    {"root_node_id":"focus-panel","data_namespace":"focus"},
                    {"root_node_id":"tasks-panel","data_namespace":"tasks"}
                ]
            }),
        )
        .await;
        assert_eq!(partitioned["ok"], true);
        let grants = partitioned["result"]["scopes"].as_array().unwrap();
        let focus = grants
            .iter()
            .find(|grant| grant["root_node_id"] == "focus-panel")
            .unwrap();
        let tasks = grants
            .iter()
            .find(|grant| grant["root_node_id"] == "tasks-panel")
            .unwrap();
        let vacant_tasks_status = rpc(
            &mut owner,
            "tasks-status-vacant",
            "scope.status",
            json!({
                "world_id":world_id,
                "scope_id":tasks["scope_id"],
                "generation":tasks["generation"]
            }),
        )
        .await;
        assert_eq!(vacant_tasks_status["ok"], true);
        assert_eq!(vacant_tasks_status["result"]["status"], "vacant");
        assert!(vacant_tasks_status["result"].get("data").is_none());
        assert!(vacant_tasks_status["result"].get("writer").is_none());

        let focus_join = rpc(
            &mut owner,
            "focus-join",
            "scope.join",
            json!({
                "world_id":world_id,
                "scope_id":focus["scope_id"],
                "generation":focus["generation"],
                "join_key":focus["join_key"],
                "mode":"write"
            }),
        )
        .await;
        assert_eq!(focus_join["ok"], true);
        let focus_lease = focus_join["result"]["lease"].clone();

        let (mut tasks_provider, _) = connect_test_provider_with_protocol(
            &server.descriptor,
            "scope.tasks",
            COMPONENT_LEASES_PREVIEW_PROTOCOL,
        )
        .await;
        let tasks_join = rpc(
            &mut tasks_provider,
            "tasks-join",
            "scope.join",
            json!({
                "world_id":world_id,
                "scope_id":tasks["scope_id"],
                "generation":tasks["generation"],
                "join_key":tasks["join_key"],
                "mode":"write"
            }),
        )
        .await;
        assert_eq!(tasks_join["ok"], true);
        let tasks_lease = tasks_join["result"]["lease"].clone();
        let active_tasks_status = rpc(
            &mut owner,
            "tasks-status-online",
            "scope.status",
            json!({
                "world_id":world_id,
                "scope_id":tasks["scope_id"],
                "generation":tasks["generation"]
            }),
        )
        .await;
        assert_eq!(active_tasks_status["ok"], true);
        assert_eq!(active_tasks_status["result"]["status"], "online");

        let (mut observer, _) = connect_test_provider_with_protocol(
            &server.descriptor,
            "scope.observer",
            COMPONENT_LEASES_PREVIEW_PROTOCOL,
        )
        .await;
        let observer_join = rpc(
            &mut observer,
            "observer-join",
            "scope.join",
            json!({
                "world_id":world_id,
                "scope_id":focus["scope_id"],
                "generation":focus["generation"],
                "join_key":focus["join_key"],
                "mode":"read"
            }),
        )
        .await;
        assert_eq!(observer_join["ok"], true);
        let sibling_status = rpc(
            &mut observer,
            "sibling-status-forbidden",
            "scope.status",
            json!({
                "world_id":world_id,
                "scope_id":tasks["scope_id"],
                "generation":tasks["generation"]
            }),
        )
        .await;
        assert_eq!(sibling_status["ok"], false);
        assert_eq!(sibling_status["error"]["code"], "FORBIDDEN");
        let scope_projection = serde_json::to_string(&observer_join["result"]["snapshot"]).unwrap();
        assert!(scope_projection.contains("focus-secret"));
        assert!(!scope_projection.contains("tasks-secret"));
        assert!(!scope_projection.contains("tasks-panel"));

        let focus_slot = rpc(
            &mut owner,
            "focus-slot-create",
            "state.slot.create",
            json!({
                "world_id":world_id,
                "lease":focus_lease,
                "name":"focus.progress",
                "schema":{"type":"integer","min":0,"max":100},
                "initial_value":10,
                "reader_scopes":[{"scope_id":tasks["scope_id"],"generation":tasks["generation"]}]
            }),
        )
        .await;
        assert_eq!(focus_slot["ok"], true);
        let focus_slot_id = focus_slot["result"]["slot_id"].as_str().unwrap();
        let focus_slot_generation = focus_slot["result"]["generation"].as_u64().unwrap();
        let focus_slot_revision = focus_slot["result"]["revision"].as_u64().unwrap();

        let unjoined_slot_read = rpc(
            &mut observer,
            "slot-read-before-scope-join",
            "state.slot.read",
            json!({
                "world_id":world_id,
                "slot_id":focus_slot_id,
                "generation":focus_slot_generation,
                "reader_scope_id":tasks["scope_id"],
                "reader_scope_generation":tasks["generation"]
            }),
        )
        .await;
        assert_eq!(unjoined_slot_read["ok"], false);
        assert_eq!(unjoined_slot_read["error"]["code"], "FORBIDDEN");

        let observer_tasks_join = rpc(
            &mut observer,
            "observer-tasks-join",
            "scope.join",
            json!({
                "world_id":world_id,
                "scope_id":tasks["scope_id"],
                "generation":tasks["generation"],
                "join_key":tasks["join_key"],
                "mode":"read"
            }),
        )
        .await;
        assert_eq!(observer_tasks_join["ok"], true);
        let slot_read = rpc(
            &mut observer,
            "slot-read-authorized",
            "state.slot.read",
            json!({
                "world_id":world_id,
                "slot_id":focus_slot_id,
                "generation":focus_slot_generation,
                "reader_scope_id":tasks["scope_id"],
                "reader_scope_generation":tasks["generation"]
            }),
        )
        .await;
        assert_eq!(slot_read["ok"], true);
        assert_eq!(slot_read["result"]["value"], 10);

        let winning_cas = rpc(
            &mut owner,
            "focus-slot-cas",
            "state.slot.compare_and_set",
            json!({
                "world_id":world_id,
                "lease":focus_lease,
                "slot_id":focus_slot_id,
                "generation":focus_slot_generation,
                "expected_revision":focus_slot_revision,
                "value":20
            }),
        )
        .await;
        assert_eq!(winning_cas["ok"], true);
        let stale_cas = rpc(
            &mut owner,
            "focus-slot-stale-cas",
            "state.slot.compare_and_set",
            json!({
                "world_id":world_id,
                "lease":focus_lease,
                "slot_id":focus_slot_id,
                "generation":focus_slot_generation,
                "expected_revision":focus_slot_revision,
                "value":30
            }),
        )
        .await;
        assert_eq!(stale_cas["ok"], false);
        assert_eq!(stale_cas["error"]["code"], "STATE_REVISION_CONFLICT");
        let foreign_cas = rpc(
            &mut tasks_provider,
            "foreign-slot-cas",
            "state.slot.compare_and_set",
            json!({
                "world_id":world_id,
                "lease":tasks_lease,
                "slot_id":focus_slot_id,
                "generation":focus_slot_generation,
                "expected_revision":winning_cas["result"]["revision"],
                "value":30
            }),
        )
        .await;
        assert_eq!(foreign_cas["ok"], false);
        assert_eq!(foreign_cas["error"]["code"], "STATE_SLOT_FORBIDDEN");
        let invalid_slot_value = rpc(
            &mut owner,
            "focus-slot-invalid-value",
            "state.slot.compare_and_set",
            json!({
                "world_id":world_id,
                "lease":focus_lease,
                "slot_id":focus_slot_id,
                "generation":focus_slot_generation,
                "expected_revision":winning_cas["result"]["revision"],
                "value":"not an integer"
            }),
        )
        .await;
        assert_eq!(invalid_slot_value["ok"], false);
        assert_eq!(
            invalid_slot_value["error"]["code"],
            "INVALID_STATE_SLOT_VALUE"
        );

        let tasks_slot = rpc(
            &mut tasks_provider,
            "tasks-slot-create",
            "state.slot.create",
            json!({
                "world_id":world_id,
                "lease":tasks_lease,
                "name":"tasks.available",
                "schema":{"type":"boolean"},
                "initial_value":true,
                "reader_scopes":[{"scope_id":focus["scope_id"],"generation":focus["generation"]}]
            }),
        )
        .await;
        assert_eq!(tasks_slot["ok"], true);
        let tasks_slot_read = rpc(
            &mut observer,
            "tasks-slot-read",
            "state.slot.read",
            json!({
                "world_id":world_id,
                "slot_id":tasks_slot["result"]["slot_id"],
                "generation":tasks_slot["result"]["generation"],
                "reader_scope_id":focus["scope_id"],
                "reader_scope_generation":focus["generation"]
            }),
        )
        .await;
        assert_eq!(tasks_slot_read["ok"], true);

        let temporary_slot = rpc(
            &mut owner,
            "temporary-slot-create",
            "state.slot.create",
            json!({
                "world_id":world_id,
                "lease":focus_lease,
                "name":"focus.temporary",
                "schema":{"type":"boolean"},
                "initial_value":false
            }),
        )
        .await;
        assert_eq!(temporary_slot["ok"], true);
        let temporary_slot_delete = rpc(
            &mut owner,
            "temporary-slot-delete",
            "state.slot.delete",
            json!({
                "world_id":world_id,
                "lease":focus_lease,
                "slot_id":temporary_slot["result"]["slot_id"],
                "generation":temporary_slot["result"]["generation"],
                "expected_revision":temporary_slot["result"]["revision"]
            }),
        )
        .await;
        assert_eq!(temporary_slot_delete["ok"], true);

        let revoke_slot_reader = rpc(
            &mut owner,
            "focus-slot-revoke-reader",
            "state.slot.set_readers",
            json!({
                "world_id":world_id,
                "lease":focus_lease,
                "slot_id":focus_slot_id,
                "generation":focus_slot_generation,
                "expected_revision":winning_cas["result"]["revision"],
                "reader_scopes":[]
            }),
        )
        .await;
        assert_eq!(revoke_slot_reader["ok"], true);
        let revoked_slot_read = rpc(
            &mut observer,
            "slot-read-after-grant-revocation",
            "state.slot.read",
            json!({
                "world_id":world_id,
                "slot_id":focus_slot_id,
                "generation":focus_slot_generation,
                "reader_scope_id":tasks["scope_id"],
                "reader_scope_generation":tasks["generation"]
            }),
        )
        .await;
        assert_eq!(revoked_slot_read["ok"], false);
        assert_eq!(revoked_slot_read["error"]["code"], "STATE_SLOT_FORBIDDEN");

        let observer_scope_revision = observer_join["result"]["snapshot"]["revision"]
            .as_u64()
            .unwrap();
        let full_snapshot = rpc(
            &mut observer,
            "observer-world-read",
            "world.snapshot",
            json!({"world_id":world_id}),
        )
        .await;
        assert_eq!(full_snapshot["ok"], false);
        assert_eq!(full_snapshot["error"]["code"], "SCOPE_REQUIRED");

        let focus_update = rpc(
            &mut owner,
            "focus-update",
            "scope.patch",
            json!({
                "world_id":world_id,
                "lease":focus_lease,
                "expected_scope_revision":focus_join["result"]["snapshot"]["revision"],
                "ops":[{"op":"props","node_id":"focus-value","props":{"text":"Focus updated"}}]
            }),
        )
        .await;
        assert_eq!(focus_update["ok"], true);
        let live_scope_snapshot = next_event_matching(&mut observer, "scope.snapshot", |event| {
            event.pointer("/data/scope_id").and_then(Value::as_str) == focus["scope_id"].as_str()
                && event
                    .pointer("/data/revision")
                    .and_then(Value::as_u64)
                    .is_some_and(|revision| revision > observer_scope_revision)
        })
        .await;
        assert_eq!(
            live_scope_snapshot.pointer("/data/root/children/0/props/text"),
            Some(&json!("Focus updated"))
        );
        let live_projection = serde_json::to_string(&live_scope_snapshot["data"]).unwrap();
        assert!(live_projection.contains("focus-secret"));
        assert!(!live_projection.contains("tasks-secret"));
        let tasks_update = rpc(
            &mut tasks_provider,
            "tasks-update",
            "scope.patch",
            json!({
                "world_id":world_id,
                "lease":tasks_lease.clone(),
                "expected_scope_revision":tasks_join["result"]["snapshot"]["revision"],
                "ops":[{"op":"props","node_id":"tasks-value","props":{"text":"Tasks updated"}}]
            }),
        )
        .await;
        assert_eq!(tasks_update["ok"], true);

        let current_parent = rpc(
            &mut owner,
            "parent-snapshot-before-remove",
            "world.snapshot",
            json!({"world_id":world_id}),
        )
        .await;
        let removed_parent = rpc(
            &mut owner,
            "parent-remove-tasks",
            "scope.structure.patch",
            json!({
                "world_id":world_id,
                "authority_lease":partitioned["result"]["authority_lease"],
                "expected_revision":current_parent["result"]["revision"],
                "ops":[{"op":"remove","node_id":"tasks-panel"}]
            }),
        )
        .await;
        assert_eq!(removed_parent["ok"], true);
        {
            let core = hub.lock();
            let world = &core.worlds[&world_id.parse().unwrap()];
            let tasks_slot_id = tasks_slot["result"]["slot_id"].as_str().unwrap();
            assert!(!world
                .state_slots
                .values()
                .any(|slot| slot.id.to_string() == tasks_slot_id));
            let retained_focus_slot = world
                .state_slots
                .values()
                .find(|slot| slot.name == "focus.progress")
                .unwrap();
            let tasks_scope_id =
                uuid::Uuid::parse_str(tasks["scope_id"].as_str().unwrap()).unwrap();
            assert!(!retained_focus_slot
                .reader_scopes
                .contains_key(&tasks_scope_id));
        }
        assert!(removed_parent["result"]["scene"]["data"]
            .get("tasks")
            .is_none());
        assert!(removed_parent["result"]["scene"]["root"]["children"]
            .as_array()
            .unwrap()
            .iter()
            .all(|node| node["id"] != "tasks-panel"));
        let revoked_tasks_status = rpc(
            &mut owner,
            "tasks-status-revoked",
            "scope.status",
            json!({
                "world_id":world_id,
                "scope_id":tasks["scope_id"],
                "generation":tasks["generation"]
            }),
        )
        .await;
        assert_eq!(revoked_tasks_status["ok"], true);
        assert_eq!(revoked_tasks_status["result"]["status"], "revoked");
        assert_eq!(
            revoked_tasks_status["result"]["current_generation"],
            Value::Null
        );
        let focus_status_after_sibling_revoke = rpc(
            &mut owner,
            "focus-status-after-sibling-revocation",
            "scope.status",
            json!({
                "world_id":world_id,
                "scope_id":focus["scope_id"],
                "generation":focus["generation"]
            }),
        )
        .await;
        assert_eq!(focus_status_after_sibling_revoke["ok"], true);
        assert_eq!(
            focus_status_after_sibling_revoke["result"]["status"],
            "online"
        );
        let revoked_event = next_event_matching(&mut tasks_provider, "scope.revoked", |event| {
            event.pointer("/data/scope_id").and_then(Value::as_str) == tasks["scope_id"].as_str()
        })
        .await;
        assert_eq!(revoked_event["data"]["reason"], "parent_structure_removed");
        let stale_tasks_patch = rpc(
            &mut tasks_provider,
            "tasks-after-parent-remove",
            "scope.patch",
            json!({
                "world_id":world_id,
                "lease":tasks_lease,
                "expected_scope_revision":tasks_update["result"]["revision"],
                "ops":[{"op":"props","node_id":"tasks-value","props":{"text":"must be rejected"}}]
            }),
        )
        .await;
        assert_eq!(stale_tasks_patch["ok"], false);
        assert_eq!(stale_tasks_patch["error"]["code"], "STALE_SCOPE");

        let (mut legacy, _) =
            connect_test_provider(&server.descriptor, "legacy.scope-client").await;
        let legacy_capabilities = rpc(
            &mut legacy,
            "legacy-capabilities",
            "host.capabilities",
            json!({}),
        )
        .await;
        assert_eq!(legacy_capabilities["result"]["component_leases"], false);
        let legacy_status = rpc(
            &mut legacy,
            "legacy-scope-status",
            "scope.status",
            json!({
                "world_id":world_id,
                "scope_id":focus["scope_id"],
                "generation":focus["generation"]
            }),
        )
        .await;
        assert_eq!(legacy_status["ok"], false);
        assert_eq!(legacy_status["error"]["code"], "PROTOCOL_MISMATCH");
        let legacy_join = rpc(
            &mut legacy,
            "legacy-join",
            "world.join",
            json!({"world_id":world_id,"join_key":world_join_key,"mode":"write"}),
        )
        .await;
        assert_eq!(legacy_join["ok"], false);
        assert_eq!(legacy_join["error"]["code"], "SCOPE_REQUIRED");

        let composed = hub.renderer_snapshot(world_id.parse().unwrap()).unwrap();
        assert_eq!(
            composed.scene.root.find("focus-value").unwrap().props["text"],
            "Focus updated"
        );
        assert!(composed.scene.root.find("tasks-value").is_none());
        server.shutdown().await;
    }

    #[tokio::test]
    async fn scoped_interaction_event_and_ack_are_bound_to_the_component_scope_writer() {
        let runtime_dir =
            std::env::temp_dir().join(format!("wincraft-scope-action-{}", Uuid::new_v4()));
        let _cleanup = TestRuntimeDirectory(runtime_dir.clone());
        let hub = Hub::new(false);
        let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap(), &runtime_dir)
            .await
            .expect("loopback server starts");
        let (mut authority, _) = connect_test_provider_with_protocol(
            &server.descriptor,
            "scope-action-authority",
            COMPONENT_LEASES_PREVIEW_PROTOCOL,
        )
        .await;
        let (mut focus, _) = connect_test_provider_with_protocol(
            &server.descriptor,
            "scope-action-focus",
            COMPONENT_LEASES_PREVIEW_PROTOCOL,
        )
        .await;
        let (mut tasks, _) = connect_test_provider_with_protocol(
            &server.descriptor,
            "scope-action-tasks",
            COMPONENT_LEASES_PREVIEW_PROTOCOL,
        )
        .await;
        let (mut stable, _) =
            connect_test_provider(&server.descriptor, "scope-action-stable-03").await;

        let capabilities = rpc(&mut focus, "caps", "host.capabilities", json!({})).await;
        assert_eq!(
            capabilities["result"]["component_leases"]["scope_interactions"]["version"],
            1
        );
        let created = rpc(
            &mut authority,
            "create",
            "world.create",
            json!({"window":{"title":"synthetic scope action"},"claim":true}),
        )
        .await;
        let world_id = created["result"]["world"]["id"].as_str().unwrap();
        let world_id_uuid = world_id.parse::<Uuid>().unwrap();
        let world_lease = created["result"]["lease"].clone();
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
        let replaced = rpc(
            &mut authority,
            "replace",
            "scene.replace",
            json!({
                "world_id":world_id,
                "lease":world_lease,
                "expected_revision":created["result"]["world"]["revision"],
                "scene":scene
            }),
        )
        .await;
        assert_eq!(replaced["ok"], true);
        let partitioned = rpc(
            &mut authority,
            "partition",
            "scope.partition",
            json!({
                "world_id":world_id,
                "lease":world_lease,
                "expected_revision":replaced["result"]["revision"],
                "scopes":[
                    {"root_node_id":"focus-panel","data_namespace":"focus"},
                    {"root_node_id":"tasks-panel","data_namespace":"tasks"}
                ]
            }),
        )
        .await;
        assert_eq!(partitioned["ok"], true);
        let grants = partitioned["result"]["scopes"].as_array().unwrap();
        let focus_grant = grants
            .iter()
            .find(|grant| grant["root_node_id"] == "focus-panel")
            .unwrap();
        let tasks_grant = grants
            .iter()
            .find(|grant| grant["root_node_id"] == "tasks-panel")
            .unwrap();
        let focus_join = rpc(
            &mut focus,
            "join-focus",
            "scope.join",
            json!({
                "world_id":world_id,
                "scope_id":focus_grant["scope_id"],
                "generation":focus_grant["generation"],
                "join_key":focus_grant["join_key"],
                "mode":"write"
            }),
        )
        .await;
        let tasks_join = rpc(
            &mut tasks,
            "join-tasks",
            "scope.join",
            json!({
                "world_id":world_id,
                "scope_id":tasks_grant["scope_id"],
                "generation":tasks_grant["generation"],
                "join_key":tasks_grant["join_key"],
                "mode":"write"
            }),
        )
        .await;
        assert_eq!(focus_join["ok"], true);
        assert_eq!(tasks_join["ok"], true);

        let current = hub.renderer_snapshot(world_id_uuid).unwrap();
        let event_id = hub
            .interact_with_source(
                world_id_uuid,
                "focus-action",
                Value::Null,
                wincraft_core::InteractionSource::Click,
                current.revision,
            )
            .unwrap();
        let event = next_event_matching(&mut focus, "scope.interaction", |message| {
            message["data"]["id"] == event_id.to_string()
        })
        .await;
        assert_eq!(event["data"]["scope_id"], focus_grant["scope_id"]);
        assert_eq!(event["data"]["scope_generation"], focus_grant["generation"]);
        assert_eq!(event["data"]["component_id"], "focus-action");
        assert_eq!(event["data"]["action"], "focus.refresh");

        let wrong_owner_ack = rpc(
            &mut tasks,
            "wrong-owner-ack",
            "scope.action.result",
            json!({
                "world_id":world_id,
                "lease":tasks_join["result"]["lease"],
                "event_id":event_id,
                "ok":true
            }),
        )
        .await;
        assert_eq!(wrong_owner_ack["ok"], false);
        assert_eq!(wrong_owner_ack["error"]["code"], "SCOPE_ACTION_FORBIDDEN");

        let stable_capabilities =
            rpc(&mut stable, "stable-caps", "host.capabilities", json!({})).await;
        assert_eq!(stable_capabilities["result"]["component_leases"], false);
        let stable_ack = rpc(
            &mut stable,
            "stable-ack",
            "scope.action.result",
            json!({
                "world_id":world_id,
                "lease":focus_join["result"]["lease"],
                "event_id":event_id,
                "ok":true
            }),
        )
        .await;
        assert_eq!(stable_ack["ok"], false);
        assert_eq!(stable_ack["error"]["code"], "PROTOCOL_MISMATCH");

        let acknowledged = rpc(
            &mut focus,
            "owner-ack",
            "scope.action.result",
            json!({
                "world_id":world_id,
                "lease":focus_join["result"]["lease"],
                "event_id":event_id,
                "ok":true,
                "message":"synthetic focus update"
            }),
        )
        .await;
        assert_eq!(acknowledged["ok"], true);
        let action = hub
            .renderer_snapshot(world_id_uuid)
            .unwrap()
            .actions
            .into_iter()
            .find(|action| action.id == event_id)
            .unwrap();
        assert_eq!(action.status, "ok");
        assert_eq!(action.message.as_deref(), Some("synthetic focus update"));

        let authority_lease = partitioned["result"]["authority_lease"].clone();
        let destroyed = rpc(
            &mut authority,
            "destroy",
            "world.destroy",
            json!({"world_id":world_id,"lease":authority_lease}),
        )
        .await;
        assert_eq!(destroyed["ok"], true);
        authority.close(None).await.expect("authority closes");
        focus.close(None).await.expect("focus writer closes");
        tasks.close(None).await.expect("tasks writer closes");
        stable.close(None).await.expect("stable provider closes");
        server.shutdown().await;
    }

    #[tokio::test]
    async fn dropping_server_stops_loopback_listener_and_removes_descriptor() {
        let runtime_dir =
            std::env::temp_dir().join(format!("wincraft-server-drop-{}", Uuid::new_v4()));
        let _cleanup = TestRuntimeDirectory(runtime_dir.clone());
        let server = start(
            Hub::new(false),
            "127.0.0.1:0".parse().unwrap(),
            &runtime_dir,
        )
        .await
        .expect("loopback server starts");
        let address: SocketAddr = server
            .descriptor
            .http_url
            .strip_prefix("http://")
            .expect("HTTP URL prefix")
            .parse()
            .expect("server address");
        let descriptor_file = server.file.clone();

        drop(server);

        assert!(!descriptor_file.exists(), "descriptor is removed on drop");
        for _ in 0..20 {
            if tokio::net::TcpStream::connect(address).await.is_err() {
                return;
            }
            tokio::time::sleep(Duration::from_millis(25)).await;
        }
        panic!("loopback listener remained open after RunningServer drop");
    }
}
