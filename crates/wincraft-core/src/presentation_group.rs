//! Presentation groups: host-side orchestration over an ordered set of worlds.
//!
//! A group is *not* a shared-memory construct and it does not relax world
//! ownership. Every member keeps its own lease, and every operation is applied
//! to each member independently. A member that cannot be operated on records
//! its own failure; the group never pretends the whole set moved atomically.
//!
//! Roles are plain labels carried by the group. They carry no business
//! meaning, no mood or emotion engine, and no authority of their own.

use crate::Fault;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use uuid::Uuid;

/// Upper bound on members in one group, so a group can never become an
/// unbounded fan-out over the host's world table.
pub const MAX_GROUP_MEMBERS: usize = 32;
/// Upper bound on the number of distinct roles carried by one group.
pub const MAX_GROUP_ROLES: usize = 16;
/// Upper bound on the byte length of a single role name.
pub const MAX_GROUP_ROLE_NAME_BYTES: usize = 64;

/// A role label attached to a group member.
///
/// Roles are descriptive metadata for presentation. They are never a source
/// of authority: a role cannot grant write access, bypass a lease, or let a
/// group act on a world it does not own.
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default, deny_unknown_fields)]
pub struct GroupRole {
    pub name: String,
    /// Optional member this role applies to. `None` means the whole group.
    pub member: Option<Uuid>,
}
impl GroupRole {
    pub fn validate(&self) -> Result<(), Fault> {
        let trimmed = self.name.trim();
        if trimmed.is_empty() {
            return Err(Fault::new("INVALID_GROUP", "role name must not be empty"));
        }
        if trimmed.chars().count() > MAX_GROUP_ROLE_NAME_BYTES {
            return Err(Fault::new(
                "INVALID_GROUP",
                "role name exceeds the supported length",
            ));
        }
        Ok(())
    }
}

/// One member of a group.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default, deny_unknown_fields)]
pub struct GroupMember {
    pub world_id: Uuid,
    /// Free-form ordering key; ties keep insertion order.
    pub order: i64,
}
impl Default for GroupMember {
    fn default() -> Self {
        Self {
            world_id: Uuid::nil(),
            order: 0,
        }
    }
}

/// A presentation group: an ordered, role-tagged set of worlds.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default, deny_unknown_fields)]
pub struct PresentationGroup {
    pub id: Uuid,
    pub name: String,
    pub members: Vec<GroupMember>,
    pub roles: Vec<GroupRole>,
}
impl Default for PresentationGroup {
    fn default() -> Self {
        Self {
            id: Uuid::nil(),
            name: String::new(),
            members: Vec::new(),
            roles: Vec::new(),
        }
    }
}

/// The outcome of applying one operation to one member.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum MemberOutcome {
    /// The member accepted the operation.
    Applied,
    /// The member refused the operation; the group continued with the rest.
    Refused { code: String, message: String },
}
impl MemberOutcome {
    pub fn is_applied(&self) -> bool {
        matches!(self, MemberOutcome::Applied)
    }
    pub fn is_refused(&self) -> bool {
        matches!(self, MemberOutcome::Refused { .. })
    }
}

/// Per-member result of a group operation.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default, deny_unknown_fields)]
pub struct MemberResult {
    pub world_id: Uuid,
    pub outcome: MemberOutcome,
}
impl Default for MemberResult {
    fn default() -> Self {
        Self {
            world_id: Uuid::nil(),
            outcome: MemberOutcome::Applied,
        }
    }
}

/// The aggregate result of a group operation.
///
/// `atomic` is always false: the host applies the operation member by member
/// and reports each outcome separately.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default, deny_unknown_fields)]
pub struct GroupResult {
    pub group_id: Uuid,
    pub results: Vec<MemberResult>,
    /// Number of members that accepted the operation.
    pub applied: usize,
    /// Number of members that refused the operation.
    pub refused: usize,
}
impl Default for GroupResult {
    fn default() -> Self {
        Self {
            group_id: Uuid::nil(),
            results: Vec::new(),
            applied: 0,
            refused: 0,
        }
    }
}
impl GroupResult {
    /// A group result is complete only when every member applied the
    /// operation. A partial result is reported as-is and never upgraded.
    pub fn is_complete(&self) -> bool {
        self.refused == 0
    }
}

