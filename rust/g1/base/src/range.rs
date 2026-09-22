use std::error::Error;
use std::fmt::{self, Display, Formatter};
use std::ops::{Bound, IntoBounds, RangeBounds};
use std::range::{Range, RangeFrom, RangeFull, RangeInclusive, RangeTo, RangeToInclusive};
use std::str::FromStr;

// Provide a rudimentary `FromStr` implementation for range types.  Note that parsing will be
// ambiguous if the `Idx` input format can contain `..` or `=`.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub enum RangeKind<Idx> {
    Range(Range<Idx>),
    RangeInclusive(RangeInclusive<Idx>),
    RangeFrom(RangeFrom<Idx>),
    RangeTo(RangeTo<Idx>),
    RangeToInclusive(RangeToInclusive<Idx>),
    RangeFull(RangeFull),
}

impl<Idx> Display for RangeKind<Idx>
where
    Idx: Display,
{
    fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
        match self {
            Self::Range(Range { start, end }) => write!(f, "{start}..{end}"),
            Self::RangeInclusive(RangeInclusive { start, last }) => write!(f, "{start}..={last}"),
            Self::RangeFrom(RangeFrom { start }) => write!(f, "{start}.."),
            Self::RangeTo(RangeTo { end }) => write!(f, "..{end}"),
            Self::RangeToInclusive(RangeToInclusive { last }) => write!(f, "..={last}"),
            Self::RangeFull(RangeFull) => f.write_str(".."),
        }
    }
}

impl<Idx> FromStr for RangeKind<Idx>
where
    Idx: FromStr,
{
    type Err = ParseRangeError<<Idx as FromStr>::Err>;

    fn from_str(range: &str) -> Result<Self, Self::Err> {
        let (start, end) = range
            .split_once("..")
            .ok_or(ParseRangeError::MissingRangeOperator)?;
        let (end, inclusive) = match end.strip_prefix("=") {
            Some(end) => (end, true),
            None => (end, false),
        };
        if end.is_empty() && inclusive {
            return Err(ParseRangeError::InclusiveRangeWithNoEnd);
        }

        let start = if start.is_empty() {
            Bound::Unbounded
        } else {
            Bound::Included(start.parse().map_err(ParseRangeError::Start)?)
        };

        let end = if end.is_empty() {
            assert!(!inclusive);
            Bound::Unbounded
        } else {
            let end = end.parse().map_err(ParseRangeError::End)?;
            if inclusive {
                Bound::Included(end)
            } else {
                Bound::Excluded(end)
            }
        };

        Ok(match start {
            Bound::Included(start) => match end {
                Bound::Excluded(end) => Self::Range((start..end).into()),
                Bound::Included(last) => Self::RangeInclusive((start..=last).into()),
                Bound::Unbounded => Self::RangeFrom((start..).into()),
            },
            Bound::Unbounded => match end {
                Bound::Excluded(end) => Self::RangeTo(..end),
                Bound::Included(last) => Self::RangeToInclusive((..=last).into()),
                Bound::Unbounded => Self::RangeFull(..),
            },
            Bound::Excluded(_) => unreachable!(),
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParseRangeError<E> {
    MissingRangeOperator,
    InclusiveRangeWithNoEnd,
    Start(E),
    End(E),
}

impl<E> Display for ParseRangeError<E>
where
    E: Display,
{
    fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
        match self {
            Self::MissingRangeOperator => f.write_str("missing range operator"),
            Self::InclusiveRangeWithNoEnd => f.write_str("inclusive range with no end"),
            Self::Start(error) => write!(f, "invalid range start: {error}"),
            Self::End(error) => write!(f, "invalid range end: {error}"),
        }
    }
}

impl<E> Error for ParseRangeError<E> where E: Error {}

macro_rules! dispatch {
    ($self:ident, |$range:ident| $expr:expr) => {
        match $self {
            Self::Range($range) => $expr,
            Self::RangeInclusive($range) => $expr,
            Self::RangeFrom($range) => $expr,
            Self::RangeTo($range) => $expr,
            Self::RangeToInclusive($range) => $expr,
            Self::RangeFull($range) => $expr,
        }
    };
}

impl<Idx> RangeBounds<Idx> for RangeKind<Idx> {
    fn start_bound(&self) -> Bound<&Idx> {
        dispatch!(self, |r| r.start_bound())
    }

    fn end_bound(&self) -> Bound<&Idx> {
        dispatch!(self, |r| r.end_bound())
    }
}

impl<Idx> IntoBounds<Idx> for RangeKind<Idx> {
    fn into_bounds(self) -> (Bound<Idx>, Bound<Idx>) {
        dispatch!(self, |r| r.into_bounds())
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches;

    use super::*;

    #[test]
    fn parse() {
        for (testdata, expect) in [
            ("1..2", RangeKind::Range((1..2).into())),
            ("1..=2", RangeKind::RangeInclusive((1..=2).into())),
            ("1..", RangeKind::RangeFrom((1..).into())),
            ("..2", RangeKind::RangeTo((..2).into())),
            ("..=2", RangeKind::RangeToInclusive((..=2).into())),
            ("..", RangeKind::RangeFull((..).into())),
        ] {
            assert_eq!(testdata.parse(), Ok(expect));
        }

        assert_eq!(
            "".parse::<RangeKind<u8>>(),
            Err(ParseRangeError::MissingRangeOperator),
        );
        assert_eq!(
            "1..=".parse::<RangeKind<u8>>(),
            Err(ParseRangeError::InclusiveRangeWithNoEnd),
        );
        assert_matches!(
            "1 ..2".parse::<RangeKind<u8>>(),
            Err(ParseRangeError::Start(_)),
        );
        assert_matches!(
            "1.. 2".parse::<RangeKind<u8>>(),
            Err(ParseRangeError::End(_)),
        );
    }
}
