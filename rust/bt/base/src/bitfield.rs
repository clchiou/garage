use bitvec::prelude::*;
use bytes::Bytes;
use snafu::prelude::*;

// Use the BEP 3 wire format's bit layout for faster conversion.
pub type Bitfield = BitVec<u8, Msb0>;
pub type Bitslice = BitSlice<u8, Msb0>;

pub trait BitfieldExt: Sized {
    // We avoid naming it `try_from_slice` to prevent name conflicts.
    fn try_from_bytes(bytes: &[u8], num_pieces: usize) -> Result<Self, TryFromBytesError>;
}

pub trait BitsliceExt {
    fn check_spare_bits(&self, num_pieces: usize) -> bool;
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("bitfield spare bits: {spare_bits:?}"))]
pub struct TryFromBytesError {
    spare_bits: Bytes,
}

impl BitfieldExt for Bitfield {
    fn try_from_bytes(bytes: &[u8], num_pieces: usize) -> Result<Self, TryFromBytesError> {
        let bytes = bytes.view_bits();
        // Check and remove spare bits.
        if bytes.check_spare_bits(num_pieces) {
            Ok(bytes[0..num_pieces].to_bitvec())
        } else {
            Err(TryFromBytesError {
                spare_bits: bytes[num_pieces..].to_bitvec().into_vec().into(),
            })
        }
    }
}

impl BitsliceExt for Bitslice {
    fn check_spare_bits(&self, num_pieces: usize) -> bool {
        self.len() >= num_pieces && self[num_pieces..].not_any()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn raw_slice() {
        let mut bitfield = Bitfield::new();
        assert_eq!(bitfield.as_raw_slice(), &[] as &[u8]);

        bitfield.push(true);
        assert_eq!(bitfield.as_raw_slice(), &[0x80]);

        bitfield.push(false);
        bitfield.push(true);
        assert_eq!(bitfield.as_raw_slice(), &[0xa0]);

        bitfield.push(false);
        bitfield.push(true);
        bitfield.push(true);
        assert_eq!(bitfield.as_raw_slice(), &[0xac]);

        bitfield.push(false);
        bitfield.push(true);
        bitfield.push(true);
        assert_eq!(bitfield.as_raw_slice(), &[0xad, 0x80]);
    }

    #[test]
    fn try_from_bytes() {
        assert_eq!(
            Bitfield::try_from_bytes(&[0x38], 5),
            Ok(bitvec![u8, Msb0; 0, 0, 1, 1, 1]),
        );
        assert_eq!(
            Bitfield::try_from_bytes(&[0x01], 5),
            Err(TryFromBytesError {
                spare_bits: Bytes::from_static(b"\x01")
            })
        );
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
