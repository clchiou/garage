package g1.msg;

import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;
import org.capnproto.Serialize;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Channels;

// TODO: Should we replace `byte[]` with a `java.nio.ByteBuffer`?
public class Capnp {
    /**
     * Constant copied from {@code org.capnproto.Constants}.
     */
    private static final int BYTES_PER_WORD = 8;

    private Capnp() {
        throw new AssertionError();
    }

    public static MessageReader decode(byte[] buffer) throws Exception {
        return decode(buffer, 0, buffer.length);
    }

    public static MessageReader decode(byte[] buffer, int offset, int length) throws Exception {
        return Serialize.read(ByteBuffer.wrap(buffer, offset, length));
    }

    public static byte[] encode(MessageBuilder builder) {
        int size = (int) Serialize.computeSerializedSizeInWords(builder);
        ByteArrayOutputStream stream = new ByteArrayOutputStream(
            // Reserve an extra 16 bytes, just to be safe.
            size * BYTES_PER_WORD + 16
        );
        try {
            Serialize.write(Channels.newChannel(stream), builder);
        } catch (IOException e) {
            // Turn it into an unchecked exception.
            throw new RuntimeException(e);
        }
        return stream.toByteArray();
    }
}
