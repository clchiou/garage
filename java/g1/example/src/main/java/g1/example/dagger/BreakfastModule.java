package g1.example.dagger;

import dagger.Module;
import dagger.Provides;

import javax.inject.Singleton;

@Module(includes = ToasterModule.class)
public class BreakfastModule {
    @Provides
    @Singleton
    public Heater provideHeater() {
        return new AwesomeHeater();
    }
}
