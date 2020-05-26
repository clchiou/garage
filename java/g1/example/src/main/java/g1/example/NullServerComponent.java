package g1.example;

import dagger.Component;
import g1.base.ServerComponent;

import javax.inject.Singleton;

@Singleton
@Component(modules = {NullServerModule.class})
public interface NullServerComponent extends ServerComponent {
}
