pub mod private;

use serde::de::Deserializer;
use serde::ser::Serializer;

pub use bt_serde_attribute::optional;

// When implementing this trait, you are usually doing so for a foreign type.  To avoid triggering
// Rust's orphan rule, we design this trait to accept the (foreign) type as an associated type.
pub trait SerdeWith {
    type Value;

    fn deserialize<'de, D>(deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>;

    fn serialize<S>(value: &Self::Value, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer;
}
