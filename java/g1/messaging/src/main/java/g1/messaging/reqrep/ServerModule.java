package g1.messaging.reqrep;

import com.google.common.collect.ImmutableList;
import com.google.common.util.concurrent.Service;
import dagger.Module;
import dagger.Provides;
import dagger.multibindings.ElementsIntoSet;
import dagger.multibindings.IntoSet;
import g1.base.Configuration;
import g1.messaging.Packed;
import g1.messaging.SocketContainer;
import g1.messaging.Unpacked;
import g1.messaging.Wiredata;
import nng.Context;
import nng.Protocols;
import nng.Socket;

import javax.inject.Provider;
import javax.inject.Singleton;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

import static com.google.common.base.Preconditions.checkNotNull;
import static com.google.common.base.Preconditions.checkState;
import static g1.messaging.Utils.openSocket;

/**
 * Dagger module to create reqrep server.
 */
@Module
public class ServerModule {

    /**
     * URL that server listens from.
     */
    @Configuration
    public static String url = null;

    /**
     * Number of the server threads.
     */
    @Configuration
    public static int parallelism = 1;

    /**
     * Whether to use Cap'n Proto packed format.
     */
    @Configuration
    public static boolean packed = false;

    @Provides
    @Internal
    @Singleton
    public Socket provideSocket() {
        checkNotNull(url);
        return openSocket(
            Protocols.REP0, ImmutableList.of(), ImmutableList.of(url)
        );
    }

    @Provides
    @Internal
    public Context provideContext(@Internal Socket socket) {
        return new Context(socket);
    }

    @Provides
    @Internal
    @Singleton
    public Wiredata provideWiredata() {
        return packed ? Packed.WIREDATA : Unpacked.WIREDATA;
    }

    @Provides
    @Singleton
    @IntoSet
    public Service provideSocketContainer(@Internal Socket socket) {
        return new SocketContainer(socket);
    }

    @Provides
    @Singleton
    @ElementsIntoSet
    public Set<Service> provideServices(Provider<ServerContainer> provider) {
        checkState(parallelism > 0);
        return IntStream.range(0, parallelism)
            .mapToObj(i -> provider.get())
            .collect(Collectors.toSet());
    }
}
