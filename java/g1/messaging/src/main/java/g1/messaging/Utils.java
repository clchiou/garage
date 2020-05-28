package g1.messaging;

import nng.Protocols;
import nng.Socket;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Utility functions.
 */
public class Utils {
    private static final Logger LOG = LoggerFactory.getLogger(Utils.class);

    /**
     * Helper for opening a socket.
     */
    public static Socket openSocket(
        Protocols protocol,
        Iterable<String> dialUrls,
        Iterable<String> listenUrls
    ) {
        Socket socket = Socket.open(protocol);
        try {
            for (String url : dialUrls) {
                LOG.atInfo().addArgument(url).log("dial: {}");
                socket.dial(url);
            }
            for (String url : listenUrls) {
                LOG.atInfo().addArgument(url).log("listen: {}");
                socket.listen(url);
            }
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
        return socket;
    }

    /**
     * Check whether it is a {@code NNG_ECLOSED}.
     */
    public static boolean isSocketClosed(Exception e) {
        return e instanceof nng.Error &&
            ((nng.Error) e).getErrno() == nng.Error.NNG_ECLOSED;
    }
}
