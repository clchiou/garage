use std::net::{IpAddr, SocketAddr};
use std::ops::RangeInclusive;
use std::time::{Duration, Instant};

use sha1::{Digest, Sha1};

//
// Implementer's Notes: BEP 5 recommends generating tokens by computing the SHA-1 hash of the IP
// address concatenated with a secret that changes every five minutes, and accepting tokens that
// are up to ten minutes old.
//
// For now, we deviate from the recommendation in BEP 5 for the sake of simplicity by generating a
// token as the SHA-1 hash of the IP address, the port, "age", and the secret.  Age is defined as
// the current time divided by the token generation period.
//

#[derive(Debug)]
pub(crate) struct TokenSource {
    start: Instant,
    period: u32,
    valid_since: Age,
    secret: [u8; 8],
}

pub(crate) type Token = [u8; 20];

type Age = u64;

impl TokenSource {
    pub(crate) fn new() -> Self {
        Self::with_state(
            Instant::now(),
            *crate::token_period(),
            *crate::token_valid_since(),
            *crate::token_secret(),
        )
    }

    fn with_state(start: Instant, period: Duration, valid_since: Duration, secret: u64) -> Self {
        let period = u32::try_from(period.as_secs()).unwrap();
        Self {
            start,
            period,
            valid_since: (valid_since / period).as_secs(),
            secret: secret.to_be_bytes(),
        }
    }

    fn age(&self, now: Instant) -> Age {
        (now.saturating_duration_since(self.start) / self.period).as_secs()
    }

    fn valid_range(&self, now: Instant) -> RangeInclusive<Age> {
        let valid_to = self.age(now);
        let valid_from = valid_to.saturating_sub(self.valid_since);
        valid_from..=valid_to
    }

    pub(crate) fn generate(&self, endpoint: SocketAddr) -> Token {
        self.generate_at(endpoint, self.age(Instant::now()))
    }

    fn generate_at(&self, endpoint: SocketAddr, age: Age) -> Token {
        let mut hasher = Sha1::new();
        match endpoint.ip() {
            IpAddr::V4(address) => hasher.update(address.octets()),
            IpAddr::V6(address) => hasher.update(address.octets()),
        }
        hasher.update(endpoint.port().to_be_bytes());
        hasher.update(age.to_be_bytes());
        hasher.update(self.secret);
        hasher.finalize().into()
    }

    pub(crate) fn validate(&self, endpoint: SocketAddr, token: &[u8]) -> bool {
        self.validate_in(endpoint, token, self.valid_range(Instant::now()))
    }

    fn validate_in(
        &self,
        endpoint: SocketAddr,
        token: &[u8],
        mut valid_range: RangeInclusive<u64>,
    ) -> bool {
        valid_range.any(|age| self.generate_at(endpoint, age) == token)
    }
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;

    use super::*;

    const S0: Duration = Duration::from_secs(0);
    const S1: Duration = Duration::from_secs(1);
    const S2: Duration = Duration::from_secs(2);
    const S3: Duration = Duration::from_secs(3);
    const S4: Duration = Duration::from_secs(4);
    const S5: Duration = Duration::from_secs(5);
    const S6: Duration = Duration::from_secs(6);

    fn digest(data: &[u8]) -> Token {
        Sha1::digest(data).into()
    }

    #[test]
    fn age() {
        let t0 = Instant::now();
        let src = TokenSource::with_state(t0, S3, S0, 0);
        assert_eq!(src.age(t0 - S4), 0);
        assert_eq!(src.age(t0 - S3), 0);
        assert_eq!(src.age(t0 - S2), 0);
        assert_eq!(src.age(t0 - S1), 0);
        assert_eq!(src.age(t0), 0);
        assert_eq!(src.age(t0 + S1), 0);
        assert_eq!(src.age(t0 + S2), 0);
        assert_eq!(src.age(t0 + S3), 1);
        assert_eq!(src.age(t0 + S4), 1);
        assert_eq!(src.age(t0 + S5), 1);
        assert_eq!(src.age(t0 + S6), 2);
    }

