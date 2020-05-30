package g1.messaging.pubsub;

import com.google.common.util.concurrent.AbstractExecutionThreadService;
import g1.messaging.NameGenerator;
import g1.messaging.Wiredata;
import nng.Socket;
import org.capnproto.MessageReader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;

import static g1.messaging.Utils.isSocketClosed;

/**
 * Subscriber container for a pubsub subscriber.
 */
public class SubscriberContainer extends AbstractExecutionThreadService {
    private static final Logger LOG = LoggerFactory.getLogger(
        SubscriberContainer.class
    );

    private static final NameGenerator NAMES = new NameGenerator("subscriber");

    // We use socket rather than context because somehow context recv
    // does not work on sub0 sockets.  Also, we do not "own" the socket,
    // and so we do not close it when shutting down.
    private final String name;
    private final Socket socket;
    private final Wiredata wiredata;
    private final Subscriber subscriber;

    @Inject
    public SubscriberContainer(
        @Internal Socket socket,
        @Internal Wiredata wiredata,
        Subscriber subscriber
    ) {
        super();
        this.name = NAMES.next();
        this.socket = socket;
        this.wiredata = wiredata;
        this.subscriber = subscriber;
    }

    @Override
    protected String serviceName() {
        return name;
    }

    @Override
    protected void run() throws Exception {
        while (isRunning()) {
            byte[] messageRaw = null;
            try {
                messageRaw = socket.recv();
            } catch (Exception e) {
                if (isSocketClosed(e)) {
                    LOG.atInfo().log("recv: socket closed");
                    break;
                }
                LOG.atError().setCause(e).log("recv error");
                continue;
            }
            MessageReader message = null;
            try {
                message = wiredata.upper(messageRaw);
            } catch (Exception e) {
                LOG.atWarn().setCause(e).log("invalid message");
                continue;
            }
            try {
                subscriber.consume(message);
            } catch (Exception e) {
                LOG.atError()
                    .addArgument(message)
                    .setCause(e)
                    .log("internal error");
            }
        }
    }
}
