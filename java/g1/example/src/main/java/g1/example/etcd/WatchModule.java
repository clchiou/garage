package g1.example.etcd;

import dagger.Binds;
import dagger.Module;
import dagger.Provides;
import dagger.multibindings.IntoSet;
import g1.etcd.Controller;
import g1.etcd.ControllerModule;

import javax.inject.Named;
import javax.inject.Singleton;

import static com.google.common.base.Preconditions.checkNotNull;

@Module(includes = {ControllerModule.class})
abstract class WatchModule {

    @Provides
    @Named("key")
    static String provideKey() {
        return checkNotNull(Watch.key);
    }

    @Provides
    @IntoSet
    static String provideNamespace() {
        return "g1";
    }

    // TODO: Remove the `<?>` workaround after [#1757] is fixed.
    // [#1757]: https://github.com/google/dagger/issues/1757
    @Binds
    @Singleton
    abstract Controller<?> bindWatch(Watch watch);
}
