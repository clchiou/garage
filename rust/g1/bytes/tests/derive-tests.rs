use bytes::{Buf, TryGetError};

use g1_bytes::{BufExt, BufMutExt, BufPeekExt};

#[derive(BufExt, BufPeekExt, BufMutExt, Debug, Eq, PartialEq)]
#[endian("little")]
struct Struct {
    x: u16,
    #[endian("big")]
    y: u16,
}

#[derive(BufExt, BufPeekExt, BufMutExt, Debug, Eq, PartialEq)]
struct Tuple(u16, #[endian("little")] u32);

#[derive(BufExt, BufPeekExt, BufMutExt, Debug, Eq, PartialEq)]
struct Unit;

#[test]
fn buf_ext() {
    let x = Struct {
        x: 0x0201,
        y: 0x0304,
    };
    let mut buf: &[u8] = &[1, 2, 3, 4];
    assert_eq!(buf.get_struct(), x);
    assert_eq!(buf, &[]);
    let mut buf: &[u8] = &[1, 2, 3, 4];
    assert_eq!(buf.try_get_struct(), Ok(x));
    assert_eq!(buf, &[]);
    let mut buf: &[u8] = &[0; 3];
    assert_eq!(
        buf.try_get_struct(),
        Err(TryGetError {
            requested: 4,
            available: 3,
        }),
    );
    assert_eq!(buf, &[0; 3]);

    let x = Tuple(0x0102, 0x06050403);
    let mut buf: &[u8] = &[1, 2, 3, 4, 5, 6];
    assert_eq!(buf.get_tuple(), x);
    assert_eq!(buf, &[]);
    let mut buf: &[u8] = &[1, 2, 3, 4, 5, 6];
    assert_eq!(buf.try_get_tuple(), Ok(x));
    assert_eq!(buf, &[]);
    let mut buf: &[u8] = &[0; 5];
    assert_eq!(
        buf.try_get_tuple(),
        Err(TryGetError {
            requested: 6,
            available: 5,
        }),
    );
    assert_eq!(buf, &[0; 5]);

    let mut buf: &[u8] = &[];
    assert_eq!(buf.get_unit(), Unit);
    assert_eq!(buf, &[]);
    assert_eq!(buf.try_get_unit(), Ok(Unit));
    assert_eq!(buf, &[]);
}

#[test]
fn buf_peek_ext() {
    let x = Struct {
        x: 0x0201,
        y: 0x0304,
    };
    let buf: &[u8] = &[1, 2, 3, 4];
    assert_eq!(buf.peek_struct(), Ok(x));
    let buf: &[u8] = &[0; 3];
    assert_eq!(
        buf.peek_struct(),
        Err(TryGetError {
            requested: 4,
            available: 3,
        }),
    );

    let x = Tuple(0x0102, 0x06050403);
    let buf: &[u8] = &[1, 2, 3, 4, 5, 6];
    assert_eq!(buf.peek_tuple(), Ok(x));
    let buf: &[u8] = &[0; 5];
    assert_eq!(
        buf.peek_tuple(),
        Err(TryGetError {
            requested: 6,
            available: 5,
        }),
    );

    let buf: &[u8] = &[];
    assert_eq!(buf.peek_unit(), Ok(Unit));
}

#[test]
fn buf_mut_ext() {
    let mut buf = Vec::new();
    buf.put_struct(&Struct {
        x: 0x0201,
        y: 0x0304,
    });
    assert_eq!(buf, [1, 2, 3, 4]);

    let mut buf = Vec::new();
    buf.put_tuple(&Tuple(0x0102, 0x06050403));
    assert_eq!(buf, [1, 2, 3, 4, 5, 6]);

    let mut buf = Vec::new();
    buf.put_unit(&Unit);
    assert_eq!(buf, []);
}
