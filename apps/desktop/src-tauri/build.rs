use std::{fs, path::PathBuf};

fn main() {
    let build_id_path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../dist/build-id.txt");
    println!("cargo:rerun-if-changed={}", build_id_path.display());
    let build_id = fs::read_to_string(&build_id_path).unwrap_or_else(|_| "unknown".into());
    let build_id = build_id.trim();
    let build_id =
        if !build_id.is_empty() && build_id.bytes().all(|byte| byte.is_ascii_alphanumeric()) {
            build_id
        } else {
            "unknown"
        };
    println!("cargo:rustc-env=WINCRAFT_BUILD_ID={build_id}");
    tauri_build::build()
}
