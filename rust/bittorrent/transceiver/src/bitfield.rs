use bitvec::prelude::*;

// Use the same bit layout as the wire format for faster conversion.
pub(crate) type Bitfield = BitSlice<u8, Msb0>;

pub(crate) trait BitfieldExt {
    fn from_bytes(bytes: &[u8], num_pieces: usize) -> Option<&Self>;

    fn check_spare_bits(&self, num_pieces: usize) -> bool;
}

impl BitfieldExt for Bitfield {
    fn from_bytes(bytes: &[u8], num_pieces: usize) -> Option<&Self> {
        let bitfield = bytes.view_bits();
        // Check and remove spare bits.
        if bitfield.check_spare_bits(num_pieces) {
            Some(&bitfield[0..num_pieces])
        } else {
            None
        }
    }

    fn check_spare_bits(&self, num_pieces: usize) -> bool {
        self.len() >= num_pieces && self[num_pieces..].not_any()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn from_bytes() {
        assert_eq!(
            Bitfield::from_bytes(&[0x38], 5),
            Some(bits![u8, Msb0; 0, 0, 1, 1, 1]),
        );
        assert_eq!(Bitfield::from_bytes(&[0x01], 5), None);
    }

    #[test]
    fn spare_bits() {
        let bitfield = bits![u8, Msb0; 0, 0, 0, 0, 1, 0, 0, 0];
        assert_eq!(bitfield.check_spare_bits(0), false);
        assert_eq!(bitfield.check_spare_bits(4), false);
        assert_eq!(bitfield.check_spare_bits(5), true);
        assert_eq!(bitfield.check_spare_bits(8), true);
        assert_eq!(bitfield.check_spare_bits(9), false);
    }
}
