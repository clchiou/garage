package g1.messaging.pubsub;

import com.google.common.util.concurrent.AbstractExecutionThreadService;
import g1.messaging.NameGenerator;
import g1.messaging.Wiredata;
import nng.Context;
import nng.Options;
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

    private final String name;
    private final Context context;
    private final Wiredata wiredata;
    private final Subscriber subscriber;

    @Inject
    public SubscriberContainer(
        @Internal Context context,
        @Internal Wiredata wiredata,
        Subscriber subscriber
    ) {
        super();
        this.name = NAMES.next();
        this.context = context;
        this.wiredata = wiredata;
        this.subscriber = subscriber;
    }

    @Override
    protected String serviceName() {
        return name;
    }

    @Override
    protected void run() throws Exception {
        // For now we subscribe to empty topic only.
        context.set(Options.NNG_OPT_SUB_SUBSCRIBE, new byte[0]);
        while (isRunning()) {
            byte[] messageRaw = null;
            try {
                messageRaw = context.recv();
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
                message = wiredata.toUpper(messageRaw);
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

    @Override
    protected void shutDown() throws Exception {
        try {
            context.close();
        } catch (Exception e) {
            if (isSocketClosed(e)) {
                LOG.atInfo().log("context.close: socket closed");
                return;
            }
            throw e;
        }
    }
}
