//! Host-side registry for presentation groups.
//!
//! A group is a host projection over worlds the caller already owns. The
//! registry never grants authority: every operation re-checks the caller's
//! write lease per member, and a member that cannot be written records its own
//! refusal instead of being silently skipped.

use std::collections::BTreeMap;
use uuid::Uuid;
use wincraft_core::Result;
use wincraft_core::{Fault, PresentationGroup};

/// Owner of every registered group, so one provider cannot address another
/// provider's group.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GroupOwner(pub Uuid);

#[derive(Default)]
pub struct PresentationGroupRegistry {
    groups: BTreeMap<Uuid, (GroupOwner, PresentationGroup)>,
}

impl PresentationGroupRegistry {
    pub fn insert(&mut self, owner: Uuid, group: PresentationGroup) -> Result<()> {
        if self.groups.contains_key(&group.id) {
            return Err(Fault::new("INVALID_GROUP", "group id already registered"));
        }
        self.groups.insert(group.id, (GroupOwner(owner), group));
        Ok(())
    }

    pub fn get(&self, owner: Uuid, group_id: Uuid) -> Result<PresentationGroup> {
        let (group_owner, group) = self
            .groups
            .get(&group_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "presentation group not found"))?;
        if group_owner.0 != owner {
            // Discovery grants no operation right: a group owned by another
            // session stays invisible as an actionable resource.
            return Err(Fault::new("NOT_FOUND", "presentation group not found"));
        }
        Ok(group.clone())
    }

    pub fn list(&self, owner: Uuid) -> Vec<PresentationGroup> {
        self.groups
            .values()
            .filter(|(group_owner, _)| group_owner.0 == owner)
            .map(|(_, group)| group.clone())
            .collect()
    }

    pub fn remove(&mut self, owner: Uuid, group_id: Uuid) -> Result<()> {
        let (group_owner, _) = self
            .groups
            .get(&group_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "presentation group not found"))?;
        if group_owner.0 != owner {
            return Err(Fault::new("NOT_FOUND", "presentation group not found"));
        }
        self.groups.remove(&group_id);
        Ok(())
    }

    pub fn update(
        &mut self,
        owner: Uuid,
        group_id: Uuid,
        mutate: impl FnOnce(&mut PresentationGroup) -> Result<()>,
    ) -> Result<PresentationGroup> {
        let (group_owner, group) = self
            .groups
            .get_mut(&group_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "presentation group not found"))?;
        if group_owner.0 != owner {
            return Err(Fault::new("NOT_FOUND", "presentation group not found"));
        }
        mutate(group)?;
        Ok(group.clone())
    }
}
