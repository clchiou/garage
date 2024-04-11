pub use zmq::Message as Frame;

pub use crate::Multipart;

#[derive(Debug, Eq, PartialEq)]
pub struct Envelope<T = Vec<Frame>> {
    routing_id: Vec<Frame>,
    data: T,
}

impl<T> Envelope<T> {
    pub fn new(routing_id: Vec<Frame>, data: T) -> Self {
        Self { routing_id, data }
    }

    pub fn routing_id(&self) -> &[Frame] {
        &self.routing_id
    }

    pub fn data(&self) -> &T {
        &self.data
    }

    pub fn map<F, U>(self, f: F) -> Envelope<U>
    where
        F: FnOnce(T) -> U,
    {
        Envelope::new(self.routing_id, f(self.data))
    }

    pub fn unwrap(self) -> (Vec<Frame>, T) {
        (self.routing_id, self.data)
    }
}

impl<T> Envelope<Option<T>> {
    pub fn transpose(self) -> Option<Envelope<T>> {
        Some(Envelope::new(self.routing_id, self.data?))
    }
}

impl<T, E> Envelope<Result<T, E>> {
    pub fn transpose(self) -> Result<Envelope<T>, E> {
        Ok(Envelope::new(self.routing_id, self.data?))
    }

    pub fn unzip(self) -> Result<Envelope<T>, Envelope<E>> {
        match self.data {
            Ok(data) => Ok(Envelope::new(self.routing_id, data)),
            Err(error) => Err(Envelope::new(self.routing_id, error)),
        }
    }
}

fn delimiter_index(frames: &Multipart) -> Option<usize> {
    frames.iter().position(|frame| frame.is_empty())
}

impl TryFrom<Multipart> for Envelope<Vec<Frame>> {
    type Error = Multipart;

    fn try_from(mut frames: Multipart) -> Result<Self, Self::Error> {
        let Some(i) = delimiter_index(&frames) else {
            return Err(frames);
        };
        let data = frames.split_off(i + 1);
        assert!(frames.pop().unwrap().is_empty());
        Ok(Self {
            routing_id: frames,
            data,
        })
    }
}

impl From<Envelope<Vec<Frame>>> for Multipart {
    fn from(message: Envelope<Vec<Frame>>) -> Self {
        let Envelope {
            routing_id: mut frames,
            mut data,
        } = message;
        frames.push(Frame::new());
        frames.append(&mut data);
        frames
    }
}

//
// Implement the "exactly one data frame" special case.
//

impl TryFrom<Multipart> for Envelope<Frame> {
    type Error = Multipart;

    fn try_from(mut frames: Multipart) -> Result<Self, Self::Error> {
        let Some(i) = delimiter_index(&frames) else {
            return Err(frames);
        };
        if i + 2 != frames.len() {
            return Err(frames);
        }
        let data = frames.pop().unwrap();
        assert!(frames.pop().unwrap().is_empty());
        Ok(Self {
            routing_id: frames,
            data,
        })
    }
}

impl From<Envelope<Frame>> for Multipart {
    fn from(message: Envelope<Frame>) -> Self {
        let Envelope {
            routing_id: mut frames,
            data,
        } = message;
        frames.push(Frame::new());
        frames.push(data);
        frames
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn m<const N: usize>(frames: [&[u8]; N]) -> Multipart {
        frames.into_iter().map(f).collect()
    }

    fn f(frame: &[u8]) -> Frame {
        frame.into()
    }

    #[test]
    fn conversion() {
        for testdata in [
            || (m([b""]), Envelope::new(m([]), m([]))),
            || (m([b"", b"foo"]), Envelope::new(m([]), m([b"foo"]))),
            || {
                (
                    m([b"", b"foo", b"bar"]),
                    Envelope::new(m([]), m([b"foo", b"bar"])),
                )
            },
            || {
                (
                    m([b"spam", b"", b"foo"]),
                    Envelope::new(m([b"spam"]), m([b"foo"])),
                )
            },
            || {
                (
                    m([b"spam", b"egg", b"", b"foo"]),
                    Envelope::new(m([b"spam", b"egg"]), m([b"foo"])),
                )
            },
        ] {
            let (frames, envelope) = testdata();
            assert_eq!(Envelope::try_from(frames), Ok(envelope));
            let (frames, envelope) = testdata();
            assert_eq!(Multipart::from(envelope), frames);
        }

        assert_eq!(
            Envelope::<Vec<Frame>>::try_from(m([b"foo"])),
            Err(m([b"foo"])),
        );
    }

    #[test]
    fn conversion_one() {
        for testdata in [
            || (m([b"", b"foo"]), Envelope::new(m([]), f(b"foo"))),
            || {
                (
                    m([b"spam", b"", b"foo"]),
                    Envelope::new(m([b"spam"]), f(b"foo")),
                )
            },
            || {
                (
                    m([b"spam", b"egg", b"", b"foo"]),
                    Envelope::new(m([b"spam", b"egg"]), f(b"foo")),
                )
            },
        ] {
            let (frames, envelope) = testdata();
            assert_eq!(Envelope::try_from(frames), Ok(envelope));
            let (frames, envelope) = testdata();
            assert_eq!(Multipart::from(envelope), frames);
        }

        assert_eq!(Envelope::<Frame>::try_from(m([b"foo"])), Err(m([b"foo"])));
        assert_eq!(Envelope::<Frame>::try_from(m([b""])), Err(m([b""])));
        assert_eq!(
            Envelope::<Frame>::try_from(m([b"", b"foo", b"bar"])),
            Err(m([b"", b"foo", b"bar"])),
        );
    }
}
