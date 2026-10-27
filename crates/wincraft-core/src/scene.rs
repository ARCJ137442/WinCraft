use crate::{Fault, Result, MAX_PAYLOAD};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::{HashMap, HashSet};

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    Stack,
    Row,
    Text,
    Metric,
    Progress,
    Badge,
    Button,
    Input,
    #[serde(rename = "textarea")]
    TextArea,
    KeyValue,
    Icon,
    BarChart,
    Divider,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum InteractionSource {
    Click,
    ContextMenu,
    Escape,
    ControlEnter,
}
impl Kind {
    pub fn container(self) -> bool {
        matches!(self, Self::Stack | Self::Row)
    }
    pub fn interactive(self) -> bool {
        matches!(self, Self::Button | Self::Input | Self::TextArea)
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Node {
    pub id: String,
    pub kind: Kind,
    #[serde(default)]
    pub props: Map<String, Value>,
    #[serde(default)]
    pub children: Vec<Node>,
}
impl Node {
    pub fn new(id: &str, kind: Kind, props: Value, children: Vec<Node>) -> Self {
        Self {
            id: id.into(),
            kind,
            props: props.as_object().cloned().unwrap_or_default(),
            children,
        }
    }
    pub fn find(&self, id: &str) -> Option<&Node> {
        if self.id == id {
            return Some(self);
        }
        self.children.iter().find_map(|x| x.find(id))
    }
    pub fn find_mut(&mut self, id: &str) -> Option<&mut Node> {
        if self.id == id {
            return Some(self);
        }
        self.children.iter_mut().find_map(|x| x.find_mut(id))
    }
    fn take(&mut self, id: &str) -> Option<Node> {
        if let Some(i) = self.children.iter().position(|n| n.id == id) {
            return Some(self.children.remove(i));
        }
        self.children.iter_mut().find_map(|n| n.take(id))
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ThemeTokens {
    pub background: String,
    pub foreground: String,
    pub accent: String,
    pub font_scale: f64,
    pub radius_px: u8,
    pub spacing_px: u8,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum NativeWindowApplication {
    Obsidian,
    TrafficMonitor,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct NativeWindowAction {
    pub application: NativeWindowApplication,
    pub operation: NativeWindowOperation,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title_contains: Option<String>,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum NativeWindowOperation {
    Activate,
    Maximize,
    Minimize,
    Restore,
}

impl ThemeTokens {
    pub fn validate(&self) -> Result<()> {
        if !self.font_scale.is_finite() || !(0.9..=2.0).contains(&self.font_scale) {
            return Err(Fault::new(
                "INVALID_SCENE",
                "theme font_scale must be finite and within 0.9..=2.0",
            ));
        }
        if self.radius_px > 32 || self.spacing_px > 32 {
            return Err(Fault::new(
                "INVALID_SCENE",
                "theme radius_px and spacing_px must be within 0..=32",
            ));
        }

        let background = parse_theme_color(&self.background)?;
        let foreground = parse_theme_color(&self.foreground)?;
        let accent = parse_theme_color(&self.accent)?;
        if contrast_ratio(background, foreground) < 4.5 {
            return Err(Fault::new(
                "INVALID_SCENE",
                "theme foreground/background contrast must be at least 4.5:1",
            ));
        }
        if contrast_ratio(background, accent) < 4.5 {
            return Err(Fault::new(
                "INVALID_SCENE",
                "theme accent/background contrast must be at least 4.5:1",
            ));
        }
        Ok(())
    }
}

fn parse_theme_color(value: &str) -> Result<[f64; 3]> {
    let bytes = value.as_bytes();
    if bytes.len() != 7 || bytes[0] != b'#' {
        return Err(Fault::new(
            "INVALID_SCENE",
            "theme colors must use the #RRGGBB format",
        ));
    }
    let mut channels = [0.0; 3];
    for (index, channel) in channels.iter_mut().enumerate() {
        let start = 1 + index * 2;
        let high = theme_hex_nibble(bytes[start])?;
        let low = theme_hex_nibble(bytes[start + 1])?;
        let srgb = f64::from(high * 16 + low) / 255.0;
        *channel = if srgb <= 0.04045 {
            srgb / 12.92
        } else {
            ((srgb + 0.055) / 1.055).powf(2.4)
        };
    }
    Ok(channels)
}

fn theme_hex_nibble(value: u8) -> Result<u8> {
    match value {
        b'0'..=b'9' => Ok(value - b'0'),
        b'a'..=b'f' => Ok(value - b'a' + 10),
        b'A'..=b'F' => Ok(value - b'A' + 10),
        _ => Err(Fault::new(
            "INVALID_SCENE",
            "theme colors must use the #RRGGBB format",
        )),
    }
}

fn contrast_ratio(first: [f64; 3], second: [f64; 3]) -> f64 {
    let luminance = |rgb: [f64; 3]| 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
    let first_luminance = luminance(first);
    let second_luminance = luminance(second);
    let (lighter, darker) = if first_luminance >= second_luminance {
        (first_luminance, second_luminance)
    } else {
        (second_luminance, first_luminance)
    };
    (lighter + 0.05) / (darker + 0.05)
}

fn is_bounded_binding(value: &Value) -> bool {
    let Some(object) = value.as_object() else {
        return false;
    };
    if object.len() != 1 {
        return false;
    }
    object
        .get("$path")
        .and_then(Value::as_str)
        .is_some_and(|path| path.len() <= 256 && (path.is_empty() || path.starts_with('/')))
}

fn is_bounded_key_value_text(value: &Value) -> bool {
    is_bounded_binding(value)
        || value.is_number()
        || value.is_boolean()
        || value.is_null()
        || value
            .as_str()
            .is_some_and(|text| text.chars().count() <= 256)
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Scene {
    pub root: Node,
    #[serde(default)]
    pub data: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub theme: Option<ThemeTokens>,
}
impl Default for Scene {
    fn default() -> Self {
        Self {
            root: Node::new(
                "root",
                Kind::Stack,
                serde_json::json!({}),
                vec![Node::new(
                    "empty",
                    Kind::Text,
                    serde_json::json!({"text":"空白世界 · 等待提供者加入"}),
                    vec![],
                )],
            ),
            data: Value::Null,
            theme: None,
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum SceneOp {
    Insert {
        parent: String,
        index: usize,
        node: Node,
    },
    Remove {
        node_id: String,
    },
    Replace {
        node_id: String,
        node: Node,
    },
    Move {
        node_id: String,
        parent: String,
        index: usize,
    },
    Props {
        node_id: String,
        props: Map<String, Value>,
    },
}
impl Scene {
    pub fn validate(&self) -> Result<()> {
        if let Some(theme) = &self.theme {
            theme.validate()?;
        }
        let bytes =
            serde_json::to_vec(self).map_err(|e| Fault::new("INVALID_SCENE", e.to_string()))?;
        if bytes.len() > MAX_PAYLOAD {
            return Err(Fault::new("LIMIT", "scene exceeds 256 KiB"));
        }
        fn walk(
            n: &Node,
            depth: usize,
            ids: &mut HashSet<String>,
            escape_shortcuts: &mut usize,
            ctrl_enter_shortcuts: &mut usize,
            selection_groups: &mut HashMap<String, (String, usize)>,
        ) -> Result<()> {
            if depth > 16 || ids.len() >= 256 {
                return Err(Fault::new("LIMIT", "maximum 256 nodes, depth 16"));
            }
            if n.id.is_empty()
                || n.id.len() > 64
                || !n
                    .id
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || "_-.:".contains(c))
            {
                return Err(Fault::new("INVALID_SCENE", "invalid component id"));
            }
            if !ids.insert(n.id.clone()) {
                return Err(Fault::new("INVALID_SCENE", "duplicate component id"));
            }
            if !n.kind.container() && !n.children.is_empty() {
                return Err(Fault::new("INVALID_SCENE", "leaf has children"));
            }
            let allowed: &[&str] = match n.kind {
                Kind::Stack | Kind::Row => &["gap", "align"],
                Kind::Text => &["text", "size", "tone"],
                Kind::Metric => &["label", "value", "unit", "caption", "tone"],
                Kind::Progress => &["label", "value", "max", "tone"],
                Kind::Badge => &["text", "tone"],
                Kind::Button => &[
                    "label",
                    "action",
                    "appearance",
                    "native_window_action",
                    "context_action",
                    "disabled",
                    "tone",
                    "shortcut",
                    "shortcut_action",
                    "selection_group",
                    "selection_mode",
                    "pressed",
                ],
                Kind::Input => &[
                    "label",
                    "value",
                    "action",
                    "context_action",
                    "placeholder",
                    "disabled",
                    "submit_label",
                ],
                Kind::TextArea => &[
                    "label",
                    "value",
                    "action",
                    "context_action",
                    "placeholder",
                    "disabled",
                    "submit_label",
                    "shortcut",
                    "shortcut_action",
                ],
                Kind::KeyValue => &["items", "action"],
                Kind::Icon => &["name", "label", "tone"],
                Kind::BarChart => &["label", "items"],
                Kind::Divider => &[],
            };
            for (k, v) in &n.props {
                if !allowed.contains(&k.as_str()) {
                    return Err(Fault::new(
                        "INVALID_SCENE",
                        format!("unsupported prop: {k}"),
                    ));
                }
                if let Some(path) = v.as_object().and_then(|x| x.get("$path")) {
                    if !path.is_string() || v.as_object().unwrap().len() != 1 {
                        return Err(Fault::new(
                            "INVALID_SCENE",
                            "binding must be {$path: JSON-pointer}",
                        ));
                    }
                    let p = path.as_str().unwrap();
                    if p.len() > 256 || !(p.is_empty() || p.starts_with('/')) {
                        return Err(Fault::new("INVALID_SCENE", "invalid JSON pointer"));
                    }
                }
            }
            if n.kind.interactive() {
                let action = n.props.get("action").and_then(Value::as_str).unwrap_or("");
                if action.is_empty() || action.len() > 128 {
                    return Err(Fault::new(
                        "INVALID_SCENE",
                        "interactive action must be a static short string",
                    ));
                }
                if let Some(value) = n.props.get("context_action") {
                    let action = value.as_str().unwrap_or("");
                    if action.is_empty() || action.len() > 128 {
                        return Err(Fault::new(
                            "INVALID_SCENE",
                            "context_action must be a static short string",
                        ));
                    }
                }
            }
            if n.kind == Kind::Button {
                if let Some(appearance) = n.props.get("appearance") {
                    let appearance = appearance.as_str().unwrap_or("");
                    if !matches!(appearance, "default" | "link" | "title") {
                        return Err(Fault::new("INVALID_SCENE", "unsupported button appearance"));
                    }
                }
                if let Some(action) = n.props.get("native_window_action") {
                    let action: NativeWindowAction = serde_json::from_value(action.clone())
                        .map_err(|_| Fault::new("INVALID_SCENE", "invalid native window action"))?;
                    if action
                        .title_contains
                        .as_ref()
                        .is_some_and(|value| value.chars().count() > 128)
                    {
                        return Err(Fault::new(
                            "INVALID_SCENE",
                            "native window title filter is too long",
                        ));
                    }
                }
            }
            if n.kind == Kind::KeyValue && n.props.contains_key("action") {
                let action = n.props.get("action").and_then(Value::as_str).unwrap_or("");
                if action.is_empty() || action.len() > 128 {
                    return Err(Fault::new(
                        "INVALID_SCENE",
                        "key_value action must be a static short string",
                    ));
                }
            }
            if n.kind == Kind::Icon {
                let name = n.props.get("name").and_then(Value::as_str).unwrap_or("");
                if !matches!(name, "pin" | "link" | "external" | "clock" | "check") {
                    return Err(Fault::new("INVALID_SCENE", "icon name is not allowlisted"));
                }
                if let Some(label) = n.props.get("label") {
                    if !label.is_string() || label.as_str().unwrap_or("").chars().count() > 80 {
                        return Err(Fault::new(
                            "INVALID_SCENE",
                            "icon label must be text up to 80 characters",
                        ));
                    }
                }
            }
            if let Some(items) = n.props.get("items").and_then(Value::as_array) {
                if n.kind == Kind::KeyValue {
                    if items.len() > 64 {
                        return Err(Fault::new("LIMIT", "key_value accepts at most 64 rows"));
                    }
                    for item in items {
                        let Some(record) = item.as_object() else {
                            return Err(Fault::new(
                                "INVALID_SCENE",
                                "key_value items must be objects",
                            ));
                        };
                        if record.keys().any(|key| {
                            !matches!(
                                key.as_str(),
                                "key" | "value" | "secondary" | "icon" | "tone"
                            )
                        }) || !record.contains_key("key")
                            || !record.contains_key("value")
                        {
                            return Err(Fault::new(
                                "INVALID_SCENE",
                                "invalid key_value item fields",
                            ));
                        }
                        for field in ["key", "value", "secondary"] {
                            if let Some(value) = record.get(field) {
                                if !is_bounded_key_value_text(value) {
                                    return Err(Fault::new(
                                        "INVALID_SCENE",
                                        "key_value text values must be bounded scalars",
                                    ));
                                }
                            }
                        }
                        if let Some(icon) = record.get("icon") {
                            if !matches!(
                                icon.as_str(),
                                Some("pin" | "link" | "external" | "clock" | "check")
                            ) {
                                return Err(Fault::new(
                                    "INVALID_SCENE",
                                    "key_value icon is not allowlisted",
                                ));
                            }
                        }
                        if let Some(tone) = record.get("tone") {
                            if !matches!(
                                tone.as_str(),
                                Some(
                                    "normal"
                                        | "muted"
                                        | "accent"
                                        | "success"
                                        | "warning"
                                        | "danger"
                                )
                            ) {
                                return Err(Fault::new(
                                    "INVALID_SCENE",
                                    "key_value tone is not allowlisted",
                                ));
                            }
                        }
                    }
                }
                if n.kind == Kind::BarChart {
                    if items.len() > 8 {
                        return Err(Fault::new("LIMIT", "bar_chart accepts at most 8 items"));
                    }
                    for item in items {
                        let Some(record) = item.as_object() else {
                            return Err(Fault::new(
                                "INVALID_SCENE",
                                "bar_chart items must be objects",
                            ));
                        };
                        if record
                            .keys()
                            .any(|key| !matches!(key.as_str(), "label" | "value" | "tone"))
                            || !record.get("label").is_some_and(Value::is_string)
                            || !record.get("value").is_some_and(Value::is_number)
                        {
                            return Err(Fault::new(
                                "INVALID_SCENE",
                                "invalid bar_chart item fields",
                            ));
                        }
                        let label_len = record
                            .get("label")
                            .and_then(Value::as_str)
                            .map(|label| label.chars().count())
                            .unwrap_or(usize::MAX);
                        let value = record
                            .get("value")
                            .and_then(Value::as_f64)
                            .unwrap_or(f64::NAN);
                        if label_len > 80
                            || !value.is_finite()
                            || !(0.0..=1_000_000.0).contains(&value)
                        {
                            return Err(Fault::new(
                                "INVALID_SCENE",
                                "bar_chart labels or values are outside limits",
                            ));
                        }
                        if let Some(tone) = record.get("tone") {
                            if !matches!(
                                tone.as_str(),
                                Some(
                                    "normal"
                                        | "muted"
                                        | "accent"
                                        | "success"
                                        | "warning"
                                        | "danger"
                                )
                            ) {
                                return Err(Fault::new(
                                    "INVALID_SCENE",
                                    "bar_chart tone is not allowlisted",
                                ));
                            }
                        }
                    }
                }
            }
            if n.kind == Kind::BarChart
                && (!n.props.contains_key("label") || !n.props.contains_key("items"))
            {
                return Err(Fault::new(
                    "INVALID_SCENE",
                    "bar_chart requires label and items",
                ));
            }
            if n.kind == Kind::BarChart {
                let label = n.props.get("label").unwrap();
                let label_is_binding = label
                    .as_object()
                    .is_some_and(|object| object.contains_key("$path"));
                if !label_is_binding && !label.is_string() {
                    return Err(Fault::new(
                        "INVALID_SCENE",
                        "bar_chart label must be text or a data binding",
                    ));
                }
                let items = n.props.get("items").unwrap();
                let items_is_binding = items
                    .as_object()
                    .is_some_and(|object| object.contains_key("$path"));
                if !items_is_binding && !items.is_array() {
                    return Err(Fault::new(
                        "INVALID_SCENE",
                        "bar_chart items must be an array or a data binding",
                    ));
                }
            }
            if n.kind == Kind::Button || n.kind == Kind::TextArea {
                let shortcut = n.props.get("shortcut").and_then(Value::as_str);
                if n.props.contains_key("shortcut") && shortcut.is_none() {
                    return Err(Fault::new("INVALID_SCENE", "shortcut must be static text"));
                }
                let shortcut_action = n
                    .props
                    .get("shortcut_action")
                    .and_then(Value::as_str)
                    .unwrap_or("");
                if let Some(shortcut) = shortcut {
                    let registered = match (n.kind, shortcut) {
                        (Kind::Button, "escape") => {
                            *escape_shortcuts += 1;
                            *escape_shortcuts <= 1
                        }
                        (Kind::TextArea, "ctrl_enter") => {
                            *ctrl_enter_shortcuts += 1;
                            *ctrl_enter_shortcuts <= 1
                        }
                        _ => false,
                    };
                    if !registered || shortcut_action.is_empty() || shortcut_action.len() > 128 {
                        return Err(Fault::new(
                            "INVALID_SCENE",
                            "shortcut/action pair is unsupported, duplicated, or invalid",
                        ));
                    }
                } else if n.props.contains_key("shortcut_action") {
                    return Err(Fault::new(
                        "INVALID_SCENE",
                        "shortcut_action requires a registered shortcut",
                    ));
                }
            }
            if n.kind == Kind::Button {
                let group = n.props.get("selection_group");
                let mode = n.props.get("selection_mode");
                let pressed = n.props.get("pressed");
                if group.is_some() || mode.is_some() || pressed.is_some() {
                    let group = group.and_then(Value::as_str).unwrap_or("");
                    let mode = mode.and_then(Value::as_str).unwrap_or("");
                    let pressed = pressed.and_then(Value::as_bool).ok_or_else(|| {
                        Fault::new("INVALID_SCENE", "selection-group pressed must be boolean")
                    })?;
                    if group.is_empty()
                        || group.len() > 64
                        || !group
                            .chars()
                            .all(|c| c.is_ascii_alphanumeric() || "_.:-".contains(c))
                        || !matches!(mode, "single" | "multiple")
                    {
                        return Err(Fault::new(
                            "INVALID_SCENE",
                            "invalid selection group or mode",
                        ));
                    }
                    let entry = selection_groups
                        .entry(group.to_owned())
                        .or_insert_with(|| (mode.to_owned(), 0));
                    if entry.0 != mode {
                        return Err(Fault::new(
                            "INVALID_SCENE",
                            "selection group modes must match",
                        ));
                    }
                    if pressed {
                        entry.1 += 1;
                        if mode == "single" && entry.1 > 1 {
                            return Err(Fault::new(
                                "INVALID_SCENE",
                                "single selection group has multiple pressed options",
                            ));
                        }
                    }
                }
            }
            for child in &n.children {
                walk(
                    child,
                    depth + 1,
                    ids,
                    escape_shortcuts,
                    ctrl_enter_shortcuts,
                    selection_groups,
                )?;
            }
            Ok(())
        }
        walk(
            &self.root,
            0,
            &mut HashSet::new(),
            &mut 0,
            &mut 0,
            &mut HashMap::new(),
        )
    }
    /// Work on a clone; failures never partially modify the published scene.
    pub fn patch(&self, ops: &[SceneOp]) -> Result<Self> {
        if ops.len() > 128 {
            return Err(Fault::new("LIMIT", "too many scene operations"));
        }
        let mut next = self.clone();
        for op in ops {
            match op {
                SceneOp::Insert {
                    parent,
                    index,
                    node,
                } => insert(&mut next.root, parent, *index, node.clone())?,
                SceneOp::Remove { node_id } => {
                    if next.root.id == *node_id {
                        return Err(Fault::new("INVALID_PATCH", "cannot remove root"));
                    }
                    next.root
                        .take(node_id)
                        .ok_or_else(|| Fault::new("NOT_FOUND", "component missing"))?;
                }
                SceneOp::Replace { node_id, node } => {
                    let target = next
                        .root
                        .find_mut(node_id)
                        .ok_or_else(|| Fault::new("NOT_FOUND", "component missing"))?;
                    *target = node.clone();
                }
                SceneOp::Move {
                    node_id,
                    parent,
                    index,
                } => {
                    if next.root.id == *node_id {
                        return Err(Fault::new("INVALID_PATCH", "cannot move root"));
                    }
                    // Removing first also makes moving into one's own descendant fail atomically.
                    let node = next
                        .root
                        .take(node_id)
                        .ok_or_else(|| Fault::new("NOT_FOUND", "component missing"))?;
                    insert(&mut next.root, parent, *index, node)?;
                }
                SceneOp::Props { node_id, props } => {
                    let node = next
                        .root
                        .find_mut(node_id)
                        .ok_or_else(|| Fault::new("NOT_FOUND", "component missing"))?;
                    for (key, value) in props {
                        node.props.insert(key.clone(), value.clone());
                    }
                }
            }
        }
        next.validate()?;
        Ok(next)
    }
}
fn insert(root: &mut Node, parent: &str, index: usize, node: Node) -> Result<()> {
    let target = root
        .find_mut(parent)
        .ok_or_else(|| Fault::new("NOT_FOUND", "parent missing"))?;
    if !target.kind.container() || index > target.children.len() {
        return Err(Fault::new(
            "INVALID_PATCH",
            "invalid container or insertion index",
        ));
    }
    target.children.insert(index, node);
    Ok(())
}
