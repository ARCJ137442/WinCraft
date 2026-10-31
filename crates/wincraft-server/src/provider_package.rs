//! Safe preview and installation for user-confirmed Provider bundles.
//!
//! A Provider bundle is deliberately distinct from a configuration pack: it may
//! contain code, but this module only validates and copies files. It never runs
//! anything. The desktop host owns the separate, explicit launch confirmation.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions},
    io::{Read, Seek},
    path::{Component, Path, PathBuf},
};
use uuid::Uuid;
use wincraft_core::Fault;
use zip::ZipArchive;

const MANIFEST_PATH: &str = "wincraft-provider.json";
const SCHEMA_VERSION: &str = "1";
const MAX_ARCHIVE_BYTES: u64 = 64 * 1024 * 1024;
const MAX_MANIFEST_BYTES: u64 = 1024 * 1024;
const MAX_ENTRY_BYTES: u64 = 32 * 1024 * 1024;
const MAX_EXPANDED_BYTES: u64 = 64 * 1024 * 1024;
const MAX_FILES: usize = 256;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ProviderRuntime {
    Python,
    Node,
    Native,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ProviderManifest {
    kind: String,
    schema_version: String,
    id: String,
    version: String,
    title: BTreeMap<String, String>,
    entrypoint: ProviderEntrypoint,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ProviderEntrypoint {
    runtime: ProviderRuntime,
    path: String,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct ProviderBundlePreview {
    pub id: String,
    pub version: String,
    pub title: String,
    pub runtime: ProviderRuntime,
    pub entrypoint: String,
    pub file_count: usize,
    pub expanded_bytes: u64,
    pub sha256: String,
    pub entrypoint_sha256: String,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct InstalledProviderBundle {
    pub id: String,
    pub version: String,
    pub title: String,
    pub runtime: ProviderRuntime,
    pub entrypoint: String,
    pub install_dir: PathBuf,
    pub sha256: String,
    pub entrypoint_sha256: String,
}

struct LoadedProviderBundle {
    preview: ProviderBundlePreview,
    files: BTreeMap<String, Vec<u8>>,
}

/// Validate a `.wcp` Provider bundle. This is read-only and cannot execute code.
pub fn preview_provider_bundle_file(path: &Path) -> Result<ProviderBundlePreview, Fault> {
    load_provider_bundle_file(path).map(|loaded| loaded.preview)
}

/// Install a previously previewed bundle after re-reading it and checking its
/// digest. Files are written to a private staging directory and atomically moved
/// into place; existing package versions are never overwritten.
pub fn install_provider_bundle_file(
    archive_path: &Path,
    store_root: &Path,
    expected_sha256: &str,
) -> Result<InstalledProviderBundle, Fault> {
    let loaded = load_provider_bundle_file(archive_path)?;
    if !constant_time_hex_eq(&loaded.preview.sha256, expected_sha256) {
        return Err(Fault::new(
            "PROVIDER_PACKAGE_CHANGED",
            "the package changed after preview; review it again",
        ));
    }

    fs::create_dir_all(store_root).map_err(|_| {
        Fault::new(
            "PROVIDER_PACKAGE_INSTALL_FAILED",
            "could not create Provider folder",
        )
    })?;
    let root_metadata = fs::symlink_metadata(store_root).map_err(|_| {
        Fault::new(
            "PROVIDER_PACKAGE_INSTALL_FAILED",
            "Provider folder is unavailable",
        )
    })?;
    if root_metadata.file_type().is_symlink() || !root_metadata.is_dir() {
        return Err(Fault::new(
            "PROVIDER_PACKAGE_INSTALL_FAILED",
            "Provider folder must be a regular local directory",
        ));
    }
    let root = store_root.canonicalize().map_err(|_| {
        Fault::new(
            "PROVIDER_PACKAGE_INSTALL_FAILED",
            "Provider folder is unavailable",
        )
    })?;
    let package_id_dir = root.join(&loaded.preview.id);
    match fs::symlink_metadata(&package_id_dir) {
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_dir() => {
            return Err(Fault::new(
                "PROVIDER_PACKAGE_INSTALL_FAILED",
                "Provider package folder must not be a link or file",
            ));
        }
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            fs::create_dir(&package_id_dir).map_err(|_| {
                Fault::new(
                    "PROVIDER_PACKAGE_INSTALL_FAILED",
                    "could not create Provider folder",
                )
            })?;
        }
        Err(_) => {
            return Err(Fault::new(
                "PROVIDER_PACKAGE_INSTALL_FAILED",
                "Provider package folder is unavailable",
            ));
        }
    }
    let destination = package_id_dir.join(&loaded.preview.version);
    if fs::symlink_metadata(&destination).is_ok() {
        return Err(Fault::new(
            "PROVIDER_PACKAGE_EXISTS",
            "this Provider version is already installed and will not be replaced",
        ));
    }
    let staging = package_id_dir.join(format!(".staging-{}", Uuid::new_v4()));
    fs::create_dir(&staging).map_err(|_| {
        Fault::new(
            "PROVIDER_PACKAGE_INSTALL_FAILED",
            "could not stage Provider files",
        )
    })?;

    let write_result = write_bundle_files(&staging, &loaded.files);
    if let Err(error) = write_result {
        let _ = fs::remove_dir_all(&staging);
        return Err(error);
    }
    if let Err(_error) = fs::rename(&staging, &destination) {
        let _ = fs::remove_dir_all(&staging);
        return Err(Fault::new(
            "PROVIDER_PACKAGE_INSTALL_FAILED",
            "could not activate the staged Provider folder",
        ));
    }

    Ok(InstalledProviderBundle {
        id: loaded.preview.id,
        version: loaded.preview.version,
        title: loaded.preview.title,
        runtime: loaded.preview.runtime,
        entrypoint: loaded.preview.entrypoint,
        install_dir: destination,
        sha256: loaded.preview.sha256,
        entrypoint_sha256: loaded.preview.entrypoint_sha256,
    })
}

/// Refuse to launch if the installed entrypoint changed after the user's review.
pub fn verify_installed_provider_entrypoint(bundle: &InstalledProviderBundle) -> Result<(), Fault> {
    let entrypoint = bundle.install_dir.join(&bundle.entrypoint);
    let metadata = fs::symlink_metadata(&entrypoint).map_err(|_| {
        Fault::new(
            "PROVIDER_ENTRYPOINT_CHANGED",
            "installed Provider entrypoint is unavailable",
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > MAX_ENTRY_BYTES
    {
        return Err(Fault::new(
            "PROVIDER_ENTRYPOINT_CHANGED",
            "installed Provider entrypoint is not a regular bounded file",
        ));
    }
    let bytes = fs::read(&entrypoint).map_err(|_| {
        Fault::new(
            "PROVIDER_ENTRYPOINT_CHANGED",
            "installed Provider entrypoint cannot be read",
        )
    })?;
    let digest = format!("{:x}", Sha256::digest(&bytes));
    if !constant_time_hex_eq(&digest, &bundle.entrypoint_sha256) {
        return Err(Fault::new(
            "PROVIDER_ENTRYPOINT_CHANGED",
            "installed Provider entrypoint changed after review; import and review it again",
        ));
    }
    Ok(())
}

fn load_provider_bundle_file(path: &Path) -> Result<LoadedProviderBundle, Fault> {
    let metadata = fs::symlink_metadata(path).map_err(|_| {
        Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "Provider package is unavailable",
        )
    })?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || !path
            .extension()
            .and_then(|value| value.to_str())
            .is_some_and(|extension| extension.eq_ignore_ascii_case("wcp"))
        || metadata.len() > MAX_ARCHIVE_BYTES
    {
        return Err(Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "choose a regular .wcp file no larger than 64 MiB",
        ));
    }
    let file = File::open(path).map_err(|_| {
        Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "Provider package is unavailable",
        )
    })?;
    load_provider_bundle_archive(file)
}

fn load_provider_bundle_archive<R: Read + Seek>(reader: R) -> Result<LoadedProviderBundle, Fault> {
    let mut archive = ZipArchive::new(reader).map_err(|_| {
        Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "Provider package archive is invalid",
        )
    })?;
    if archive.is_empty() || archive.len() > MAX_FILES {
        return Err(Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "Provider package must contain between 1 and 256 files",
        ));
    }

    let mut files = BTreeMap::new();
    let mut total = 0_u64;
    for index in 0..archive.len() {
        let mut entry = archive.by_index(index).map_err(|_| {
            Fault::new(
                "PROVIDER_PACKAGE_INVALID",
                "Provider package entry is invalid",
            )
        })?;
        let name = entry
            .name()
            .map_err(|_| {
                Fault::new(
                    "PROVIDER_PACKAGE_INVALID",
                    "Provider package path is invalid",
                )
            })?
            .into_owned();
        if entry.is_dir()
            || !safe_bundle_path(&name)
            || entry.size() > MAX_ENTRY_BYTES
            || (name == MANIFEST_PATH && entry.size() > MAX_MANIFEST_BYTES)
            || entry
                .unix_mode()
                .is_some_and(|mode| mode & 0o170000 != 0o100000)
        {
            return Err(Fault::new(
                "PROVIDER_PACKAGE_INVALID",
                "Provider package contains an unsafe, non-file, or oversized entry",
            ));
        }
        total = total.checked_add(entry.size()).ok_or_else(|| {
            Fault::new("PROVIDER_PACKAGE_INVALID", "Provider package is too large")
        })?;
        if total > MAX_EXPANDED_BYTES {
            return Err(Fault::new(
                "PROVIDER_PACKAGE_INVALID",
                "Provider package expands beyond 64 MiB",
            ));
        }
        let expected_len = entry.size();
        let mut bounded = (&mut entry).take(MAX_ENTRY_BYTES + 1);
        let mut bytes = Vec::with_capacity(expected_len as usize);
        bounded.read_to_end(&mut bytes).map_err(|_| {
            Fault::new(
                "PROVIDER_PACKAGE_INVALID",
                "Provider package entry cannot be read",
            )
        })?;
        if bytes.len() as u64 != expected_len || files.insert(name, bytes).is_some() {
            return Err(Fault::new(
                "PROVIDER_PACKAGE_INVALID",
                "Provider package has duplicate paths or inconsistent entry sizes",
            ));
        }
    }

    let manifest_bytes = files.remove(MANIFEST_PATH).ok_or_else(|| {
        Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "Provider package manifest is missing",
        )
    })?;
    let manifest: ProviderManifest = serde_json::from_slice(&manifest_bytes).map_err(|_| {
        Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "Provider package manifest is invalid",
        )
    })?;
    validate_manifest(&manifest, &files)?;
    let entrypoint_bytes = files
        .get(&manifest.entrypoint.path)
        .expect("validated Provider entrypoint is present");
    let entrypoint_sha256 = format!("{:x}", Sha256::digest(entrypoint_bytes));
    files.insert(MANIFEST_PATH.to_owned(), manifest_bytes);
    let title = manifest
        .title
        .get("zh-CN")
        .or_else(|| manifest.title.get("en-US"))
        .map(|title| title.trim().to_owned())
        .unwrap_or_default();
    if title.is_empty() || title.chars().count() > 120 {
        return Err(Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "Provider title must contain 1 to 120 characters",
        ));
    }

    let mut digest = Sha256::new();
    let mut archive_reader = archive.into_inner();
    archive_reader.rewind().map_err(|_| {
        Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "Provider package cannot be verified",
        )
    })?;
    let mut hash_reader = (&mut archive_reader).take(MAX_ARCHIVE_BYTES + 1);
    let mut raw = Vec::new();
    hash_reader.read_to_end(&mut raw).map_err(|_| {
        Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "Provider package cannot be verified",
        )
    })?;
    if raw.len() as u64 > MAX_ARCHIVE_BYTES {
        return Err(Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "Provider package exceeds the archive size limit",
        ));
    }
    digest.update(&raw);
    let sha256 = format!("{:x}", digest.finalize());

    Ok(LoadedProviderBundle {
        preview: ProviderBundlePreview {
            id: manifest.id,
            version: manifest.version,
            title,
            runtime: manifest.entrypoint.runtime,
            entrypoint: manifest.entrypoint.path,
            file_count: files.len(),
            expanded_bytes: total,
            sha256,
            entrypoint_sha256,
        },
        files,
    })
}

