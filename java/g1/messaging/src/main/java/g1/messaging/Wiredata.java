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

    MessageReader toUpper(
        byte[] buffer, int offset, int length
    ) throws IOException;

    default MessageReader toUpper(byte[] buffer) throws IOException {
        return toUpper(buffer, 0, buffer.length);
    }

    byte[] toLower(MessageBuilder builder) throws IOException;
}
