package g1.example.msg;

import dagger.Component;
import g1.base.ServerComponent;

import javax.inject.Singleton;

@Singleton
@Component(modules = {BookServerModule.class})
interface BookServerComponent extends ServerComponent {
}
