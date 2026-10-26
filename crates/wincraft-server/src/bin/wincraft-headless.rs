//! Tests the REAL Rust engine and network protocol without a desktop renderer.
use std::{net::SocketAddr, path::PathBuf};
use wincraft_server::{start, Hub};
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let bind: SocketAddr = std::env::var("WINCRAFT_BIND")
        .unwrap_or_else(|_| "127.0.0.1:0".into())
        .parse()?;
    let dir =
        PathBuf::from(std::env::var("WINCRAFT_RUNTIME_DIR").unwrap_or_else(|_| ".wincraft".into()));
    let _server = start(Hub::new(false), bind, &dir).await?;
    tokio::signal::ctrl_c().await?;
    Ok(())
}
