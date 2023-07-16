mod rtt;
mod state;
mod window;

use snafu::prelude::*;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub(crate) enum Error {
    #[snafu(display("resend limit exceeded: seq={seq}"))]
    ResendLimitExceeded { seq: u16 },

    #[snafu(display("ack exceed seq: ack={ack} seq={seq}"))]
    AckExceedSeq { ack: u16, seq: u16 },
    #[snafu(display("different eof seq: old={old} new={new}"))]
    DifferentEof { old: u16, new: u16 },
    #[snafu(display("distant seq: seq={seq} in_order_seq={in_order_seq}"))]
    DistantSeq { seq: u16, in_order_seq: u16 },
    #[snafu(display("seq exceed eof seq: seq={seq} eof={eof}"))]
    SeqExceedEof { seq: u16, eof: u16 },
}

const MIN_PACKET_SIZE: usize = 150;
