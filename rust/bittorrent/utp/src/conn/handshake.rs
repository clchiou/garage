#[derive(Debug)]
pub(crate) struct Handshake {
    recv_id: u16,
    send_id: u16,
    seq: u16,
}

impl Handshake {
    pub(crate) fn new_connect() -> Self {
        let recv_id = rand::random();
        Self::new(recv_id, recv_id.wrapping_add(1), 1)
    }

    pub(crate) fn new_accept() -> Self {
        Self::new(0, 0, rand::random())
    }

    fn new(recv_id: u16, send_id: u16, seq: u16) -> Self {
        Self {
            recv_id,
            send_id,
            seq,
        }
    }
}
