package g1.messaging;

import com.google.common.util.concurrent.AbstractIdleService;
import nng.Socket;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Manage life cycle of {@link Socket}.
 */
public class SocketContainer extends AbstractIdleService {
    private static final Logger LOG = LoggerFactory.getLogger(
        SocketContainer.class
    );

    private static final NameGenerator NAMES = new NameGenerator("socket");

    private final String name;
    private final Socket socket;

    public SocketContainer(Socket socket) {
        super();
        this.name = NAMES.next();
        this.socket = socket;
    }

    @Override
    protected String serviceName() {
        return name;
    }

    @Override
    protected void startUp() throws Exception {
        // Do nothing here for now.
    }

    @Override
    protected void shutDown() throws Exception {
        LOG.atInfo().log("close socket");
        socket.close();
    }
}
