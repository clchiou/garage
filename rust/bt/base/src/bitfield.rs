use bitvec::prelude::*;

// Use the BEP 3 wire format's bit layout for faster conversion.
pub type Bitfield = BitVec<u8, Msb0>;
