#![feature(try_blocks)]

use chrono::{DateTime, Utc};

pub type Timestamp = DateTime<Utc>;

pub trait TimestampExt: Sized {
    fn now() -> Self;

    fn from_timestamp_secs_u64(secs: u64) -> Result<Self, u64>;

    // NOTE: I am not sure if this is a good idea, but we will crash on timestamps before 1970.
    fn timestamp_u64(&self) -> u64;

    fn tomorrow(&self) -> Option<Self>;
}

impl TimestampExt for Timestamp {
    fn now() -> Self {
        Utc::now()
    }

    fn from_timestamp_secs_u64(secs: u64) -> Result<Self, u64> {
        try { Self::from_timestamp_secs(secs.try_into().ok()?)? }.ok_or(secs)
    }

    fn timestamp_u64(&self) -> u64 {
        self.timestamp().try_into().expect("u64")
    }

    fn tomorrow(&self) -> Option<Self> {
        self.date_naive()
            .succ_opt()
            .map(|tomorrow| tomorrow.and_time(self.time()).and_utc())
    }
}

impl TimestampExt for Option<Timestamp> {
    fn now() -> Self {
        Some(Timestamp::now())
    }

    fn from_timestamp_secs_u64(secs: u64) -> Result<Self, u64> {
        (secs != 0)
            .then(|| Timestamp::from_timestamp_secs_u64(secs))
            .transpose()
    }

    fn timestamp_u64(&self) -> u64 {
        self.as_ref().map_or(0, Timestamp::timestamp_u64)
    }

    fn tomorrow(&self) -> Option<Self> {
        Some(match self.as_ref() {
            Some(this) => Some(this.tomorrow()?),
            None => None,
        })
    }
}

#[cfg(test)]
mod tests {
    use std::fmt::Debug;

    use super::*;

    #[test]
    fn tomorrow() {
        fn test<T>(testdata: T, expect: Option<T>)
        where
            T: Debug + PartialEq + TimestampExt,
        {
            assert_eq!(testdata.tomorrow(), expect);
        }

        for (testdata, expect) in [
            (Timestamp::MIN_UTC, "-262143-01-02T00:00:00Z"),
            (Timestamp::UNIX_EPOCH, "1970-01-02T00:00:00Z"),
            (
                "2001-02-03T04:05:06Z".parse().unwrap(),
                "2001-02-04T04:05:06Z",
            ),
        ] {
            let expect = expect.parse().unwrap();
            test(testdata, Some(expect));
            test(Some(testdata), Some(Some(expect)));
        }

        test(None, Some(None));

        test(Timestamp::MAX_UTC, None);
        test(Some(Timestamp::MAX_UTC), None);
    }
}
