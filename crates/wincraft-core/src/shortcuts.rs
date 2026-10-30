use crate::{Fault, Result};
use std::collections::{BTreeMap, BTreeSet};
use uuid::Uuid;

const MAX_SHORTCUT_CHORD_BYTES: usize = 64;
const MAX_SHORTCUT_ACTION_BYTES: usize = 128;
const MAX_SHORTCUT_PARTS: usize = 5;
const MODIFIER_ORDER: [&str; 4] = ["ctrl", "alt", "shift", "win"];
/// System and common East Asian IME combinations must not be captured globally.
const RESERVED_SHORTCUTS: [&str; 10] = [
    "alt+tab",
    "ctrl+alt+delete",
    "ctrl+shift+escape",
    "ctrl+.",
    "ctrl+space",
    "shift+space",
    "win+l",
    "win+u",
    "win+space",
    "win+/",
];

/// Host-level shortcut intent. This registry deliberately does not listen for
/// keyboard input or call an OS API; the native adapter must perform an explicit
/// user-authorized registration later.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct ShortcutSpec {
    pub chord: String,
    pub action: String,
}

#[derive(Clone, Debug, Default)]
pub struct ShortcutRegistry {
    by_chord: BTreeMap<String, (Uuid, ShortcutSpec)>,
    by_session: BTreeMap<Uuid, BTreeSet<String>>,
}

impl ShortcutRegistry {
    pub fn register(&mut self, session: Uuid, spec: ShortcutSpec) -> Result<String> {
        let chord = validate(&spec)?;
        if self.by_chord.contains_key(&chord) {
            return Err(Fault::new(
                "SHORTCUT_CONFLICT",
                "shortcut is already registered",
            ));
        }
        let normalized_spec = ShortcutSpec {
            chord: chord.clone(),
            action: spec.action,
        };
        self.by_chord
            .insert(chord.clone(), (session, normalized_spec));
        self.by_session
            .entry(session)
            .or_default()
            .insert(chord.clone());
        Ok(chord)
    }

    pub fn unregister(&mut self, session: Uuid, chord: &str) -> Result<bool> {
        let chord = canonicalize_chord(chord)?;
        let Some((owner, _)) = self.by_chord.get(&chord) else {
            return Ok(false);
        };
        if *owner != session {
            return Err(Fault::new(
                "FORBIDDEN",
                "shortcut belongs to another session",
            ));
        }
        self.by_chord.remove(&chord);
        self.remove_session_chord(session, &chord);
        Ok(true)
    }

    pub fn revoke_session(&mut self, session: Uuid) -> usize {
        let chords = self.by_session.remove(&session).unwrap_or_default();
        let count = chords.len();
        for chord in chords {
            self.by_chord.remove(&chord);
        }
        count
    }

    pub fn contains(&self, chord: &str) -> bool {
        canonicalize_chord(chord).is_ok_and(|normalized| self.by_chord.contains_key(&normalized))
    }

    fn remove_session_chord(&mut self, session: Uuid, chord: &str) {
        if let Some(chords) = self.by_session.get_mut(&session) {
            chords.remove(chord);
            if chords.is_empty() {
                self.by_session.remove(&session);
            }
        }
    }
}

fn validate(spec: &ShortcutSpec) -> Result<String> {
    if spec.action.is_empty() || spec.action.len() > MAX_SHORTCUT_ACTION_BYTES {
        return Err(Fault::new(
            "INVALID_SHORTCUT",
            "shortcut action is outside bounds",
        ));
    }
    canonicalize_chord(&spec.chord)
}

fn canonicalize_chord(chord: &str) -> Result<String> {
    if chord.is_empty() || chord.len() > MAX_SHORTCUT_CHORD_BYTES {
        return Err(Fault::new("INVALID_SHORTCUT", "shortcut is outside bounds"));
    }
    let parts: Vec<&str> = chord.split('+').map(str::trim).collect();
    if !(2..=MAX_SHORTCUT_PARTS).contains(&parts.len()) || parts.iter().any(|part| part.is_empty())
    {
        return Err(Fault::new(
            "INVALID_SHORTCUT",
            "shortcut must contain one key and one or more modifiers",
        ));
    }

    let mut modifiers = BTreeSet::new();
    let mut key = None;
    for part in parts {
        let normalized = part.to_ascii_lowercase();
        let modifier = match normalized.as_str() {
            "ctrl" | "control" => Some("ctrl"),
            "alt" => Some("alt"),
            "shift" => Some("shift"),
            "win" | "windows" => Some("win"),
            _ => None,
        };
        if let Some(modifier) = modifier {
            if !modifiers.insert(modifier) {
                return Err(Fault::new(
                    "INVALID_SHORTCUT",
                    "shortcut modifiers must be unique",
                ));
            }
            continue;
        }
        if key.is_some() {
            return Err(Fault::new(
                "INVALID_SHORTCUT",
                "shortcut must contain exactly one non-modifier key",
            ));
        }
        key = Some(canonicalize_key(&normalized)?);
    }
    if modifiers.is_empty() {
        return Err(Fault::new(
            "INVALID_SHORTCUT",
            "shortcut must include a modifier",
        ));
    }
    let key = key.ok_or_else(|| {
        Fault::new(
            "INVALID_SHORTCUT",
            "shortcut must contain exactly one non-modifier key",
        )
    })?;
    let mut canonical_parts: Vec<&str> = MODIFIER_ORDER
        .into_iter()
        .filter(|modifier| modifiers.contains(modifier))
        .collect();
    canonical_parts.push(&key);
    let canonical = canonical_parts.join("+");
    if RESERVED_SHORTCUTS.contains(&canonical.as_str()) {
        return Err(Fault::new(
            "RESERVED_SHORTCUT",
            "shortcut is reserved by Windows",
        ));
    }
    Ok(canonical)
}