    #[test]
    fn valid_range() {
        let t0 = Instant::now();
        let t1 = t0 + S1;
        let t2 = t0 + S2;
        let t3 = t0 + S3;
        let make_src = |valid_since| TokenSource::with_state(t0, S1, valid_since, 0);

        let src = make_src(S0);
        assert_eq!(src.valid_range(t0), 0..=0);
        assert_eq!(src.valid_range(t1), 1..=1);
        assert_eq!(src.valid_range(t2), 2..=2);
        assert_eq!(src.valid_range(t3), 3..=3);

        let src = make_src(S1);
        assert_eq!(src.valid_range(t0), 0..=0);
        assert_eq!(src.valid_range(t1), 0..=1);
        assert_eq!(src.valid_range(t2), 1..=2);
        assert_eq!(src.valid_range(t3), 2..=3);

        let src = make_src(S2);
        assert_eq!(src.valid_range(t0), 0..=0);
        assert_eq!(src.valid_range(t1), 0..=1);
        assert_eq!(src.valid_range(t2), 0..=2);
        assert_eq!(src.valid_range(t3), 1..=3);
    }

    #[test]
    fn generate() {
        let endpoint = "127.0.0.1:8000".parse().unwrap();
        let src = TokenSource::with_state(Instant::now(), S1, S0, 0x0102030405060708);
        assert_eq!(
            src.generate_at(endpoint, 0),
            digest(&hex!("7f000001 1f40 0000000000000000 0102030405060708")),
        );
        assert_eq!(
            src.generate_at(endpoint, 1),
            digest(&hex!("7f000001 1f40 0000000000000001 0102030405060708")),
        );
        assert_eq!(
            src.generate_at(endpoint, 2),
            digest(&hex!("7f000001 1f40 0000000000000002 0102030405060708")),
        );
    }

    #[test]
    fn validate() {
        let t0 = Instant::now();
        let t1 = t0 + S1;
        let t2 = t0 + S2;
        let t3 = t0 + S3;
        let make_src =
            |valid_since| TokenSource::with_state(t0, S1, valid_since, 0x0102030405060708);

        let endpoint = "127.0.0.1:8000".parse().unwrap();
        let tokens = [
            digest(&hex!("7f000001 1f40 0000000000000000 0102030405060708")),
            digest(&hex!("7f000001 1f40 0000000000000001 0102030405060708")),
            digest(&hex!("7f000001 1f40 0000000000000002 0102030405060708")),
            digest(&hex!("7f000001 1f40 0000000000000003 0102030405060708")),
        ];

        {
            let src = make_src(S0);
            let validate = |token, now| src.validate_in(endpoint, token, src.valid_range(now));
            assert_eq!(validate(&tokens[0], t0), true);
            assert_eq!(validate(&tokens[1], t0), false);
            assert_eq!(validate(&tokens[2], t0), false);

            assert_eq!(validate(&tokens[0], t1), false);
            assert_eq!(validate(&tokens[1], t1), true);
            assert_eq!(validate(&tokens[2], t1), false);

            assert_eq!(validate(&tokens[0], t2), false);
            assert_eq!(validate(&tokens[1], t2), false);
            assert_eq!(validate(&tokens[2], t2), true);
        }

        {
            let src = make_src(S1);
            let validate = |token, now| src.validate_in(endpoint, token, src.valid_range(now));
            assert_eq!(validate(&tokens[0], t0), true);
            assert_eq!(validate(&tokens[1], t0), false);
            assert_eq!(validate(&tokens[2], t0), false);

            assert_eq!(validate(&tokens[0], t1), true);
            assert_eq!(validate(&tokens[1], t1), true);
            assert_eq!(validate(&tokens[2], t1), false);

            assert_eq!(validate(&tokens[0], t2), false);
            assert_eq!(validate(&tokens[1], t2), true);
            assert_eq!(validate(&tokens[2], t2), true);
        }

        {
            let src = make_src(S2);
            let validate = |token, now| src.validate_in(endpoint, token, src.valid_range(now));
            assert_eq!(validate(&tokens[0], t0), true);
            assert_eq!(validate(&tokens[1], t0), false);
            assert_eq!(validate(&tokens[2], t0), false);
            assert_eq!(validate(&tokens[3], t0), false);

            assert_eq!(validate(&tokens[0], t1), true);
            assert_eq!(validate(&tokens[1], t1), true);
            assert_eq!(validate(&tokens[2], t1), false);
            assert_eq!(validate(&tokens[3], t1), false);

            assert_eq!(validate(&tokens[0], t2), true);
            assert_eq!(validate(&tokens[1], t2), true);
            assert_eq!(validate(&tokens[2], t2), true);
            assert_eq!(validate(&tokens[3], t2), false);

            assert_eq!(validate(&tokens[0], t3), false);
            assert_eq!(validate(&tokens[1], t3), true);
            assert_eq!(validate(&tokens[2], t3), true);
            assert_eq!(validate(&tokens[3], t3), true);
        }
    }
}