fn validate_manifest(
    manifest: &ProviderManifest,
    files: &BTreeMap<String, Vec<u8>>,
) -> Result<(), Fault> {
    if manifest.kind != "wincraft.provider-bundle"
        || manifest.schema_version != SCHEMA_VERSION
        || !valid_id(&manifest.id)
        || !valid_version(&manifest.version)
        || manifest.title.len() > 2
        || manifest
            .title
            .keys()
            .any(|locale| !matches!(locale.as_str(), "zh-CN" | "en-US"))
        || manifest
            .title
            .values()
            .any(|title| title.trim().is_empty() || title.chars().count() > 120)
        || !safe_bundle_path(&manifest.entrypoint.path)
        || !files.contains_key(&manifest.entrypoint.path)
        || !entrypoint_extension_matches(&manifest.entrypoint)
    {
        return Err(Fault::new(
            "PROVIDER_PACKAGE_INVALID",
            "Provider manifest fields or entrypoint do not match the supported contract",
        ));
    }
    Ok(())
}

fn valid_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value.as_bytes()[0].is_ascii_lowercase()
        && !value.ends_with('.')
        && !reserved_windows_component(value)
        && value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || b"._-".contains(&byte)
        })
}

fn valid_version(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 48
        && value != "."
        && value != ".."
        && !value.ends_with('.')
        && !reserved_windows_component(value)
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._-+".contains(&byte))
}

