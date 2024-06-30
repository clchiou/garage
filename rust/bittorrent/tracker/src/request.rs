use std::collections::VecDeque;
use std::net::IpAddr;

use percent_encoding::{self, AsciiSet, NON_ALPHANUMERIC};
use rand::prelude::*;

use bittorrent_base::{InfoHash, PeerId};
use bittorrent_metainfo::Metainfo;

use crate::error::Error;

// Although the [URL spec] only requires you to %-escape a small set of characters, in practice you
// probably should %-escape all non-alphanumeric characters.
//
// [URL spec]: https://url.spec.whatwg.org/#special-query-percent-encode-set
const QUERY: &AsciiSet = NON_ALPHANUMERIC;

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct AnnounceUrls {
    urls: Vec<VecDeque<String>>,
    i: usize,
    j: usize,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Request<'a> {
    pub info_hash: InfoHash,
    pub self_id: PeerId,
    pub port: u16,
    pub uploaded: u64,
    pub downloaded: u64,
    pub left: u64,
    pub compact: bool,
    pub no_peer_id: bool,
    pub event: Option<Event>,
    pub ip: Option<IpAddr>,
    pub num_want: Option<u16>,
    pub key: Option<&'a str>,
    pub tracker_id: Option<&'a str>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Event {
    Started,
    Completed,
    Stopped,
}

impl AnnounceUrls {
    pub(crate) fn new(metainfo: &Metainfo) -> Self {
        Self {
            urls: if let Some(list) = &metainfo.announce_list {
                let mut rng = rand::thread_rng();
                list.iter()
                    .map(|urls| {
                        let mut urls: VecDeque<_> =
                            urls.iter().map(|url| url.to_string()).collect();
                        // Shuffle the URLs as specified by BEP 12.
                        urls.make_contiguous().shuffle(&mut rng);
                        urls
                    })
                    .collect()
            } else if let Some(url) = &metainfo.announce {
                vec![VecDeque::from([url.to_string()])]
            } else {
                panic!("expect announce or announce_list: {:?}", metainfo);
            },
            i: 0,
            j: 0,
        }
    }

    pub(crate) fn url(&self) -> &str {
        &self.urls[self.i][self.j]
    }

    /// Moves the succeeded URL to the front as specified in BEP 12.
    pub(crate) fn succeed(&mut self) {
        let urls = &mut self.urls[self.i];
        let url = urls.remove(self.j).unwrap();
        urls.push_front(url);
        self.i = 0;
        self.j = 0;
    }

    /// Moves the internal index to the next URL as specified in BEP 12.
    pub(crate) fn fail(&mut self) -> Result<(), Error> {
        self.j = (self.j + 1) % self.urls[self.i].len();
        if self.j == 0 {
            self.i = (self.i + 1) % self.urls.len();
        }
        if self.i == 0 && self.j == 0 {
            Err(Error::AnnounceUrlsFailed)
        } else {
            Ok(())
        }
    }
}

// Some trackers only support the compact peer representation.
const COMPACT: bool = true;
// Trackers ignore this option when `compact` is true.
const NO_PEER_ID: bool = false;

// TODO: What default value should we use?
const NUM_WANT: Option<u16> = Some(64);

impl<'a> Request<'a> {
    /// Makes a request with sensible defaults.
    pub fn new(
        info_hash: InfoHash,
        self_id: PeerId,
        port: u16,
        uploaded: u64,
        downloaded: u64,
        left: u64,
        event: Option<Event>,
    ) -> Self {
        Self {
            info_hash,
            self_id,
            port,
            uploaded,
            downloaded,
            left,
            compact: COMPACT,
            no_peer_id: NO_PEER_ID,
            event,
            ip: None,
            num_want: NUM_WANT,
            key: None,
            tracker_id: None,
        }
    }

