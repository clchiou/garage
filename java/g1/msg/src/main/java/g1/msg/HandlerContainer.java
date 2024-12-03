package g1.msg;

import com.google.common.util.concurrent.AbstractExecutionThreadService;
import g1.base.Names;
import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.zeromq.ZMQ;
import org.zeromq.ZMQException;
import zmq.ZError;

import javax.annotation.Nonnull;
import javax.annotation.Nullable;

import static com.google.common.base.Preconditions.checkNotNull;
import static com.google.common.base.Preconditions.checkState;

// Use `AbstractExecutionThreadService` because `ZMQ.Socket` must not be shared among threads.
class HandlerContainer extends AbstractExecutionThreadService {
    private static final Logger LOG = LoggerFactory.getLogger(HandlerContainer.class);

    private static final Names NAMES = new Names("handler");

    private final String name;
    private final ZMQ.Socket socket;
    private final ZMQ.CancellationToken cancel;
    private final Handler handler;

    HandlerContainer(ZMQ.Socket socket, Handler handler) {
        super();
        this.name = NAMES.next();
        this.socket = socket;
        this.cancel = socket.createCancellationToken();
        this.handler = handler;
    }

    private static boolean shouldExit(ZMQException e) {
        return switch (e.getErrorCode()) {
            case ZError.ECANCELED, ZError.ETERM -> true;
            default -> false;
        };
    }

    @Override
    @Nonnull
    protected String serviceName() {
        return name;
    }

    @Override
    protected void run() {
        while (isRunning()) {
            byte[] rawRequest = recv();
            if (rawRequest == null) {
                break;
            }

            MessageReader request;
            try {
                request = Capnp.decode(rawRequest);
            } catch (Exception e) {
                LOG.atDebug()
                    .addArgument(rawRequest)
                    .setCause(e)
                    .log("decode request error: {}");
                continue;
            }

            MessageBuilder response = new MessageBuilder();
            try {
                handler.handle(checkNotNull(request), response);
            } catch (Exception e) {
                LOG.atError().addArgument(request).setCause(e).log("uncaught handler error: {}");
                continue;
            }

            if (send(Capnp.encode(response))) {
                break;
            }
        }
    }

    @Nullable
    private byte[] recv() {
        while (isRunning()) {
            try {
                // TODO: The [doc] claims that `socket.recv` returns `null` on errors, but where
                // can we find the `errno`?
                // [doc]: https://javadoc.io/static/org.zeromq/jeromq/0.6.0/org/zeromq/ZMQ.Socket.html#recv(int,org.zeromq.ZMQ.CancellationToken)
                return socket.recv(0, cancel);
            } catch (ZMQException e) {
                if (shouldExit(e)) {
                    break;
                }
                // We assume that other `recv` errors are transient and do not exit.
                LOG.atWarn().setCause(e).log("recv error");
            }
        }
        return null;
    }

    private boolean send(byte[] response) {
        try {
            checkState(socket.send(response, 0, cancel));
        } catch (ZMQException e) {
            if (shouldExit(e)) {
                return true;
            }
            // We assume that other `send` errors are transient and do not exit.
            LOG.atWarn().setCause(e).log("send error");
        }
        return false;
    }

    @Override
    protected void triggerShutdown() {
        cancel.cancel();
    }

    @Override
    protected void shutDown() {
        socket.close();
    }
}
