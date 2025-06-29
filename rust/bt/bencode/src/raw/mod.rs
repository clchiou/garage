pub(crate) mod de;
pub(crate) mod ser;

mod de_impl;
mod ser_impl;

use std::fmt;

use g1_base::fmt::EscapeAscii;
use g1_base::ops::Deref;

// `WithRaw` is de/serialized as a newtype struct in the form: `MAGIC((T, D))`.
#[derive(Clone, Deref, Eq, PartialEq)]
pub struct WithRaw<T, D>(#[deref(target)] T, D);

// Magic string that does not collide with any legitimate type name.
pub(crate) const MAGIC: &str = "$bt_bencode::raw::MAGIC";

impl<T, D> fmt::Debug for WithRaw<T, D>
where
    T: fmt::Debug,
    D: AsRef<[u8]>,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_tuple("WithRaw")
            .field(&self.0)
            .field(&EscapeAscii(self.1.as_ref()))
            .finish()
    }
}

impl<T, D> From<WithRaw<T, D>> for (T, D) {
    fn from(WithRaw(value, bytes): WithRaw<T, D>) -> Self {
        (value, bytes)
    }
}

impl<T, D> WithRaw<T, D>
where
    D: AsRef<[u8]>,
{
    pub fn as_raw(this: &Self) -> &[u8] {
        this.1.as_ref()
    }
}
