use std::io;

use bytes::BufMut;
use snafu::prelude::*;

use crate::error::Error;
use crate::error::io::{Error as IoError, IoSnafu};
use crate::int::{INTEGER_BUF_SIZE, Int};

pub(crate) trait Write<E> {
    fn write_u8(&mut self, byte: u8) -> Result<(), E>;

    fn write_slice(&mut self, slice: &[u8]) -> Result<(), E>;

    //
    // Bencode helpers.
    //

    fn write_byte_string(&mut self, bytes: &[u8]) -> Result<(), E> {
        let mut len = [0u8; INTEGER_BUF_SIZE];
        let len = g1_base::format_str!(&mut len, "{}:", bytes.len());
        self.write_slice(len.as_bytes())?;
        self.write_slice(bytes)
    }

    fn write_string(&mut self, string: &str) -> Result<(), E> {
        self.write_byte_string(string.as_bytes())
    }

    fn write_integer<I>(&mut self, int: I) -> Result<(), E>
    where
        I: Int,
    {
        let mut integer = [0u8; INTEGER_BUF_SIZE];
        let integer = g1_base::format_str!(&mut integer, "i{int}e");
        self.write_slice(integer.as_bytes())
    }

    fn write_list_begin(&mut self) -> Result<(), E> {
        self.write_u8(b'l')
    }

    fn write_list_end(&mut self) -> Result<(), E> {
        self.write_u8(b'e')
    }

    fn write_dictionary_begin(&mut self) -> Result<(), E> {
        self.write_u8(b'd')
    }

    fn write_dictionary_end(&mut self) -> Result<(), E> {
        self.write_u8(b'e')
    }
}

impl<B> Write<Error> for B
where
    B: BufMut,
{
    fn write_u8(&mut self, byte: u8) -> Result<(), Error> {
        self.put_u8(byte);
        Ok(())
    }

    fn write_slice(&mut self, slice: &[u8]) -> Result<(), Error> {
        self.put_slice(slice);
        Ok(())
    }
}

impl<W> Write<IoError> for W
where
    W: io::Write,
{
    fn write_u8(&mut self, byte: u8) -> Result<(), IoError> {
        self.write_all(&[byte]).context(IoSnafu)
    }

    fn write_slice(&mut self, slice: &[u8]) -> Result<(), IoError> {
        self.write_all(slice).context(IoSnafu)
    }
}
