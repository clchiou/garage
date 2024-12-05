package g1.etcd;

import com.google.common.util.concurrent.AbstractIdleService;
import g1.base.Names;
import io.etcd.jetcd.Client;

import javax.annotation.Nonnull;
import javax.inject.Inject;

class ClientContainer extends AbstractIdleService {
    private static final Names NAMES = new Names("client");

    private final String name;
    private final Client client;

    @Inject
    ClientContainer(Client client) {
        super();
        this.name = NAMES.next();
        this.client = client;
    }

    @Override
    @Nonnull
    protected String serviceName() {
        return name;
    }

    @Override
    protected void startUp() {
        // Do nothing here.
    }

    // TODO: There is no guarantee that `ClientContainer.shutDown` will be called only after all
    // call sites of `Client` return.  Could this be a problem?
    @Override
    protected void shutDown() {
        client.close();
    }
}
