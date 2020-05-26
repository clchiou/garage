package g1.base;

import com.google.common.util.concurrent.MoreExecutors;
import com.google.common.util.concurrent.Service;
import com.google.common.util.concurrent.ServiceManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.annotation.Nonnull;
import java.util.ArrayList;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Server application.
 * <p>
 * Services are injected through Dagger.
 */
public class ServerApp extends ConfiguredApp {
    private static final Logger LOG = LoggerFactory.getLogger(ServerApp.class);

    @Configuration
    public static String name = "server";

    @Configuration
    public static long gracePeriod = 4000L;  // Unit: millisecond.

    private final ServerComponent component;

    public ServerApp(ServerComponent component) {
        this.component = component;
    }

    /**
     * Simple main function for server applications.
     * <p>
     * This main function is for simple use cases.  For more complex use
     * cases like creating server component after configuration data are
     * loaded, you have to write your own custom main function.
     */
    public static void main(ServerComponent component, String[] args) {
        Application.main(new ServerApp(component), args);
    }

    private static ServiceManager makeServiceManager(
        Iterable<Service> services
    ) {
        final ServiceManager manager = new ServiceManager(services);

        manager.addListener(
            new ServiceManager.Listener() {
                @Override
                public void healthy() {
                    LOG.atInfo()
                        .addArgument(name)
                        .log("{}: all services are running");
                    // What else should I do here?
                }

                @Override
                public void failure(@Nonnull Service service) {
                    LOG.atError()
                        .addArgument(name)
                        .addArgument(service)
                        .log("{}: a service has failed: {}");
                    // This triggers the shutdown hook below.
                    System.exit(1);
                }

                @Override
                public void stopped() {
                    LOG.atInfo()
                        .addArgument(name)
                        .log("{}: all services have stopped");
                    // What else should I do here?
                }
            },
            MoreExecutors.directExecutor()
        );

        Runtime.getRuntime().addShutdownHook(
            new Thread(
                () -> {
                    LOG.atInfo().addArgument(name).log("{}: VM shutdown");
                    try {
                        manager.stopAsync()
                            .awaitStopped(gracePeriod, TimeUnit.MILLISECONDS);
                    } catch (TimeoutException e) {
                        LOG.atError()
                            .addArgument(name)
                            .log("{}: grace period exceeds");
                        // Should I call halt here?  (Which forcibly
                        // terminates VM.)
                    }
                },
                name + "-shutdown"
            )
        );

        return manager;
    }

    @Override
    public void run() throws Exception {
        new ConfigurationLoader(new ArrayList<>(component.namespaces()))
            .load(configPaths);
        ServiceManager manager = makeServiceManager(component.services());
        manager.startAsync();
        manager.awaitStopped();
    }
}
