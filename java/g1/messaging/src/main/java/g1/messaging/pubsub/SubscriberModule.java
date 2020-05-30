package g1.messaging.pubsub;

import com.google.common.collect.ImmutableList;
import com.google.common.util.concurrent.Service;
import dagger.Binds;
import dagger.Module;
import dagger.Provides;
import dagger.multibindings.IntoSet;
import g1.base.Configuration;
import g1.messaging.Packed;
import g1.messaging.SocketContainer;
import g1.messaging.Unpacked;
import g1.messaging.Wiredata;
import nng.Options;
import nng.Protocols;
import nng.Socket;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Singleton;

import static com.google.common.base.Preconditions.checkNotNull;
import static g1.messaging.Utils.openSocket;

/**
 * Dagger module to create pubsub subscriber.
 */
@Module
public abstract class SubscriberModule {
    private static final Logger LOG = LoggerFactory.getLogger(
        SubscriberModule.class
    );

    /**
     * URL that subscriber dials to.
     */
    @Configuration
    public static String url = null;

    /**
     * Whether to use Cap'n Proto packed format.
     */
    @Configuration
    public static boolean packed = false;

    @Provides
    @Internal
    @Singleton
    public static Socket provideSocket() {
        checkNotNull(url);
        Socket socket = openSocket(
            Protocols.SUB0, ImmutableList.of(url), ImmutableList.of()
        );
        try {
            // TODO: Do we need to set NNG_OPT_RECVTIMEO?
            // For now we subscribe to empty topic only.
            socket.set(Options.NNG_OPT_SUB_SUBSCRIBE, new byte[0]);
        } catch (Throwable e) {
            try {
                socket.close();
            } catch (Exception exc) {
                LOG.atError()
                    .addArgument(e)
                    .setCause(exc)
                    .log("error in error: {}");
            }
            throw e;
        }
        return socket;
    }

    @Provides
    @Internal
    @Singleton
    public static Wiredata provideWiredata() {
        return packed ? Packed.WIREDATA : Unpacked.WIREDATA;
    }

    @Provides
    @Singleton
    @IntoSet
    public static Service provideSocketContainer(@Internal Socket socket) {
        return new SocketContainer(socket);
    }

    @Binds
    @Singleton
    @IntoSet
    public abstract Service provideSubscriberContainer(
        SubscriberContainer subscriberContainer
    );
}
