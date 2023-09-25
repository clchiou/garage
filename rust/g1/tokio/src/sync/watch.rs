use tokio::sync::watch::Sender;

pub trait Update<T> {
    fn update(&self, value: T) -> bool;
}

impl<T> Update<T> for Sender<T>
where
    T: PartialEq,
{
    fn update(&self, value: T) -> bool {
        self.send_if_modified(move |current| {
            if &value == current {
                false
            } else {
                *current = value;
                true
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use tokio::sync::watch;

    use super::*;

    #[test]
    fn update() {
        let (send, mut recv) = watch::channel(0);
        assert_matches!(recv.has_changed(), Ok(false));
        assert_matches!(*recv.borrow(), 0);

        assert_eq!(send.update(1), true);
        assert_matches!(recv.has_changed(), Ok(true));
        assert_matches!(*recv.borrow_and_update(), 1);

        for _ in 0..3 {
            assert_eq!(send.update(1), false);
            assert_matches!(recv.has_changed(), Ok(false));
            assert_matches!(*recv.borrow(), 1);
        }

        assert_eq!(send.update(2), true);
        assert_matches!(recv.has_changed(), Ok(true));
        assert_matches!(*recv.borrow_and_update(), 2);

        for _ in 0..3 {
            assert_eq!(send.update(2), false);
            assert_matches!(recv.has_changed(), Ok(false));
            assert_matches!(*recv.borrow(), 2);
        }
    }
}
