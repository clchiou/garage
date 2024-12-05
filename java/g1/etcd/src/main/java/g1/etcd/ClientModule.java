package g1.etcd;

import com.google.common.util.concurrent.Service;
import dagger.Binds;
import dagger.BindsOptionalOf;
import dagger.Module;
import dagger.Provides;
import dagger.multibindings.IntoSet;
import io.etcd.jetcd.Client;
import io.etcd.jetcd.ClientBuilder;

import javax.inject.Named;
import javax.inject.Singleton;
import java.util.Optional;

import static g1.base.Optionals.flatten;

@Module
public abstract class ClientModule {

    @Provides
    @Singleton
    static Client provideClient(
        @Named("endpoint") Optional<Optional<String>> endpoint,
        @Named("user") Optional<Optional<String>> user,
        @Named("password") Optional<Optional<String>> password
    ) {
        ClientBuilder builder =
            Client.builder().endpoints(flatten(endpoint).orElse("http://127.0.0.1:2379"));
        flatten(user).map(ByteSequences::from).ifPresent(builder::user);
        flatten(password).map(ByteSequences::from).ifPresent(builder::password);
        return builder.build();
    }

    @BindsOptionalOf
    @Named("endpoint")
    abstract Optional<String> bindOptionalEndpoint();

    @BindsOptionalOf
    @Named("user")
    abstract Optional<String> bindOptionalUser();

    @BindsOptionalOf
    @Named("password")
    abstract Optional<String> bindOptionalPassword();

    @Binds
    @Singleton
    @IntoSet
    abstract Service bindClientContainer(ClientContainer container);
}
