use crate::{Fault, Result, ScopedLeaseKey, MAX_SCOPES_PER_WORLD};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use uuid::Uuid;

pub const MAX_STATE_SLOTS_PER_WORLD: usize = 64;
pub const MAX_STATE_SLOTS_PER_SCOPE: usize = 16;
pub const MAX_STATE_SLOT_READERS: usize = MAX_SCOPES_PER_WORLD - 1;
pub const MAX_STATE_SLOT_VALUE_BYTES: usize = 8_192;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum StateSlotSchema {
    Boolean,
    Integer { min: Option<i64>, max: Option<i64> },
    Number { min: Option<f64>, max: Option<f64> },
    String { max_chars: u16 },
    Enum { values: Vec<String> },
}

impl StateSlotSchema {
    pub fn validate_definition(&self) -> Result<()> {
        match self {
            Self::Boolean => Ok(()),
            Self::Integer { min, max } => {
                if min.zip(*max).is_some_and(|(min, max)| min > max) {
                    return Err(Fault::new(
                        "INVALID_STATE_SLOT_SCHEMA",
                        "integer minimum must not exceed maximum",
                    ));
                }
                Ok(())
            }
            Self::Number { min, max } => {
                if min.is_some_and(|value| !value.is_finite())
                    || max.is_some_and(|value| !value.is_finite())
                    || min.zip(*max).is_some_and(|(min, max)| min > max)
                {
                    return Err(Fault::new(
                        "INVALID_STATE_SLOT_SCHEMA",
                        "number bounds must be finite and ordered",
                    ));
                }
                Ok(())
            }
            Self::String { max_chars } => {
                if *max_chars == 0 || usize::from(*max_chars) > MAX_STATE_SLOT_VALUE_BYTES {
                    return Err(Fault::new(
                        "INVALID_STATE_SLOT_SCHEMA",
                        "string max_chars must be within 1..=8192",
                    ));
                }
                Ok(())
            }
            Self::Enum { values } => {
                if values.is_empty()
                    || values.len() > 64
                    || values
                        .iter()
                        .any(|value| value.is_empty() || value.chars().count() > 128)
                    || values
                        .iter()
                        .collect::<std::collections::BTreeSet<_>>()
                        .len()
                        != values.len()
                {
                    return Err(Fault::new(
                        "INVALID_STATE_SLOT_SCHEMA",
                        "enum requires 1..64 unique nonempty values of at most 128 characters",
                    ));
                }
                Ok(())
            }
        }
    }

    pub fn validate_value(&self, value: &Value) -> Result<()> {
        self.validate_definition()?;
        let encoded_len = serde_json::to_vec(value)
            .map_err(|error| Fault::new("INVALID_STATE_SLOT_VALUE", error.to_string()))?
            .len();
        if encoded_len > MAX_STATE_SLOT_VALUE_BYTES {
            return Err(Fault::new(
                "LIMIT",
                "state slot value exceeds 8192 encoded bytes",
            ));
        }
        let valid = match self {
            Self::Boolean => value.is_boolean(),
            Self::Integer { min, max } => value.as_i64().is_some_and(|number| {
                min.is_none_or(|minimum| number >= minimum)
                    && max.is_none_or(|maximum| number <= maximum)
            }),
            Self::Number { min, max } => value.as_f64().is_some_and(|number| {
                number.is_finite()
                    && min.is_none_or(|minimum| number >= minimum)
                    && max.is_none_or(|maximum| number <= maximum)
            }),
            Self::String { max_chars } => value
                .as_str()
                .is_some_and(|text| text.chars().count() <= usize::from(*max_chars)),
            Self::Enum { values } => value
                .as_str()
                .is_some_and(|text| values.iter().any(|candidate| candidate == text)),
        };
        if !valid {
            return Err(Fault::new(
                "INVALID_STATE_SLOT_VALUE",
                "value does not match the slot schema",
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct StateSlotSnapshot {
    pub world_id: Uuid,
    pub slot_id: Uuid,
    pub name: String,
    pub generation: u64,
    pub revision: u64,
    pub owner_scope_id: Uuid,
    pub access_scope_id: Uuid,
    pub schema: StateSlotSchema,
    pub value: Value,
}

#[derive(Clone, Debug)]
pub struct StateSlot {
    pub id: Uuid,
    pub name: String,
    pub generation: u64,
    pub revision: u64,
    pub owner_scope_id: Uuid,
    pub owner_scope_generation: u64,
    pub schema: StateSlotSchema,
    pub value: Value,
    pub reader_scopes: BTreeMap<Uuid, u64>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StateSlotScopeRef {
    pub scope_id: Uuid,
    pub generation: u64,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StateSlotCreateRequest {
    pub world_id: Uuid,
    pub lease: ScopedLeaseKey,
    pub name: String,
    pub schema: StateSlotSchema,
    pub initial_value: Value,
    #[serde(default)]
    pub reader_scopes: Vec<StateSlotScopeRef>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StateSlotSetReadersRequest {
    pub world_id: Uuid,
    pub lease: ScopedLeaseKey,
    pub slot_id: Uuid,
    pub generation: u64,
    pub expected_revision: u64,
    pub reader_scopes: Vec<StateSlotScopeRef>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StateSlotReadRequest {
    pub world_id: Uuid,
    pub slot_id: Uuid,
    pub generation: u64,
    pub reader_scope_id: Uuid,
    pub reader_scope_generation: u64,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StateSlotCompareAndSetRequest {
    pub world_id: Uuid,
    pub lease: ScopedLeaseKey,
    pub slot_id: Uuid,
    pub generation: u64,
    pub expected_revision: u64,
    pub value: Value,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StateSlotDeleteRequest {
    pub world_id: Uuid,
    pub lease: ScopedLeaseKey,
    pub slot_id: Uuid,
    pub generation: u64,
    pub expected_revision: u64,
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn scalar_schema_validation_rejects_wrong_types_and_out_of_range_values() {
        let integer = StateSlotSchema::Integer {
            min: Some(0),
            max: Some(100),
        };
        assert!(integer.validate_value(&json!(50)).is_ok());
        assert_eq!(
            integer.validate_value(&json!(-1)).unwrap_err().code,
            "INVALID_STATE_SLOT_VALUE"
        );
        assert_eq!(
            integer
                .validate_value(&json!({"value":50}))
                .unwrap_err()
                .code,
            "INVALID_STATE_SLOT_VALUE"
        );

        let enumeration = StateSlotSchema::Enum {
            values: vec!["idle".into(), "active".into()],
        };
        assert!(enumeration.validate_value(&json!("active")).is_ok());
        assert_eq!(
            enumeration
                .validate_value(&json!("unknown"))
                .unwrap_err()
                .code,
            "INVALID_STATE_SLOT_VALUE"
        );
    }

    #[test]
    fn definitions_and_encoded_values_obey_finite_bounds_and_size_caps() {
        assert_eq!(
            StateSlotSchema::Integer {
                min: Some(2),
                max: Some(1),
            }
            .validate_definition()
            .unwrap_err()
            .code,
            "INVALID_STATE_SLOT_SCHEMA"
        );
        assert_eq!(
            StateSlotSchema::Number {
                min: Some(f64::NAN),
                max: None,
            }
            .validate_definition()
            .unwrap_err()
            .code,
            "INVALID_STATE_SLOT_SCHEMA"
        );
        let oversized = StateSlotSchema::String { max_chars: 5000 }
            .validate_value(&json!("界".repeat(3000)))
            .unwrap_err();
        assert_eq!(oversized.code, "LIMIT");
    }
}
