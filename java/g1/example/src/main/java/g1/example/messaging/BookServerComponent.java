package g1.example.messaging;

import dagger.Component;
import g1.base.ServerComponent;

import javax.inject.Singleton;

@Singleton
@Component(modules = {BookServerModule.class})
public interface BookServerComponent extends ServerComponent {
}