impl PresentationGroup {
    pub fn new(id: Uuid, name: impl Into<String>) -> Self {
        Self {
            id,
            name: name.into(),
            members: Vec::new(),
            roles: Vec::new(),
        }
    }

    /// Members in presentation order: by `order`, then by insertion order.
    pub fn ordered_members(&self) -> Vec<&GroupMember> {
        let mut indexed: Vec<(usize, &GroupMember)> = self.members.iter().enumerate().collect();
        indexed.sort_by(|a, b| a.1.order.cmp(&b.1.order).then(a.0.cmp(&b.0)));
        indexed.into_iter().map(|(_, member)| member).collect()
    }

    /// Member identifiers in presentation order, without duplicates.
    pub fn ordered_member_ids(&self) -> Vec<Uuid> {
        let mut seen = BTreeSet::new();
        let mut ordered = Vec::new();
        for member in self.ordered_members() {
            if seen.insert(member.world_id) {
                ordered.push(member.world_id);
            }
        }
        ordered
    }

    pub fn add_member(&mut self, world_id: Uuid, order: i64) -> Result<(), Fault> {
        if self.members.iter().any(|m| m.world_id == world_id) {
            return Err(Fault::new(
                "INVALID_GROUP",
                "group already contains this world",
            ));
        }
        if self.members.len() >= MAX_GROUP_MEMBERS {
            return Err(Fault::new("INVALID_GROUP", "group member limit reached"));
        }
        self.members.push(GroupMember { world_id, order });
        Ok(())
    }

    pub fn remove_member(&mut self, world_id: Uuid) -> bool {
        let before = self.members.len();
        self.members.retain(|m| m.world_id != world_id);
        self.roles.retain(|r| r.member != Some(world_id));
        before != self.members.len()
    }

    /// Attach a role to the whole group, or to one member.
    pub fn add_role(&mut self, role: GroupRole) -> Result<(), Fault> {
        role.validate()?;
        if self
            .roles
            .iter()
            .any(|r| r.name == role.name && r.member == role.member)
        {
            return Err(Fault::new("INVALID_GROUP", "role already present"));
        }
        if self.roles.len() >= MAX_GROUP_ROLES {
            return Err(Fault::new("INVALID_GROUP", "role limit reached"));
        }
        if let Some(member) = role.member {
            if !self.members.iter().any(|m| m.world_id == member) {
                return Err(Fault::new(
                    "INVALID_GROUP",
                    "role references a world that is not a group member",
                ));
            }
        }
        self.roles.push(role);
        Ok(())
    }

    /// Roles that apply to one member, including group-wide roles.
    pub fn roles_for(&self, world_id: Uuid) -> Vec<&GroupRole> {
        self.roles
            .iter()
            .filter(|r| r.member.is_none() || r.member == Some(world_id))
            .collect()
    }