    pub fn append_url_query_to(&self, query: &mut String) {
        macro_rules! field {
            ($name:tt => $value:expr) => {{
                query.push_str(stringify!($name));
                query.push('=');
                query.push_str($value);
            }};
            ($name:tt => %$value:expr) => {{
                query.push_str(stringify!($name));
                query.push('=');
                query.extend($value);
            }};
            ($name:ident) => {{
                query.push_str(stringify!($name));
                query.push('=');
                query.push_str(&self.$name.to_string());
            }};
        }

        field!(info_hash => %percent_encoding::percent_encode(self.info_hash.as_ref(), QUERY));
        query.push('&');
        field!(peer_id => %percent_encoding::percent_encode(self.self_id.as_ref(), QUERY));
        query.push('&');
        field!(port);
        query.push('&');
        field!(uploaded);
        query.push('&');
        field!(downloaded);
        query.push('&');
        field!(left);
        query.push('&');
        field!(compact => if self.compact { "1" } else { "0" });
        if !self.compact {
            query.push('&');
            field!(no_peer_id => if self.no_peer_id { "1" } else { "0" });
        }
        if let Some(event) = &self.event {
            query.push('&');
            field!(event => match event {
                Event::Started => "started",
                Event::Completed => "completed",
                Event::Stopped => "stopped",
            });
        }
        if let Some(ip) = self.ip {
            query.push('&');
            field!(ip => &ip.to_string());
        }
        if let Some(num_want) = self.num_want {
            query.push('&');
            field!(numwant => &num_want.to_string());
        }
        if let Some(key) = &self.key {
            query.push('&');
            field!(key => %percent_encoding::utf8_percent_encode(key, QUERY));
        }
        if let Some(tracker_id) = &self.tracker_id {
            query.push('&');
            field!(trackerid => %percent_encoding::utf8_percent_encode(tracker_id, QUERY));
        }
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl AnnounceUrls {
        pub fn new_mock(urls: &[&[&str]]) -> Self {
            Self {
                urls: urls
                    .into_iter()
                    .map(|urls| urls.into_iter().map(|url| url.to_string()).collect())
                    .collect(),
                i: 0,
                j: 0,
            }
        }
    }

    impl<'a> Request<'a> {
        pub fn new_dummy() -> Self {
            Self {
                info_hash: InfoHash::new(Default::default()),
                self_id: PeerId::new(Default::default()),
                port: 0,
                uploaded: 0,
                downloaded: 0,
                left: 0,
                compact: false,
                no_peer_id: false,
                event: None,
                ip: None,
                num_want: None,
                key: None,
                tracker_id: None,
            }
        }

        pub(crate) fn to_string(&self) -> String {
            let mut query = String::new();
            self.append_url_query_to(&mut query);
            query
        }
    }
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;

    use super::*;

    #[test]
    fn announce_urls_new() {
        let mut metainfo = Metainfo::new_dummy();

        metainfo.announce = Some("x");
        assert_eq!(
            AnnounceUrls::new(&metainfo),
            AnnounceUrls::new_mock(&[&["x"]]),
        );

        // Prefer `announce_list` over `announce`.
        metainfo.announce_list = Some(vec![vec!["y"], vec!["z"]]);
        assert_eq!(
            AnnounceUrls::new(&metainfo),
            AnnounceUrls::new_mock(&[&["y"], &["z"]]),
        );
    }

    #[test]
    fn announce_urls_succeed() {
        let mut urls = AnnounceUrls::new_mock(&[&["x", "y", "z"], &["w"]]);
        assert_eq!(urls.url(), "x");
        assert_eq!(urls, AnnounceUrls::new_mock(&[&["x", "y", "z"], &["w"]]));

        urls.succeed();
        assert_eq!(urls.url(), "x");
        assert_eq!(urls, AnnounceUrls::new_mock(&[&["x", "y", "z"], &["w"]]));

        urls.j = 1;
        assert_eq!(urls.url(), "y");
        urls.succeed();
        assert_eq!(urls, AnnounceUrls::new_mock(&[&["y", "x", "z"], &["w"]]));

        urls.j = 2;
        assert_eq!(urls.url(), "z");
        urls.succeed();
        assert_eq!(urls, AnnounceUrls::new_mock(&[&["z", "y", "x"], &["w"]]));

        urls.i = 1;
        assert_eq!(urls.url(), "w");
        urls.succeed();
        assert_eq!(urls, AnnounceUrls::new_mock(&[&["z", "y", "x"], &["w"]]));
    }

    #[test]
    fn announce_urls_fail() {
        let mut urls = AnnounceUrls::new_mock(&[&["x", "y", "z"], &["w"]]);
        let mut expect = AnnounceUrls::new_mock(&[&["x", "y", "z"], &["w"]]);
        assert_eq!(urls.url(), "x");
        assert_eq!(urls, expect);

        assert_eq!(urls.fail(), Ok(()));
        assert_eq!(urls.url(), "y");
        expect.j = 1;
        assert_eq!(urls, expect);

        assert_eq!(urls.fail(), Ok(()));
        assert_eq!(urls.url(), "z");
        expect.j = 2;
        assert_eq!(urls, expect);

        assert_eq!(urls.fail(), Ok(()));
        assert_eq!(urls.url(), "w");
        expect.i = 1;
        expect.j = 0;
        assert_eq!(urls, expect);

        assert_eq!(urls.fail(), Err(Error::AnnounceUrlsFailed));
        assert_eq!(urls.url(), "x");
        expect.i = 0;
        expect.j = 0;
        assert_eq!(urls, expect);
    }

    #[test]
    fn request_new() {
        assert_eq!(
            Request::new(
                InfoHash::new(hex!("da39a3ee5e6b4b0d3255bfef95601890afd80709")),
                PeerId::new(*b"0123456789abcdef0123"),
                6881,
                1,
                2,
                42,
                Some(Event::Started),
            ),
            Request {
                info_hash: InfoHash::new(hex!("da39a3ee5e6b4b0d3255bfef95601890afd80709")),
                self_id: PeerId::new(*b"0123456789abcdef0123"),
                port: 6881,
                uploaded: 1,
                downloaded: 2,
                left: 42,
                compact: true,
                no_peer_id: false,
                event: Some(Event::Started),
                ip: None,
                num_want: Some(64),
                key: None,
                tracker_id: None,
            },
        );
    }

    #[test]
    fn request_to_url_query() {
        let mut request = Request::new_dummy();
        assert_eq!(
            request.to_string(),
            "info_hash=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            peer_id=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            port=0&uploaded=0&downloaded=0&left=0&compact=0&no_peer_id=0",
        );

        request.no_peer_id = true;
        assert_eq!(
            request.to_string(),
            "info_hash=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            peer_id=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            port=0&uploaded=0&downloaded=0&left=0&compact=0&no_peer_id=1",
        );
        request.compact = true;
        assert_eq!(
            request.to_string(),
            "info_hash=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            peer_id=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            port=0&uploaded=0&downloaded=0&left=0&compact=1",
        );

        request.event = Some(Event::Started);
        assert_eq!(
            request.to_string(),
            "info_hash=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            peer_id=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            port=0&uploaded=0&downloaded=0&left=0&compact=1&event=started",
        );
        request.event = Some(Event::Completed);
        assert_eq!(
            request.to_string(),
            "info_hash=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            peer_id=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            port=0&uploaded=0&downloaded=0&left=0&compact=1&event=completed",
        );
        request.event = Some(Event::Stopped);
        assert_eq!(
            request.to_string(),
            "info_hash=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            peer_id=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            port=0&uploaded=0&downloaded=0&left=0&compact=1&event=stopped",
        );
        request.event = None;

        request.ip = Some("127.0.0.1".parse().unwrap());
        assert_eq!(
            request.to_string(),
            "info_hash=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            peer_id=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            port=0&uploaded=0&downloaded=0&left=0&compact=1&ip=127.0.0.1",
        );
        request.ip = Some("::1".parse().unwrap());
        assert_eq!(
            request.to_string(),
            "info_hash=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            peer_id=%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00%00&\
            port=0&uploaded=0&downloaded=0&left=0&compact=1&ip=::1",
        );
        request.ip = None;

        let mut info_hash = [0u8; 20];
        for i in 0..request.info_hash.as_ref().len() {
            info_hash[i] = i as u8 + 1;
        }
        request.info_hash = InfoHash::new(info_hash);
        let mut self_id = [0u8; 20];
        for i in 0..request.self_id.as_ref().len() {
            self_id[i] = (20 - i) as u8;
        }
        request.self_id = PeerId::new(self_id);
        request.num_want = Some(50);
        request.key = Some("hello world\"#<>'");
        request.tracker_id = Some("spam egg\"#<>'");
        assert_eq!(
            request.to_string(),
            "info_hash=%01%02%03%04%05%06%07%08%09%0A%0B%0C%0D%0E%0F%10%11%12%13%14&\
            peer_id=%14%13%12%11%10%0F%0E%0D%0C%0B%0A%09%08%07%06%05%04%03%02%01&\
            port=0&uploaded=0&downloaded=0&left=0&compact=1&numwant=50&\
            key=hello%20world%22%23%3C%3E%27&\
            trackerid=spam%20egg%22%23%3C%3E%27",
        );
    }
}
