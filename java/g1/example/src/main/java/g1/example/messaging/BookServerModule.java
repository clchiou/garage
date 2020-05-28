package g1.example.messaging;

import dagger.Binds;
import dagger.Module;
import dagger.Provides;
import dagger.multibindings.IntoSet;
import g1.messaging.reqrep.Server;
import g1.messaging.reqrep.ServerModule;

import javax.inject.Singleton;

@Module(includes = {ServerModule.class})
public abstract class BookServerModule {

    @Provides
    @IntoSet
    public static String provideNamespace() {
        return "g1";
    }

    @Binds
    @Singleton
    public abstract Server provideServer(BookServer server);
}
