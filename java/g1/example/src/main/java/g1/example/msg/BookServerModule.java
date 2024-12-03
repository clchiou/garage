package g1.example.msg;

import dagger.Binds;
import dagger.Module;
import dagger.Provides;
import dagger.multibindings.IntoSet;
import g1.msg.Handler;
import g1.msg.ServerModule;

import javax.inject.Named;
import javax.inject.Singleton;

import static com.google.common.base.Preconditions.checkNotNull;

@Module(includes = {ServerModule.class})
abstract class BookServerModule {

    @Provides
    @Named("url")
    static String provideUrl() {
        return checkNotNull(BookServer.url);
    }

    @Provides
    @Named("parallelism")
    static int provideParallelism() {
        return BookServer.parallelism;
    }

    @Provides
    @IntoSet
    static String provideNamespace() {
        return "g1";
    }

    @Binds
    @Singleton
    abstract Handler bindBookHandler(BookHandler handler);
}
