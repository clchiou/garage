package g1.messaging.reqrep;

import com.google.common.util.concurrent.AbstractExecutionThreadService;
import g1.messaging.NameGenerator;
import g1.messaging.Wiredata;
import nng.Context;
import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;

import static g1.messaging.Utils.isSocketClosed;

/**
 * Server container for a reqrep server.
 */
public class ServerContainer extends AbstractExecutionThreadService {
    private static final Logger LOG = LoggerFactory.getLogger(
        ServerContainer.class
    );

    private static final NameGenerator NAMES = new NameGenerator("server");

    private final String name;
    private final Context context;
    private final Wiredata wiredata;
    private final Server server;

    @Inject
    public ServerContainer(
        @Internal Context context,
        @Internal Wiredata wiredata,
        Server server
    ) {
        super();
        this.name = NAMES.next();
        this.context = context;
        this.wiredata = wiredata;
        this.server = server;
    }

    @Override
    protected String serviceName() {
        return name;
    }

    @Override
    protected void run() throws Exception {
        while (isRunning()) {
            byte[] requestRaw = null;
            try {
                requestRaw = context.recv();
            } catch (Exception e) {
                if (isSocketClosed(e)) {
                    LOG.atInfo().log("recv: socket closed");
                    break;
                }
                LOG.atError().setCause(e).log("recv error");
                continue;
            }
            MessageReader request = null;
            try {
                request = wiredata.upper(requestRaw);
            } catch (Exception e) {
                LOG.atWarn().setCause(e).log("invalid request");
                continue;
            }
            byte[] responseRaw = null;
            try {
                MessageBuilder response = new MessageBuilder();
                server.serve(request, response);
                responseRaw = wiredata.lower(response);
            } catch (Exception e) {
                LOG.atError()
                    .addArgument(request)
                    .setCause(e)
                    .log("internal error");
                continue;
            }
            try {
                context.send(responseRaw);
            } catch (Exception e) {
                if (isSocketClosed(e)) {
                    LOG.atInfo().log("send: socket closed");
                    break;
                }
                LOG.atError().setCause(e).log("send error");
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
