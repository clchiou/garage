package g1.example.dagger;

import dagger.Lazy;

import javax.inject.Inject;

public class BreakfastMaker {
    private final Lazy<Heater> heater;
    private final Toaster toaster;

    @Inject
    public BreakfastMaker(Lazy<Heater> heater, Toaster toaster) {
        this.heater = heater;
        this.toaster = toaster;
    }

    public void make() {
        heater.get().on();
        toaster.toast();
        heater.get().off();
    }
}
