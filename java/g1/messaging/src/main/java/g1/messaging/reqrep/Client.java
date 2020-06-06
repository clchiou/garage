package g1.messaging.reqrep;

import com.google.common.collect.ImmutableList;
import g1.base.Configuration;
import g1.messaging.Packed;
import g1.messaging.Unpacked;
import g1.messaging.Wiredata;
import nng.Context;
import nng.Error;
import nng.Options;
import nng.Protocols;
import nng.Socket;
import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import static g1.messaging.Utils.openSocket;

/**
 * Client of a reqrep socket.
 */
public class Client implements AutoCloseable {
    private static final Logger LOG = LoggerFactory.getLogger(Client.class);

    /**
     * Send timeout.
     * <p>
     * Unit: milliseconds.
     */
    @Configuration
    public static int sendTimeout = 2000;

    /**
     * Receive timeout.
     * <p>
     * Unit: milliseconds.
     */
    @Configuration
    public static int recvTimeout = 4000;

    private final Socket socket;
    private final Wiredata wiredata;

    public Client(String url, boolean packed) {
        socket = openSocket(
            Protocols.REQ0, ImmutableList.of(url), ImmutableList.of()
        );
        try {
            socket.set(Options.NNG_OPT_SENDTIMEO, sendTimeout);
            socket.set(Options.NNG_OPT_RECVTIMEO, recvTimeout);
        } catch (Throwable e) {
            try {
                socket.close();
            } catch (Exception exc) {
                LOG.atError()
                    .addArgument(e)
                    .setCause(exc)
                    .log("error in error: {}");
            }
            throw e;
        }
        wiredata = packed ? Packed.WIREDATA : Unpacked.WIREDATA;
    }

    @Override
    public void close() throws Exception {
        socket.close();
    }

    public MessageReader transceive(MessageBuilder request) throws Exception {
        try (Context context = new Context(socket)) {
            context.send(wiredata.lower(request));
            return wiredata.upper(context.recv());
        } catch (Error e) {
            if (e.getErrno() == Error.NNG_ETIMEDOUT) {
                throw new Timeout();
            }
            throw e;
        }
    }

    /**
     * Thrown when send or recv timeout.
     * <p>
     * Should it inherit from Exception (thus a checked exception)?
     */
    public static class Timeout extends RuntimeException {
    }
}
