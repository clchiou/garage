package g1.etcd;

import com.google.common.util.concurrent.Service;
import dagger.Binds;
import dagger.Module;
import dagger.Provides;
import dagger.multibindings.IntoSet;
import io.etcd.jetcd.Client;

import javax.inject.Named;
import javax.inject.Singleton;

@Module(includes = ClientModule.class)
public abstract class ControllerModule {

    // TODO: [Dagger][#1757] does not currently allow `@Provides` on static generic methods.
    // [#1757]: https://github.com/google/dagger/issues/1757
    @Provides
    @Singleton
    static ControllerContainer provideControllerContainer(
        Client client,
        @Named("key") String key,
        Controller<?> controller
    ) {
        return ControllerContainer.make(client, key, controller);
    }

    @Binds
    @Singleton
    @IntoSet
    abstract Service bindControllerContainer(ControllerContainer container);
}
