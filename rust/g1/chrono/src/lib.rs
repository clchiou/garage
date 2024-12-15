use chrono::{DateTime, Utc};

pub type Timestamp = DateTime<Utc>;

pub trait TimestampExt: Sized {
    fn now() -> Self;

    fn from_timestamp_secs(secs: u64) -> Result<Self, u64>;

    // NOTE: I am not sure if this is a good idea, but we will crash on timestamps before 1970.
    fn timestamp_u64(&self) -> u64;
}

impl TimestampExt for Timestamp {
    fn now() -> Self {
        Utc::now()
    }

    fn from_timestamp_secs(secs: u64) -> Result<Self, u64> {
        secs.try_into()
            .ok()
            .and_then(|secs| Self::from_timestamp(secs, 0))
            .ok_or(secs)
    }

    fn timestamp_u64(&self) -> u64 {
        self.timestamp().try_into().expect("u64")
    }
}

impl TimestampExt for Option<Timestamp> {
    fn now() -> Self {
        Some(Timestamp::now())
    }

    fn from_timestamp_secs(secs: u64) -> Result<Self, u64> {
        (secs != 0)
            .then(|| Timestamp::from_timestamp_secs(secs))
            .transpose()
    }

    fn timestamp_u64(&self) -> u64 {
        self.as_ref().map_or(0, Timestamp::timestamp_u64)
    }
}
