package g1.messaging;

import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;
import org.capnproto.Serialize;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Channels;

/**
 * Expose unpacked Cap'n Proto format.
 */
public class Unpacked implements Wiredata {
    public static final Wiredata WIREDATA = new Unpacked();

    @Override
    public MessageReader toUpper(
        byte[] buffer, int offset, int length
    ) throws IOException {
        return Serialize.read(ByteBuffer.wrap(buffer, offset, length));
    }

    @Override
    public byte[] toLower(MessageBuilder builder) throws IOException {
        int size = (int) Serialize.computeSerializedSizeInWords(builder);
        ByteArrayOutputStream stream = new ByteArrayOutputStream(
            // Reserve extra 16 bytes; just to be safe.
            size * BYTES_PER_WORD + 16
        );
        Serialize.write(Channels.newChannel(stream), builder);
        return stream.toByteArray();
    }
}
