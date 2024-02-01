use std::cmp;
use std::ops::Range;

use bittorrent_base::{BlockDesc, BlockOffset, Dimension, PieceIndex};

/// Progress of receiving a piece.
///
/// NOTE: It is not viable to track progress with a `Set<BlockDesc>`, as peers may send blocks of
/// arbitrary sizes to us.
#[derive(Debug)]
pub(crate) struct Progress {
    not_yet_received: Vec<Range<u64>>,
    piece: PieceIndex, // Just for sanity check.
}

impl Progress {
    pub(crate) fn new(dim: &Dimension, piece: PieceIndex) -> Self {
        Self {
            not_yet_received: new_ranges(dim.piece_size(piece)),
            piece,
        }
    }

    pub(crate) fn is_completed(&self) -> bool {
        self.not_yet_received.is_empty()
    }

    // NOTE: This method assumes the caller has checked `block`.
    pub(crate) fn add(&mut self, block: BlockDesc) -> u64 {
        let BlockDesc(BlockOffset(piece, offset), size) = block;
        assert_eq!(piece, self.piece);
        hollow_out(&mut self.not_yet_received, offset..offset + size)
    }
}

#[allow(clippy::single_range_in_vec_init)]
fn new_ranges(piece_size: u64) -> Vec<Range<u64>> {
    vec![0..piece_size]
}

fn hollow_out(ranges: &mut Vec<Range<u64>>, range: Range<u64>) -> u64 {
    let mut amount = 0;
    let mut i = 0;
    while i < ranges.len() {
        match exclude(&ranges[i], &range) {
            Some((left, right)) => {
                amount += range_size(&ranges[i]) - range_size(&left) - range_size(&right);
                match (left.is_empty(), right.is_empty()) {
                    (true, true) => {
                        ranges.remove(i);
                    }
                    (true, false) => {
                        ranges[i] = right;
                        i += 1;
                    }
                    (false, true) => {
                        ranges[i] = left;
                        i += 1;
                    }
                    (false, false) => {
                        ranges[i] = left;
                        ranges.insert(i + 1, right);
                        i += 2;
                    }
                }
            }
            None => i += 1,
        }
    }
    amount
}

/// Returns `p - q`.
fn exclude(p: &Range<u64>, q: &Range<u64>) -> Option<(Range<u64>, Range<u64>)> {
    let start = cmp::max(p.start, q.start);
    let end = cmp::min(p.end, q.end);
    (start < end).then_some((p.start..start, end..p.end))
}

fn range_size(range: &Range<u64>) -> u64 {
    range.end - range.start
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl Progress {
        pub fn assert_progress<const N: usize>(&self, expect: [Range<u64>; N]) {
            assert_eq!(self.is_completed(), expect.is_empty());
            assert_eq!(
                self.not_yet_received,
                expect.into_iter().collect::<Vec<_>>(),
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn add() {
        let mut progress = Progress::new(&Dimension::new(1, 10, 10, 16384), 0.into());
        progress.assert_progress([0..10]);

        assert_eq!(progress.add((0, 0, 0).into()), 0);
        progress.assert_progress([0..10]);

        assert_eq!(progress.add((0, 1, 2).into()), 2);
        progress.assert_progress([0..1, 3..10]);

        assert_eq!(progress.add((0, 1, 1).into()), 0);
        progress.assert_progress([0..1, 3..10]);

        assert_eq!(progress.add((0, 0, 7).into()), 5);
        progress.assert_progress([7..10]);

        assert_eq!(progress.add((0, 2, 8).into()), 3);
        progress.assert_progress([]);

        assert_eq!(progress.add((0, 3, 4).into()), 0);
        progress.assert_progress([]);
    }

    #[test]
    fn test_hollow_out() {
        let mut ranges = new_ranges(1);
        assert_eq!(ranges, &[0..1]);

        assert_eq!(hollow_out(&mut ranges, 10..20), 0);
        assert_eq!(hollow_out(&mut ranges, 0..0), 0);
        assert_eq!(ranges, &[0..1]);

        assert_eq!(hollow_out(&mut ranges, 0..1), 1);
        assert_eq!(ranges, &[]);
        assert_eq!(hollow_out(&mut ranges, 0..1), 0);
        assert_eq!(ranges, &[]);

        let mut ranges = new_ranges(20);
        assert_eq!(ranges, &[0..20]);

        assert_eq!(hollow_out(&mut ranges, 0..0), 0);
        assert_eq!(hollow_out(&mut ranges, 10..10), 0);
        assert_eq!(hollow_out(&mut ranges, 20..30), 0);
        assert_eq!(ranges, &[0..20]);

        assert_eq!(hollow_out(&mut ranges, 9..11), 2);
        assert_eq!(ranges, &[0..9, 11..20]);
        assert_eq!(hollow_out(&mut ranges, 9..11), 0);
        assert_eq!(ranges, &[0..9, 11..20]);

        assert_eq!(hollow_out(&mut ranges, 7..11), 2);
        assert_eq!(ranges, &[0..7, 11..20]);

        assert_eq!(hollow_out(&mut ranges, 0..3), 3);
        assert_eq!(ranges, &[3..7, 11..20]);

        assert_eq!(hollow_out(&mut ranges, 9..13), 2);
        assert_eq!(ranges, &[3..7, 13..20]);

        assert_eq!(hollow_out(&mut ranges, 4..5), 1);
        assert_eq!(ranges, &[3..4, 5..7, 13..20]);

        assert_eq!(hollow_out(&mut ranges, 19..30), 1);
        assert_eq!(ranges, &[3..4, 5..7, 13..19]);

        assert_eq!(hollow_out(&mut ranges, 1..14), 4);
        assert_eq!(ranges, &[14..19]);

        let mut ranges = new_ranges(20);
        for i in 0..10 {
            assert_eq!(hollow_out(&mut ranges, i..i + 1), 1);
        }
        assert_eq!(ranges, &[10..20]);

        let mut ranges = new_ranges(20);
        for i in (10..20).rev() {
            assert_eq!(hollow_out(&mut ranges, i..i + 1), 1);
        }
        assert_eq!(ranges, &[0..10]);

        let mut ranges = new_ranges(20);
        for i in (1..10).step_by(2) {
            assert_eq!(hollow_out(&mut ranges, i..i + 1), 1);
        }
        assert_eq!(ranges, &[0..1, 2..3, 4..5, 6..7, 8..9, 10..20]);
    }

    #[test]
    fn test_exclude() {
        assert_eq!(exclude(&(10..20), &(15..15)), None);
        assert_eq!(exclude(&(15..15), &(10..20)), None);

        assert_eq!(exclude(&(10..20), &(0..10)), None);
        assert_eq!(exclude(&(10..20), &(20..30)), None);

        assert_eq!(exclude(&(10..20), &(10..20)), Some((10..10, 20..20)));
        assert_eq!(exclude(&(10..20), &(0..30)), Some((10..10, 20..20)));

        assert_eq!(exclude(&(10..20), &(10..15)), Some((10..10, 15..20)));
        assert_eq!(exclude(&(10..20), &(0..15)), Some((10..10, 15..20)));
        assert_eq!(exclude(&(10..20), &(15..20)), Some((10..15, 20..20)));
        assert_eq!(exclude(&(10..20), &(15..30)), Some((10..15, 20..20)));

        assert_eq!(exclude(&(10..20), &(11..19)), Some((10..11, 19..20)));
    }
}