fn canonicalize_key(key: &str) -> Result<String> {
    if key.len() == 1 && key.is_ascii() && !key.as_bytes()[0].is_ascii_control() {
        return Ok(key.to_ascii_lowercase());
    }
    if let Some(number) = key
        .strip_prefix('f')
        .and_then(|value| value.parse::<u8>().ok())
    {
        if (1..=24).contains(&number) {
            return Ok(format!("f{number}"));
        }
    }
    let canonical = match key {
        "space" => "space",
        "enter" | "return" => "enter",
        "esc" | "escape" => "escape",
        "tab" => "tab",
        "backspace" => "backspace",
        "delete" | "del" => "delete",
        "insert" | "ins" => "insert",
        "home" => "home",
        "end" => "end",
        "pageup" | "pgup" => "pageup",
        "pagedown" | "pgdn" => "pagedown",
        "up" => "up",
        "down" => "down",
        "left" => "left",
        "right" => "right",
        "pause" => "pause",
        "printscreen" => "printscreen",
        _ => {
            return Err(Fault::new(
                "INVALID_SHORTCUT",
                "shortcut contains an unsupported key",
            ));
        }
    };
    Ok(canonical.into())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn spec(chord: &str) -> ShortcutSpec {
        ShortcutSpec {
            chord: chord.into(),
            action: "召回".into(),
        }
    }

    #[test]
    fn conflicts_do_not_replace_existing_owner() {
        let mut registry = ShortcutRegistry::default();
        let first = Uuid::new_v4();
        let second = Uuid::new_v4();
        registry
            .register(first, spec(" Ctrl + Shift + W "))
            .unwrap();
        assert_eq!(
            registry
                .register(second, spec("shift+control+w"))
                .unwrap_err()
                .code,
            "SHORTCUT_CONFLICT"
        );
        assert!(registry.contains("CTRL+Shift+W"));
        assert_eq!(
            registry
                .unregister(second, "Control + Shift + W")
                .unwrap_err()
                .code,
            "FORBIDDEN"
        );
        assert!(registry.unregister(first, "shift+ctrl+w").unwrap());
        assert!(!registry.contains("Ctrl+Shift+W"));
    }

    #[test]
    fn session_revoke_releases_all_shortcuts_without_touching_other_sessions() {
        let mut registry = ShortcutRegistry::default();
        let first = Uuid::new_v4();
        let second = Uuid::new_v4();
        registry.register(first, spec("Ctrl+Shift+W")).unwrap();
        registry.register(second, spec("Ctrl+Shift+T")).unwrap();
        assert_eq!(registry.revoke_session(first), 1);
        assert!(!registry.contains("Ctrl+Shift+W"));
        assert!(registry.contains("Ctrl+Shift+T"));
    }

    #[test]
    fn reserved_and_unmodified_shortcuts_fail_closed() {
        let mut registry = ShortcutRegistry::default();
        let session = Uuid::new_v4();
        assert_eq!(
            registry
                .register(session, spec(" Win + L "))
                .unwrap_err()
                .code,
            "RESERVED_SHORTCUT"
        );
        assert_eq!(
            registry
                .register(session, spec("CTRL + ALT + DELETE"))
                .unwrap_err()
                .code,
            "RESERVED_SHORTCUT"
        );
        assert_eq!(
            registry
                .register(session, spec("Ctrl + Shift + Esc"))
                .unwrap_err()
                .code,
            "RESERVED_SHORTCUT"
        );
        for reserved in ["Ctrl+.", "Ctrl+Space", "Shift+Space", "Win+Space", "Win+/"] {
            assert_eq!(
                registry.register(session, spec(reserved)).unwrap_err().code,
                "RESERVED_SHORTCUT",
                "system or IME shortcut should be reserved: {reserved}"
            );
        }
        assert_eq!(
            registry.register(session, spec("F12")).unwrap_err().code,
            "INVALID_SHORTCUT"
        );
        for malformed in ["Ctrl++W", "Ctrl+W+T", "Ctrl+Control+W", "Meta+W"] {
            assert_eq!(
                registry
                    .register(session, spec(malformed))
                    .unwrap_err()
                    .code,
                "INVALID_SHORTCUT",
                "malformed shortcut should fail closed: {malformed}"
            );
        }
    }
}
