package g1.example.dagger;

import javax.inject.Inject;

public class AwesomeToaster implements Toaster {
    private final Heater heater;

    @Inject
    public AwesomeToaster(Heater heater) {
        this.heater = heater;
    }

    @Override
    public void toast() {
        if (heater.isHot()) {
            System.out.println("Making toasts...");
        }
    }
}
