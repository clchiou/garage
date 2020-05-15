package g1.example.dagger;

import dagger.Binds;
import dagger.Module;

@Module
public abstract class ToasterModule {
    @Binds
    public abstract Toaster provideToaster(AwesomeToaster toaster);
}
