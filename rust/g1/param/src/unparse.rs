use std::time::Duration;

//
// Useful if you want to serialize parameter values.
//

pub fn duration(d: Duration) -> String {
    match (d.as_secs(), d.subsec_nanos()) {
        (0, 0) => "0s".to_string(),
        (0, nanos) => format!("{nanos}ns"),
        (secs, 0) => format!("{secs}s"),
        (secs, nanos) => format!("{secs}s{nanos}ns"),
    }
}

#[cfg(test)]
mod tests {
    use crate::parse;

    use super::*;

    #[test]
    fn unparse_duration() {
        for (d, expect) in [
            (Duration::ZERO, "0s"),
            (Duration::new(1, 2), "1s2ns"),
            (Duration::new(4321, 123_456_789), "4321s123456789ns"),
            (Duration::from_secs(1), "1s"),
            (Duration::from_millis(2), "2000000ns"),
            (Duration::from_micros(3), "3000ns"),
            (Duration::from_nanos(4), "4ns"),
        ] {
            assert_eq!(duration(d), expect);
            assert_eq!(parse::duration(duration(d)).unwrap(), d);
        }
    }
}
