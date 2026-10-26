use crate::{Fault, Result, MAX_PAYLOAD};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::HashSet;

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
    KeyValue,
    Divider,
}
impl Kind {
    pub fn container(self) -> bool {
        matches!(self, Self::Stack | Self::Row)
    }
    pub fn interactive(self) -> bool {
        matches!(self, Self::Button | Self::Input)
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
pub struct Scene {
    pub root: Node,
    #[serde(default)]
    pub data: Value,
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
        let bytes =
            serde_json::to_vec(self).map_err(|e| Fault::new("INVALID_SCENE", e.to_string()))?;
        if bytes.len() > MAX_PAYLOAD {
            return Err(Fault::new("LIMIT", "scene exceeds 256 KiB"));
        }
        fn walk(n: &Node, depth: usize, ids: &mut HashSet<String>) -> Result<()> {
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
                Kind::Button => &["label", "action", "context_action", "disabled", "tone"],
                Kind::Input => &[
                    "label",
                    "value",
                    "action",
                    "context_action",
                    "placeholder",
                    "disabled",
                ],
                Kind::KeyValue => &["items"],
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
            for child in &n.children {
                walk(child, depth + 1, ids)?;
            }
            Ok(())
        }
        walk(&self.root, 0, &mut HashSet::new())
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
