package nng;

import com.sun.jna.Pointer;
import com.sun.jna.ptr.PointerByReference;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import static com.google.common.base.Preconditions.checkArgument;
import static com.google.common.base.Preconditions.checkNotNull;
import static nng.Constants.NNG_FLAG_NONBLOCK;
import static nng.Error.check;
import static nng.Nng.NNG;
import static nng.Utils.allocMessage;

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
            return;
        } catch (Error e) {
            if (e.getErrno() != Error.NNG_ECONNREFUSED) {
                throw e;
            }
            LOG.atDebug()
                .addArgument(url)
                .log("blocking dial: connection refused: {}");
            // Fall through to non-blocking nng_dial below.
        }
        check(
            NNG.nng_dial(checkNotNull(socket), url, null, NNG_FLAG_NONBLOCK)
        );
    }

    public void listen(String url) {
        check(NNG.nng_listen(checkNotNull(socket), url, null, 0));
    }

    public void send(byte[] data) {
        send(data, data.length);
    }

    public void send(byte[] data, int length) {
        checkArgument(0 < length);
        checkArgument(length <= data.length);
        Pointer message = allocMessage();
        try {
            check(NNG.nng_msg_append(message, data, length));
            check(NNG.nng_sendmsg(checkNotNull(socket), message, 0));
        } catch (Exception e) {
            // Ownership of message is transferred on success; we only
            // need to free it on error.
            NNG.nng_msg_free(message);
            throw e;
        }
    }

    public byte[] recv() {
        PointerByReference messageRef = new PointerByReference();
        check(NNG.nng_recvmsg(checkNotNull(socket), messageRef, 0));
        Pointer message = messageRef.getValue();
        try {
            Pointer body = checkNotNull(NNG.nng_msg_body(message));
            return body.getByteArray(0L, (int) NNG.nng_msg_len(message));
        } finally {
            NNG.nng_msg_free(message);
        }
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
