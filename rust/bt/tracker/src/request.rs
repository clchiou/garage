use std::borrow::Cow;

use percent_encoding::{self, NON_ALPHANUMERIC};

use g1_url::UpdateQuery;

use bt_base::{InfoHash, PeerId};

#[derive(Clone, Debug, Default, Eq, PartialEq, UpdateQuery)]
pub struct Request {
    //
    // BEP 3
    //
    #[g1_url(insert_raw, to_string_with = "bytes_to_str")]
    pub info_hash: InfoHash,

    #[g1_url(rename = "peer_id", insert_raw, to_string_with = "bytes_to_str")]
    pub self_id: PeerId,

    pub ip: Option<String>,
    pub port: u16,

    pub uploaded: u64,
    pub downloaded: u64,
    pub left: u64,

    #[g1_url(to_string_with = "Event::to_str")]
    pub event: Option<Event>,

    //
    // BEP 3, allegedly (I cannot find them in the BEP text).
    //
    #[g1_url(rename = "numwant")]
    pub num_want: Option<usize>,

    pub key: Option<String>,

    #[g1_url(rename = "trackerid")]
    pub tracker_id: Option<String>,

    //
    // BEP 23
    //
    #[g1_url(to_string_with = "bool_to_str")]
    pub compact: Option<bool>,

    //
    // BEP 23, allegedly (I cannot find them in the BEP text).
    //
    #[g1_url(to_string_with = "bool_to_str")]
    pub no_peer_id: Option<bool>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Event {
    Started,
    Completed,
    Stopped,
}

fn bool_to_str(b: &bool) -> &'static str {
    if *b { "1" } else { "0" }
}

fn bytes_to_str<T>(bytes: &T) -> Cow<str>
where
    T: AsRef<[u8]>,
{
    // Although the [URL spec] only requires you to %-escape a small set of characters, in practice
    // you probably should %-escape all non-alphanumeric characters.
    //
    // [URL spec]: https://url.spec.whatwg.org/#special-query-percent-encode-set
    percent_encoding::percent_encode(bytes.as_ref(), NON_ALPHANUMERIC).into()
}

impl Event {
    #[allow(clippy::wrong_self_convention)]
    fn to_str(&self) -> &'static str {
        match self {
            Self::Started => "started",
            Self::Completed => "completed",
            Self::Stopped => "stopped",
        }
    }
}

#[cfg(test)]
mod tests {
    use std::mem;

    use hex_literal::hex;
    use url::Url;

    use g1_url::UrlExt;

    use super::*;

    #[test]
    fn request() {
        let request = Request::default();
        assert_eq!(request.query_pairs().collect::<Vec<_>>(), &[]);
        let url = Url::parse("http://127.0.0.1/").unwrap();
        assert_eq!(url.clone().update_query(&[&request]), url);

        let request = Request {
            info_hash: InfoHash::from(hex!("00010203040506070809 0a0b0c0d0e0f 10111213")),
            self_id: PeerId::from(hex!("141516171819 1a1b1c1d1e1f 2021222324252627")),
            ip: Some("localhost".to_string()),
            port: 6881,
            uploaded: 1,
            downloaded: 2,
            left: 3,
            event: Some(Event::Started),
            num_want: Some(50),
            key: Some("spam".to_string()),
            tracker_id: Some("egg".to_string()),
            compact: Some(true),
            no_peer_id: Some(true),
        };
        let expect: &[(Cow<str>, Cow<str>)] = &[
            ("compact".into(), "1".into()),
            ("downloaded".into(), "2".into()),
            ("event".into(), "started".into()),
            ("ip".into(), "localhost".into()),
            ("key".into(), "spam".into()),
            ("left".into(), "3".into()),
            ("no_peer_id".into(), "1".into()),
            ("numwant".into(), "50".into()),
            ("port".into(), "6881".into()),
            ("trackerid".into(), "egg".into()),
            ("uploaded".into(), "1".into()),
        ];
        let expect_raw: &[(Cow<str>, Cow<str>)] = &[
            (
                "info_hash".into(),
                "%00%01%02%03%04%05%06%07%08%09%0A%0B%0C%0D%0E%0F%10%11%12%13".into(),
            ),
            (
                "peer_id".into(),
                "%14%15%16%17%18%19%1A%1B%1C%1D%1E%1F%20%21%22%23%24%25%26%27".into(),
            ),
        ];

        assert_eq!(request.query_pairs().collect::<Vec<_>>(), expect);

        let mut expect_url = "http://127.0.0.1/?".to_string();
        let mut first = true;
        for (key, value) in expect.into_iter().chain(expect_raw) {
            if !mem::take(&mut first) {
                expect_url.push('&');
            }
            expect_url.push_str(key);
            expect_url.push('=');
            expect_url.push_str(value);
        }
        let expect_url = Url::parse(&expect_url).unwrap();
        let url = Url::parse("http://127.0.0.1/").unwrap();
        assert_eq!(url.update_query(&[&request]), expect_url);
    }
}
