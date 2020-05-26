package g1.example;

import com.google.common.util.concurrent.Service;
import dagger.Binds;
import dagger.Module;
import dagger.Provides;
import dagger.multibindings.IntoSet;

import javax.inject.Singleton;

@Module
public abstract class NullServerModule {

    @Provides
    @IntoSet
    public static String provideNamespace() {
        return "g1";
    }

    @Binds
    @Singleton
    @IntoSet
    public abstract Service provideNullServer(NullServer server);
}
