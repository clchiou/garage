use std::time::Duration;

use lazy_regex::regex;
use serde::Deserialize;

use crate::Error;

pub trait Parse
where
    Self: Sized,
{
    fn parse(value: &str) -> Result<Self, Error>;
}

impl<T> Parse for T
where
    T: for<'a> Deserialize<'a>,
{
    default fn parse(value: &str) -> Result<Self, Error> {
        serde_json::from_str::<Self>(value).map_err(Error::from)
    }
}

// TODO: This is less useful than I expected.  For example, it does not parse `Option<Duration>`.
// How do we improve this?
impl Parse for Duration {
    fn parse(value: &str) -> Result<Self, Error> {
        serde_json::from_str::<Self>(value)
            .or_else(|error| parse_duration(value).ok_or(error))
            .map_err(Error::from)
    }
}

fn parse_duration(duration: &str) -> Option<Duration> {
    if !regex!(r"(?i)^\s*(?:\d+\s*(?:s|ms|us|ns)\s*)+$").is_match(duration) {
        return None;
    }
    let mut acc = Duration::ZERO;
    for (_, [amount, unit]) in regex!(r"(?i)\s*(\d+)\s*(s|ms|us|ns)\s*")
        .captures_iter(duration)
        .map(|c| c.extract())
    {
        acc += if unit.eq_ignore_ascii_case("s") {
            Duration::from_secs
        } else if unit.eq_ignore_ascii_case("ms") {
            Duration::from_millis
        } else if unit.eq_ignore_ascii_case("us") {
            Duration::from_micros
        } else if unit.eq_ignore_ascii_case("ns") {
            Duration::from_nanos
        } else {
            std::unreachable!()
        }(amount.parse::<u64>().ok()?);
    }
    Some(acc)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_duration() {
        assert_eq!(parse_duration("1s"), Some(Duration::from_secs(1)));
        assert_eq!(parse_duration("2ms"), Some(Duration::from_millis(2)));
        assert_eq!(parse_duration("3us"), Some(Duration::from_micros(3)));
        assert_eq!(parse_duration("4ns"), Some(Duration::from_nanos(4)));

        assert_eq!(
            parse_duration("\t\t 1s 2ms\t\t 3us   4   ns  100\t\tS    200 mS  300Us  400NS \t\t"),
            Some(
                Duration::from_secs(101)
                    + Duration::from_millis(202)
                    + Duration::from_micros(303)
                    + Duration::from_nanos(404)
            ),
        );

        assert_eq!(parse_duration(""), None);
        assert_eq!(parse_duration("   "), None);
        assert_eq!(parse_duration("\t"), None);
        assert_eq!(parse_duration(" abc "), None);

        assert_eq!(parse_duration("1s abc"), None);

        assert_eq!(parse_duration("0.1s"), None);
        assert_eq!(parse_duration("-1s"), None);

        assert_eq!(parse_duration("1ps"), None);
    }
}
