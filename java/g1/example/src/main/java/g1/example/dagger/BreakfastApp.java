package g1.example.dagger;

import dagger.Component;

import javax.inject.Singleton;

public class BreakfastApp {
    public static void main(String[] args) {
        Cafe cafe = DaggerBreakfastApp_Cafe.builder().build();
        cafe.maker().make();
    }

    @Singleton
    @Component(modules = {BreakfastModule.class})
    public interface Cafe {
        BreakfastMaker maker();
    }
}
