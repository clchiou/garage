package g1.messaging;

import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;

import java.io.IOException;

/**
 * Interface of converting to/from Cap'n Proto messages.
 * <p>
 * TODO: Should we replace {@code byte[]} with
 * {@link java.nio.ByteBuffer}?
 */
public interface Wiredata {
    /**
     * Constant copied from {@code org.capnproto.Constants}.
     */
    int BYTES_PER_WORD = 8;

    MessageReader upper(
        byte[] buffer, int offset, int length
    ) throws IOException;

    default MessageReader upper(byte[] buffer) throws IOException {
        return upper(buffer, 0, buffer.length);
    }

    byte[] lower(MessageBuilder builder) throws IOException;
}
