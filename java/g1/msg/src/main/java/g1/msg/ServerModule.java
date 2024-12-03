package g1.msg;

import com.google.common.util.concurrent.Service;
import dagger.Module;
import dagger.Provides;
import dagger.multibindings.ElementsIntoSet;

import javax.inject.Named;
import javax.inject.Provider;
import javax.inject.Singleton;
import java.util.HashSet;
import java.util.Set;

import static com.google.common.base.Preconditions.checkArgument;

@Module
public class ServerModule {

    @Provides
    @Singleton
    @ElementsIntoSet
    static Set<Service> provideServices(
        @Named("url") String url,
        @Named("parallelism") int parallelism,
        Provider<Handler> provider
    ) {
        checkArgument(parallelism > 0);

        HashSet<Service> services = new HashSet<>(1 + parallelism);

        Server server = new Server(url);
        services.add(server);

        for (int i = 0; i < parallelism; i++) {
            services.add(server.createHandlerContainer(provider.get()));
        }

        return services;
    }
}
