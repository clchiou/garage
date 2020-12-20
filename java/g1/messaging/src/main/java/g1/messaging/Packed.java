package g1.messaging;

import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;
import org.capnproto.SerializePacked;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.channels.Channels;

/**
 * Expose packed Cap'n Proto format.
 */
public class Packed implements Wiredata {
    public static final Wiredata WIREDATA = new Packed();

    @Override
    public MessageReader toUpper(
        byte[] buffer, int offset, int length
    ) throws IOException {
        return SerializePacked.readFromUnbuffered(
            Channels.newChannel(
                new ByteArrayInputStream(buffer, offset, length)
            )
        );
    }

    @Override
    public byte[] toLower(MessageBuilder builder) throws IOException {
        ByteArrayOutputStream stream = new ByteArrayOutputStream();
        SerializePacked.writeToUnbuffered(
            Channels.newChannel(stream), builder
        );
        return stream.toByteArray();
    }
}
