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
import nng.Context;
import nng.Protocols;
import nng.Socket;

import javax.inject.Singleton;

import static com.google.common.base.Preconditions.checkNotNull;
import static g1.messaging.Utils.openSocket;

/**
 * Dagger module to create pubsub subscriber.
 */
@Module
public abstract class SubscriberModule {

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
        return openSocket(
            Protocols.SUB0, ImmutableList.of(url), ImmutableList.of()
        );
    }

    @Provides
    @Internal
    public static Context provideContext(@Internal Socket socket) {
        return new Context(socket);
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
