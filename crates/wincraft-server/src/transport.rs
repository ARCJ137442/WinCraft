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
    io::Write,
    net::SocketAddr,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};
use tokio::time::timeout;
use uuid::Uuid;
use wincraft_core::{Fault, MAX_PAYLOAD, PROTOCOL};

#[derive(Clone)]
struct Transport {
    hub: Hub,
    token: String,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Descriptor {
    pub protocol: String,
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
}
impl Drop for RunningServer {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.file);
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
        host_id: hub.host_id,
        http_url: format!("http://{addr}"),
        ws_url: format!("ws://{addr}/v1/ws"),
        token: token.clone(),
        pid: std::process::id(),
        native_windows: hub.native_windows,
    };
    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/discovery", get(discovery))
        .route("/v1/ws", get(upgrade))
        .with_state(Transport {
            hub: hub.clone(),
            token,
        });
    hub.start_housekeeping();
    tokio::spawn(async move {
        if let Err(e) = axum::serve(listener, app).await {
            eprintln!("WinCraft server stopped: {e}");
        }
    });
    std::fs::create_dir_all(runtime_dir)?;
    let file = runtime_dir.join(format!("{}.runtime.json", hub.host_id));
    write_descriptor(&file, &descriptor)?;
    // Descriptor contains a bearer credential. Log only its path, never its contents.
    eprintln!("WinCraft runtime descriptor: {}", file.display());
    Ok(RunningServer { descriptor, file })
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
    ws.max_message_size(MAX_PAYLOAD)
        .max_frame_size(MAX_PAYLOAD)
        .on_upgrade(move |socket| serve_socket(socket, t.hub))
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
async fn serve_socket(mut socket: WebSocket, hub: Hub) {
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
    if hello.protocol != PROTOCOL {
        let _ = send(
            &mut socket,
            json!({"id":req.id,"ok":false,"error":Fault::new("PROTOCOL_MISMATCH",PROTOCOL)}),
        )
        .await;
        return;
    }
    let sid_result = hub.lock().register(hello.provider_name, false);
    let sid = match sid_result {
        Ok(id) => id,
        Err(e) => {
            let _ = send(&mut socket, json!({"id":req.id,"ok":false,"error":e})).await;
            return;
        }
    };
    let mut events = hub.subscribe();
    if !send(&mut socket,json!({"id":req.id,"ok":true,"result":{"session_id":sid,"host_id":hub.host_id,"capabilities":hub.capabilities()}})).await{
        hub.disconnect(sid);return;
    }
    let mut idle = tokio::time::interval(Duration::from_secs(2));
    let mut last_seen = Instant::now();
    let mut rate_start = Instant::now();
    let mut count = 0u32;
    loop {
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
                        let reply=hub.reply(sid,request);
                        if !send(&mut socket,reply).await{break;}
                    },
                    Some(Ok(Message::Ping(_)))|Some(Ok(Message::Pong(_)))=>{last_seen=Instant::now();},
                    Some(Ok(Message::Close(_)))|None|Some(Err(_))=>break,
                    Some(Ok(Message::Binary(_)))=>break,
                }
            },
            notice=events.recv()=>{
                let outbound=match notice{
                    Ok(Notice::Changed(id))=>{
                        let snapshot=hub.lock().read(sid,id);
                        snapshot.ok().map(|s|json!({"event":"world.snapshot","data":s}))
                    },
                    Ok(Notice::Directed(target,event)) if target==sid=>Some(event),
                    Ok(Notice::Deleted{world_id,members}) if members.contains(&sid)=>Some(json!({"event":"world.deleted","world_id":world_id})),
                    Ok(_)=>None,
                    // Do not silently lose a human action. Fail the session; the provider must reconnect.
                    Err(tokio::sync::broadcast::error::RecvError::Lagged(_))=>{
                        let _=send(&mut socket,json!({"event":"resync_required","reason":"slow consumer; reconnect and reacquire"})).await;break;
                    },
                    Err(_)=>break,
                };
                if let Some(value)=outbound{if !send(&mut socket,value).await{break;}}
            },
            _=idle.tick()=>{if last_seen.elapsed()>Duration::from_secs(20){break;}}
        }
    }
    hub.disconnect(sid);
}
#[cfg(test)]
mod tests {
    use super::*;
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
}
