package nng;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import static com.google.common.base.Preconditions.checkNotNull;
import static nng.Constants.NNG_FLAG_NONBLOCK;
import static nng.Error.check;
import static nng.Nng.NNG;

/**
 * Higher-level representation of socket.
 */
public class Socket implements AutoCloseable {
    private static final Logger LOG = LoggerFactory.getLogger(Socket.class);

    /* package private */ nng_socket.ByValue socket;

    private Socket(nng_socket socket) {
        this.socket = new nng_socket.ByValue(socket);
    }

    public static void closeAll() {
        LOG.atInfo().log("close all sockets");
        NNG.nng_closeall();
    }

    public static Socket open(Protocols protocol) {
        nng_socket socket = new nng_socket();
        protocol.open(socket);
        return new Socket(socket);
    }

    public static Socket openRaw(Protocols protocol) {
        nng_socket socket = new nng_socket();
        protocol.openRaw(socket);
        return new Socket(socket);
    }

    public Object get(Options option) {
        return option.get(checkNotNull(socket));
    }

    public void set(Options option, Object value) {
        option.set(checkNotNull(socket), value);
    }

    public void dial(String url) {
        try {
            check(NNG.nng_dial(checkNotNull(socket), url, null, 0));
        } catch (Error e) {
            if (e.getErrno() != Error.NNG_ECONNREFUSED) {
                throw e;
            }
            LOG.atDebug()
                .addArgument(url)
                .log("blocking dial: connection refused: {}");
        }
        check(
            NNG.nng_dial(checkNotNull(socket), url, null, NNG_FLAG_NONBLOCK)
        );
    }

    public void listen(String url) {
        check(NNG.nng_listen(checkNotNull(socket), url, null, 0));
    }

    @Override
    public void close() throws Exception {
        if (socket == null) {
            return;
        }
        check(NNG.nng_close(socket));
        socket = null;
    }
}