    /// Apply one operation to every member, independently.
    ///
    /// `operate` receives the member id and returns the member's own result.
    /// The callback is invoked once per member even when an earlier member
    /// failed, so a partial failure stays observable instead of aborting the
    /// whole group silently.
    pub fn apply_to_members<F>(&self, group_id: Uuid, mut operate: F) -> GroupResult
    where
        F: FnMut(Uuid) -> Result<(), Fault>,
    {
        let mut results = Vec::new();
        let mut applied = 0usize;
        let mut refused = 0usize;
        for member in self.ordered_members() {
            let outcome = match operate(member.world_id) {
                Ok(()) => {
                    applied += 1;
                    MemberOutcome::Applied
                }
                Err(fault) => {
                    refused += 1;
                    MemberOutcome::Refused {
                        code: fault.code,
                        message: fault.message,
                    }
                }
            };
            results.push(MemberResult {
                world_id: member.world_id,
                outcome,
            });
        }
        GroupResult {
            group_id,
            results,
            applied,
            refused,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn group_with(members: &[(Uuid, i64)]) -> PresentationGroup {
        let mut group = PresentationGroup::new(Uuid::new_v4(), "hud");
        for (id, order) in members {
            group.add_member(*id, *order).unwrap();
        }
        group
    }

    #[test]
    fn members_are_ordered_and_deduplicated() {
        let a = Uuid::new_v4();
        let b = Uuid::new_v4();
        let c = Uuid::new_v4();
        let mut group = group_with(&[(a, 2), (b, 1), (c, 2)]);
        assert_eq!(group.ordered_member_ids(), vec![b, a, c]);
        assert!(group.add_member(a, 9).is_err());
        assert_eq!(group.members.len(), 3);
    }

    #[test]
    fn group_member_limit_is_enforced() {
        let mut group = PresentationGroup::new(Uuid::new_v4(), "hud");
        for _ in 0..MAX_GROUP_MEMBERS {
            group.add_member(Uuid::new_v4(), 0).unwrap();
        }
        assert!(group.add_member(Uuid::new_v4(), 0).is_err());
    }

    #[test]
    fn partial_failure_is_reported_per_member() {
        let a = Uuid::new_v4();
        let b = Uuid::new_v4();
        let c = Uuid::new_v4();
        let group = group_with(&[(a, 0), (b, 1), (c, 2)]);
        let mut visited = Vec::new();
        let result = group.apply_to_members(group.id, |id| {
            visited.push(id);
            if id == b {
                Err(Fault::new("STALE_LEASE", "world has no writer"))
            } else {
                Ok(())
            }
        });
        assert_eq!(visited, vec![a, b, c]);
        assert_eq!(result.applied, 2);
        assert_eq!(result.refused, 1);
        assert!(!result.is_complete());
        assert_eq!(result.results.len(), 3);
        assert!(result.results[1].outcome.is_refused());
        assert!(result.results[0].outcome.is_applied());
    }

    #[test]
    fn every_member_is_visited_even_after_a_failure() {
        let a = Uuid::new_v4();
        let b = Uuid::new_v4();
        let group = group_with(&[(a, 0), (b, 1)]);
        let result =
            group.apply_to_members(group.id, |_| Err(Fault::new("NOT_FOUND", "world missing")));
        assert_eq!(result.refused, 2);
        assert_eq!(result.applied, 0);
        assert!(!result.is_complete());
    }

    #[test]
    fn roles_are_labels_and_never_imply_membership() {
        let a = Uuid::new_v4();
        let b = Uuid::new_v4();
        let mut group = group_with(&[(a, 0), (b, 1)]);
        group
            .add_role(GroupRole {
                name: "primary".into(),
                member: None,
            })
            .unwrap();
        group
            .add_role(GroupRole {
                name: "secondary".into(),
                member: Some(b),
            })
            .unwrap();
        assert_eq!(group.roles_for(a).len(), 1);
        assert_eq!(group.roles_for(b).len(), 2);
        // A role that references a non-member is refused.
        assert!(group
            .add_role(GroupRole {
                name: "ghost".into(),
                member: Some(Uuid::new_v4()),
            })
            .is_err());
    }

    #[test]
    fn removing_a_member_drops_its_member_scoped_roles() {
        let a = Uuid::new_v4();
        let b = Uuid::new_v4();
        let mut group = group_with(&[(a, 0), (b, 1)]);
        group
            .add_role(GroupRole {
                name: "only-a".into(),
                member: Some(a),
            })
            .unwrap();
        assert!(group.remove_member(a));
        assert_eq!(group.roles.len(), 0);
        assert!(!group.remove_member(a));
    }

    #[test]
    fn empty_role_name_is_refused() {
        let mut group = PresentationGroup::new(Uuid::new_v4(), "hud");
        assert!(group
            .add_role(GroupRole {
                name: "   ".into(),
                member: None,
            })
            .is_err());
    }
}