fn reserved_windows_component(value: &str) -> bool {
    let base = value
        .split('.')
        .next()
        .unwrap_or_default()
        .to_ascii_lowercase();
    matches!(base.as_str(), "con" | "prn" | "aux" | "nul")
        || (base.len() == 4
            && (base.starts_with("com") || base.starts_with("lpt"))
            && base.as_bytes()[3].is_ascii_digit()
            && base.as_bytes()[3] != b'0')
}

fn safe_bundle_path(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 240
        && !value.chars().any(|character| {
            character.is_control()
                || matches!(
                    character,
                    '\\' | ':' | '\0' | '<' | '>' | '|' | '?' | '*' | '"'
                )
        })
        && Path::new(value)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
        && !value.split('/').any(|part| part.is_empty())
        && !value.split('/').any(|part| {
            part.ends_with('.') || part.ends_with(' ') || reserved_windows_component(part)
        })
}

fn entrypoint_extension_matches(entrypoint: &ProviderEntrypoint) -> bool {
    let extension = Path::new(&entrypoint.path)
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default();
    match entrypoint.runtime {
        ProviderRuntime::Python => extension.eq_ignore_ascii_case("py"),
        ProviderRuntime::Node => {
            extension.eq_ignore_ascii_case("js") || extension.eq_ignore_ascii_case("mjs")
        }
        ProviderRuntime::Native => extension.eq_ignore_ascii_case("exe"),
    }
}

