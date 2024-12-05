package g1.example.etcd;

import dagger.Component;
import g1.base.ServerComponent;

import javax.inject.Singleton;

@Singleton
@Component(modules = {WatchModule.class})
interface WatchComponent extends ServerComponent {
}
