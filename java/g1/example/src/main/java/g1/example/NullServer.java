package g1.example;

import com.google.common.util.concurrent.AbstractIdleService;
import g1.base.ServerApp;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;

public class NullServer extends AbstractIdleService {
    private static final Logger LOG = LoggerFactory.getLogger(
        NullServer.class
    );

    @Inject
    public NullServer() {
        super();
        // Nothing here for now; adding this nullary constructor only
        // for the Inject annotation.
    }

    public static void main(String[] args) {
        ServerApp.main(DaggerNullServerComponent.create(), args);
    }

    @Override
    protected String serviceName() {
        return "null-server";
    }

    @Override
    protected void startUp() throws Exception {
        LOG.atInfo().log("start up");
    }

    @Override
    protected void shutDown() throws Exception {
        LOG.atInfo().log("shut down");
    }
}