fn write_bundle_files(root: &Path, files: &BTreeMap<String, Vec<u8>>) -> Result<(), Fault> {
    for (relative, bytes) in files {
        if !safe_bundle_path(relative) {
            return Err(Fault::new(
                "PROVIDER_PACKAGE_INVALID",
                "Provider package contains an unsafe file path",
            ));
        }
        let path = root.join(relative);
        let parent = path.parent().ok_or_else(|| {
            Fault::new("PROVIDER_PACKAGE_INVALID", "Provider file path is invalid")
        })?;
        fs::create_dir_all(parent).map_err(|_| {
            Fault::new(
                "PROVIDER_PACKAGE_INSTALL_FAILED",
                "could not create Provider files",
            )
        })?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
            .map_err(|_| {
                Fault::new(
                    "PROVIDER_PACKAGE_INSTALL_FAILED",
                    "could not write Provider files",
                )
            })?;
        use std::io::Write;
        file.write_all(bytes).map_err(|_| {
            Fault::new(
                "PROVIDER_PACKAGE_INSTALL_FAILED",
                "could not write Provider files",
            )
        })?;
    }
    Ok(())
}

fn constant_time_hex_eq(left: &str, right: &str) -> bool {
    let left = left.as_bytes();
    let right = right.as_bytes();
    let mut difference = left.len() ^ right.len();
    for index in 0..left.len().max(right.len()) {
        difference |= usize::from(
            left.get(index).copied().unwrap_or_default()
                ^ right.get(index).copied().unwrap_or_default(),
        );
    }
    difference == 0
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Cursor, Write};
    use zip::write::SimpleFileOptions;

    fn archive(manifest: serde_json::Value, extras: &[(&str, &[u8])]) -> Vec<u8> {
        let cursor = Cursor::new(Vec::new());
        let mut writer = zip::ZipWriter::new(cursor);
        let options = SimpleFileOptions::default();
        writer
            .start_file(MANIFEST_PATH, options)
            .expect("manifest entry");
        writer
            .write_all(manifest.to_string().as_bytes())
            .expect("manifest bytes");
        for (name, bytes) in extras {
            writer.start_file(name, options).expect("payload entry");
            writer.write_all(bytes).expect("payload bytes");
        }
        writer.finish().expect("archive finish").into_inner()
    }

    fn manifest(path: &str, runtime: &str) -> serde_json::Value {
        serde_json::json!({
            "kind":"wincraft.provider-bundle",
            "schema_version":"1",
            "id":"sample-provider",
            "version":"1.0.0",
            "title":{"zh-CN":"示例提供者","en-US":"Sample Provider"},
            "entrypoint":{"runtime":runtime,"path":path}
        })
    }

    #[test]
    fn preview_only_reads_manifest_and_does_not_extract_or_execute() {
        let bytes = archive(
            manifest("main.py", "python"),
            &[("main.py", b"raise SystemExit(99)")],
        );
        let preview = load_provider_bundle_archive(Cursor::new(bytes))
            .expect("valid package previews")
            .preview;
        assert_eq!(preview.id, "sample-provider");
        assert_eq!(preview.entrypoint, "main.py");
        assert_eq!(preview.file_count, 2);
    }

    #[test]
    fn rejects_path_traversal_and_runtime_extension_mismatch() {
        let unsafe_package = archive(manifest("../main.py", "python"), &[("../main.py", b"x")]);
        assert!(load_provider_bundle_archive(Cursor::new(unsafe_package)).is_err());
        let mismatched = archive(manifest("main.exe", "python"), &[("main.exe", b"x")]);
        assert!(load_provider_bundle_archive(Cursor::new(mismatched)).is_err());
        let reserved = archive(manifest("con.py", "python"), &[("con.py", b"x")]);
        assert!(load_provider_bundle_archive(Cursor::new(reserved)).is_err());
    }

    #[test]
    fn rejects_oversized_manifest_before_deserialization() {
        let mut oversized = manifest("main.py", "python");
        oversized["title"]["en-US"] =
            serde_json::Value::String("x".repeat(MAX_MANIFEST_BYTES as usize + 1));
        let bytes = archive(oversized, &[("main.py", b"pass")]);
        assert_eq!(
            load_provider_bundle_archive(Cursor::new(bytes))
                .err()
                .expect("oversized manifest is rejected")
                .code,
            "PROVIDER_PACKAGE_INVALID"
        );
    }

    #[test]
    fn install_requires_unchanged_preview_digest_and_never_overwrites_version() {
        let bytes = archive(
            manifest("main.py", "python"),
            &[("main.py", b"print('safe test')")],
        );
        let dir = std::env::temp_dir().join(format!("wincraft-provider-test-{}", Uuid::new_v4()));
        fs::create_dir_all(&dir).expect("test root");
        let archive_path = dir.join("sample.wcp");
        fs::write(&archive_path, &bytes).expect("package write");
        let preview = preview_provider_bundle_file(&archive_path).expect("preview");
        assert_eq!(
            install_provider_bundle_file(&archive_path, &dir.join("providers"), "wrong-digest")
                .unwrap_err()
                .code,
            "PROVIDER_PACKAGE_CHANGED"
        );
        let installed =
            install_provider_bundle_file(&archive_path, &dir.join("providers"), &preview.sha256)
                .expect("install valid package");
        assert_eq!(
            fs::read(installed.install_dir.join("main.py")).unwrap(),
            b"print('safe test')"
        );
        verify_installed_provider_entrypoint(&installed).expect("entrypoint digest matches");
        fs::write(installed.install_dir.join("main.py"), b"print('changed')").unwrap();
        assert_eq!(
            verify_installed_provider_entrypoint(&installed)
                .unwrap_err()
                .code,
            "PROVIDER_ENTRYPOINT_CHANGED"
        );
        assert_eq!(
            install_provider_bundle_file(&archive_path, &dir.join("providers"), &preview.sha256)
                .unwrap_err()
                .code,
            "PROVIDER_PACKAGE_EXISTS"
        );
        fs::remove_dir_all(dir).expect("test cleanup");
    }

    #[test]
    #[ignore = "requires scripts/build_provider_bundle.py to create the local ignored target artifact"]
    fn generated_python_bundle_archive_is_accepted_by_the_host_parser() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/provider-bundles/wincraft-sample-provider.wcp");
        let preview = preview_provider_bundle_file(&path).expect("generated bundle is valid");
        assert_eq!(preview.id, "sample-click-counter");
        assert_eq!(preview.entrypoint, "main.py");
        assert_eq!(preview.runtime, ProviderRuntime::Python);
    }
}
