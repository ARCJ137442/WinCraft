use crate::{Fault, Result};
use std::collections::{BTreeMap, BTreeSet};
use uuid::Uuid;

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
    pub fn register(&mut self, session: Uuid, spec: ShortcutSpec) -> Result<()> {
        validate(&spec)?;
        if self.by_chord.contains_key(&spec.chord) {
            return Err(Fault::new(
                "SHORTCUT_CONFLICT",
                "shortcut is already registered",
            ));
        }
        self.by_chord
            .insert(spec.chord.clone(), (session, spec.clone()));
        self.by_session
            .entry(session)
            .or_default()
            .insert(spec.chord);
        Ok(())
    }

    pub fn unregister(&mut self, session: Uuid, chord: &str) -> Result<bool> {
        let Some((owner, _)) = self.by_chord.get(chord) else {
            return Ok(false);
        };
        if *owner != session {
            return Err(Fault::new(
                "FORBIDDEN",
                "shortcut belongs to another session",
            ));
        }
        self.by_chord.remove(chord);
        self.remove_session_chord(session, chord);
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
        self.by_chord.contains_key(chord)
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

fn validate(spec: &ShortcutSpec) -> Result<()> {
    if spec.chord.is_empty()
        || spec.chord.len() > 64
        || spec.action.is_empty()
        || spec.action.len() > 128
    {
        return Err(Fault::new(
            "INVALID_SHORTCUT",
            "shortcut or action is outside bounds",
        ));
    }
    let normalized = spec.chord.to_ascii_lowercase();
    let reserved = ["alt+tab", "ctrl+alt+delete", "win+l", "win+u"];
    if reserved.contains(&normalized.as_str()) {
        return Err(Fault::new(
            "RESERVED_SHORTCUT",
            "shortcut is reserved by Windows",
        ));
    }
    if !normalized.contains('+') {
        return Err(Fault::new(
            "INVALID_SHORTCUT",
            "shortcut must include a modifier",
        ));
    }
    Ok(())
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
        registry.register(first, spec("Ctrl+Shift+W")).unwrap();
        assert_eq!(
            registry
                .register(second, spec("Ctrl+Shift+W"))
                .unwrap_err()
                .code,
            "SHORTCUT_CONFLICT"
        );
        assert!(registry.contains("Ctrl+Shift+W"));
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
            registry.register(session, spec("Win+L")).unwrap_err().code,
            "RESERVED_SHORTCUT"
        );
        assert_eq!(
            registry.register(session, spec("F12")).unwrap_err().code,
            "INVALID_SHORTCUT"
        );
    }
}
