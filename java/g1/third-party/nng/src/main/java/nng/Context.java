package nng;

import com.sun.jna.Pointer;

import static com.google.common.base.Preconditions.checkArgument;
import static com.google.common.base.Preconditions.checkNotNull;
import static nng.Constants.NNG_DURATION_DEFAULT;
import static nng.Error.check;
import static nng.Nng.NNG;
import static nng.Utils.allocAio;
import static nng.Utils.allocMessage;

/**
 * Higher-level representation of socket context.
 */
public class Context implements AutoCloseable {
    private nng_ctx.ByValue context;

    public Context(Socket socket) {
        nng_ctx context = new nng_ctx();
        check(NNG.nng_ctx_open(context, socket.socket));
        this.context = new nng_ctx.ByValue(context);
    }

    public Object get(Options option) {
        return option.get(checkNotNull(context));
    }

    public void set(Options option, Object value) {
        option.set(checkNotNull(context), value);
    }

    public void send(byte[] data) {
        send(data, data.length);
    }

    public void send(byte[] data, int length) {
        checkArgument(0 < length);
        checkArgument(length <= data.length);
        Pointer aio = allocAio();
        try {
            // Strangely, aio's default is not NNG_DURATION_DEFAULT
            // but NNG_DURATION_INFINITE; let's make default the
            // default.
            NNG.nng_aio_set_timeout(aio, NNG_DURATION_DEFAULT);
            Pointer message = allocMessage();
            try {
                check(NNG.nng_msg_append(message, data, length));
                NNG.nng_aio_set_msg(aio, message);
                NNG.nng_ctx_send(checkNotNull(context), aio);
                NNG.nng_aio_wait(aio);
                check(NNG.nng_aio_result(aio));
            } catch (Exception e) {
                // Ownership of message is transferred on success; we
                // only need to free it on error.
                NNG.nng_msg_free(message);
                throw e;
            }
        } finally {
            NNG.nng_aio_free(aio);
        }
    }

    public byte[] recv() {
        Pointer aio = allocAio();
        try {
            // Strangely, aio's default is not NNG_DURATION_DEFAULT
            // but NNG_DURATION_INFINITE; let's make default the
            // default.
            NNG.nng_aio_set_timeout(aio, NNG_DURATION_DEFAULT);
            NNG.nng_ctx_recv(checkNotNull(context), aio);
            NNG.nng_aio_wait(aio);
            check(NNG.nng_aio_result(aio));
            Pointer message = NNG.nng_aio_get_msg(aio);
            try {
                Pointer body = checkNotNull(NNG.nng_msg_body(message));
                return body.getByteArray(0L, (int) NNG.nng_msg_len(message));
            } finally {
                NNG.nng_msg_free(message);
            }
        } finally {
            NNG.nng_aio_free(aio);
        }
    }

    @Override
    public void close() throws Exception {
        if (context == null) {
            return;
        }
        check(NNG.nng_ctx_close(context));
        context = null;
    }
}
